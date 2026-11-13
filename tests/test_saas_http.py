import json, tempfile, threading, unittest, urllib.request, urllib.error
from pathlib import Path
from http.server import HTTPServer
from labs_meet.saas_web import SaaSConfig,handler,SESSION,BROWSER
from labs_meet.auth_core import AuthCore

class HttpJourney(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.codes={};self.calls=[]
  def sender(phone,code,ttl):self.codes[phone]=code;self.assertEqual(len(code),4);return True
  def verifier(credential,**kw):
   self.calls.append((credential,kw))
   if credential=='invalid':raise ValueError()
   return {'issuer':'google','subject':credential}
  self.config=SaaSConfig(self.root,'https://bot.143.lat',b'x'*32,otp_sender=sender,google_client_id='test.apps.googleusercontent.com',google_verifier=verifier,operations_enabled=True)
  self.server=HTTPServer(('127.0.0.1',0),handler(self.config));self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
 def tearDown(self):self.server.shutdown();self.server.server_close();self.thread.join();self.temp.cleanup()
 def req(self,path,data=None,cookies='',csrf=None,origin='https://bot.143.lat',host='bot.143.lat',extra=None):
  headers={'Host':host,'Cookie':cookies}
  if data is not None:headers.update({'Origin':origin,'Content-Type':'application/json'})
  if csrf is not None:headers['X-Labs-CSRF']=csrf
  if extra:headers.update(extra)
  req=urllib.request.Request(f'http://127.0.0.1:{self.server.server_port}'+path,data=json.dumps(data).encode() if data is not None else None,headers=headers)
  try:r=urllib.request.urlopen(req,timeout=3)
  except urllib.error.HTTPError as err:r=err
  raw=r.read();body=json.loads(raw) if 'application/json' in r.headers.get('Content-Type','') else raw
  return r.code,body,r.headers
 def begin(self):
  code,body,headers=self.req('/auth/begin');self.assertEqual(code,200)
  return f'{BROWSER}='+body['nonce']
 def login(self,subject='alice'):
  cookie=self.begin();code,result,headers=self.req('/auth/google',{'credential':subject},cookie);self.assertEqual(code,200)
  session=[s.split(';')[0] for s in headers.get_all('Set-Cookie') if s.startswith(SESSION+'=')][0]
  return session,result['csrf']
 def create(self,cookie,csrf,link='https://meet.google.com/abc-defg-hij',title='Private A'):
  return self.req('/api/operate',{'action':'create','title':title,'link':link,'consent_confirmed':True},cookie,csrf)
 def test_no_session_no_private_resources(self):
  for path in ['/app','/api/review','/app.js','/style.css','/auth/session']:self.assertEqual(self.req(path)[0],401)
 def test_workspace_assets_private_and_served_from_public_bundle(self):
  assets={'/app/':b'id="add-dialog"','/app/workspace.css':b'--paper','/app/workspace.js':b'async function logout'}
  for path in assets:self.assertEqual(self.req(path)[0],401)
  cookie,_=self.login()
  for path,marker in assets.items():
   status,body,headers=self.req(path,cookies=cookie)
   self.assertEqual(status,200);self.assertIn(marker,body)
   self.assertIn('no-store',headers['Cache-Control'])
 def test_workspace_frontend_mutation_and_logout_guards(self):
  js=(Path(__file__).parents[1]/'labs_meet/public/workspace.js').read_text()
  self.assertIn('if (mutationBusy) return;',js)
  self.assertIn('setBusy(mutationBusy)',js)
  self.assertIn("if (!operations || mutationBusy) return;",js)
  self.assertIn("$('empty-add-button').setAttribute('data-operate', 'true')",js)
  self.assertIn("await apiJson('/auth/logout'",js)
  self.assertIn('Your session may still be active',js)
  self.assertNotIn('innerHTML',js)
 def test_secure_http_only_strict_cookie(self):
  cookie=self.begin();status,body,headers=self.req('/auth/google',{'credential':'alice'},cookie)
  self.assertEqual(status,200)
  for value in headers.get_all('Set-Cookie'):
   for flag in ['Secure','HttpOnly','SameSite=Strict','Path=/']:self.assertIn(flag,value)
  self.assertNotIn('token',body)
 def test_google_nonce_single_use(self):
  cookie=self.begin();self.assertEqual(self.req('/auth/google',{'credential':'alice'},cookie)[0],200)
  self.assertEqual(self.req('/auth/google',{'credential':'alice'},cookie)[0],400)
 def test_google_invalid_no_account(self):
  self.assertEqual(self.req('/auth/google',{'credential':'invalid'},self.begin())[0],400)
  a=AuthCore(self.root/'auth.db',b'x'*32,allow_signup=True);self.assertEqual(a.db.execute('SELECT count(*) FROM google_accounts').fetchone()[0],0);a.db.close()
 def test_otp_four_digit_single_use_and_new_account(self):
  cookie=self.begin();status,result,_=self.req('/auth/otp/request',{'phone':'+12025550101'},cookie);self.assertEqual(status,200)
  data={'challenge':result['challenge'],'code':self.codes['+12025550101']}
  status,body,headers=self.req('/auth/otp/verify',data,cookie);self.assertEqual(status,200);self.assertNotIn('token',body)
  self.assertEqual(self.req('/auth/otp/verify',data,cookie)[0],400)
 def test_wrong_code_and_nonce_cannot_sign_in(self):
  cookie=self.begin();_,result,_=self.req('/auth/otp/request',{'phone':'+12025550101'},cookie)
  self.assertEqual(self.req('/auth/otp/verify',{'challenge':result['challenge'],'code':self.codes['+12025550101']},self.begin())[0],400)
 def test_no_automatic_google_phone_link(self):
  google,_=self.login('+12025550101');browser=self.begin();_,req,_=self.req('/auth/otp/request',{'phone':'+12025550101'},browser)
  _,res,heads=self.req('/auth/otp/verify',{'challenge':req['challenge'],'code':self.codes['+12025550101']},browser)
  phone=[v.split(';')[0] for v in heads.get_all('Set-Cookie') if v.startswith(SESSION+'=')][0]
  a=AuthCore(self.root/'auth.db',b'x'*32,allow_signup=True);self.assertNotEqual(a.session(google.split('=',1)[1]),a.session(phone.split('=',1)[1]));a.db.close()
 def test_cross_account_private_meeting_and_same_code_denied(self):
  a,ca=self.login('alice');b,cb=self.login('bob');status,result,_=self.create(a,ca);self.assertEqual(status,200);mid=result['result']['meeting']
  self.assertEqual(len(self.req('/api/review',cookies=b)[1]['meetings']),0)
  self.assertEqual(self.create(b,cb)[0],400)
  self.assertEqual(self.req('/api/operate',{'action':'leave','meeting':mid},b,cb)[0],400)
  self.assertNotIn('Private A',json.dumps(self.req('/api/review',cookies=b)[1]))
 def test_cross_account_outbox_approval_denied(self):
  a,ca=self.login();b,cb=self.login('bob');_,res,_=self.create(a,ca);out=res['result']['outbox']
  self.assertEqual(self.req('/api/operate',{'action':'approve','outbox':out,'digest':'bad'},b,cb)[0],400)
 def test_csrf_origin_host_and_forwarded_header_refused(self):
  a,ca=self.login()
  self.assertEqual(self.create(a,'bad')[0],400)
  self.assertEqual(self.req('/auth/logout',{},a,ca,origin='https://evil.invalid')[0],403)
  self.assertEqual(self.req('/api/review',cookies=a,host='evil.invalid')[0],403)
  self.assertEqual(self.req('/auth/logout',{},a,ca,extra={'Sec-Fetch-Site':'cross-site'})[0],403)
 def test_tenant_path_and_fake_user_fields_ignored(self):
  a,ca=self.login();self.assertEqual(self.req('/api/operate',{'action':'create','title':'A','link':'https://meet.google.com/abc-defg-hij','consent_confirmed':True,'tenant':'../escape','db':'/tmp/evil','vexa_key':'injected'},a,ca)[0],200)
  self.assertEqual(len(list((self.root/'tenants').iterdir())),1);self.assertFalse((self.root/'escape').exists())
 def test_logout_and_rotate_old_session(self):
  a,ca=self.login();browser=self.begin();_,res,heads=self.req('/auth/google',{'credential':'alice'},browser+'; '+a)
  self.assertEqual(self.req('/api/review',cookies=a)[0],401)
  b=[s.split(';')[0] for s in heads.get_all('Set-Cookie') if s.startswith(SESSION+'=')][0]
  self.assertEqual(self.req('/auth/logout',{},b,res['csrf'])[0],200);self.assertEqual(self.req('/api/review',cookies=b)[0],401)
 def test_duplicate_cookie_refused(self):
  a,ca=self.login();self.assertEqual(self.req('/api/review',cookies=a+'; '+a)[0],401)
 def test_gis_json_cookie_does_not_hide_app_session(self):
  a,ca=self.login()
  for cookies in ['g_state={"i_l":0}; '+a,a+'; g_state={"i_l":0}']:
   self.assertEqual(self.req('/auth/session',cookies=cookies)[0],200)
   self.assertEqual(self.req('/api/review',cookies=cookies)[0],200)
  self.assertEqual(self.req('/auth/session',cookies='g_state={"i_l":0}; '+a+'; '+a)[0],401)
 def test_gis_json_cookie_does_not_hide_nonce(self):
  cookie=self.begin()
  self.assertEqual(self.req('/auth/google',{'credential':'alice'},'g_state={"i_l":0}; '+cookie)[0],200)
 def test_live_off_no_transcript_network(self):
  a,ca=self.login();_,result,_=self.create(a,ca)
  self.assertEqual(self.req('/api/operate',{'action':'sync','meeting':result['result']['meeting']},a,ca)[0],400)
 def test_errors_redact_credentials(self):
  status,body,_=self.req('/auth/google',{'credential':'secret-marker'},self.begin(),origin='https://evil.invalid');self.assertNotIn('secret-marker',json.dumps(body))
 def test_explicit_link_existing_google_workspace_refused_not_merged(self):
  google,cg=self.login('alice');phonebrowser=self.begin();_,req,_=self.req('/auth/otp/request',{'phone':'+12025550101'},phonebrowser)
  _,result,heads=self.req('/auth/otp/verify',{'challenge':req['challenge'],'code':self.codes['+12025550101']},phonebrowser)
  phone=[v.split(';')[0] for v in heads.get_all('Set-Cookie') if v.startswith(SESSION+'=')][0]
  self.assertEqual(self.req('/auth/link/google',{'credential':'alice'},phone+'; '+self.begin(),result['csrf'])[0],400)
 def test_profile_email_not_browser_supplied(self):
  a,ca=self.login('alice');self.assertIsNone(self.req('/auth/session',cookies=a)[1]['profile']['verified_email'])
  self.assertEqual(self.req('/auth/link/google',{'credential':'alice','email':'attacker@example.test'},a+'; '+self.begin(),ca)[0],200)
  self.assertIsNone(self.req('/auth/session',cookies=a)[1]['profile']['verified_email'])
 def test_untrusted_forwarded_header_cannot_choose_rate_identity(self):
  _,body,_=self.req('/auth/begin',extra={'X-Real-IP':'198.51.100.17','X-Forwarded-For':'198.51.100.18'})
  a=AuthCore(self.root/'auth.db',b'x'*32,allow_signup=True)
  self.assertTrue(a.db.execute('SELECT 1 FROM limits WHERE scope=?',(a.seal('http-ip','127.0.0.1'),)).fetchone())
  self.assertFalse(a.db.execute('SELECT 1 FROM limits WHERE scope=?',(a.seal('http-ip','198.51.100.17'),)).fetchone());a.db.close()
 def test_explicit_trusted_proxy_distinct_client_budgets(self):
  from dataclasses import replace
  self.server.RequestHandlerClass=handler(replace(self.config,trusted_proxy_ips=('127.0.0.1',)))
  for ip in ['198.51.100.17','198.51.100.18']:self.assertEqual(self.req('/auth/begin',extra={'X-Real-IP':ip,'X-Forwarded-For':'attacker'})[0],200)
  a=AuthCore(self.root/'auth.db',b'x'*32,allow_signup=True)
  for ip in ['198.51.100.17','198.51.100.18']:self.assertEqual(a.db.execute('SELECT sends FROM limits WHERE scope=?',(a.seal('http-ip',ip),)).fetchone()[0],1)
  a.db.close()
 def test_trusted_proxy_invalid_or_missing_header_refused(self):
  from dataclasses import replace
  self.server.RequestHandlerClass=handler(replace(self.config,trusted_proxy_ips=('127.0.0.1',)))
  for value in ['', '198.51.100.17,198.51.100.18','not-ip','198.51.100.17 ']:
   self.assertEqual(self.req('/auth/begin',extra={'X-Real-IP':value})[0],401)
 def test_explicit_link_refuses_replace_google_identity(self):
  a,ca=self.login('alice')
  self.assertEqual(self.req('/auth/link/google',{'credential':'bob'},a+'; '+self.begin(),ca)[0],400)
 def test_link_nonce_replay_refused(self):
  a,ca=self.login('alice');browser=self.begin()
  self.assertEqual(self.req('/auth/link/google',{'credential':'alice'},a+'; '+browser,ca)[0],200)
  self.assertEqual(self.req('/auth/link/google',{'credential':'alice'},a+'; '+browser,ca)[0],400)
