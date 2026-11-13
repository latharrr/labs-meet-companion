"""Synthetic tenant/OTP foundation tests, no sender or HTTP integration."""
import json, tempfile, unittest
from pathlib import Path
from labs_meet.auth_core import AuthCore, AuthError
from labs_meet.tenancy import tenant_store
from labs_meet.core import Segment

class SaaSBoundaries(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.root=Path(self.t.name);self.now=[1000000];self.sent=[]
  self.auth=AuthCore(self.root/'auth.db',b'synthetic-test-key-not-production!',allow_signup=True,clock=lambda:self.now[0])
 def tearDown(self):self.auth.db.close();self.t.cleanup()
 def sender(self,phone,code,ttl):self.sent.append((phone,code,ttl));return True
 def request(self,phone='+15555550199',nonce='a'*32,ip='127.0.0.1'):return self.auth.request(phone,nonce,ip,self.sender)
 def login(self,phone='+15555550199'):
  r=self.request(phone);return self.auth.verify(r['challenge'],self.sent[-1][1],'a'*32)
 def test_explicit_audience_and_dedicated_key_required(self):
  with self.assertRaises(AuthError):AuthCore(self.root/'other.db',b'synthetic-test-key-not-production!')
  with self.assertRaises(AuthError):AuthCore(self.root/'other.db',b'short',allow_signup=True)
 def test_six_digits_no_plaintext_storage(self):
  r=self.request();code=self.sent[-1][1];self.assertRegex(code,r'^[0-9]{6}$')
  row=self.auth.db.execute('SELECT * FROM challenges').fetchone();self.assertNotIn(code,json.dumps(dict(row)))
  self.assertNotIn('+15555550199',str(self.auth.db.execute('SELECT * FROM limits').fetchall()))
 def test_single_use_and_browser_binding(self):
  r=self.request();code=self.sent[-1][1]
  with self.assertRaises(AuthError):self.auth.verify(r['challenge'],code,'b'*32)
  session=self.auth.verify(r['challenge'],code,'a'*32)
  with self.assertRaises(AuthError):self.auth.verify(r['challenge'],code,'a'*32)
  self.assertRegex(self.auth.session(session['token']),r'^[a-f0-9]{32}$')
 def test_code_expiry(self):
  r=self.request();self.now[0]+=181
  with self.assertRaises(AuthError):self.auth.verify(r['challenge'],self.sent[-1][1],'a'*32)
 def test_resend_does_not_reset_failure_budget(self):
  r=self.request();wrong='000000' if self.sent[-1][1]!='000000' else '111111'
  for _ in range(4):
   with self.assertRaises(AuthError):self.auth.verify(r['challenge'],wrong,'a'*32)
  self.now[0]+=61;r2=self.request();wrong='000000' if self.sent[-1][1]!='000000' else '111111'
  with self.assertRaises(AuthError):self.auth.verify(r2['challenge'],wrong,'a'*32)
  with self.assertRaises(AuthError):self.auth.verify(r2['challenge'],self.sent[-1][1],'a'*32)
 def test_resend_invalidates_old_code(self):
  r=self.request();old=self.sent[-1][1];self.now[0]+=61;self.request()
  with self.assertRaises(AuthError):self.auth.verify(r['challenge'],old,'a'*32)
 def test_cooldown_and_daily_cap(self):
  self.request()
  with self.assertRaises(AuthError):self.request()
  for _ in range(4):self.now[0]+=61;self.request()
  self.now[0]+=61
  with self.assertRaises(AuthError):self.request()
 def test_unknown_sender_result_no_retry_no_session(self):
  calls=[]
  def bad(*args):calls.append(1);raise TimeoutError('sensitive provider response')
  with self.assertRaisesRegex(AuthError,'not confirmed'):self.auth.request('+15555550199','a'*32,'127.0.0.1',bad)
  self.assertEqual(len(calls),1);self.assertEqual(self.auth.db.execute('SELECT count(*) FROM sessions').fetchone()[0],0)
 def test_session_expiry_logout_and_csrf(self):
  s=self.login()
  with self.assertRaises(AuthError):self.auth.session(s['token'],csrf='wrong')
  self.assertTrue(self.auth.session(s['token'],csrf=s['csrf']))
  self.auth.logout(s['token'])
  with self.assertRaises(AuthError):self.auth.session(s['token'])
 def test_owner_mode_refuses_other_number_without_sender_call(self):
  a=AuthCore(self.root/'owner.db',b'synthetic-test-key-not-production!',owner_phone='+15555550199')
  try:
   with self.assertRaises(AuthError):a.request('+15555550198','a'*32,'127.0.0.1',self.sender)
   self.assertEqual(self.sent,[])
  finally:a.db.close()
 def test_two_accounts_cannot_read_or_approve_each_others_records(self):
  s1=self.login();self.now[0]+=61;s2=self.login('+15555550198')
  t1,t2=self.auth.session(s1['token']),self.auth.session(s2['token']);self.assertNotEqual(t1,t2)
  a,b=tenant_store(self.root/'workspaces',t1),tenant_store(self.root/'workspaces',t2)
  try:
   mid=a.create('Tenant A private','abc-defg-hij','Synthetic');a.ingest(mid,[Segment('x',0,1,'Private A','A')]);oid=a.stage(mid,'chat',{'text':'Private A'})
   with self.assertRaises(ValueError):b.meeting(mid)
   with self.assertRaises(ValueError):b.approve(oid,a.out(oid)['digest'])
   self.assertEqual(b.db.execute('SELECT count(*) FROM segments').fetchone()[0],0)
  finally:a.db.close();b.db.close()
 def test_tenant_path_rejects_client_path_traversal_and_symlink(self):
  for bad in ['../other','+15555550199','A'*32,'x'*32,None]:
   with self.assertRaises(ValueError):tenant_store(self.root/'workspaces',bad)
  base=self.root/'workspaces';base.mkdir();(base/('a'*32)).symlink_to(self.root,target_is_directory=True)
  with self.assertRaises(ValueError):tenant_store(base,'a'*32)
 def test_concurrent_verification_issues_only_one_session(self):
  import threading
  r=self.request();code=self.sent[-1][1];barrier=threading.Barrier(2);results=[]
  def worker():
   a=AuthCore(self.root/'auth.db',b'synthetic-test-key-not-production!',allow_signup=True,clock=lambda:self.now[0]);barrier.wait()
   try:a.verify(r['challenge'],code,'a'*32);results.append('verified')
   except AuthError:results.append('refused')
   finally:a.db.close()
  threads=[threading.Thread(target=worker) for _ in range(2)]
  for t in threads:t.start()
  for t in threads:t.join(10)
  self.assertEqual(sorted(results),['refused','verified'])
  self.assertEqual(self.auth.db.execute('SELECT count(*) FROM sessions').fetchone()[0],1)
