import tempfile,unittest,threading,concurrent.futures
from pathlib import Path
from labs_meet.workspaces import Registry,ScopedVexa,WorkspaceError

class Guards(unittest.TestCase):
 def setUp(self):self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'global.db';self.a='a'*32;self.b='b'*32;self.r=Registry(self.path,b'k'*32,capacity=1)
 def tearDown(self):self.r.db.close();self.temp.cleanup()
 def prep(self,tenant,code,key):self.r.bind_credential(tenant,key);self.r.claim(tenant,code)
 def test_same_code_cross_account_denied(self):
  self.r.claim(self.a,'abc-defg-hij')
  with self.assertRaises(WorkspaceError):self.r.claim(self.b,'abc-defg-hij')
 def test_reused_upstream_key_denied(self):
  self.r.bind_credential(self.a,'a-secret-key-000000')
  with self.assertRaises(WorkspaceError):self.r.bind_credential(self.b,'a-secret-key-000000')
 def test_no_capacity_no_send(self):
  r=Registry(self.path,b'k'*32)
  with self.assertRaises(WorkspaceError):r.reserve(self.a,'abc-defg-hij','x'*32)
  r.db.close()
 def test_global_active_limit_and_uncertain_no_retry(self):
  self.prep(self.a,'abc-defg-hij','a-secret-key-000000');self.prep(self.b,'klm-nopq-rst','b-secret-key-000000');self.r.reserve(self.a,'abc-defg-hij','x'*32)
  for tenant,code,attempt in [(self.b,'klm-nopq-rst','y'*32),(self.a,'abc-defg-hij','x'*32)]:
   with self.assertRaises(WorkspaceError):self.r.reserve(tenant,code,attempt)
  self.r.close_checked('x'*32,'Operator verified bot stopped');self.r.reserve(self.b,'klm-nopq-rst','y'*32)
 def test_daily_budget_retained_after_checked_close(self):
  self.r.tenant_daily=1;self.prep(self.a,'abc-defg-hij','a-secret-key-000000');self.r.reserve(self.a,'abc-defg-hij','x'*32);self.r.close_checked('x'*32,'Verified stopped')
  with self.assertRaises(WorkspaceError):self.r.reserve(self.a,'abc-defg-hij','y'*32)
 def test_concurrent_global_reserve_only_one(self):
  self.prep(self.a,'abc-defg-hij','a-secret-key-000000');self.prep(self.b,'klm-nopq-rst','b-secret-key-000000');barrier=threading.Barrier(2)
  def run(data):
   r=Registry(self.path,b'k'*32,capacity=1);barrier.wait()
   try:r.reserve(*data);return True
   except WorkspaceError:return False
   finally:r.db.close()
  with concurrent.futures.ThreadPoolExecutor(2) as pool:result=list(pool.map(run,[(self.a,'abc-defg-hij','x'*32),(self.b,'klm-nopq-rst','y'*32)]))
  self.assertEqual(sum(result),1)
 def test_scoped_adapter_checks_every_resource_before_transport(self):
  calls=[]
  class Fake:
   def __init__(self,*args):pass
   def transcript(self,code):calls.append(code);return {}
   def perform(self,*args):calls.append(args);return {}
   def chat_status(self,*args):calls.append(args);return {}
  self.prep(self.a,'abc-defg-hij','a-secret-key-000000');v=ScopedVexa(self.r,self.b,'https://unused.invalid','b-secret-key-000000',upstream_user_id=2,upstream_isolation_verified=True,transport=Fake)
  for func in [lambda:v.transcript('abc-defg-hij'),lambda:v.perform('leave',{'code':'abc-defg-hij'}),lambda:v.chat_status('abc-defg-hij','id')]:
   with self.assertRaises(WorkspaceError):func()
  self.assertEqual(calls,[])
 def test_unverified_upstream_refused(self):
  with self.assertRaises(WorkspaceError):ScopedVexa(self.r,self.a,'https://unused.invalid','a-secret-key-000000')
 def test_two_tokens_same_upstream_owner_refused(self):
  ScopedVexa(self.r,self.a,'https://unused.invalid','a-secret-key-000000',upstream_user_id=1,upstream_isolation_verified=True)
  with self.assertRaises(WorkspaceError):ScopedVexa(self.r,self.b,'https://unused.invalid','b-secret-key-000000',upstream_user_id=1,upstream_isolation_verified=True)
 def test_exact_row_transcript_and_missing_join_id_no_retry(self):
  calls=[]
  class Fake:
   def __init__(self,*args):pass
   def transcript_by_id(self,row):calls.append(('row',row));return {'segments':[]}
   def perform(self,kind,payload):calls.append((kind,payload));return {'id':42}
  self.r.claim(self.a,'abc-defg-hij');v=ScopedVexa(self.r,self.a,'https://unused.invalid','a-secret-key-000000',upstream_user_id=1,upstream_isolation_verified=True,transport=Fake)
  with self.assertRaises(WorkspaceError):v.transcript('abc-defg-hij')
  v.attempt='x'*32;v.perform('join',{'code':'abc-defg-hij'});v.transcript('abc-defg-hij');self.assertEqual(calls[-1],('row',42))
  with self.assertRaises(WorkspaceError):v.perform('join',{'code':'abc-defg-hij'})
 def test_join_unknown_response_keeps_slot(self):
  class Fake:
   def __init__(self,*args):pass
   def perform(self,*args):return {'status':'unknown'}
  self.r.claim(self.a,'abc-defg-hij');v=ScopedVexa(self.r,self.a,'https://unused.invalid','a-secret-key-000000',upstream_user_id=1,upstream_isolation_verified=True,transport=Fake);v.attempt='x'*32
  with self.assertRaises(WorkspaceError):v.perform('join',{'code':'abc-defg-hij'})
  self.assertEqual(self.r.db.execute('SELECT active FROM joins').fetchone()[0],1)
 def test_wrapper_contains_exact_row_route_not_shares(self):
  import ast
  tree=ast.parse((Path(__file__).parents[1]/'deploy/meeting-gateway.py').read_text())
  allowed=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='ALLOWED' for t in n.targets))
  self.assertEqual(allowed['/transcripts/by-id/{meeting_id}'],{'GET'});self.assertEqual(len(allowed),8);self.assertFalse(any('share' in p for p in allowed))
 def test_private_join_explicit_no_sharedworkspace_no_recording(self):
  from labs_meet.workspaces import PrivateVexa
  from unittest.mock import patch
  with patch('labs_meet.workspaces.request',return_value={'id':42}) as send:
   v=PrivateVexa('https://unused.invalid','synthetic-secret');v.perform('join',{'code':'abc-defg-hij'})
   body=send.call_args.args[4];self.assertEqual(body['workspace_id'],'personal');self.assertIs(body['recording_enabled'],False);self.assertIs(body['transcribe_enabled'],True)
