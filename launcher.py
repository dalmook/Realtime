"""Company run and synthetic demo launchers. No hardcoded user paths, no pip calls."""
from __future__ import annotations
import argparse,contextlib,copy,json,logging,os,sys,threading,webbrowser
from pathlib import Path
from scm_db.settings import Settings
from scm_db.database import Database
from scm_db.common import ProcessLock,ConfigError,safe_error
from dashboard import runtime
ROOT=Path(__file__).resolve().parent

def main(argv=None):
    argv=list(sys.argv[1:] if argv is None else argv)
    command=argv[0] if argv else 'run'
    if command not in ('run','serve','demo','init','setup','doctor'):
        from scm_db.cli import main as legacy
        return legacy(argv)
    parser=argparse.ArgumentParser(description='SCM local dashboard')
    parser.add_argument('command',nargs='?',default='run',choices=['run','serve','demo','init','setup','doctor'])
    parser.add_argument('--port',type=int);parser.add_argument('--data-dir');parser.add_argument('--no-browser',action='store_true')
    a=parser.parse_args(argv)
    if a.command=='setup':
        f=ROOT/'.env'
        if not f.exists():f.write_bytes((ROOT/'.env.example').read_bytes());print('Created .env. Enter approved company connection settings.')
        else:print('Existing .env preserved.')
        return 0
    demo=a.command=='demo'
    if demo:
        cfg=json.loads((ROOT/'config/pipeline.json').read_text(encoding='utf-8-sig'))
        env={k:'' for k in ('SPLUNK_HOST','SPLUNK_USER','SPLUNK_PASSWORD','ORACLE_USER','ORACLE_PASSWORD','ORACLE_DSN','DATA_DIR')}
        env.update(ORACLE_ENABLED='false',SPLUNK_ENABLED='false',AUTO_BACKUP='false',DASH_HOST='127.0.0.1',DASH_PORT=str(a.port or 8765),SHIPMENT_BOX_CONFIRMED='true')
        path=Path(a.data_dir) if a.data_dir else Path(os.getenv('LOCALAPPDATA',str(Path.home()/'.local/share')))/'SCMRealtimeDB'/'demo-web'
        s=Settings(ROOT,env=env,config=cfg,data_dir=path)
    else:s=Settings(ROOT,data_dir=a.data_dir)
    runtime.configure(s,demo=demo)
    if a.command=='doctor':
        print('Python:',sys.version.split()[0]);print('DB:',s.db_path)
        from scm_db.database import choose_journal
        import sqlite3
        print('SQLite:',sqlite3.sqlite_version,'journal:',choose_journal())
        if s.db_path.is_file():
            with contextlib.closing(Database(s.db_path,ROOT).connect(True)) as c:print('Integrity:',c.execute('PRAGMA quick_check').fetchone()[0])
        for prefix,fields in [('Splunk',('SPLUNK_HOST','SPLUNK_USER','SPLUNK_PASSWORD')),('Oracle',('ORACLE_USER','ORACLE_PASSWORD','ORACLE_DSN'))]:
            print(prefix,'configured:',all(bool(s.get(k)) for k in fields))
        if s.flag('ORACLE_ENABLED',True):
            try:
                from scm_db.connectors.oracle import prepare_driver
                _,name=prepare_driver(s);print('Oracle Thick initialized:',name)
            except Exception as e:print('Oracle prerequisite:',safe_error(e))
        return 0
    with contextlib.ExitStack() as stack:
        # Lock is never bypassed; held for the entire collector lifespan.
        if a.command!='serve':stack.enter_context(ProcessLock(s.data_dir/'writer.lock'))
        if demo:
            from scm_db.demo_seed import seed
            db=seed(s)
        else:
            db=Database(s.db_path,ROOT)
            if a.command!='serve' or not s.db_path.exists():db.initialize(s.config)
        runtime.ensure_runtime()
        if a.command=='init':print('Initialized:',db.path);return 0
        from dashboard.server import make_server
        server=make_server(port=a.port)
        engine=None;worker=None
        if a.command=='run':
            from scm_db.engine import Engine
            from scm_db.cli import logging_setup
            logging_setup(s)
            cfg=copy.deepcopy(s.config)
            configured=all(s.get(k) for k in ('SPLUNK_HOST','SPLUNK_USER','SPLUNK_PASSWORD'))
            if not s.flag('SPLUNK_ENABLED',True) or not configured:
                for d in cfg['splunk_sources']:d['enabled']=False
                print('Splunk collector disabled or connection fields incomplete; no synthetic data is substituted.')
            s.config=cfg
            engine=Engine(s,db);worker=threading.Thread(target=engine.loop,name='scm-collector',daemon=True);worker.start()
        address=f'http://127.0.0.1:{server.server_port}/'
        print(('SYNTHETIC DEMO — no company connections' if demo else 'LIVE local API'),flush=True)
        print('DB:',db.path,flush=True);print('OPEN:',address,flush=True)
        if not a.no_browser and s.flag('OPEN_BROWSER',True):webbrowser.open(address)
        try:server.serve_forever()
        except KeyboardInterrupt:print('\nStopping...')
        finally:
            if engine:engine.stop.set()
            server.server_close()
            if worker:worker.join(timeout=5)
        return 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as e:print('ERROR:',safe_error(e),file=sys.stderr);raise SystemExit(1)
