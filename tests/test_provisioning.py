import tempfile,unittest
from pathlib import Path
from labs_meet.provisioning import Provisioner,ProvisionError

class Provision(unittest.TestCase):
 def setUp(self):self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.calls=[]
 def tearDown(self):self.temp.cleanup()
 def api(self,base,path,key,method='GET',body=None,**kw):
  self.calls.append((path,method,body,kw))
  if '/email/' in path:raise RuntimeError('Upstream HTTP 404; no automatic retry')
  if path.endswith('/tokens'):return {'id':4,'user_id':3,'scopes':['bot','tx'],'token':'synthetic-test-key-00000000'}
  user={'id':3,'email':'real@example.test','max_concurrent_bots':1}
  return (201,user) if kw.get('with_status') else user
 def make(self,**kwargs):return Provisioner(self.root,'http://127.0.0.1:8001','synthetic-admin-key-32bytes-long!!!',api=self.api,**kwargs)
 def test_disabled_never_calls(self):
  p=self.make()
  with self.assertRaises(ProvisionError):p.provision('a'*32,'real@example.test')
  self.assertEqual(self.calls,[]);p.db.close()
 def test_phone_not_invented_email(self):
  p=self.make(enabled=True,hooks_isolated=True)
  with self.assertRaises(ProvisionError):p.provision('a'*32,'+12025550101')
  self.assertEqual(self.calls,[]);p.db.close()
 def test_success_explicit_caps_scopes_expiry_saved_not_returned(self):
  p=self.make(enabled=True,hooks_isolated=True);result=p.provision('a'*32,'Real@example.test')
  self.assertNotIn('key',result);self.assertEqual(result['max_concurrent_bots'],1);self.assertEqual(self.calls[-1][2]['expires_in'],86400)
  self.assertEqual((self.root/('a'*32+'.json')).stat().st_mode&0o777,0o600)
  self.assertEqual(self.calls[1][2]['max_concurrent_bots'],1)
  with self.assertRaises(ProvisionError):p.provision('a'*32,'real@example.test')
  self.assertEqual(len(self.calls),4);p.db.close()
 def test_unknown_admin_response_no_second_attempt(self):
  p=self.make(enabled=True,hooks_isolated=True)
  def unknown(*args,**kwargs):self.calls.append('one');raise TimeoutError()
  p.api=unknown
  for _ in range(2):
   with self.assertRaises(ProvisionError):p.provision('a'*32,'real@example.test')
  self.assertEqual(self.calls,['one']);self.assertEqual(p.db.execute('SELECT state FROM provisioning').fetchone()[0],'unknown');p.db.close()
 def test_existing_email_never_merged(self):
  p=self.make(enabled=True,hooks_isolated=True);p.api=lambda *a,**k:{'id':99}
  with self.assertRaises(ProvisionError):p.provision('a'*32,'real@example.test')
  self.assertEqual((self.root/('a'*32+'.json')).read_bytes(),b'');p.db.close()
 def test_create_race_existing200_never_mints_token(self):
  p=self.make(enabled=True,hooks_isolated=True)
  original=self.api
  def api(*args,**kw):
   res=original(*args,**kw)
   if kw.get('with_status'):return 200,res[1]
   return res
  p.api=api
  with self.assertRaises(ProvisionError):p.provision('a'*32,'real@example.test')
  self.assertEqual(len(self.calls),2);p.db.close()
 def test_readonly_credential_callback_tenant_bound_private_expiring(self):
  import json
  from labs_meet.provisioning import CredentialFiles
  p=self.make(enabled=True,hooks_isolated=True);p.provision('a'*32,'real@example.test');p.db.close()
  read=CredentialFiles(self.root,'http://127.0.0.1:8056');self.assertEqual(read('a'*32)['user_id'],3);self.assertIsNone(read('b'*32))
  with self.assertRaises(ProvisionError):read('../other')
  file=self.root/('a'*32+'.json');data=json.loads(file.read_text());data['expires_at']=0;file.write_text(json.dumps(data))
  with self.assertRaises(ProvisionError):read('a'*32)
 def test_readonly_credential_callback_rejects_symlink_or_publicfile(self):
  from labs_meet.provisioning import CredentialFiles
  p=self.make(enabled=True,hooks_isolated=True);p.provision('a'*32,'real@example.test');p.db.close()
  file=self.root/('a'*32+'.json');file.chmod(0o644);read=CredentialFiles(self.root,'http://127.0.0.1:8056')
  with self.assertRaises(ProvisionError):read('a'*32)
  file.unlink();file.symlink_to('/etc/passwd')
  with self.assertRaises(ProvisionError):read('a'*32)

 def test_provision_database_symlink_refused(self):
  target=self.root/'outside';target.write_text('not SQLite');(self.root/'provision.db').symlink_to(target)
  with self.assertRaises(ProvisionError):self.make()
  self.assertEqual(target.read_text(),'not SQLite')
