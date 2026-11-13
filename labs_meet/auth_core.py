"""Offline-reviewed OTP/session foundation, not a configured login service.

No provider implementation, public HTTP routes or fallback sender is included.
Six-digit codes are the proposed baseline; approval of product UX is separate.
Secrets are never returned to the browser, logged, or stored in plaintext.
A dedicated approved authentication-template sender must be supplied separately.
"""
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import time
from pathlib import Path


class AuthError(ValueError):
    pass


class AuthCore:
    TTL = 180
    SESSION_TTL = 3600
    COOLDOWN = 60
    MAX_FAILURES = 5
    PHONE_SENDS_PER_DAY = 5
    IP_SENDS_PER_DAY = 20

    def __init__(self, path, key, *, owner_phone=None, allow_signup=False, clock=time.time, digits=6):
        if not isinstance(key, bytes) or len(key) < 32:
            raise AuthError('Provision a dedicated authentication key before enabling login')
        if owner_phone is None and not allow_signup:
            raise AuthError('Choose an explicit launch audience before enabling login')
        if digits not in (4, 6):
            raise AuthError('Unsupported code length')
        self.digits = digits
        self.key, self.owner_phone, self.allow_signup, self.clock = key, owner_phone, allow_signup, clock
        p = Path(path)
        p.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        if p.is_symlink():
            raise AuthError('Authentication path refused')
        self.db = sqlite3.connect(p)
        os.chmod(p, 0o600)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS accounts(phone_key TEXT PRIMARY KEY, tenant TEXT NOT NULL UNIQUE);
        CREATE TABLE IF NOT EXISTS limits(scope TEXT PRIMARY KEY, window REAL NOT NULL,
          sends INTEGER NOT NULL DEFAULT 0, failures INTEGER NOT NULL DEFAULT 0, last_send REAL NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS challenges(id_key TEXT PRIMARY KEY, phone_key TEXT NOT NULL,
          browser_key TEXT NOT NULL, code_key TEXT NOT NULL, expires REAL NOT NULL, used INTEGER NOT NULL,
          status TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS profiles(tenant TEXT PRIMARY KEY, verified_email TEXT NOT NULL, source TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS google_accounts(subject_key TEXT PRIMARY KEY, tenant TEXT NOT NULL UNIQUE);
        CREATE TABLE IF NOT EXISTS browser_nonces(nonce_key TEXT PRIMARY KEY, expires REAL NOT NULL, used INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS sessions(token_key TEXT PRIMARY KEY, tenant TEXT NOT NULL,
          expires REAL NOT NULL, csrf_key TEXT NOT NULL);
        ''')
        self.db.commit()

    def seal(self, kind, value):
        return hmac.new(self.key, (kind + ':' + value).encode(), hashlib.sha256).hexdigest()

    @staticmethod
    def phone(value):
        if not isinstance(value, str) or not re.fullmatch(r'\+[1-9][0-9]{7,14}', value):
            raise AuthError('Use a valid international WhatsApp number')
        return value

    def _limit(self, scope, now):
        row = self.db.execute('SELECT * FROM limits WHERE scope=?', (scope,)).fetchone()
        if row is None:
            self.db.execute('INSERT INTO limits(scope,window) VALUES(?,?)', (scope, now))
        elif now - row['window'] >= 86400:
            self.db.execute('UPDATE limits SET window=?,sends=0,failures=0 WHERE scope=?', (now, scope))
        return self.db.execute('SELECT * FROM limits WHERE scope=?', (scope,)).fetchone()

    def request(self, phone, browser_nonce, remote_ip, sender):
        phone = self.phone(phone)
        if not isinstance(browser_nonce, str) or len(browser_nonce) < 32:
            raise AuthError('Start a fresh browser authentication session')
        if not isinstance(remote_ip, str) or not remote_ip:
            raise AuthError('Source address required')
        if self.owner_phone and phone != self.owner_phone:
            # An owner-only build does not silently create public accounts.
            raise AuthError('Login is not available for this request')
        now = self.clock()
        pk, ik = self.seal('phone', phone), self.seal('ip', remote_ip)
        challenge = secrets.token_urlsafe(32)
        code = str(secrets.randbelow(10 ** self.digits)).zfill(self.digits)
        ck = self.seal('challenge', challenge)
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            pr, ir = self._limit(pk, now), self._limit(ik, now)
            if pr['failures'] >= self.MAX_FAILURES or pr['sends'] >= self.PHONE_SENDS_PER_DAY or ir['sends'] >= self.IP_SENDS_PER_DAY:
                raise AuthError('Request limit reached. Try later.')
            if pr['last_send'] and now - pr['last_send'] < self.COOLDOWN:
                raise AuthError('Wait before requesting another code')
            for scope in (pk, ik):
                self.db.execute('UPDATE limits SET sends=sends+1,last_send=? WHERE scope=?', (now, scope))
            # Resending invalidates the old challenge, never its failed-attempt budget.
            self.db.execute('UPDATE challenges SET used=1 WHERE phone_key=?', (pk,))
            self.db.execute('INSERT INTO challenges VALUES(?,?,?,?,?,0,?)',
                            (ck, pk, self.seal('browser', browser_nonce), self.seal('code', ck + ':' + code), now + self.TTL, 'pending'))
        try:
            # This boundary accepts only an explicit, separately approved sender.
            # Sender must NOT log the code or retry an uncertain provider result.
            result = sender(phone, code, self.TTL)
            if result is not True:
                raise AuthError('Authentication delivery was not confirmed')
        except Exception:
            with self.db:
                self.db.execute("UPDATE challenges SET status='unknown' WHERE id_key=?", (ck,))
            raise AuthError('Code request was not confirmed. Do not retry blindly.') from None
        with self.db:
            self.db.execute("UPDATE challenges SET status='sent' WHERE id_key=?", (ck,))
        return {'challenge': challenge, 'expires_in': self.TTL, 'retry_after': self.COOLDOWN}

    def verify(self, challenge, code, browser_nonce, *, consume_nonce=False):
        if not all(isinstance(v, str) for v in (challenge, code, browser_nonce)):
            raise AuthError('Code invalid or expired')
        ck = self.seal('challenge', challenge)
        now = self.clock()
        # Commit the failed-attempt budget before raising; exceptions inside a
        # transaction would otherwise roll back the very lockout being enforced.
        failed = True
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            row = self.db.execute('SELECT * FROM challenges WHERE id_key=?', (ck,)).fetchone()
            if row and not row['used']:
                limit = self._limit(row['phone_key'], now)
                good = (row['status'] == 'sent' and row['expires'] > now and
                        limit['failures'] < self.MAX_FAILURES and
                        hmac.compare_digest(row['browser_key'], self.seal('browser', browser_nonce)) and
                        re.fullmatch(r'[0-9]{%d}' % self.digits, code) and
                        hmac.compare_digest(row['code_key'], self.seal('code', ck + ':' + code)))
                if good:
                    if consume_nonce:
                        self.consume_browser(browser_nonce)
                    self.db.execute('UPDATE challenges SET used=1 WHERE id_key=?', (ck,))
                    account = self.db.execute('SELECT tenant FROM accounts WHERE phone_key=?', (row['phone_key'],)).fetchone()
                    tenant = account['tenant'] if account else secrets.token_hex(16)
                    if account is None:
                        self.db.execute('INSERT INTO accounts VALUES(?,?)', (row['phone_key'], tenant))
                    token = secrets.token_urlsafe(32)
                    csrf = self.seal('csrf-token', token)
                    self.db.execute('INSERT INTO sessions VALUES(?,?,?,?)', (self.seal('session', token), tenant, now + self.SESSION_TTL, self.seal('csrf', csrf)))
                    failed = False
                else:
                    self.db.execute('UPDATE limits SET failures=failures+1 WHERE scope=?', (row['phone_key'],))
        if failed:
            raise AuthError('Code invalid or expired')
        return {'token': token, 'csrf': csrf, 'expires_in': self.SESSION_TTL}

    def session(self, token, *, csrf=None):
        if not isinstance(token, str):
            raise AuthError('Sign in required')
        row = self.db.execute('SELECT * FROM sessions WHERE token_key=?', (self.seal('session', token),)).fetchone()
        if not row or row['expires'] <= self.clock():
            raise AuthError('Sign in required')
        if csrf is not None and (not isinstance(csrf, str) or not hmac.compare_digest(row['csrf_key'], self.seal('csrf', csrf))):
            raise AuthError('Request validation failed')
        return row['tenant']

    def logout(self, token):
        if isinstance(token, str):
            with self.db:
                self.db.execute('DELETE FROM sessions WHERE token_key=?', (self.seal('session', token),))

    def begin(self):
        nonce = secrets.token_urlsafe(32)
        with self.db:
            self.db.execute('DELETE FROM browser_nonces WHERE expires<=?', (self.clock(),))
            self.db.execute('INSERT INTO browser_nonces VALUES(?,?,0)', (self.seal('nonce', nonce), self.clock()+self.TTL))
        return nonce

    def browser(self, nonce):
        if not isinstance(nonce, str) or len(nonce) < 32:
            raise AuthError('Fresh browser required')
        row = self.db.execute('SELECT * FROM browser_nonces WHERE nonce_key=?', (self.seal('nonce', nonce),)).fetchone()
        if not row or row['used'] or row['expires'] <= self.clock():
            raise AuthError('Fresh browser required')
        return nonce

    def consume_browser(self, nonce):
        # OTP callers use this in the same transaction as verification.
        self.browser(nonce)
        self.db.execute('UPDATE browser_nonces SET used=1 WHERE nonce_key=?', (self.seal('nonce', nonce),))

    def google_login(self, credential, nonce, client_id, verifier):
        self.browser(nonce)
        identity = verifier(credential, configured_client_id=client_id, expected_nonce=nonce, include_verified_email=True)
        if identity.get('issuer') != 'google' or not isinstance(identity.get('subject'), str) or not identity['subject']:
            raise AuthError('Identity did not validate')
        subject = self.seal('google', identity['subject'])
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            self.consume_browser(nonce)
            account = self.db.execute('SELECT tenant FROM google_accounts WHERE subject_key=?', (subject,)).fetchone()
            tenant = account['tenant'] if account else secrets.token_hex(16)
            if account is None:
                self.db.execute('INSERT INTO google_accounts VALUES(?,?)', (subject, tenant))
            email=identity.get('verified_email')
            if isinstance(email,str) and re.fullmatch(r'[^\s@<>;,\r\n]+@[^\s@<>;,\r\n]+\.[^\s@<>;,\r\n]+',email):
                self.db.execute('INSERT OR REPLACE INTO profiles VALUES(?,?,?)',(tenant,email,'google-verified'))
            token = secrets.token_urlsafe(32)
            csrf = self.seal('csrf-token', token)
            self.db.execute('INSERT INTO sessions VALUES(?,?,?,?)', (self.seal('session', token), tenant, self.clock()+self.SESSION_TTL, self.seal('csrf', csrf)))
        return {'token': token, 'csrf': csrf, 'expires_in': self.SESSION_TTL}

    def public_session(self, token):
        self.session(token)
        return {'authenticated': True, 'csrf': self.seal('csrf-token', token)}

    def profile(self, tenant):
        row=self.db.execute('SELECT verified_email,source FROM profiles WHERE tenant=?',(tenant,)).fetchone()
        return dict(row) if row else {'verified_email':None,'source':None}

    def link_google(self, token, csrf, credential, nonce, client_id, verifier):
        tenant=self.session(token,csrf=csrf)
        self.browser(nonce)
        identity=verifier(credential,configured_client_id=client_id,expected_nonce=nonce,include_verified_email=True)
        if identity.get('issuer')!='google' or not isinstance(identity.get('subject'),str) or not identity['subject']:
            raise AuthError('Identity did not validate')
        subject=self.seal('google',identity['subject'])
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            self.consume_browser(nonce)
            row=self.db.execute('SELECT tenant FROM google_accounts WHERE subject_key=?',(subject,)).fetchone()
            if row and row['tenant']!=tenant:raise AuthError('This Google identity already has another workspace. No automatic merge.')
            current=self.db.execute('SELECT subject_key FROM google_accounts WHERE tenant=?',(tenant,)).fetchone()
            if current and current['subject_key']!=subject:raise AuthError('Workspace already has a Google identity; replacement requires account recovery')
            self.db.execute('INSERT OR IGNORE INTO google_accounts VALUES(?,?)',(subject,tenant))
            email=identity.get('verified_email')
            if isinstance(email,str) and re.fullmatch(r'[^\s@<>;,\r\n]+@[^\s@<>;,\r\n]+\.[^\s@<>;,\r\n]+',email):
                self.db.execute('INSERT OR REPLACE INTO profiles VALUES(?,?,?)',(tenant,email,'google-verified'))
        return {'linked':True,'profile_ready':self.profile(tenant)['verified_email'] is not None}
