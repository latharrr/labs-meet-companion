#!/usr/bin/env python3
"""Prepare a meeting-only supervisor/config review tree from an exact Vexa checkout.
Does not build, run, install, provision secrets or modify the upstream checkout.
Output is a review artifact, not a deployment-ready stack.
"""
import configparser
import shutil
from pathlib import Path
import re
import subprocess
import sys

PIN='6b26f7b921756d6db128d42cd70b4b7046381407'
KEEP={'redis','admin-api','runtime','meeting-api','gateway'}


def supervisor(text):
    config=configparser.ConfigParser(interpolation=None,strict=True)
    config.read_string(text)
    for section in list(config.sections()):
        if section.startswith('program:') and section[8:] not in KEEP:
            config.remove_section(section)
    for section in config.sections():
        if section.startswith('group:'):
            config[section]['programs']=', '.join(sorted(KEEP))
    config['program:runtime']['environment']=config['program:runtime']['environment'].replace('AGENT_WORKER_COMMAND="%(ENV_AGENT_WORKER_COMMAND)s"','AGENT_WORKER_COMMAND="/usr/bin/false"').replace('HOST_CLAUDE_CREDENTIALS="%(ENV_HOST_CLAUDE_CREDENTIALS)s"','HOST_CLAUDE_CREDENTIALS=""')
    config['program:gateway']['command']='/usr/local/bin/no-user-namespaces /opt/venvs/gateway/bin/python /usr/local/bin/meeting-gateway.py'
    config['program:gateway']['environment']=config['program:gateway']['environment'].replace('AGENT_API_URL="http://localhost:8100"','AGENT_API_URL=""').replace('MCP_URL="http://localhost:8010"','MCP_URL=""')
    return config


def main():
    root=Path(sys.argv[1]).resolve();dest=Path(sys.argv[2]).resolve()
    sha=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()
    if sha!=PIN:raise ValueError('Exact audited source required')
    if dest.exists():raise ValueError('Output directory must be new')
    config=supervisor((root/'deploy/lite/supervisord.conf').read_text())
    dest.mkdir(mode=0o700,parents=True)
    with (dest/'supervisord.meetings.conf').open('w') as f:config.write(f)
    env='\n'.join(v for section in config.sections() for v in config[section].values())
    names=sorted(set(re.findall(r'%\(ENV_([A-Z0-9_]+)\)s',env)))
    (dest/'required-environment.txt').write_text('\n'.join(names)+'\n')
    for file in ('meeting-entrypoint.py','meeting-gateway.py'):
        shutil.copy2(Path(__file__).parent/file,dest/file)
    paths={'admin':'core/identity/services/admin-api','runtime':'core/runtime','meeting':'core/meetings/services/meeting-api','gateway':'core/gateway/services/gateway'}
    for name,relative in paths.items():
        source=root/relative;target=dest/name;target.mkdir()
        for file in ('pyproject.toml','uv.lock'):shutil.copy2(source/file,target/file)
        shutil.copytree(source/'src',target/'src',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    shutil.copytree(root/'core/meetings/contracts',dest/'meeting/contracts')
    shutil.copytree(root/'core/runtime/contracts',dest/'runtime/contracts')
    for file in ('routes.v1.json','mcp.tools.v1.json'):shutil.copy2(root/'core/meetings'/file,dest/'meeting'/file)
    # Gateway currently requires MCP manifest even with no MCP service. Wrapper removes its routes.
    for file in ('core/gateway/services/gateway/routes.v1.json','core/meetings/routes.v1.json','core/identity/routes.v1.json','core/gateway/services/mcp/routes.v1.json'):
        target=dest/'gateway/manifests'/file.removeprefix('core/');target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(root/file,target)
    (dest/'bin').mkdir()
    for file in ('vexa-bot-launch','vexa-runtime','bot-display','no-user-namespaces'):shutil.copy2(root/'deploy/lite/bin'/file,dest/'bin'/file)
    for file in ('LICENSE','NOTICE'):
        if (root/file).is_file():shutil.copy2(root/file,dest/file)
    lite=(root/'deploy/lite/Dockerfile.lite').read_text()
    # Preserve the pinned/checksummed Valkey builder, never copy stock agent/terminal stages.
    start=lite.index('FROM mcr.microsoft.com/playwright:',lite.index('# Stage 2c:'))
    end=lite.index('# Stage 3:',start)
    stage=lite[start:end].replace(' AS valkey-builder',' AS valkey').replace('-j"$(nproc)"','-j1')
    template=(Path(__file__).parent/'Dockerfile.meetings.template').read_text()
    template=template.replace('FROM bot AS meetings',stage+'\nFROM bot AS meetings')
    uv_start=lite.index('ARG UV_VERSION=')
    uv_end=lite.index('ENV UV_LINK_MODE=',uv_start)
    template=template.replace('@UV_INSTALL@',lite[uv_start:uv_end])
    (dest/'Dockerfile').write_text(template)
    (dest/'.dockerignore').write_text('__pycache__/\n*.pyc\n*.env\n.git/\n')

    (dest/'REVIEW-NOT-READY.md').write_text('Meeting-only supervisor generated from pinned Vexa. No agent/terminal/model-proxy/MCP programs. This is not a bootable/deployable image. Dockerfile/entrypoint/context generated but NOT BUILT. Remaining: native build audit, internal key provisioning, PostgreSQL/storage init, one-bot quota, no-provider real-contract tests. Do not execute stock Lite entrypoint or make target.\n')
    print(dest)

if __name__=='__main__':main()
