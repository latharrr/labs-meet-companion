import tempfile,unittest,threading,concurrent.futures
from pathlib import Path
from labs_meet.otp_broker import BoundedOtpBroker,OtpUnavailable

class Broker(unittest.TestCase):
 def setUp(self):self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'otp.db';self.now=[1794578400];self.calls=[];self.count=[12]
 def tearDown(self):self.temp.cleanup()
 def make(self,**kwargs):
  settings={'base':'http://127.0.0.1:2785','api_key':'synthetic-key','session':'approved','health':lambda:{'session':'approved','ready':True,'as_of':self.now[0]},'aggregate':lambda:{'count':self.count[0],'utc_day':int(self.now[0]//86400)*86400,'as_of':self.now[0]},'clock':lambda:self.now[0],'api':self.api,'enabled':True,'allowed_numbers':['+12025550101']};settings.update(kwargs)
  return BoundedOtpBroker(self.path,b'synthetic-test-key-32bytes-long!!',**settings)
 def api(self,base,path,key,method='GET',body=None):
  self.calls.append((path,method,body))
  if method=='GET':return {'number':path.rsplit('/',1)[1],'exists':True,'whatsappId':'12025550101@c.us'}
  return {'messageId':'synthetic-id'}
 def test_owner_scope_default_deny_no_observation_or_reservation(self):
  observed=[]
  b=self.make(allowed_numbers=(),health=lambda:observed.append('health'),aggregate=lambda:observed.append('count'))
  with self.assertRaises(OtpUnavailable):b('+12025550101','1234',180)
  with self.assertRaises(OtpUnavailable):b.reserve('+12025550101')
  self.assertEqual(observed,[]);self.assertEqual(self.calls,[])
  self.assertEqual(b.db.execute('SELECT count(*) FROM attempts').fetchone()[0],0);b.db.close()
 def test_owner_scope_other_number_denied_before_any_effect(self):
  observed=[];b=self.make(health=lambda:observed.append('health'))
  with self.assertRaises(OtpUnavailable):b('+12025550102','1234',180)
  self.assertEqual(observed,[]);self.assertEqual(self.calls,[])
  self.assertEqual(b.db.execute('SELECT count(*) FROM sender_lock').fetchone()[0],0);b.db.close()
 def test_owner_scope_rejects_multiple_or_malformed_configuration(self):
  for allowed in [None,'+12025550101',['+12025550101','+12025550102'],['12025550101'],[True]]:
   with self.assertRaises(OtpUnavailable):self.make(allowed_numbers=allowed)
 def test_disabled_no_lookup_or_send(self):
  b=self.make(enabled=False)
  with self.assertRaises(OtpUnavailable):b('+12025550101','1234',180)
  self.assertEqual(self.calls,[]);b.db.close()
 def test_resolved_send_once_and_no_plaintext_ledger(self):
  b=self.make();self.assertIs(b('+12025550101','1234',180),True);self.assertEqual(len(self.calls),2);self.assertIn('Do not reply',self.calls[1][2]['text'])
  self.assertNotIn('1234',str([dict(r) for r in b.db.execute('SELECT * FROM attempts')]));self.assertNotIn('+12025550101',str(list(b.db.execute('SELECT * FROM attempts'))));b.db.close()
 def test_headroom_health_day_stale_failclosed(self):
  for field,value in [('aggregate',lambda:{'count':150,'utc_day':int(self.now[0]//86400)*86400,'as_of':self.now[0]}),('health',lambda:{'session':'wrong','ready':True,'as_of':self.now[0]}),('aggregate',lambda:{'count':0,'utc_day':0,'as_of':self.now[0]}),('health',lambda:{'session':'approved','ready':True,'as_of':self.now[0]-16})]:
   b=self.make(**{field:value})
   with self.assertRaises(OtpUnavailable):b('+12025550101','1234',180)
   b.db.close()
  self.assertEqual(self.calls,[])
 def test_perphone_cooldown_and_cap(self):
  b=self.make();b('+12025550101','1234',180)
  with self.assertRaises(OtpUnavailable):b('+12025550101','1234',180)
  for _ in range(2):self.now[0]+=61;b('+12025550101','1234',180)
  self.now[0]+=61
  with self.assertRaises(OtpUnavailable):b('+12025550101','1234',180)
  self.assertEqual(len(self.calls),6);b.db.close()
 def test_globalten_and_fifteen_second_gap(self):
  b=self.make()
  for n in range(10):
   b.allowed_numbers=frozenset(['+120255501'+str(n).zfill(2)]);b('+120255501'+str(n).zfill(2),'1234',180);self.now[0]+=16
  b.allowed_numbers=frozenset(['+12025550199'])
  with self.assertRaises(OtpUnavailable):b('+12025550199','1234',180)
  self.assertEqual(len(self.calls),20);b.db.close()
 def test_unknown_send_holds_lock_across_reopen(self):
  def api(*a,**kw):
   if len(a)>3 and a[3]=='POST':self.calls.append('post');raise TimeoutError()
   return {'number':'12025550101','exists':True,'whatsappId':'12025550101@c.us'}
  b=self.make(api=api)
  with self.assertRaises(OtpUnavailable):b('+12025550101','1234',180)
  b.db.close();self.now[0]+=100;b=self.make(api=api)
  with self.assertRaises(OtpUnavailable):b('+12025550101','1234',180)
  self.assertEqual(self.calls,['post']);b.db.close()
 def test_unknown_lookup_no_guessed_send(self):
  def api(*a,**kw):self.calls.append('lookup');raise RuntimeError('503')
  b=self.make(api=api)
  with self.assertRaises(OtpUnavailable):b('+12025550101','1234',180)
  self.assertEqual(self.calls,['lookup']);self.assertEqual(b.db.execute('SELECT status FROM attempts').fetchone()[0],'not-sent');b.db.close()
 def test_concurrent_only_one_inflight(self):
  b=self.make();b.db.close();barrier=threading.Barrier(2)
  def run(n):
   b=self.make(allowed_numbers=['+1202555010'+str(n)]);barrier.wait()
   try:b.reserve('+1202555010'+str(n));return True
   except OtpUnavailable:return False
   finally:b.db.close()
  with concurrent.futures.ThreadPoolExecutor(2) as pool:self.assertEqual(sum(pool.map(run,[1,2])),1)
 def test_noncanonical_or_nonexistent_refused(self):
  for value in [{'number':'wrong','exists':True,'whatsappId':'123@c.us'},{'number':'12025550101','exists':False,'whatsappId':'123@c.us'},{'number':'12025550101','exists':True,'whatsappId':'arbitrary'}]:
   b=self.make(api=lambda *a,**k:value)
   with self.assertRaises(OtpUnavailable):b('+12025550101','1234',180)
   b.db.close();self.now[0]+=61
 def test_actual_gateway_health_exact_binding_and_failclosed(self):
  from labs_meet.otp_broker import GatewayHealth
  good={'id':'approved','phone':'12025550101','status':'ready','engineLoaded':True,'restriction':None,'lastError':None}
  for field,value in [(None,None),('id','wrong'),('phone','12025550102'),('status','connected'),('engineLoaded',False),('restriction','limited'),('lastError','failed')]:
   result=good if field is None else {**good,field:value};h=GatewayHealth('http://127.0.0.1:2785','synthetic-key','approved','+12025550101',api=lambda *a:result,clock=lambda:self.now[0]);self.assertEqual(h()['ready'],field is None)
 def test_aggregate_strict_validation(self):
  import datetime
  from labs_meet.otp_broker import validate_aggregate
  data={'session_id':'approved','utc_day':datetime.datetime.fromtimestamp(self.now[0],datetime.timezone.utc).strftime('%Y-%m-%d'),'outgoing_count':12,'observed_at_utc':datetime.datetime.fromtimestamp(self.now[0],datetime.timezone.utc).isoformat()}
  read=lambda x:validate_aggregate(x,'approved',self.now[0]);self.assertEqual(read(data)['count'],12)
  for field,value in [('session_id','wrong'),('utc_day','2000-01-01'),('outgoing_count',True),('observed_at_utc','2000-01-01T00:00:00Z'),('error','refused')]:
   with self.assertRaises(OtpUnavailable):read({**data,field:value})
 def test_fifteen_second_gap_applies_between_different_numbers(self):
  b=self.make();b('+12025550101','1234',180);self.now[0]+=14;b.allowed_numbers=frozenset(['+12025550102'])
  with self.assertRaises(OtpUnavailable):b('+12025550102','1234',180)
  self.assertEqual(len(self.calls),2);b.db.close()
 def test_actual_private_socket_success_and_failures(self):
  import socket,threading,json,datetime
  from labs_meet.otp_broker import AggregateSocket
  root=Path(self.temp.name);root.chmod(0o700)
  data={'session_id':'approved','utc_day':datetime.datetime.fromtimestamp(self.now[0],datetime.timezone.utc).strftime('%Y-%m-%d'),'outgoing_count':12,'observed_at_utc':datetime.datetime.fromtimestamp(self.now[0],datetime.timezone.utc).isoformat()}
  for i,payload in enumerate([(json.dumps(data)+'\n').encode(),b'{"error":"observation_unavailable"}\n',b'x'*513,b'{}\n{}\n']):
   path=root/f'count{i}.sock';server=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);server.bind(str(path));root.chmod(0o750);path.chmod(0o660);server.listen(1);received=[]
   def serve():
    conn,_=server.accept()
    with conn:received.append(conn.recv(32));conn.sendall(payload)
   worker=threading.Thread(target=serve);worker.start()
   try:
    from unittest.mock import patch
    with patch('labs_meet.otp_broker.os.geteuid',return_value=path.stat().st_uid+1):
     read=AggregateSocket(path,'approved',collector_uid=path.stat().st_uid,ipc_gid=path.stat().st_gid,clock=lambda:self.now[0])
    if i==0:self.assertEqual(read()['count'],12)
    else:
     with self.assertRaises(OtpUnavailable):read()
   finally:worker.join(2);server.close()
   self.assertEqual(received,[b'COUNT\n'])
 def test_moving_callback_clock_and_rollover(self):
  def health():
   self.now[0]+=.01;return {'session':'approved','ready':True,'as_of':self.now[0]}
  def aggregate():
   self.now[0]+=.01;return {'count':12,'utc_day':int(self.now[0]//86400)*86400,'as_of':self.now[0]}
  b=self.make(health=health,aggregate=aggregate);b.observe();b.db.close()
  self.now[0]=int(self.now[0]//86400)*86400+86399.99
  old=int(self.now[0]//86400)*86400
  def rollover():self.now[0]+=1;return {'count':12,'utc_day':old,'as_of':self.now[0]}
  b=self.make(health=health,aggregate=rollover)
  with self.assertRaises(OtpUnavailable):b.observe()
  b.db.close()
 def test_missing_health_error_fields_failclosed(self):
  from labs_meet.otp_broker import GatewayHealth
  good={'id':'approved','phone':'12025550101','status':'ready','engineLoaded':True,'restriction':None,'lastError':None}
  for field in good:
   result={k:v for k,v in good.items() if k!=field};self.assertFalse(GatewayHealth('http://127.0.0.1:2785','key','approved','+12025550101',api=lambda *a:result)()['ready'])
 def test_ledger_parent_and_file_permissions_failclosed(self):
  import os
  root=Path(self.temp.name)
  root.chmod(0o777)
  with self.assertRaises(OtpUnavailable):self.make()
  root.chmod(0o700);self.path.write_text('');self.path.chmod(0o644)
  with self.assertRaises(OtpUnavailable):self.make()
  self.path.unlink();target=root/'target';target.write_text('unchanged');self.path.symlink_to(target)
  with self.assertRaises(OtpUnavailable):self.make()
  self.assertEqual(target.read_text(),'unchanged')

 def test_single_test_attempt_persists_after_success_and_restart(self):
  b=self.make(test_id='synthetic-approval-0001');b('+12025550101','1234',180);b.db.close();self.now[0]+=86401
  b=self.make(test_id='synthetic-approval-0001')
  with self.assertRaises(OtpUnavailable):b('+12025550101','5678',180)
  self.assertEqual(len(self.calls),2);b.db.close()
 def test_single_test_attempt_lookup_failure_still_consumes(self):
  def fail(*a,**k):self.calls.append('lookup');raise TimeoutError()
  b=self.make(test_id='synthetic-approval-0001',api=fail)
  with self.assertRaises(OtpUnavailable):b('+12025550101','1234',180)
  self.now[0]+=100
  with self.assertRaises(OtpUnavailable):b('+12025550101','5678',180)
  self.assertEqual(self.calls,['lookup']);b.db.close()
 def test_single_test_attempt_atomic_across_instances(self):
  b=self.make(test_id='synthetic-approval-0001');b.db.close();barrier=threading.Barrier(2)
  def run(n):
   b=self.make(test_id='synthetic-approval-0001');barrier.wait()
   try:b.reserve('+12025550101');return True
   except OtpUnavailable:return False
   finally:b.db.close()
  with concurrent.futures.ThreadPoolExecutor(2) as pool:self.assertEqual(sum(pool.map(run,[1,2])),1)
