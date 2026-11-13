"""Isolated SaaS startup; requires explicit private operator configuration.

Never discovers legacy credentials or starts the meeting engine. Check mode is
local validation only, not external/provider acceptance or deployment permission.
"""
import argparse
import json
import re
import os
from pathlib import Path
import stat
from .saas_web import SaaSConfig,serve
from .otp_broker import BoundedOtpBroker,GatewayHealth,AggregateSocket
from .provisioning import CredentialFiles

def private_bytes(path,limit=16384):
    p=Path(path).absolute()
    # Config and secrets must not be replaceable through an ancestor, even if
    # their leaf inode looks private. Trusted sticky temp is only for tests or
    # explicit app-owned temporary parents, not the deployment path proposal.
    for ancestor in (p.parent,*p.parent.parents):
        if ancestor.is_symlink():raise ValueError('Private configuration ancestor refused')
        info=ancestor.stat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid not in (0,os.geteuid()):raise ValueError('Trusted configuration ancestor required')
        if info.st_mode&0o022 and not (info.st_uid in (0,os.geteuid()) and info.st_mode&stat.S_ISVTX):raise ValueError('Writable configuration ancestor refused')
    try:fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    except OSError:raise ValueError('Private configuration open refused') from None
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.geteuid() or stat.S_IMODE(info.st_mode)!=0o600 or info.st_size>limit:raise ValueError('Private owner-only configuration required')
        content=b''
        while len(content)<=limit:
            block=os.read(fd,limit+1-len(content))
            if not block:break
            content+=block
        if len(content)>limit:raise ValueError('Private configuration too large')
        return content
    finally:os.close(fd)

def load(path):
    data=json.loads(private_bytes(path))
    if not isinstance(data,dict):raise ValueError('Configuration object required')
    allowed={'root','origin','auth_key_file','google_client_id','port','trusted_proxy_ips','operations_enabled','upstream_isolation_verified','vexa_base','credential_root','daily_joins','tenant_daily','capacity','otp'}
    if set(data)-allowed:raise ValueError('Unknown configuration fields')
    if data.get('origin')!='https://bot.143.lat':raise ValueError('Expected exact deployment origin')
    root=Path(data['root']).absolute()
    for ancestor in (root,*root.parents):
        if ancestor.is_symlink():raise ValueError('Private state path refused')
        if ancestor.exists():
            info=ancestor.stat()
            if not stat.S_ISDIR(info.st_mode) or (info.st_mode&0o022 and not (info.st_uid in (0,os.geteuid()) and info.st_mode&stat.S_ISVTX)):raise ValueError('Untrusted state ancestor')
    if root.exists() and (root.stat().st_uid!=os.geteuid() or stat.S_IMODE(root.stat().st_mode)!=0o700):raise ValueError('Private app state directory required')
    for field in ('daily_joins','tenant_daily'):
        if field in data and (type(data[field]) is not int or not 1<=data[field]<=20):raise ValueError('Bounded join allocation required')
    key=private_bytes(data['auth_key_file'],128)
    if len(key)!=32:raise ValueError('Dedicated raw 32-byte auth key required')
    for field in ('operations_enabled','upstream_isolation_verified'):
        if field in data and type(data[field]) is not bool:raise ValueError('Boolean gate required')
    provider=None
    if data.get('operations_enabled'):
        if data.get('upstream_isolation_verified') is not True:raise ValueError('Upstream isolation acceptance required')
        if type(data.get('capacity')) is not int or data['capacity']!=1:raise ValueError('Accepted initial global capacity of one required')
        provider=CredentialFiles(data['credential_root'],data['vexa_base'])
    sender=None
    otp=data.get('otp',{})
    if not isinstance(otp,dict):raise ValueError('OTP configuration required')
    otp_allowed={'enabled','base','api_key_file','session_id','sender_phone','ledger_key_file','collector_socket','collector_uid','ipc_gid','allowed_numbers','test_id'}
    if set(otp)-otp_allowed or type(otp.get('enabled',False)) is not bool:raise ValueError('Explicit OTP gate required')
    if otp.get('enabled'):
        allowed=otp.get('allowed_numbers')
        if not isinstance(allowed,list) or len(allowed)!=1 or not isinstance(allowed[0],str) or not re.fullmatch(r'\+[1-9][0-9]{7,14}',allowed[0]):raise ValueError('One explicit owner-test recipient required')
        test_id=otp.get('test_id')
        if not isinstance(test_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{16,96}',test_id):raise ValueError('Explicit test authorization identity required')
        api_key=private_bytes(otp['api_key_file']).decode().strip()
        if not api_key:raise ValueError('Sender key required')
        health=GatewayHealth(otp['base'],api_key,otp['session_id'],otp['sender_phone'])
        aggregate=AggregateSocket(otp['collector_socket'],otp['session_id'],collector_uid=otp['collector_uid'],ipc_gid=otp['ipc_gid'])
        sender=BoundedOtpBroker(root/'otp'/'ledger.db',private_bytes(otp['ledger_key_file'],128),base=otp['base'],api_key=api_key,session=otp['session_id'],health=health,aggregate=aggregate,enabled=True,allowed_numbers=allowed,test_id=test_id)
    port=data.get('port',8081)
    if type(port) is not int or not 1024<=port<=65535:raise ValueError('Unprivileged isolated port required')
    config=SaaSConfig(root=root,origin=data['origin'],key=key,otp_sender=sender,google_client_id=data.get('google_client_id',''),credential_for=provider,upstream_isolation_verified=data.get('upstream_isolation_verified',False),capacity=data.get('capacity'),daily_joins=data.get('daily_joins',20),tenant_daily=data.get('tenant_daily',3),trusted_proxy_ips=tuple(data.get('trusted_proxy_ips',())),operations_enabled=data.get('operations_enabled',False))
    return config,port

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--config',required=True);parser.add_argument('--check',action='store_true');args=parser.parse_args()
    try:
        config,port=load(args.config)
        if args.check:
            print('Local configuration valid. External acceptance not checked.');return
        serve(config,port)
    except (ValueError,KeyError,OSError,TypeError):
        raise SystemExit('SaaS configuration/startup refused. Check private configuration and acceptance gates; no automatic retry.') from None
if __name__=='__main__':main()
