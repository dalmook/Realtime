"""Allowlisted source packaging. Never include .env, a database, logs or installed binaries."""
from __future__ import annotations
import argparse,hashlib,json,re,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
ROOT_NAMES={'.env.example','.gitignore','.gitattributes','README.md','START_HERE.txt','VERSION','MANIFEST.json','pyproject.toml'}
DIRS={'scm_db','dashboard','sql','config','tests','tools','docs','examples','offline_wheels','.github','site'}
BLOCK_DIRS={'.git','.venv','venv','__pycache__','node_modules','logs','backups','staging','live','demo-web','artifacts'}
BLOCK_SUFFIX={'.db','.sqlite','.sqlite3','.db-wal','.sqlite-wal','.sqlite-shm','.log','.pyc','.dll','.exe','.pem','.key','.p12','.pfx','.whl','.zip'}
SECRET=re.compile(r'\b(?:github_pat_[A-Za-z0-9_]{30,}|gh[pousr]_[A-Za-z0-9]{25,}|sk-[A-Za-z0-9_-]{25,})\b')

def source_files(root=ROOT):
    root=Path(root)
    for f in sorted(root.rglob('*')):
        if not f.is_file() or f.is_symlink():continue
        rel=f.relative_to(root)
        if any(x in BLOCK_DIRS for x in rel.parts) or f.suffix.lower() in BLOCK_SUFFIX:continue
        if any(x.startswith('backup_') for x in rel.parts):continue
        if f.name.startswith('.env') and f.name!='.env.example':continue
        if len(rel.parts)==1:
            if f.name not in ROOT_NAMES and f.suffix not in ('.py','.cmd','.ps1'):continue
        elif rel.parts[0] not in DIRS:continue
        raw=f.read_bytes()
        if SECRET.search(raw.decode('utf-8',errors='ignore')):raise ValueError('Credential-like string in '+str(rel))
        yield f

def manifest(root=ROOT):
    root=Path(root);return {'version':(root/'VERSION').read_text().strip(),'files':{str(f.relative_to(root)).replace('\\','/'):{'bytes':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()} for f in source_files(root) if f.name!='MANIFEST.json'}}

def build(output=None):
    (ROOT/'MANIFEST.json').write_text(json.dumps(manifest(),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    dst=Path(output) if output else ROOT.parent/'SCMRealtimeDB_portable.zip';dst.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(dst,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for f in source_files():z.write(f,'SCMRealtimeDB/'+f.relative_to(ROOT).as_posix())
    return dst
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output');a=p.parse_args();print(build(a.output))
