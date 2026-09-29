from __future__ import annotations
import argparse, contextlib, csv, getpass, importlib.util, json, logging, logging.handlers, os, shutil, sqlite3, sys
from datetime import datetime
from pathlib import Path
from .common import *
from .settings import Settings, read_env
from .database import Database, choose_journal
from .engine import Engine
ROOT=Path(__file__).resolve().parent.parent

def logging_setup(s):
    p=s.data_dir/'logs'; p.mkdir(parents=True,exist_ok=True)
    log=logging.getLogger('scm_db'); log.setLevel(logging.INFO)
    if log.handlers: return
    fmt=logging.Formatter('%(asctime)s %(levelname)s %(message)s')
    file=logging.handlers.RotatingFileHandler(p/'collector.log',maxBytes=3*1024*1024,backupCount=3,encoding='utf-8')
    console=logging.StreamHandler(); file.setFormatter(fmt); console.setFormatter(fmt)
    log.addHandler(file); log.addHandler(console)

def setup(root=ROOT,from_env=None):
    path=root/'.env'
    if path.exists():
        print('.env가 이미 있습니다. 자동 덮어쓰지 않습니다:',path); return
    defaults=read_env(root/'.env.example')
    if from_env:
        source=Path(from_env)
        if source.resolve()==path.resolve(): raise ConfigError('원본과 대상 .env가 같습니다')
        old=read_env(source)
        allowed={k for k in defaults if k.startswith(('SPLUNK_','ORACLE_'))}
        for k in allowed:
            if k in old: defaults[k]=old[k]
        defaults['SPLUNK_VERIFY_SSL']='false'; defaults['SPLUNK_CA_BUNDLE']=''; defaults['ORACLE_ENABLED']='true'
        print('기존 .env에서 연결 설정만 복사합니다. 원본 파일은 수정하지 않습니다.')
    for key,label in [('SPLUNK_PASSWORD','Splunk 비밀번호'),('ORACLE_PASSWORD','Oracle 비밀번호')]:
        if not defaults.get(key): defaults[key]=getpass.getpass(label+' (비워두면 추후 .env 입력): ')
    # No shell escaping/interpolation: store literal values surrounded by a quote not present at the ends.
    result=['# SCMRealtimeDB project-only settings. Never commit/share this file.']
    for key,value in defaults.items():
        if '\n' in value or '\r' in value: raise ConfigError('환경값에는 줄바꿈을 넣을 수 없습니다')
        quote='"' if value.startswith("'") or value.endswith("'") else "'"
        result.append(key+'='+quote+value+quote)
    atomic_text(path,'\n'.join(result)+'\n')
    with contextlib.suppress(OSError): path.chmod(0o600)
    print('생성:',path,'\nSplunk SSL 검증: OFF / Oracle: Thick / 자동 조회: 매일 09:00 KST')

def print_rows(rows):
    if not rows: print('(0 rows)'); return
    for row in rows: print(js(row))

def status(s,db):
    print('\nSCM Realtime DB 1.0 · UI 없음 / 외부 접속 포트 없음')
    print('Python:',sys.executable); print('SQLite:',sqlite3.sqlite_version,'journal:',choose_journal()); print('DB:',db.path)
    print('\n[원천 상태]'); print_rows(db.query('SELECT * FROM v_source_health'))
    print('\n[최근 실행]'); print_rows(db.query('SELECT source_id,run_kind,status,started_at,ended_at,rows_read,rows_written,rows_rejected,detail FROM etl_run ORDER BY started_at DESC LIMIT 8'))
    print('\n[09시 일정]'); print_rows(db.query('SELECT * FROM schedule_run ORDER BY local_day DESC LIMIT 3'))
    print('\n[최신행]')
    for domain in ('inbound','inventory','shipment'):
        print_rows(db.query(f"SELECT '{domain}' AS domain,COUNT(*) AS current_rows,SUM(CASE WHEN scope_ok=1 AND deleted=0 THEN 1 ELSE 0 END) AS in_scope_rows FROM {domain}_current"))

