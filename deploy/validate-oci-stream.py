#!/usr/bin/env python3
"""Strict Docker-save OCI-layout stream sink. No format conversion or tar extraction.
Usage: docker image save EXACT | python validate-oci-stream.py NEWDIR INSPECT.json
Only invoke under independently approved export resource/disk/time plan.
"""
import hashlib,json,re,sys,tarfile
from pathlib import Path

LIMIT=2*1024**3
PATTERN=re.compile(r'blobs/sha256/[0-9a-f]{64}\Z')


def receive(stream,destination,inspect):
    destination=Path(destination)
    if destination.exists():raise ValueError('New private output directory required')
    destination.mkdir(mode=0o700)
    seen=set();total=0;count=0
    with tarfile.open(fileobj=stream,mode='r|') as tar:
        for entry in tar:
            count+=1
            if count>200:raise ValueError('Too many archive entries')
            name=entry.name
            if entry.isdir():
                if name.rstrip('/') not in ('blobs','blobs/sha256'):raise ValueError('Unsupported directory')
                continue
            if not entry.isfile() or name in seen:raise ValueError('Nonregular or duplicate archive entry')
            seen.add(name)
            if not (PATTERN.fullmatch(name) or name in ('oci-layout','index.json','manifest.json','repositories')):
                raise ValueError('Not supported OCI Docker-save shape')
            total+=entry.size
            if entry.size<0 or total>LIMIT:raise ValueError('2GiB export byte cap exceeded')
            path=destination/name;path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
            digest=hashlib.sha256();read=0
            with tar.extractfile(entry) as source,path.open('xb') as output:
                while chunk:=source.read(1024*1024):
                    output.write(chunk);digest.update(chunk);read+=len(chunk)
            path.chmod(0o600)
            if read!=entry.size:raise ValueError('Truncated archive entry')
            if PATTERN.fullmatch(name) and digest.hexdigest()!=name.rsplit('/',1)[1]:raise ValueError('Blob digest mismatch')
    def doc(path):
        file=destination/path
        if not file.is_file() or file.stat().st_size>2*1024**2:raise ValueError('Missing/oversized OCI metadata')
        return json.loads(file.read_text())
    def blob(descriptor):
        digest=descriptor['digest']
        if not re.fullmatch('sha256:[0-9a-f]{64}',digest):raise ValueError('Unsupported digest')
        path='blobs/sha256/'+digest.split(':')[1]
        file=destination/path
        if not file.is_file() or file.stat().st_size!=descriptor['size']:raise ValueError('Missing/wrong-size descriptor')
        return path
    if doc('oci-layout')!={'imageLayoutVersion':'1.0.0'}:raise ValueError('Unsupported OCI layout')
    index=doc('index.json')
    if index.get('schemaVersion')!=2 or len(index.get('manifests',[]))!=1:raise ValueError('Need exactly one OCI image')
    descriptor=index['manifests'][0]
    manifest=doc(blob(descriptor))
    if 'manifests' in manifest:raise ValueError('Nested index unsupported: stop, do not select implicitly')
    allowed={'application/vnd.oci.image.manifest.v1+json','application/vnd.docker.distribution.manifest.v2+json'}
    if descriptor['mediaType'] not in allowed or manifest.get('schemaVersion')!=2:raise ValueError('Unsupported image manifest')
    config=doc(blob(manifest['config']))
    for layer in manifest['layers']:blob(layer)
    info=inspect[0] if isinstance(inspect,list) else inspect
    if config.get('architecture')!='arm64' or config.get('os')!='linux':raise ValueError('Not Linux ARM64')
    if config.get('rootfs',{}).get('diff_ids')!=info['RootFS']['Layers']:raise ValueError('Base rootfs differs from inspected retained worker')
    expected={info.get('Id',''),*info.get('RepoDigests',[])}
    if not any(x==descriptor['digest'] or x.endswith('@'+descriptor['digest']) for x in expected):
        raise ValueError('Manifest digest does not match exact inspected retained image: stop')
    return {'validated':True,'bytes':total,'manifest_digest':descriptor['digest'],'config_digest':manifest['config']['digest'],'layers':len(manifest['layers']),'architecture':'arm64'}

if __name__=='__main__':
    try:print(json.dumps(receive(sys.stdin.buffer,sys.argv[1],json.loads(Path(sys.argv[2]).read_text()))))
    except Exception as error:
        print('OCI stream refused: '+type(error).__name__+': '+str(error),file=sys.stderr);sys.exit(1)
