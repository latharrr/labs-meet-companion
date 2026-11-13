import importlib.util
from pathlib import Path
import unittest

ROOT=Path(__file__).parent.parent

def load(name,file):
    spec=importlib.util.spec_from_file_location(name,ROOT/'deploy'/file)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

class DerivativeTests(unittest.TestCase):
    def test_environment_requires_separate_secrets(self):
        m=load('meeting_entry','meeting-entrypoint.py')
        with self.assertRaises(ValueError):m.environment({})
        source={k:'a'*40 for k in m.REQUIRED}
        source.update({'ANTHROPIC_API_KEY':'never-inherit','LABS_RESEND_KEY':'never-inherit','HOST_CLAUDE_CREDENTIALS':'/host/private','BOT_COMMAND':'/host/evil','VEXA_LITE_STATE_DIR':'/host/private','PATH':'/bad'})
        env=m.environment(source)
        self.assertNotIn('never-inherit',str(env))
        self.assertNotIn('/host/',str(env))
        self.assertEqual(env['AGENT_WORKER_COMMAND'],'/usr/bin/false')
        self.assertEqual(env['MCP_URL'],'')
        self.assertEqual(env['BOT_COMMAND'],'/usr/local/bin/vexa-bot-launch')
        self.assertEqual(env['RUNTIME_BACKEND'],'process')

    def test_weak_or_interpolated_secret_refused(self):
        m=load('meeting_entry','meeting-entrypoint.py')
        for bad in ('secret','a'*31,'a'*32+'%','a'*32+'"','a'*32+'\n'):
            source={k:'a'*40 for k in m.REQUIRED};source['DB_PASSWORD']=bad
            with self.assertRaises(ValueError):m.environment(source)

    def test_supervisor_reduces_exact_programs(self):
        m=load('meeting_prepare','prepare-meeting-only.py')
        # Minimal shape of pinned supervisor, no external source needed in CI.
        text='[supervisord]\nnodaemon=true\n[group:vexa]\nprograms=redis,admin-api,runtime,agent-api,meeting-api,gateway,mcp,terminal\n'
        for name in ('redis','admin-api','runtime','meeting-api','gateway','agent-api','model-proxy','mcp','terminal'):
            text+='[program:'+name+']\ncommand=test\nenvironment=AGENT_WORKER_COMMAND="%(ENV_AGENT_WORKER_COMMAND)s",HOST_CLAUDE_CREDENTIALS="%(ENV_HOST_CLAUDE_CREDENTIALS)s",AGENT_API_URL="http://localhost:8100",MCP_URL="http://localhost:8010"\n'
        config=m.supervisor(text)
        self.assertEqual({s[8:] for s in config.sections() if s.startswith('program:')},m.KEEP)
        self.assertEqual(set(config['group:vexa']['programs'].replace(' ','').split(',')),m.KEEP)
        self.assertIn('/usr/bin/false',config['program:runtime']['environment'])
        self.assertIn('meeting-gateway.py',config['program:gateway']['command'])

    def test_supervisor_interpolation_characters_refused(self):
        m=load('meeting_entry','meeting-entrypoint.py')
        for bad in ('Injected"value','escape\\test','Percent%value','line\nvalue'):
            source={k:'a'*40 for k in m.REQUIRED};source['DEFAULT_BOT_NAME']=bad
            with self.assertRaises(ValueError):m.environment(source)

