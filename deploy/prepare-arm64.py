#!/usr/bin/env python3
"""Prepare one combined native Dockerfile from an EXACT local upstream checkout. Does not run Docker."""
from pathlib import Path
import subprocess
import sys
PIN='6b26f7b921756d6db128d42cd70b4b7046381407'
root=Path(sys.argv[1]).resolve()
sha=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()
if sha != PIN:raise SystemExit('Refusing unpinned Vexa checkout')
env=(root/'core/meetings/modules/join/Dockerfile.env').read_text()
bot=(root/'core/meetings/services/bot/Dockerfile').read_text()
lines=env.splitlines()
for i,line in enumerate(lines):
 if line.startswith('FROM '):lines[i]=line+' AS labs-join-env';break
else:raise SystemExit('Join-env FROM missing')
if bot.count('FROM vexa/meet-join-env:dev')!=2:raise SystemExit('Upstream Dockerfile changed')
bot=bot.replace('FROM vexa/meet-join-env:dev','FROM labs-join-env')
# Keep original instructions, dependency lock and licences. One build graph avoids local-image
# visibility assumptions in docker-container buildx. The source build is still unverified on ARM.
output='# syntax=docker/dockerfile:1.7\n# LABS: combined ARM feasibility build only; no upstream source changes.\n'+'\n'.join(lines)+'\n'+bot.replace('# syntax=docker/dockerfile:1.7','')
(root/'Dockerfile.labs-arm64-probe').write_text(output)
print(root/'Dockerfile.labs-arm64-probe')
