"""Loopback UI with optional, fail-closed owner operations behind HTTP Basic auth."""
from http.server import BaseHTTPRequestHandler, HTTPServer
import base64
import hmac
import json
import os
from pathlib import Path
import secrets
from .store import Store
from .core import minutes
from .service import Companion
from .adapters import Vexa
from .ai import GroundedAI


def service(store):
    vexa = Vexa(os.environ['LABS_VEXA_URL'], os.environ['LABS_VEXA_KEY']) if os.environ.get('LABS_VEXA_URL') and os.environ.get('LABS_VEXA_KEY') else None
    ai = GroundedAI(os.environ.get('LABS_AI_URL', 'https://api.groq.com/openai/v1'), os.environ['LABS_AI_KEY'], os.environ.get('LABS_AI_MODEL', 'openai/gpt-oss-20b')) if os.environ.get('LABS_AI_KEY') else None
    return Companion(store, vexa, ai)


def operation(store, data, app=None):
    app = app if app is not None else service(store)
    action = data.get('action')
    if action == 'create':
        if data.get('consent_confirmed') is not True:
            raise ValueError('Confirm organizer authority and participant notice first')
        title = str(data.get('title', '')).strip()
        if not 1 <= len(title) <= 200:
            raise ValueError('Title must be 1..200 characters')
        mid = app.create(title, data['link'], 'Authenticated organizer confirmed authority, participant notice and required consent')
        return {'meeting': mid, 'outbox': app.stage_join(mid)}
    mid = data.get('meeting')
    if action == 'join': return {'outbox': app.stage_join(mid)}
    if action == 'leave': return {'outbox': store.stage(mid, 'leave', {'code': store.meeting(mid)['code']})}
    if action == 'sync':
        # First observed snapshot establishes the chat baseline, never answers backlog.
        prior=store.db.execute("SELECT 1 FROM seen WHERE meeting=? LIMIT 1",(mid,)).fetchone()
        baseline=not prior
        drafts=app.sync(mid, baseline=baseline)
        if baseline:
            with store.db: store.db.execute("INSERT OR IGNORE INTO seen VALUES(?,?)",(mid,'__ui_baseline__'))
        return {'chat_drafts': drafts}
    if action == 'ai-notes': return app.generate_notes(mid)
    if action == 'deliver':
        kind = data.get('kind')
        return {'outbox': app.stage_whatsapp_chunks(mid, data['to']) if kind == 'whatsapp' else [app.stage_delivery(mid, kind, data['to'])]}
    if action == 'approve':
        store.approve(data['outbox'], data['digest'])
        return {'status': 'approved, not sent'}
    if action == 'execute': return app.execute(data['outbox'])
    if action == 'reconcile': return app.reconcile_chat(data['outbox'])
    raise ValueError('Unsupported operation')