class OciStreamTests(unittest.TestCase):
    def fixture(self,mutate=None):
        import hashlib,io,json,tarfile
        blobs={}
        def blob(value,media):
            data=json.dumps(value).encode();digest=hashlib.sha256(data).hexdigest();blobs['blobs/sha256/'+digest]=data
            return {'digest':'sha256:'+digest,'size':len(data),'mediaType':media}
        config=blob({'os':'linux','architecture':'arm64','rootfs':{'diff_ids':['sha256:test-diff']}},'application/vnd.oci.image.config.v1+json')
        manifest=blob({'schemaVersion':2,'config':config,'layers':[]},'application/vnd.oci.image.manifest.v1+json')
        blobs['index.json']=json.dumps({'schemaVersion':2,'manifests':[manifest]}).encode()
        blobs['oci-layout']=b'{"imageLayoutVersion":"1.0.0"}'
        if mutate:mutate(blobs)
        stream=io.BytesIO()
        with tarfile.open(fileobj=stream,mode='w') as tar:
            for name,data in blobs.items():
                item=tarfile.TarInfo(name);item.size=len(data);tar.addfile(item,io.BytesIO(data))
        stream.seek(0)
        return stream,{'Id':manifest['digest'],'RootFS':{'Layers':['sha256:test-diff']}}

    def run_sink(self,stream,info):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            return load('oci_stream','validate-oci-stream.py').receive(stream,Path(directory)/'layout',info)

    def test_valid_exact_oci_stream(self):
        result=self.run_sink(*self.fixture())
        self.assertTrue(result['validated']);self.assertEqual(result['architecture'],'arm64')

    def test_changed_blob_refused(self):
        def corrupt(blobs):
            key=next(k for k in blobs if k.startswith('blobs/'));blobs[key]+=b'changed'
        with self.assertRaisesRegex(ValueError,'digest mismatch'):self.run_sink(*self.fixture(corrupt))

    def test_path_escape_refused(self):
        with self.assertRaisesRegex(ValueError,'shape'):self.run_sink(*self.fixture(lambda b:b.update({'../escape':b'no'})))

    def test_wrong_inspect_refused(self):
        stream,info=self.fixture();info['Id']='sha256:'+'0'*64
        with self.assertRaisesRegex(ValueError,'Manifest digest'):self.run_sink(stream,info)

    def test_wrong_rootfs_refused(self):
        stream,info=self.fixture();info['RootFS']['Layers']=['other']
        with self.assertRaisesRegex(ValueError,'rootfs'):self.run_sink(stream,info)

class BootstrapTests(unittest.TestCase):
    def test_explicit_quota_and_narrow_key(self):
        import tempfile
        module=load('owner_bootstrap','bootstrap-owner.py');calls=[]
        user={'id':1,'email':'owner@example.invalid','max_concurrent_bots':1}
        def api(path,admin,method='GET',body=None):
            calls.append((path,method,body))
            if '/email/' in path:return None
            if path.endswith('/tokens'):
                return [] if method=='GET' else {'id':2,'user_id':1,'token':'synthetic-only-key','scopes':['bot','tx']}
            return user
        with tempfile.TemporaryDirectory() as directory:
            result=module.bootstrap(user['email'],Path(directory)/'key','synthetic-only-admin',api)
            self.assertTrue(result['key_saved']);self.assertNotIn('synthetic',str(result))
            self.assertEqual((Path(directory)/'key').stat().st_mode & 0o777,0o600)
        create=[body for path,method,body in calls if path=='/admin/users' and method=='POST'][0]
        self.assertEqual(create['max_concurrent_bots'],1)

    def test_existing_wrong_quota_never_mints(self):
        import tempfile
        module=load('owner_bootstrap','bootstrap-owner.py');calls=[]
        def api(path,admin,method='GET',body=None):
            calls.append(method);return {'id':1,'email':'owner@example.invalid','max_concurrent_bots':3}
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError,'cap'):module.bootstrap('owner@example.invalid',Path(directory)/'key','test',api)
        self.assertEqual(calls,['GET'])

    def test_uncertain_mint_leaves_reconciliation_guard(self):
        import tempfile
        module=load('owner_bootstrap','bootstrap-owner.py')
        def api(path,admin,method='GET',body=None):
            if path.endswith('/tokens'):
                if method=='POST':raise TimeoutError('uncertain')
                return []
            return {'id':1,'email':'owner@example.invalid','max_concurrent_bots':1}
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)/'key'
            with self.assertRaises(TimeoutError):module.bootstrap('owner@example.invalid',output,'test',api)
            self.assertTrue(output.exists());self.assertEqual(output.read_bytes(),b'')
