#!/usr/bin/env python3
"""Review-only owner bootstrap, only after separately approved deployment provisioning.
Run INSIDE isolated app container to loopback admin API. Never prints token values.
No email/sign-in/provider service is called by this script. Account API may run its
own downstream hooks: deployment must first be validated to exclude those hooks.
"""
import argparse,json,os,sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request,build_opener,HTTPRedirectHandler

BASE='http://127.0.0.1:8001'

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


def request(path,admin,method='GET',body=None):
    req=Request(BASE+path,data=None if body is None else json.dumps(body).encode(),method=method,
                headers={'X-Admin-API-Key':admin,'Content-Type':'application/json'})
    try:
        with build_opener(NoRedirect).open(req,timeout=15) as response:
            raw=response.read(1048577)
            if len(raw)>1048576:raise RuntimeError('Admin response too large')
            return json.loads(raw)
    except HTTPError as error:
        if error.code==404:return None
        raise RuntimeError('Local admin API request failed with HTTP '+str(error.code)) from None


def bootstrap(email,output,admin,api=request):
    output=Path(output)
    if output.exists() or not output.parent.is_dir():raise ValueError('New key-file path and existing private directory required')
    if output.parent.stat().st_mode & 0o077:raise ValueError('Key parent directory must be private mode700')
    if not email or '@' not in email or any(c in email for c in '\n\r\x00'):raise ValueError('Explicit owner email required')
    user=api('/admin/users/email/'+quote(email,safe=''),admin)
    if user is None:user=api('/admin/users',admin,'POST',{'email':email,'name':'Lathar Labs Meet owner','max_concurrent_bots':1})
    if not isinstance(user,dict) or not isinstance(user.get('id'),int) or user.get('email','').casefold()!=email.casefold():raise RuntimeError('Owner identity readback mismatch')
    if type(user.get('max_concurrent_bots')) is not int or user['max_concurrent_bots']!=1:raise RuntimeError('Owner cap is not exactly1; no automatic account patch permitted')
    uid=user['id'];verified=api('/admin/users/'+str(uid),admin)
    if verified.get('max_concurrent_bots')!=1 or verified.get('email','').casefold()!=email.casefold():raise RuntimeError('Owner verification mismatch')
    tokens=api('/admin/users/'+str(uid)+'/tokens',admin)
    if not isinstance(tokens,list):raise RuntimeError('Token metadata unavailable')
    if any(t.get('name')=='labs-meet-companion' for t in tokens):raise RuntimeError('A companion token already exists; reconcile private key state, do not mint duplicate')
    # Reserve local destination before minting. On uncertain API failure leave the
    # empty600file as a visible reconciliation guard rather than retry silently.
    fd=os.open(output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try:
        token=api('/admin/users/'+str(uid)+'/tokens',admin,'POST',{'name':'labs-meet-companion','scopes':['bot','tx']})
        if not isinstance(token,dict) or not isinstance(token.get('token'),str) or set(token.get('scopes',[]))!={'bot','tx'} or token.get('user_id')!=uid:raise RuntimeError('Mint response unverified; reconcile before another attempt')
        raw=token['token'].encode()
        if os.write(fd,raw)!=len(raw):raise RuntimeError('Key file write incomplete; reconcile before another attempt')
        os.fsync(fd)
    finally:os.close(fd)
    return {'user_id':uid,'max_concurrent_bots':1,'token_id':token.get('id'),'scopes':['bot','tx'],'key_saved':True}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--email',required=True);parser.add_argument('--output-key-file',required=True);parser.add_argument('--provisioning-approved',action='store_true');args=parser.parse_args()
    if not args.provisioning_approved:parser.error('Review-only until owner-authorized deployment provisioning')
    try:
        admin=os.environ.get('ADMIN_API_TOKEN','')
        if len(admin)<32:raise ValueError('Deployment admin token missing')
        print(json.dumps(bootstrap(args.email,args.output_key_file,admin)))
    except Exception:
        print('Owner bootstrap stopped. Reconcile account/token metadata and private key-file state before retrying; no automatic retry.',file=sys.stderr);sys.exit(1)
