"""Transactional ownership/capacity gate shared by every SaaS workspace.

No shared owner credential fallback, automatic credential provisioning or capacity
assumption. Credentials are server-provisioned and require verified upstream user
isolation before enabling. Unknown/active joins retain their slot until checked.
"""
import hashlib
import hmac
import re
import sqlite3
import time
from pathlib import Path
from .tenancy import TENANT
from .adapters import Vexa, request

class WorkspaceError(ValueError): pass

class Registry:
    def __init__(self, path, key, *, capacity=None, daily_joins=20, tenant_daily=3, clock=time.time):
        if not isinstance(key, bytes) or len(key)<32: raise WorkspaceError('Dedicated registry key required')
        if capacity is not None and (type(capacity) is not int or capacity<1): raise WorkspaceError('Verified capacity required')
        if not all(type(v) is int and v>0 for v in (daily_joins,tenant_daily)): raise WorkspaceError('Positive budgets required')
        p=Path(path);p.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        if p.is_symlink(): raise WorkspaceError('Registry path refused')
        self.db=sqlite3.connect(p);p.chmod(0o600);self.db.row_factory=sqlite3.Row
        self.key,self.capacity,self.daily_joins,self.tenant_daily,self.clock=key,capacity,daily_joins,tenant_daily,clock
        self.db.executescript('''PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS credentials(tenant TEXT PRIMARY KEY, fingerprint TEXT NOT NULL UNIQUE);
        CREATE TABLE IF NOT EXISTS upstream_owners(tenant TEXT PRIMARY KEY, owner INTEGER NOT NULL UNIQUE);
        CREATE TABLE IF NOT EXISTS upstream_rows(tenant TEXT NOT NULL, code TEXT NOT NULL, row_id INTEGER NOT NULL UNIQUE, PRIMARY KEY(tenant,code));
        CREATE TABLE IF NOT EXISTS ownership(code TEXT PRIMARY KEY, tenant TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS joins(attempt TEXT PRIMARY KEY, tenant TEXT NOT NULL, code TEXT NOT NULL, created REAL NOT NULL, active INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS checks(attempt TEXT PRIMARY KEY, reason TEXT NOT NULL, checked REAL NOT NULL);
        ''');self.db.commit()
    def tenant(self, tenant):
        if not isinstance(tenant,str) or not TENANT.fullmatch(tenant): raise WorkspaceError('Verified workspace required')
    def bind_credential(self,tenant,key):
        self.tenant(tenant)
        if not isinstance(key,str) or len(key)<16: raise WorkspaceError('Dedicated upstream credential required')
        fp=hmac.new(self.key,key.encode(),hashlib.sha256).hexdigest()
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            row=self.db.execute('SELECT fingerprint FROM credentials WHERE tenant=?',(tenant,)).fetchone()
            if row and not hmac.compare_digest(row['fingerprint'],fp): raise WorkspaceError('Credential rotation requires explicit migration')
            try:self.db.execute('INSERT OR IGNORE INTO credentials VALUES(?,?)',(tenant,fp))
            except sqlite3.IntegrityError:raise WorkspaceError('Credential already assigned') from None
            # OR IGNORE also ignores UNIQUE conflicts: verify tenant actually bound.
            row=self.db.execute('SELECT fingerprint FROM credentials WHERE tenant=?',(tenant,)).fetchone()
            if not row or row['fingerprint']!=fp: raise WorkspaceError('Credential already assigned')
    def claim(self,tenant,code):
        self.tenant(tenant)
        if not isinstance(code,str) or not re.fullmatch(r'[a-z]{3}-[a-z]{4}-[a-z]{3}',code):raise WorkspaceError('Valid meeting required')
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            self.db.execute('INSERT OR IGNORE INTO ownership VALUES(?,?)',(code,tenant))
            self.owns(tenant,code)
    def owns(self,tenant,code):
        self.tenant(tenant)
        row=self.db.execute('SELECT tenant FROM ownership WHERE code=?',(code,)).fetchone()
        if not row or row['tenant']!=tenant:raise WorkspaceError('Meeting unavailable for this workspace')
    def reserve(self,tenant,code,attempt):
        if self.capacity is None:raise WorkspaceError('Capacity not verified; live joins disabled')
        if not isinstance(attempt,str) or not 16<=len(attempt)<=128:raise WorkspaceError('Attempt identifier required')
        with self.db:
            self.db.execute('BEGIN IMMEDIATE');self.owns(tenant,code)
            if not self.db.execute('SELECT 1 FROM credentials WHERE tenant=?',(tenant,)).fetchone():raise WorkspaceError('Workspace not provisioned')
            if self.db.execute('SELECT 1 FROM joins WHERE attempt=?',(attempt,)).fetchone():raise WorkspaceError('Attempt already reserved; reconcile without retry')
            if self.db.execute('SELECT 1 FROM joins WHERE code=? AND active=1',(code,)).fetchone():raise WorkspaceError('Meeting already active or uncertain')
            if self.db.execute('SELECT count(*) FROM joins WHERE active=1').fetchone()[0]>=self.capacity:raise WorkspaceError('Capacity busy')
            day=int(self.clock()//86400)*86400
            total=self.db.execute('SELECT count(*) FROM joins WHERE created>=?',(day,)).fetchone()[0]
            own=self.db.execute('SELECT count(*) FROM joins WHERE created>=? AND tenant=?',(day,tenant)).fetchone()[0]
            if total>=self.daily_joins or own>=self.tenant_daily:raise WorkspaceError('Join budget reached')
            self.db.execute('INSERT INTO joins VALUES(?,?,?,?,1)',(attempt,tenant,code,self.clock()))
    def close_checked(self,attempt,reason):
        # Operator-only API, intentionally not exposed by customer HTTP routes.
        if not isinstance(reason,str) or not reason.strip():raise WorkspaceError('Verified terminal-state reason required')
        with self.db:
            if not self.db.execute('SELECT 1 FROM joins WHERE attempt=?',(attempt,)).fetchone():raise WorkspaceError('Unknown attempt')
            self.db.execute('UPDATE joins SET active=0 WHERE attempt=?',(attempt,))
            self.db.execute('INSERT OR REPLACE INTO checks VALUES(?,?,?)',(attempt,reason,self.clock()))

class PrivateVexa(Vexa):
    def perform(self,kind,payload):
        if kind=='join':
            from .core import BOT_DISPLAY_NAME
            return request(self.base,'/bots',self.key,'POST',{
                'platform':'google_meet','native_meeting_id':payload['code'],
                'bot_name':BOT_DISPLAY_NAME,'workspace_id':'personal',
                'recording_enabled':False,'transcribe_enabled':True})
        return super().perform(kind,payload)

class ScopedVexa:
    def __init__(self,registry,tenant,base,key,*,upstream_user_id=None,upstream_isolation_verified=False,transport=PrivateVexa):
        if upstream_isolation_verified is not True:raise WorkspaceError('Verify upstream per-user authorization before activation')
        if type(upstream_user_id) is not int or upstream_user_id<1:raise WorkspaceError('Verified distinct upstream owner required')
        registry.bind_credential(tenant,key)
        with registry.db:
            registry.db.execute('BEGIN IMMEDIATE')
            try:registry.db.execute('INSERT OR IGNORE INTO upstream_owners VALUES(?,?)',(tenant,upstream_user_id))
            except sqlite3.IntegrityError:raise WorkspaceError('Upstream owner already assigned') from None
            row=registry.db.execute('SELECT owner FROM upstream_owners WHERE tenant=?',(tenant,)).fetchone()
            if not row or row['owner']!=upstream_user_id:raise WorkspaceError('Upstream owner already assigned')
        self.registry,self.tenant,self.client=registry,tenant,transport(base,key)
        self.attempt=None
    def transcript(self,code):
        self.registry.owns(self.tenant,code)
        row=self.registry.db.execute('SELECT row_id FROM upstream_rows WHERE tenant=? AND code=?',(self.tenant,code)).fetchone()
        if not row:raise WorkspaceError('Exact upstream meeting not bound; reconcile join first')
        return self.client.transcript_by_id(row['row_id'])
    def chat_status(self,code,request_id):self.registry.owns(self.tenant,code);return self.client.chat_status(code,request_id)
    def perform(self,kind,payload):
        code=payload['code'];self.registry.owns(self.tenant,code)
        if kind=='join':self.registry.reserve(self.tenant,code,self.attempt)
        result=self.client.perform(kind,payload)
        if kind=='join':
            row_id=result.get('id') if isinstance(result,dict) else None
            if type(row_id) is not int or row_id<1:raise WorkspaceError('Join outcome lacks exact meeting row; reconcile without retry')
            with self.registry.db:
                self.registry.db.execute('INSERT OR REPLACE INTO upstream_rows VALUES(?,?,?)',(self.tenant,code,row_id))
        return result
