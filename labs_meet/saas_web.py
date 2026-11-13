"""Isolated public SaaS HTTP entry point. Not enabled by legacy serve().

Start only after deployment acceptance. Provider factories are operator-owned,
never request-selected. No fallback to legacy single-owner database or Vexa key.
"""
from dataclasses import dataclass
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlsplit
import ipaddress
import json
import os
import time
import sqlite3
from .auth_core import AuthCore, AuthError
from .google_identity import verify_credential
from .tenancy import tenant_store
from .workspaces import Registry, ScopedVexa, WorkspaceError
from .service import Companion
from .web import operation
from .core import meeting_code, minutes

SESSION='__Host-labs_session'
BROWSER='__Host-labs_browser'

@dataclass(frozen=True)
class SaaSConfig:
    root: Path
    origin: str
    key: bytes
    otp_sender: object = None
    google_client_id: str = ''
    google_verifier: object = verify_credential
    credential_for: object = None
    upstream_isolation_verified: bool = False
    capacity: object = None
    daily_joins: int = 20
    tenant_daily: int = 3
    trusted_proxy_ips: tuple = ()
    operations_enabled: bool = False

    def __post_init__(self):
        p=urlsplit(self.origin)
        if p.scheme!='https' or not p.hostname or p.path or p.query or p.fragment or p.username:
            raise ValueError('Exact HTTPS origin required')
        for proxy in self.trusted_proxy_ips:
            ipaddress.ip_address(proxy)
        if not isinstance(self.key,bytes) or len(self.key)<32:raise ValueError('Dedicated authentication key required')