def doctor(s,db):
    print('Python:',sys.executable,sys.version.split()[0]); print('DB:',s.db_path)
    print('DB integrity:',db.query('PRAGMA quick_check')[0]); print('SQLite journal:',choose_journal())
    print('Splunk CA 검증:',s.profile()['verify'],'(OFF는 서버 신원 확인을 생략합니다)')
    print('Oracle 활성:',s.flag('ORACLE_ENABLED',True))
    try:
        from .connectors.oracle import prepare_driver
        module,name=prepare_driver(s)
        print('Oracle driver:',name,getattr(module,'__version__','?'),'· Thick initialized')
    except Exception as exc: print('Oracle 준비 필요:',safe_error(exc))
    print('Oracle 스케줄:',s.config['oracle_schedule']['at'],'KST, 동일 날짜 재시작해도 중복 예약 조회 없음')
    print('자동 패키지 설치/외부 PyPI 호출은 수행하지 않았습니다.')

def parser():
    p=argparse.ArgumentParser(description='SCMRealtimeDB: Splunk + Oracle -> local SQL DB only')
    sub=p.add_subparsers(dest='command',required=True)
    x=sub.add_parser('setup'); x.add_argument('--from-env')
    for name in ('init','run','status','doctor','sync-oracle','discover-oracle','discover-splunk','apply-mappings','backup','menu','demo'): sub.add_parser(name)
    x=sub.add_parser('collect'); x.add_argument('--source',default='inbound_dep'); x.add_argument('--from-date')
    x=sub.add_parser('map-oracle'); x.add_argument('source')
    x=sub.add_parser('map-source'); x.add_argument('source')
    x=sub.add_parser('query'); x.add_argument('--sql'); x.add_argument('--file'); x.add_argument('--csv')
    x=sub.add_parser('reset-source'); x.add_argument('source'); x.add_argument('--confirm',action='store_true')
    x=sub.add_parser('import-snapshot'); x.add_argument('--source',required=True); x.add_argument('--file',required=True)
    x.add_argument('--as-of',required=True); x.add_argument('--token',required=True); x.add_argument('--complete',action='store_true'); x.add_argument('--confirm',action='store_true')
    return p

def menu():
    choices={'1':['status'],'2':['doctor'],'3':['sync-oracle'],'4':['discover-oracle'],'5':['apply-mappings'],
       '6':['collect'],'7':['backup'],'8':['discover-splunk']}
    while True:
        print('''\nSCM Realtime DB 관리\n1 상태  2 연결준비 검사  3 Oracle 최초/수동 복제  4 Oracle 컬럼 구조\n5 로컬 기준정보 재매핑  6 입고 1회 수집  7 백업  8 Splunk 테이블 목록\n9 기준정보 매핑  10 재고/출하 매핑  11 로컬 SQL 조회  0 종료\n상시 수집은 START.cmd에서 실행합니다. 별도 수집/매핑은 상시 수집 중지 후 실행하세요.''')
        item=input('선택: ').strip()
        if item=='0': return 0
        argv=choices.get(item)
        if item=='9': argv=['map-oracle',input('product/conversion/customer/inbound_plan/shipment_plan: ').strip()]
        if item=='10': argv=['map-source',input('inventory_dep/shipment_dep: ').strip()]
        if item=='11': argv=['query','--sql',input('SELECT 문: ').strip()]
        if argv: main(argv)

WRITES={'init','run','sync-oracle','apply-mappings','collect','map-oracle','map-source','reset-source','import-snapshot'}

