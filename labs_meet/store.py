"""SQLite outbox. A crashed send is UNKNOWN, never blindly retried."""
import json
import os
import sqlite3
import time
import uuid
from dataclasses import asdict
from pathlib import Path
from .core import Segment, digest


class Store:
    def __init__(self, path):
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db = sqlite3.connect(p)
        os.chmod(p, 0o600)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
        PRAGMA journal_mode=WAL;
        PRAGMA foreign_keys=ON;
        CREATE TABLE IF NOT EXISTS meetings(id TEXT PRIMARY KEY, title TEXT NOT NULL,
          code TEXT NOT NULL, consent TEXT NOT NULL, status TEXT NOT NULL, created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS segments(meeting TEXT NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
          id TEXT NOT NULL, data TEXT NOT NULL, PRIMARY KEY(meeting,id));
        CREATE TABLE IF NOT EXISTS outbox(id TEXT PRIMARY KEY, meeting TEXT NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
          kind TEXT NOT NULL, payload TEXT NOT NULL, digest TEXT NOT NULL, status TEXT NOT NULL,
          result TEXT, created REAL NOT NULL, UNIQUE(meeting,kind,digest));
        CREATE TABLE IF NOT EXISTS artifacts(meeting TEXT NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
          kind TEXT NOT NULL, evidence_digest TEXT NOT NULL, data TEXT NOT NULL, PRIMARY KEY(meeting,kind));
        CREATE TABLE IF NOT EXISTS seen(meeting TEXT NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
          event TEXT NOT NULL, PRIMARY KEY(meeting,event));
        ''')
        self.db.commit()

    def recover(self):
        """Run only after stopping other workers and reconciling their liveness."""
        with self.db:
            return self.db.execute("UPDATE outbox SET status='unknown' WHERE status='sending'").rowcount

    def create(self, title, code, consent):
        if not consent.strip():
            raise ValueError("Record organizer approval and participant-notice basis first")
        mid = uuid.uuid4().hex
        with self.db:
            self.db.execute("INSERT INTO meetings VALUES(?,?,?,?,?,?)", (mid, title, code, consent, "local", time.time()))
        return mid

    def meeting(self, mid):
        row = self.db.execute("SELECT * FROM meetings WHERE id=?", (mid,)).fetchone()
        if row is None:
            raise ValueError("Meeting not found")
        return dict(row)

    def ingest(self, mid, segments):
        self.meeting(mid)
        # REST returns a snapshot: replace it so withdrawn evidence doesn't survive.
        with self.db:
            self.db.execute("DELETE FROM segments WHERE meeting=?", (mid,))
            self.db.executemany("INSERT INTO segments VALUES(?,?,?)", [(mid, s.id, json.dumps(asdict(s))) for s in segments])
            # Changed evidence invalidates draft approvals, including prepared sends.
            self.db.execute("UPDATE outbox SET status='stale' WHERE meeting=? AND kind IN ('email','whatsapp','chat') AND status IN ('draft','approved')", (mid,))

    def segments(self, mid):
        return sorted([Segment(**json.loads(r[0])) for r in self.db.execute("SELECT data FROM segments WHERE meeting=?", (mid,))], key=lambda s: (s.start, s.id))

    def stage(self, mid, kind, payload):
        self.meeting(mid)
        d = digest(payload)
        oid = uuid.uuid4().hex
        # INSERT OR IGNORE makes staging idempotent under concurrent writers:
        # two writers staging the same exact payload get the same row, never
        # an IntegrityError from the UNIQUE(meeting,kind,digest) constraint.
        with self.db:
            cur = self.db.execute("INSERT OR IGNORE INTO outbox VALUES(?,?,?,?,?,?,?,?)",
                                  (oid, mid, kind, json.dumps(payload), d, "draft", None, time.time()))
            if cur.rowcount == 0:
                old = self.db.execute("SELECT id,status FROM outbox WHERE meeting=? AND kind=? AND digest=?", (mid, kind, d)).fetchone()
                if old is None:
                    raise ValueError("Outbox staging conflict; review again")
                if old[1] == "stale":
                    self.db.execute("UPDATE outbox SET status='draft' WHERE id=?", (old[0],))
                return old[0]
        return oid

    def active_join(self, exclude_oid=None):
        """Return a submitted/in-flight join that is not yet closed by a leave.

        A join counts as active until a leave for the same meeting has been
        submitted after it. This is the companion-side one-call guard; the
        Vexa-side max_concurrent_bots=1 cap (see deploy/bootstrap-owner.py)
        is separate and must also be set.
        """
        rows = self.db.execute(
            "SELECT id, meeting, created FROM outbox WHERE kind='join' AND status IN ('submitted','sending','unknown') ORDER BY created"
        ).fetchall()
        for row in rows:
            if exclude_oid and row[0] == exclude_oid:
                continue
            leave = self.db.execute(
                "SELECT 1 FROM outbox WHERE meeting=? AND kind='leave' AND status='submitted' AND created>=? LIMIT 1",
                (row[1], row[2])).fetchone()
            if not leave:
                return dict(row)
        return None

    def out(self, oid):
        row = self.db.execute("SELECT * FROM outbox WHERE id=?", (oid,)).fetchone()
        if row is None:
            raise ValueError("Outbox item not found")
        out = dict(row)
        out["payload"] = json.loads(out["payload"])
        return out

    def approve(self, oid, expected_digest):
        out = self.out(oid)
        if out["digest"] != expected_digest or digest(out["payload"]) != expected_digest:
            raise ValueError("Payload changed; review again")
        with self.db:
            changed = self.db.execute("UPDATE outbox SET status='approved' WHERE id=? AND status='draft'", (oid,)).rowcount
        if changed != 1:
            raise ValueError("Only a fresh draft can be approved")

    def claim(self, oid):
        # Serialize quota inspection and the claim across independent workers.
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            out = self.out(oid)
            if out["kind"] == "join" and self.active_join(oid):
                raise ValueError("One concurrent call limit: leave or resolve the active/unknown join first")
            n = self.db.execute("UPDATE outbox SET status='sending',created=? WHERE id=? AND status='approved'", (time.time(),oid)).rowcount
            if n != 1:
                raise ValueError("Not approved or already attempted")
        return self.out(oid)

    def settle(self, oid, status, result):
        # Compare and write under one lock; terminal results cannot race a late
        # reconciler into changing the state or overwriting provider evidence.
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            current = self.out(oid)["status"]
            if current in ("sent", "accepted", "posted", "failed", "superseded"):
                if status != current:
                    raise ValueError("Final outbox status cannot be changed")
                return
            self.db.execute("UPDATE outbox SET status=?, result=? WHERE id=?", (status, json.dumps(result), oid))

    def seen(self, mid, event):
        with self.db:
            return self.db.execute("INSERT OR IGNORE INTO seen VALUES(?,?)", (mid, event)).rowcount == 0

    def save_notes(self, mid, value, expected_digest=None):
        # A model request can overlap a transcript correction in another process.
        # Serialize validation+write so old notes cannot be labelled as new evidence.
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            self.meeting(mid)
            d = digest([s.__dict__ for s in self.segments(mid)])
            if expected_digest is not None and d != expected_digest:
                raise ValueError("Transcript changed while notes were generated; regenerate and review")
            self.db.execute("INSERT OR REPLACE INTO artifacts VALUES(?,?,?,?)", (mid,"ai-notes",d,json.dumps(value)))

    def ai_notes(self, mid):
        r = self.db.execute("SELECT evidence_digest,data FROM artifacts WHERE meeting=? AND kind='ai-notes'", (mid,)).fetchone()
        if r and r[0] == digest([s.__dict__ for s in self.segments(mid)]):
            return json.loads(r[1])
        return None

    def delete(self, mid):
        with self.db:
            self.db.execute("DELETE FROM meetings WHERE id=?", (mid,))
        self.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        self.db.execute("VACUUM")
