import json,os,tempfile,unittest
from pathlib import Path
from labs_meet.saas_runtime import load
class Runtime(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.key=self.root/'auth.key';self.key.write_bytes(b'x'*32);self.key.chmod(0o600);self.path=self.root/'config.json';self.data={'root':str(self.root/'state'),'origin':'https://bot.143.lat','auth_key_file':str(self.key)}
 def tearDown(self):self.temp.cleanup()
 def write(self):self.path.write_text(json.dumps(self.data));self.path.chmod(0o600)
 def test_defaults_no_live_services_or_credentials(self):
  self.write();config,port=load(self.path);self.assertFalse(config.operations_enabled);self.assertIsNone(config.otp_sender);self.assertIsNone(config.credential_for);self.assertEqual(port,8081)
 def test_config_public_or_symlink_refused(self):
  self.write();self.path.chmod(0o644)
  with self.assertRaises(ValueError):load(self.path)
  self.path.chmod(0o600);link=self.root/'link';link.symlink_to(self.path)
  with self.assertRaises(ValueError):load(link)
 def test_unknown_gates_costs_and_legacy_fallback_refused(self):
  for field,value in [('legacy_key','x'),('origin','http://localhost'),('operations_enabled',True),('otp',{'enabled':'yes'}),('port',80)]:
   base=self.data.copy();self.data[field]=value;self.write()
   with self.assertRaises((ValueError,KeyError)):load(self.path)
   self.data=base
 def test_actual_runtime_process_http_bootstrap(self):
  import socket,subprocess,sys,time,urllib.request
  with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
  self.data['port']=port;self.write();proc=subprocess.Popen([sys.executable,'-m','labs_meet.saas_runtime','--config',str(self.path)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
  try:
   deadline=time.monotonic()+4
   while True:
    try:
     req=urllib.request.Request(f'http://127.0.0.1:{port}/auth/begin',headers={'Host':'bot.143.lat'})
     with urllib.request.urlopen(req,timeout=1) as response:
      data=json.loads(response.read());cookie=response.headers['Set-Cookie'];break
    except OSError:
     if time.monotonic()>deadline:raise
     time.sleep(.02)
   self.assertEqual(data['otp_digits'],4);self.assertFalse(data['whatsapp_ready']);self.assertEqual(data['google_client_id'],'');self.assertIn('HttpOnly',cookie);self.assertIn('Secure',cookie)
  finally:proc.terminate();proc.communicate(timeout=3)
 def test_config_and_key_writable_or_symlink_ancestor_refused(self):
  self.write();self.root.chmod(0o777)
  with self.assertRaises(ValueError):load(self.path)
  self.root.chmod(0o700);unsafe=self.root/'unsafe';unsafe.mkdir(mode=0o777);unsafe.chmod(0o777);key=unsafe/'auth.key';key.write_bytes(b'x'*32);key.chmod(0o600);self.data['auth_key_file']=str(key);self.write()
  with self.assertRaises(ValueError):load(self.path)
  link=self.root/'alias';link.symlink_to(unsafe,target_is_directory=True);unsafe.chmod(0o700);self.data['auth_key_file']=str(link/'auth.key');self.write()
  with self.assertRaises(ValueError):load(self.path)
 def test_nonregular_and_oversize_secret_refused(self):
  from labs_meet.saas_runtime import private_bytes
  fifo=self.root/'fifo';os.mkfifo(fifo,0o600)
  with self.assertRaises(ValueError):private_bytes(fifo)
  self.key.write_bytes(b'x'*129)
  with self.assertRaises(ValueError):private_bytes(self.key,128)

 def test_enabled_otp_requires_explicit_single_owner_recipient(self):
  for allowed in [None,[],['+12025550101','+12025550102'],['bad'],[True]]:
   self.data['otp']={'enabled':True,'allowed_numbers':allowed};self.write()
   with self.assertRaisesRegex(ValueError,'owner-test recipient'):load(self.path)

 def test_enabled_owner_otp_requires_test_authorization_identity(self):
  for identity in [None,'','short',True,'x'*97]:
   self.data['otp']={'enabled':True,'allowed_numbers':['+12025550101'],'test_id':identity};self.write()
   with self.assertRaisesRegex(ValueError,'test authorization identity'):load(self.path)