def main(argv=None):
    args=parser().parse_args(argv)
    try:
        if args.command=='setup': setup(from_env=args.from_env); return 0
        if args.command=='menu': return menu()
        if args.command=='demo':
            from .demo import run_demo
            run_demo(ROOT); return 0
        s=Settings(ROOT); db=Database(s.db_path,ROOT)
        lock=ProcessLock(s.data_dir/'writer.lock') if args.command in WRITES or not db.path.exists() else contextlib.nullcontext()
        with lock:
            # Read-only commands never run DDL or require a writer lock.
            if args.command in WRITES or not db.path.exists():
                if args.command=='reset-source' and db.path.exists():
                    if not args.confirm: raise ConfigError('원천 리셋은 --confirm 필요. 자동 백업 후 해당 원천만 지웁니다')
                    d=s.source(args.source); dst=db.backup()
                    with db.transaction() as con:
                        con.execute(f"DELETE FROM {d['domain']}_current WHERE source_id=?",(args.source,))
                        con.execute('DELETE FROM fact_valuation WHERE source_id=?',(args.source,))
                        con.execute('DELETE FROM raw_splunk_event WHERE source_id=?',(args.source,))
                        con.execute('DELETE FROM source_state WHERE source_id=?',(args.source,))
                        con.execute('DELETE FROM meta WHERE key=?',('bootstrap_floor:'+args.source,))
                    print('자동 백업:',dst)
                db.initialize(s.config)
            logging_setup(s)
            engine=Engine(s,db)
            if args.command in {'init','reset-source'}: print('DB 준비 완료:',db.path)
            elif args.command=='run':
                print('DB:',db.path,'\nSplunk 최신행 수집 시작 / Oracle 매일 09:00 KST / Ctrl+C 종료')
                if not s.profile()['verify']: print('주의: 사용자 설정에 따라 Splunk TLS 인증서 검증 OFF')
                engine.loop()
            elif args.command=='status': status(s,db)
            elif args.command=='doctor': doctor(s,db)
            elif args.command=='collect':
                from_epoch=int(datetime.strptime(args.from_date,'%Y-%m-%d').replace(tzinfo=KST).timestamp()) if args.from_date else None
                print_rows([engine.collect(s.source(args.source),from_epoch=from_epoch)])
            elif args.command=='sync-oracle': print(json.dumps(engine.sync_oracle(),ensure_ascii=False,indent=2))
            elif args.command=='discover-oracle':
                from .connectors.oracle import OracleClient
                data=OracleClient(s).discover(); path=s.data_dir/'exports/oracle_schema_discovered.json'
                atomic_text(path,json.dumps(data,ensure_ascii=False,indent=2)); print('실제 컬럼 구조 저장:',path)
                for name,obj in data.items(): print(name,':',', '.join(x['name'] for x in obj['columns']))
            elif args.command=='discover-splunk':
                from .connectors.splunk import SplunkClient
                d=s.splunk[0]
                query=f'search index={d["index"]} source="{d["source"]}" EVENT_TYPE="TREAD_DYN" earliest=-24h latest=now | stats count by TABNAME | sort - count'
                print_rows(SplunkClient(s.profile()).search(query,10000))
            elif args.command=='apply-mappings':
                from .reference import project_cached
                print(json.dumps(project_cached(db,s),ensure_ascii=False,indent=2))
            elif args.command=='map-oracle':
                from .wizard import map_oracle
                map_oracle(s,db,args.source)
            elif args.command=='map-source':
                from .wizard import map_source
                map_source(s,db,args.source)
            elif args.command=='backup': print('백업:',db.backup())
            elif args.command=='query':
                sql=Path(args.file).read_text(encoding='utf-8-sig') if args.file else args.sql
                if not sql: raise ConfigError('--sql 또는 --file 필요')
                rows=db.query(sql)
                if args.csv:
                    path=Path(args.csv); path.parent.mkdir(parents=True,exist_ok=True)
                    with path.open('w',encoding='utf-8-sig',newline='') as handle:
                        if rows:
                            w=csv.DictWriter(handle,fieldnames=list(rows[0])); w.writeheader()
                            for row in rows:
                                safe={k:("'"+v if isinstance(v,str) and v.lstrip().startswith(('=','+','-','@')) else v) for k,v in row.items()}
                                w.writerow(safe)
                    print('CSV:',path,'행:',len(rows))
                else: print_rows(rows[:200]); print('전체 행:',len(rows),'(화면 최대 200행)')
            elif args.command=='import-snapshot':
                if not (args.complete and args.confirm): raise ConfigError('전체 스냅샷 교체는 --complete --confirm 필요')
                d=s.source(args.source)
                if d['domain']!='inventory': raise ConfigError('전체 스냅샷 교체는 재고에만 허용합니다')
                moment=datetime.fromisoformat(args.as_of)
                if moment.tzinfo is None: raise ConfigError('--as-of에 +09:00 등 시간대 필요')
                rows=[json.loads(line) for line in Path(args.file).read_text(encoding='utf-8-sig').splitlines() if line.strip()]
                print('교체 전 백업:',db.backup())
                result=db.ingest(d,rows,int(moment.timestamp()),int(moment.timestamp()),snapshot={'complete':True,'as_of_us':int(moment.timestamp()*1e6),'token':args.token})
                print_rows([result])
        return 0
    except KeyboardInterrupt: print('\n중단했습니다.'); return 130
    except Exception as exc:
        print('\nERROR:',safe_error(exc),file=sys.stderr); return 1
