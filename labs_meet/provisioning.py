"""Operator-only Vexa provisioning planner and bounded executor.

No HTTP customer route invokes this. Needs an approved isolated deployment and
real verified email. A phone number cannot be converted into a made-up email.
Local intent is written BEFORE admin calls; unknown results are never retried.
Admin account creation can fire upstream hooks. Verify their isolation first.
"""
import json
import os
import re
import sqlite3
import time
from pathlib import Path
from .adapters import endpoint, request
from .tenancy import TENANT

class ProvisionError(ValueError):pass

class Provisioner:
    def __init__(self,root,base,admin_key,*,enabled=False,hooks_isolated=False,api=request):
        root=Path(root)
        if root.is_symlink():raise ProvisionError('Private provisioning path required')
        root.mkdir(mode=0o700,parents=True,exist_ok=True);root.chmod(0o700)
        self.root,self.base,self.key,self.enabled,self.hooks_isolated,self.api=root,endpoint(base),admin_key,enabled,hooks_isolated,api
        if (root/'provision.db').is_symlink():raise ProvisionError('Provisioning database path refused')
        self.db=sqlite3.connect(root/'provision.db');(root/'provision.db').chmod(0o600);self.db.row_factory=sqlite3.Row
        self.db.execute('CREATE TABLE IF NOT EXISTS provisioning(tenant TEXT PRIMARY KEY,email TEXT NOT NULL UNIQUE,state TEXT NOT NULL,user_id INTEGER UNIQUE,token_id INTEGER UNIQUE)');self.db.commit()
    def provision(self,tenant,verified_email):
        if self.enabled is not True or self.hooks_isolated is not True:raise ProvisionError('Provisioning disabled pending deployment acceptance')
        if not isinstance(self.key,str) or len(self.key)<32:raise ProvisionError('Dedicated deployment admin key required')
        if not isinstance(tenant,str) or not TENANT.fullmatch(tenant):raise ProvisionError('Verified tenant required')
        if not isinstance(verified_email,str) or not re.fullmatch(r'[^\s@<>;,\r\n]+@[^\s@<>;,\r\n]+\.[^\s@<>;,\r\n]+',verified_email):raise ProvisionError('Real verified email required')
        email=verified_email.casefold()
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            if self.db.execute('SELECT 1 FROM provisioning WHERE tenant=? OR email=?',(tenant,email)).fetchone():raise ProvisionError('Existing intent: reconcile locally and upstream, never repeat automatically')
            self.db.execute('INSERT INTO provisioning VALUES(?,?,?,NULL,NULL)',(tenant,email,'pending'))
        output=self.root/(tenant+'.json')
        if output.exists() or output.is_symlink():raise ProvisionError('Private output already exists; reconcile')
        # This file remains as a reconciliation sentinel if any response is lost.
        fd=os.open(output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        try:
            from urllib.parse import quote
            # Explicit GET for an already-existing email refuses accidental merge.
            try:existing=self.api(self.base,'/admin/users/email/'+quote(email,safe=''),self.key,header='X-Admin-API-Key')
            except RuntimeError as e:
                if str(e)!='Upstream HTTP 404; no automatic retry':raise
                existing=None
            if existing is not None:raise ProvisionError('Existing upstream identity requires explicit reconciliation')
            status,user=self.api(self.base,'/admin/users',self.key,'POST',{'email':email,'name':'Lathar Labs workspace','max_concurrent_bots':1},header='X-Admin-API-Key',with_status=True)
            if status!=201:raise ProvisionError('Existing/racing upstream identity refused; reconcile without merge')
            if not isinstance(user,dict) or type(user.get('id')) is not int or user['id']<1 or user.get('email','').casefold()!=email or user.get('max_concurrent_bots')!=1:raise ProvisionError('User readback mismatch; reconcile')
            uid=user['id']
            check=self.api(self.base,'/admin/users/'+str(uid),self.key,header='X-Admin-API-Key')
            if not isinstance(check,dict) or check.get('id')!=uid or check.get('email','').casefold()!=email or check.get('max_concurrent_bots')!=1:raise ProvisionError('User identity/cap mismatch')
            with self.db:self.db.execute('UPDATE provisioning SET state=?,user_id=? WHERE tenant=?',('user-created',uid,tenant))
            token=self.api(self.base,f'/admin/users/{uid}/tokens',self.key,'POST',{'name':'labs-meet-'+tenant,'scopes':['bot','tx'],'expires_in':86400},header='X-Admin-API-Key')
            if not isinstance(token,dict) or type(token.get('id')) is not int or token.get('user_id')!=uid or set(token.get('scopes',[]))!={'bot','tx'} or not isinstance(token.get('token'),str) or len(token['token'])<16:raise ProvisionError('Token response unverified; reconcile')
            raw=json.dumps({'user_id':uid,'token_id':token['id'],'key':token['token'],'expires_in':86400,'expires_at':time.time()+86400}).encode()
            if os.write(fd,raw)!=len(raw):raise ProvisionError('Private write incomplete')
            os.fsync(fd)
            with self.db:self.db.execute('UPDATE provisioning SET state=?,token_id=? WHERE tenant=?',('ready',token['id'],tenant))
            return {'tenant':tenant,'user_id':uid,'token_id':token['id'],'scopes':['bot','tx'],'max_concurrent_bots':1,'key_saved':True,'expires_in':86400}
        except Exception:
            with self.db:self.db.execute("UPDATE provisioning SET state='unknown' WHERE tenant=?",(tenant,))
            raise ProvisionError('Provisioning not confirmed. Reconcile intent, private file, user and token metadata before any retry.') from None
        finally:os.close(fd)


class CredentialFiles:
    """Read-only server credential callback; contains no admin credential/mutation.

    Exact root/base are operator config. Session selects tenant; no browser path.
    Expired keys fail closed and require an independently approved rotation plan.
    """
    def __init__(self,root,base):self.root=Path(root);self.base=endpoint(base)
    def __call__(self,tenant):
        if not isinstance(tenant,str) or not TENANT.fullmatch(tenant):raise ProvisionError('Verified tenant required')
        if self.root.is_symlink() or not self.root.is_dir() or self.root.stat().st_mode&0o077:raise ProvisionError('Private credential directory required')
        file=self.root/(tenant+'.json')
        if not file.exists():return None
        if file.is_symlink() or not file.is_file() or file.stat().st_mode&0o077 or file.stat().st_size>8192:raise ProvisionError('Private credential file refused')
        try:data=json.loads(file.read_text())
        except (ValueError,OSError):raise ProvisionError('Credential state uncertain; reconcile before use') from None
        if not isinstance(data,dict) or type(data.get('user_id')) is not int or data['user_id']<1 or not isinstance(data.get('key'),str) or len(data['key'])<16 or type(data.get('expires_at')) not in (int,float) or data['expires_at']<=time.time():raise ProvisionError('Workspace credential unavailable or expired')
        return {'base':self.base,'key':data['key'],'user_id':data['user_id']}
