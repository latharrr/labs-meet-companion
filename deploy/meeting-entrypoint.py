#!/usr/bin/env python3
"""Meeting-only entrypoint. Reads deployment secrets; never mints/prints keys.
Not validated in a built image yet. No host mounts or account auto-discovery.
"""
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import quote

FORBIDDEN = ('ANTHROPIC_', 'CLAUDE_', 'HOST_CLAUDE', 'VEXA_MODEL_SECRET_', 'LABS_RESEND_', 'LABS_OPENWA_', 'LABS_AI_')
REQUIRED = ('DB_HOST','DB_PORT','DB_NAME','DB_USER','DB_PASSWORD','REDIS_PASSWORD','ADMIN_API_TOKEN','INTERNAL_API_SECRET','RUNTIME_API_TOKEN','VEXA_TERMINAL_SESSION_SECRET')


def environment(source):
    env={k:v for k,v in source.items() if not any(k.startswith(prefix) for prefix in FORBIDDEN)}
    for key in REQUIRED:
        if not env.get(key): raise ValueError('Required deployment field missing: '+key)
    for key in ('DB_PASSWORD','REDIS_PASSWORD','ADMIN_API_TOKEN','INTERNAL_API_SECRET','RUNTIME_API_TOKEN','VEXA_TERMINAL_SESSION_SECRET'):
        if len(env[key])<32 or not re.fullmatch(r'[A-Za-z0-9_-]+',env[key]):raise ValueError('Use separately provisioned URL-safe random deployment secret for '+key)
    # No extra env-file inherited by child programs. Only explicit declared fields.
    defaults={'LOG_LEVEL':'info','DEFAULT_BOT_NAME':'Lathar Labs | Notes','DEFAULT_TRANSCRIPTION_LANGUAGE':'','DEFAULT_TRANSCRIPTION_ALLOWED_LANGUAGES':'','TRANSCRIPTION_SERVICE_URL':'','TRANSCRIPTION_SERVICE_TOKEN':'','TRANSCRIPTION_MODEL':'whisper-large-v3-turbo','MINIO_ENDPOINT':'','MINIO_ACCESS_KEY':'','MINIO_SECRET_KEY':'','MINIO_BUCKET':'labs-meet','MINIO_SECURE':'false','GUARD_ENABLED':'true','GUARD_WS_ENABLED':'false','VEXA_LITE_STATE_DIR':'/var/lib/vexa/state','BOT_COMMAND':'/usr/local/bin/vexa-bot-launch'}
    defaults.update({k:env[k] for k in defaults if k in env})
    defaults.update({k:env[k] for k in REQUIRED})
    defaults.update({'PATH':'/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin','HOME':'/root','LANG':'C.UTF-8','PYTHONUNBUFFERED':'1','PLAYWRIGHT_BROWSERS_PATH':'/ms-playwright','RUNTIME_BACKEND':'process','AGENT_WORKER_COMMAND':'/usr/bin/false','HOST_CLAUDE_CREDENTIALS':'','AGENT_API_URL':'','MCP_URL':'','VEXA_LLM_KILL_SWITCH':'1','REDIS_URL':'redis://:'+quote(env['REDIS_PASSWORD'],safe='')+'@127.0.0.1:6379/0'})
    # Do not allow operator configuration to redirect the launcher or key directory.
    defaults['BOT_COMMAND']='/usr/local/bin/vexa-bot-launch'
    defaults['VEXA_LITE_STATE_DIR']='/var/lib/vexa/state'
    for name,value in defaults.items():
        if any(c in value for c in ('\n','\r','\x00','%','"','\\')):
            raise ValueError('Unsupported deployment field characters: '+name)
    return defaults


def main():
    env=environment(os.environ)
    token=env.pop('RUNTIME_API_TOKEN')
    for name,mode in [('/run/vexa',0o700),('/var/log/supervisor',0o700),('/var/lib/redis',0o700),('/var/lib/vexa/state/identity',0o700),('/var/lib/vexa-runtime/logs',0o700),('/tmp/.X11-unix',0o1777)]:
        Path(name).mkdir(parents=True,exist_ok=True,mode=mode);os.chmod(name,mode)
    subprocess.run(['/opt/venvs/gateway/bin/python','/app/gateway/src/gateway/identity_token.py','keygen','/var/lib/vexa/state/identity/signing-key.pem','/var/lib/vexa/state/identity/public-key.pem'],env=env,check=True)
    # Bounded DB readiness. Never start services against an unready DB.
    import time
    for attempt in range(30):
        check=subprocess.run(['pg_isready','-q','-h',env['DB_HOST'],'-p',env['DB_PORT'],'-U',env['DB_USER']],env=env)
        if check.returncode==0:break
        if attempt==29:raise RuntimeError('PostgreSQL not ready')
        time.sleep(2)
    from_config=Path('/etc/supervisor/conf.d/vexa.conf').read_text()
    if '@RUNTIME_API_TOKEN@' not in from_config:raise RuntimeError('Supervisor runtime token placeholder missing')
    config_pattern=re.compile(r'%\(ENV_([A-Z0-9_]+)\)s')
    if any(name not in env for name in config_pattern.findall(from_config)):raise RuntimeError('Supervisor required environment missing')
    rendered=from_config.replace('@RUNTIME_API_TOKEN@',token)
    config=Path('/run/vexa/supervisord.conf');config.write_text(rendered);os.chmod(config,0o600)
    valkey=Path('/run/vexa/valkey.conf');valkey.write_text('requirepass "'+env.pop('REDIS_PASSWORD')+'"\n');os.chmod(valkey,0o600)
    # Auth/bootstrap is an explicit host-local operation after startup; no printed
    # self-host key or sign-in link, no mail, no agent session DB/bucket provisioning.
    os.execve('/usr/bin/supervisord',['supervisord','-n','-c',str(config)],env)


if __name__=='__main__':
    try:main()
    except (ValueError,RuntimeError,OSError,subprocess.CalledProcessError):
        print('Meeting-only startup refused. Check private deployment configuration.',file=sys.stderr);sys.exit(1)
