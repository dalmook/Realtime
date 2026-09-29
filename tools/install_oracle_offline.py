"""Explicit optional offline install into the selected Python. No downloads or indexes."""
import os, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
wheels=sorted((ROOT/'offline_wheels').glob('*.whl'))
if not wheels:
    print('No wheel files included. Put IT-approved wheels for THIS Python/Windows and their dependencies in offline_wheels/.')
    print('Prefer SELECT_PYTHON.cmd to reuse a Python where Oracle already works. No automatic download.')
    raise SystemExit(1)
print('Target Python:',sys.executable)
print('Local wheels:',*[p.name for p in wheels],sep='\n')
if input('Install these local files into this Python? Type INSTALL: ').strip()!='INSTALL': raise SystemExit('Cancelled')
env={k:v for k,v in os.environ.items() if not k.upper().startswith('PIP_')}
env['PIP_CONFIG_FILE']=os.devnull
raise SystemExit(subprocess.call([sys.executable,'-m','pip','--disable-pip-version-check','install','--no-index','--no-deps',*[str(p) for p in wheels]],env=env))
