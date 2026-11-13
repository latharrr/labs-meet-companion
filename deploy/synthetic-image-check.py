#!/usr/bin/env python3
"""Planned isolated image smoke payload. Not approval to start a container.
No provider/DB/Redis/HTTP call. Uses synthetic-only environment/keyfiles, validates
real image service imports, reduced gateway routes and cleared runtime env.
Run with networking NONE in disposable reviewed image, tini PID1 and scoped limits.
"""
import json,os,subprocess,sys,tempfile
from pathlib import Path


def run(python,code,env):
    result=subprocess.run([python,'-c',code],env=env,capture_output=True,text=True,timeout=20)
    if result.returncode:raise RuntimeError('Synthetic service check failed: '+python+' exit'+str(result.returncode))
    return result.stdout.strip()


def main():
    assert sys.platform=='linux'
    assert Path('/usr/bin/tini').exists()
    for absent in ('/var/run/docker.sock','/app/agent','/app/terminal','/app/mcp'):
        assert not Path(absent).exists(),absent
    conf=Path('/etc/supervisor/conf.d/vexa.conf').read_text()
    import configparser
    config=configparser.ConfigParser(interpolation=None);config.read_string(conf)
    expected={'redis','admin-api','runtime','meeting-api','gateway'}
    assert {s[8:] for s in config.sections() if s.startswith('program:')}==expected
    assert set(config['group:vexa']['programs'].replace(' ','').split(','))==expected
    base={'PATH':'/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin','HOME':'/tmp','INTERNAL_API_SECRET':'synthetic-only-internal-'+40*'x','GUARD_ENABLED':'false','MCP_URL':'','AGENT_API_URL':''}
    results={}
    for name,source,module in [('admin','admin-api','admin_api.app.main'),('meeting','meeting-api','meeting_api'),('runtime','runtime','runtime_kernel')]:
        env={**base,'PYTHONPATH':'/app/'+source+'/src'}
        code='import '+module+'; print("import-pass")'
        results[name]=run('/opt/venvs/'+name+'/bin/python',code,env)
    with tempfile.TemporaryDirectory(prefix='labs-synthetic-key-') as directory:
        private=str(Path(directory)/'private.pem');public=str(Path(directory)/'public.pem')
        results['synthetic-key']=subprocess.run(['/opt/venvs/gateway/bin/python','/app/gateway/src/gateway/identity_token.py','keygen',private,public],env=base,capture_output=True,timeout=20).returncode==0
        assert results['synthetic-key']
        env={**base,'PYTHONPATH':'/app/gateway/src','VEXA_GATEWAY_IDENTITY_SIGNING_KEY_FILE':private}
        results['gateway']=run('/opt/venvs/gateway/bin/python', '''import importlib.util
s=importlib.util.spec_from_file_location('w','/usr/local/bin/meeting-gateway.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
a=m.make_app();assert len(a.routes)==7;assert {r.path for r in a.routes}==set(m.ALLOWED)
print('7-route-assembly-pass')''',env)
    results['runtime-env']=run('/opt/venvs/runtime/bin/python', '''import importlib.machinery,importlib.util
loader=importlib.machinery.SourceFileLoader('launcher','/usr/local/bin/vexa-runtime');s=importlib.util.spec_from_loader('launcher',loader);m=importlib.util.module_from_spec(s);loader.exec_module(m)
e=m.runtime_environment({'DB_PASSWORD':'DO-NOT-INHERIT','ADMIN_API_TOKEN':'DO-NOT-INHERIT','LABS_RESEND_KEY':'DO-NOT-INHERIT','ANTHROPIC_API_KEY':'DO-NOT-INHERIT','PATH':'/usr/bin','PYTHONPATH':'/app/runtime/src','RUNTIME_BACKEND':'process'},'/app/runtime/src')
assert 'DO-NOT-INHERIT' not in str(e);assert e['RUNTIME_BACKEND']=='process'
print('runtime-env-cleared-pass')''',{**base,'PYTHONPATH':'/app/runtime/src'})
    print(json.dumps({'scope':'synthetic-image-imports-only','real_meet':False,'provider_calls':False,'results':results}))


if __name__=='__main__':
    try:main()
    except Exception as error:
        print('Synthetic image check failed: '+type(error).__name__,file=sys.stderr);sys.exit(1)