def handler(db, port):
    csrf = secrets.token_urlsafe(32)
    username, password = os.environ.get('LABS_UI_USER'), os.environ.get('LABS_UI_PASSWORD')
    if bool(username) != bool(password): raise ValueError('Set both UI username and password')
    protected = bool(username and password)
    public_host = os.environ.get('LABS_UI_HOST', '')
    if public_host and not protected: raise ValueError('Configured public host requires UI authentication')
    if public_host and (any(c in public_host for c in '/?#@\r\n') or ':' in public_host): raise ValueError('UI host must be a plain DNS hostname')
    operations = protected and os.environ.get('LABS_UI_OPERATIONS') == 'explicitly-approved'
    allowed_hosts = {f'127.0.0.1:{port}', f'localhost:{port}'} | ({public_host} if public_host else set())
    allowed_origins = {f'http://127.0.0.1:{port}', f'http://localhost:{port}'} | ({'https://' + public_host} if public_host else set())

    class Handler(BaseHTTPRequestHandler):
        def allowed(self):
            if self.headers.get('Host') not in allowed_hosts:
                self.send_error(403); return False
            if protected:
                value = self.headers.get('Authorization', '')
                try:
                    raw = base64.b64decode(value[6:], validate=True).decode() if value.startswith('Basic ') else ''
                except (ValueError, UnicodeError): raw = ''
                if not hmac.compare_digest(raw.encode(), (username + ':' + password).encode()):
                    self.send_response(401); self.send_header('WWW-Authenticate', 'Basic realm="Private meeting companion", charset="UTF-8"'); self.send_header('Cache-Control','no-store'); self.end_headers(); return False
            return True

        def response(self, body, ct='application/json', status=200):
            if not isinstance(body, bytes): body=json.dumps(body).encode()
            self.send_response(status)
            for key,value in {'Content-Type':ct+'; charset=utf-8','Content-Length':str(len(body)), 'Cache-Control':'no-store', 'X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer','Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"}.items(): self.send_header(key,value)
            self.end_headers(); self.wfile.write(body)

        def do_GET(self):
            # Optional public marketing preview is a fixed synthetic asset set.
            # It never passes through the private meeting database or session APIs.
            public_files = {
                '/welcome': ('index.html', 'text/html'),
                '/welcome/': ('index.html', 'text/html'),
                '/welcome/landing.css': ('landing.css', 'text/css'),
                '/welcome/landing.js': ('landing.js', 'text/javascript'),
            }
            if os.environ.get('LABS_PUBLIC_LANDING') == 'explicitly-approved' and self.path in public_files:
                if self.headers.get('Host') not in allowed_hosts:
                    self.send_error(403); return
                # Canonical trailing slash makes relative assets resolve locally.
                if self.path == '/welcome':
                    self.send_response(302); self.send_header('Location', '/welcome/'); self.send_header('Cache-Control', 'no-store'); self.end_headers(); return
                name, content_type = public_files[self.path]
                self.response((Path(__file__).parent/'public'/name).read_bytes(), content_type)
                return
            if not self.allowed(): return
            if self.path == '/api/review':
                s=Store(db)
                try:
                    meetings=[dict(r) for r in s.db.execute('SELECT * FROM meetings ORDER BY created DESC')]
                    for m in meetings:
                        m['segments']=[seg.__dict__ for seg in s.segments(m['id'])]
                        m['notes']=minutes(s.segments(m['id']))
                        m['ai_notes']=s.ai_notes(m['id'])
                        m['outbox']=[s.out(r[0]) for r in s.db.execute('SELECT id FROM outbox WHERE meeting=? ORDER BY created',(m['id'],))]
                    self.response({'meetings':meetings, 'live_effects':os.environ.get('LABS_LIVE_EFFECTS')=='explicitly-approved', 'operations':operations, 'csrf':csrf if operations else None})
                finally: s.db.close()
            elif self.path in ('/','/style.css','/app.js'):
                file='index.html' if self.path=='/' else self.path[1:]
                self.response((Path(__file__).parent/'static'/file).read_bytes(),{'index.html':'text/html','style.css':'text/css','app.js':'text/javascript'}[file])
            else: self.send_error(404)

        def do_POST(self):
            if not self.allowed(): return
            if not operations or self.path!='/api/operate' or self.headers.get('Origin') not in allowed_origins or not hmac.compare_digest(self.headers.get('X-Labs-CSRF',''),csrf):
                self.send_error(403); return
            if self.headers.get('Content-Type') != 'application/json': self.send_error(415); return
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=8192: raise ValueError('Request too large or empty')
                data=json.loads(self.rfile.read(length))
                if not isinstance(data,dict): raise ValueError('Expected object')
                s=Store(db)
                try: result=operation(s,data)
                finally:s.db.close()
                self.response({'ok':True,'result':result})
            except (ValueError,RuntimeError,OSError,KeyError,TypeError):
                # Provider exceptions can contain sensitive data. Never return raw exception strings.
                self.response({'ok':False,'error':'Operation did not complete. Check configuration, current review state and provider status before retrying. Uncertain sends must be reconciled.'},status=400)

        def log_message(self,*args): pass
    return Handler


def serve(db,port):
    print(f'Meeting companion: http://127.0.0.1:{port} (loopback only)',flush=True)
    HTTPServer(('127.0.0.1',port),handler(db,port)).serve_forever()
