"""Select an existing Python. This tool never installs packages or contacts a network."""
from __future__ import annotations
import argparse, json, os, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
PROBE="import sys,importlib.util,json; print(json.dumps({'version':list(sys.version_info[:3]),'exe':sys.executable,'oracle':bool(importlib.util.find_spec('oracledb') or importlib.util.find_spec('cx_Oracle'))}))"
def inspect(exe):
    try:
        p=subprocess.run([str(exe),'-c',PROBE],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=15)
        d=json.loads(p.stdout.strip().splitlines()[-1])
        return d if d['version'][:2]>=[3,11] else None
    except (OSError,subprocess.SubprocessError,ValueError,KeyError,IndexError): return None

def candidates():
    items=[os.getenv('PYTHON_EXE','')]
    saved=ROOT/'.python_path'
    if saved.is_file(): items.append(saved.read_text(encoding='utf-8-sig').strip())
    for folder in ['LogisticsLiveHub','LogisticsLiveHub_v101','splunk_ipgo']:
        items.append(ROOT.parent/folder/'.venv/Scripts/python.exe')
    items += [sys.executable]
    local=Path(os.getenv('LOCALAPPDATA',str(Path.home())))
    for name in ['Python314','Python313','Python312','Python311']:
        items.append(local/'Programs/Python'/name/'python.exe')
    seen=set()
    for value in items:
        value=str(value).strip().strip('"')
        if not value or value.casefold() in seen: continue
        seen.add(value.casefold())
        if Path(value).is_file(): yield value

def main():
    p=argparse.ArgumentParser();p.add_argument('--auto',action='store_true');a=p.parse_args()
    found=[]
    for candidate in candidates():
        data=inspect(candidate)
        if data and data['exe'].casefold() not in {d['exe'].casefold() for d in found}: found.append(data)
    if not found: print('ERROR: Python 3.11+ not found. Set PYTHON_EXE to python.exe.');return 1
    if os.getenv('PYTHON_EXE'):
        chosen=inspect(os.getenv('PYTHON_EXE').strip('"'))
        if chosen is None: print('ERROR: PYTHON_EXE is not a supported Python.');return 1
    else: chosen=next((x for x in found if x['oracle']),found[0])
    if not a.auto:
        for i,d in enumerate(found,1): print(f"{i}. {d['exe']} | {'.'.join(map(str,d['version']))} | Oracle driver: {d['oracle']}")
        text=input('Enter number / full python.exe path / Enter = automatic: ').strip().strip('"')
        if text:
            if text.isdigit() and 1<=int(text)<=len(found): chosen=found[int(text)-1]
            else: chosen=inspect(text)
            if chosen is None: print('ERROR: Invalid Python path. Nothing changed.');return 1
    (ROOT/'.python_path').write_text(chosen['exe']+'\n',encoding='utf-8')
    print('Selected Python:',chosen['exe'])
    print('Oracle driver present:',chosen['oracle'])
    if not chosen['oracle']: print('NOTE: DB/Splunk work without packages. Oracle needs an EXISTING oracledb/cx_Oracle driver in this Python.')
    print('No packages were installed. No PyPI was contacted.')
    return 0
if __name__=='__main__': raise SystemExit(main())
