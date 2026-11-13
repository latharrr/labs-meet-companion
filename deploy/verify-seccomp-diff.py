#!/usr/bin/env python3
"""Read-only review: exact baseline plus one namespace sandbox rule."""
import hashlib,json,sys
from pathlib import Path
base_path,custom_path=map(Path,sys.argv[1:3])
assert hashlib.sha256(base_path.read_bytes()).hexdigest()=='785b2429264afba4d594320337cb17f144f3c7d51585f9805eef72e28f4f9334','Wrong baseline bytes'
base,custom=json.loads(base_path.read_text()),json.loads(custom_path.read_text())
rule=custom['syscalls'].pop()
assert set(rule['names'])=={'chroot','clone','unshare'}
assert rule['action']=='SCMP_ACT_ALLOW'
assert rule['excludes']=={'caps':['CAP_SYS_ADMIN']}
assert set(rule)=={'names','action','excludes','comment'}
assert base==custom,'Custom changes beyond one exact namespace rule'
print('Verified: exact Docker29.9 baseline + only clone/unshare/chroot namespace allowance; socket restrictions unchanged')
print('Custom SHA256',hashlib.sha256(custom_path.read_bytes()).hexdigest())