def handler(config):
    root=Path(config.root)
    if root.is_symlink():raise ValueError('Private root refused')
    root.mkdir(mode=0o700,parents=True,exist_ok=True);root.chmod(0o700)
    host=urlsplit(config.origin).netloc
    def auth():return AuthCore(root/'auth.db',config.key,allow_signup=True,digits=4)
    def registry():return Registry(root/'registry.db',config.key,capacity=config.capacity,daily_joins=config.daily_joins,tenant_daily=config.tenant_daily)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def response(self,body,status=200,ct='application/json',cookies=()):
            if not isinstance(body,bytes):body=json.dumps(body).encode()
            self.send_response(status)
            headers={'Content-Type':ct+'; charset=utf-8','Content-Length':str(len(body)),'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer','Content-Security-Policy':"default-src 'self'; script-src 'self' https://accounts.google.com/gsi/client; style-src 'self' https://accounts.google.com/gsi/style; frame-src https://accounts.google.com; connect-src 'self' https://accounts.google.com;  frame-ancestors 'none'; base-uri 'none'; form-action 'self'"}
            for k,v in headers.items():self.send_header(k,v)
            for name,value,age in cookies:self.send_header('Set-Cookie',f'{name}={value}; Path=/; Max-Age={age}; Secure; HttpOnly; SameSite=Strict')
            self.end_headers();self.wfile.write(body)
        def cookies(self):
            raw=self.headers.get('Cookie','')
            if len(raw)>4096:raise AuthError('Cookie refused')
            for name in (SESSION,BROWSER):
                if sum(part.strip().split('=',1)[0]==name for part in raw.split(';'))>1:raise AuthError('Cookie refused')
            # GIS adds g_state JSON, which SimpleCookie cannot parse as a
            # whole header. Unrelated site cookies must not hide app cookies.
            result={}
            for part in raw.split(';'):
                name=part.strip().split('=',1)[0]
                if name not in (SESSION,BROWSER):continue
                c=SimpleCookie();c.load(part.strip())
                if name not in c:raise AuthError('Cookie refused')
                result[name]=c[name].value
            return result
        def valid(self,post=False):
            if self.headers.get('Host')!=host: self.response({'error':'Request refused'},403);return False
            if self.headers.get('Sec-Fetch-Site','none') not in ('none','same-origin'):self.response({'error':'Request refused'},403);return False
            if post and self.headers.get('Origin')!=config.origin:self.response({'error':'Request refused'},403);return False
            return True
        def client_ip(self):
            # Nginx MUST overwrite X-Real-IP with $remote_addr, not append an
            # inbound header. Never parse/accept arbitrary X-Forwarded-For chains.
            peer=str(ipaddress.ip_address(self.client_address[0]))
            if peer in config.trusted_proxy_ips:
                values=self.headers.get_all('X-Real-IP',[])
                if len(values)!=1:raise AuthError('Exactly one client address required')
                value=values[0]
                if not value or value.strip()!=value or ',' in value:raise AuthError('Trusted proxy client address missing')
                try:return str(ipaddress.ip_address(value))
                except ValueError:raise AuthError('Trusted proxy client address invalid') from None
            return peer
        def budget(self,a):
            now=time.time();scope=a.seal('http-ip',self.client_ip())
            with a.db:
                a.db.execute('BEGIN IMMEDIATE')
                row=a._limit(scope,now)
                if row['sends']>=120:raise AuthError('Try later')
                a.db.execute('UPDATE limits SET sends=sends+1 WHERE scope=?',(scope,))
        def do_GET(self):
            if not self.valid():return
            a=None;s=None
            try:
                assets={'/':('public','index.html','text/html'),'/landing.css':('public','landing.css','text/css'),'/landing.js':('public','landing.js','text/javascript'),'/hosted-auth.js':('public','hosted-auth.js','text/javascript')}
                if self.path in assets:
                    folder,name,ct=assets[self.path];body=(Path(__file__).parent/folder/name).read_bytes()
                    if name=='index.html':
                        body=body.replace(b'<body>',b'<body data-hosted-auth="true">').replace(b'</body>',b'<script src="hosted-auth.js"></script></body>')
                    self.response(body,ct=ct);return
                a=auth();c=self.cookies()
                if self.path=='/auth/begin':
                    self.budget(a);nonce=a.begin()
                    self.response({'nonce':nonce,'otp_digits':4,'google_client_id':config.google_client_id,'whatsapp_ready':config.otp_sender is not None},cookies=[(BROWSER,nonce,a.TTL)]);return
                token=c.get(SESSION);tenant=a.session(token)
                if self.path=='/auth/session':self.response({**a.public_session(token),'profile':a.profile(tenant)});return
                if self.path=='/app':
                    self.send_response(302);self.send_header('Location','/app/');self.send_header('Cache-Control','no-store');self.end_headers();return
                workspace_assets={'/app/':'workspace.html','/app/workspace.css':'workspace.css','/app/workspace.js':'workspace.js'}
                if self.path in workspace_assets and (Path(__file__).parent/'public'/'workspace.html').is_file():
                    file=workspace_assets[self.path]
                    self.response((Path(__file__).parent/'public'/file).read_bytes(),ct={'workspace.html':'text/html','workspace.css':'text/css','workspace.js':'text/javascript'}[file]);return
                if self.path in ('/app/','/app.js','/style.css'):

                    file='index.html' if self.path=='/app/' else self.path[1:]
                    self.response((Path(__file__).parent/'static'/file).read_bytes(),ct={'index.html':'text/html','app.js':'text/javascript','style.css':'text/css'}[file]);return
                if self.path=='/api/review':
                    s=tenant_store(root/'tenants',tenant)
                    meetings=[dict(r) for r in s.db.execute('SELECT * FROM meetings ORDER BY created DESC')]
                    for m in meetings:
                        mid=m['id'];m.update(segments=[x.__dict__ for x in s.segments(mid)],notes=minutes(s.segments(mid)),ai_notes=s.ai_notes(mid),outbox=[s.out(r[0]) for r in s.db.execute('SELECT id FROM outbox WHERE meeting=? ORDER BY created',(mid,))])
                    credential=config.credential_for(tenant) if config.credential_for is not None else None
                    self.response({'provider_ready':bool(credential),'meetings':meetings,'operations':config.operations_enabled,'customer_workspace':True,'ai_available':False,'delivery_available':False,'live_effects':bool(credential) and config.operations_enabled and config.capacity is not None and config.upstream_isolation_verified and os.environ.get('LABS_LIVE_EFFECTS')=='explicitly-approved','csrf':a.public_session(token)['csrf']});return
                self.response({'error':'Not found'},404)
            except (ValueError,RuntimeError,OSError,KeyError,TypeError,sqlite3.Error):self.response({'error':'Sign in required or request unavailable'},401)
            finally:
                if s:s.db.close()
                if a:a.db.close()
        def do_POST(self):
            if not self.valid(True):return
            a=None;s=None;r=None
            try:
                if self.headers.get('Content-Type')!='application/json':self.response({'error':'JSON required'},415);return
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=16384 or self.headers.get('Transfer-Encoding'):raise ValueError('Invalid body')
                data=json.loads(self.rfile.read(length))
                if not isinstance(data,dict):raise ValueError('Object required')
                a=auth();c=self.cookies();old=c.get(SESSION)
                if self.path in ('/auth/otp/request','/auth/otp/verify','/auth/google'):
                    self.budget(a);nonce=a.browser(c.get(BROWSER))
                    if self.path=='/auth/otp/request':
                        if config.otp_sender is None:raise AuthError('Sender disabled')
                        self.response(a.request(data.get('phone'),nonce,self.client_ip(),config.otp_sender));return
                    if self.path=='/auth/otp/verify':result=a.verify(data.get('challenge'),data.get('code'),nonce,consume_nonce=True)
                    else:
                        if not config.google_client_id:raise AuthError('Google client disabled')
                        result=a.google_login(data.get('credential'),nonce,config.google_client_id,config.google_verifier)
                    if old:a.logout(old)
                    self.response({'authenticated':True,'csrf':result['csrf']},cookies=[(SESSION,result['token'],result['expires_in']),(BROWSER,'',0)]);return
                token=c.get(SESSION);tenant=a.session(token,csrf=self.headers.get('X-Labs-CSRF',''))
                if self.path=='/auth/link/google':
                    if not config.google_client_id:raise AuthError('Google client disabled')
                    result=a.link_google(token,self.headers.get('X-Labs-CSRF',''),data.get('credential'),c.get(BROWSER),config.google_client_id,config.google_verifier)
                    self.response(result,cookies=[(BROWSER,'',0)]);return
                if self.path=='/auth/logout':
                    a.logout(token);self.response({'authenticated':False},cookies=[(SESSION,'',0),(BROWSER,'',0)]);return
                if self.path!='/api/operate':self.response({'error':'Not found'},404);return
                if not config.operations_enabled:raise WorkspaceError('Operations disabled')
                # Browser supplied tenant/path/key fields are never used.
                s=tenant_store(root/'tenants',tenant);r=registry();vexa=None
                if config.credential_for is not None:
                    credential=config.credential_for(tenant)
                    if credential:
                        vexa=ScopedVexa(r,tenant,credential['base'],credential['key'],upstream_user_id=credential.get('user_id'),upstream_isolation_verified=config.upstream_isolation_verified)
                action=data.get('action')
                if action=='create':
                    # Ownership reserved before any local row or upstream access.
                    if data.get('consent_confirmed') is not True:raise ValueError('Consent required')
                    title=data.get('title')
                    if not isinstance(title,str) or not 1<=len(title.strip())<=200:raise ValueError('Title required')
                    r.claim(tenant,meeting_code(data.get('link','')))
                if action in ('sync','join','leave','ai-notes','deliver'):
                    r.owns(tenant,s.meeting(data.get('meeting'))['code'])
                if action in ('execute','reconcile','approve'):
                    out=s.out(data.get('outbox'));r.owns(tenant,s.meeting(out['meeting'])['code'])
                    if action=='execute' and out['kind'] in ('email','whatsapp'):raise WorkspaceError('Customer delivery rollout not enabled')
                    if vexa:vexa.attempt=out['id']
                result=operation(s,data,Companion(s,vexa,None))
                self.response({'ok':True,'result':result})
            except (ValueError,RuntimeError,OSError,KeyError,TypeError,sqlite3.Error):
                self.response({'ok':False,'error':'Request did not complete. Verify account, limits and provider state before retrying. No uncertain send is retried automatically.'},400)
            finally:
                if s:s.db.close()
                if r:r.db.close()
                if a:a.db.close()
    return Handler


def serve(config,port=8081):
    HTTPServer(('127.0.0.1',port),handler(config)).serve_forever()
