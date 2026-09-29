from __future__ import annotations
import contextlib, copy, json, sqlite3, time, uuid
from decimal import Decimal
from pathlib import Path
from .common import *

FACT_COLUMNS = '''source_id record_key document_no box_no material qty_i amount_i unit plant warehouse location customer_key
business_date business_time business_us modified_us generated_us indexed_us event_hash scope_ok deleted payload_json'''.split()
FACT_DDL = '''(
 source_id TEXT NOT NULL, record_key TEXT NOT NULL, document_no TEXT NOT NULL DEFAULT '',
 box_no TEXT NOT NULL DEFAULT '', material TEXT NOT NULL, qty_i INTEGER NOT NULL,
 amount_i INTEGER NOT NULL DEFAULT 0,
 unit TEXT NOT NULL, plant TEXT NOT NULL DEFAULT '', warehouse TEXT NOT NULL DEFAULT '',
 location TEXT NOT NULL DEFAULT '', customer_key TEXT NOT NULL DEFAULT '',
 business_date TEXT NOT NULL, business_time TEXT NOT NULL, business_us INTEGER NOT NULL,
 modified_us INTEGER NOT NULL, generated_us INTEGER NOT NULL, indexed_us INTEGER NOT NULL,
 event_hash TEXT NOT NULL, scope_ok INTEGER NOT NULL, deleted INTEGER NOT NULL DEFAULT 0,
 payload_json TEXT NOT NULL, PRIMARY KEY(source_id,record_key))'''
DOMAINS=('inbound','inventory','shipment','shipment_box','shipment_amount')

def choose_journal():
    # SQLite WAL reset fix: 3.51.3+, or the supported 3.50.7/3.44.6 backports.
    v=sqlite3.sqlite_version_info
    safe=v>=(3,51,3) or (v[:2]==(3,50) and v>=(3,50,7)) or (v[:2]==(3,44) and v>=(3,44,6))
    return 'WAL' if safe else 'DELETE'

class Database:
    def __init__(self,path,root): self.path=Path(path); self.root=Path(root)
    def connect(self,readonly=False):
        if readonly:
            con=sqlite3.connect(self.path.as_uri()+'?mode=ro',uri=True,timeout=30)
            con.execute('PRAGMA query_only=ON')
        else:
            self.path.parent.mkdir(parents=True,exist_ok=True)
            con=sqlite3.connect(self.path,timeout=30)
            con.execute('PRAGMA foreign_keys=ON'); con.execute('PRAGMA synchronous=FULL')
        con.row_factory=sqlite3.Row
        con.execute('PRAGMA busy_timeout=30000')
        return con
    @contextlib.contextmanager
    def transaction(self):
        con=self.connect()
        try:
            con.execute('BEGIN'); yield con; con.commit()
        except BaseException: con.rollback(); raise
        finally: con.close()
    def initialize(self,config):
        if sqlite3.sqlite_version_info<(3,25,0): raise ConfigError('SQLite 3.25 이상을 포함하는 Python이 필요합니다')
        con=self.connect()
        try:
            versions=[]
            if con.execute("SELECT 1 FROM sqlite_master WHERE name='schema_version'").fetchone():
                versions=[x[0] for x in con.execute('SELECT version FROM schema_version')]
            if versions and max(versions)>1: raise ConfigError('이 프로그램보다 새로운 DB입니다. 덮어쓰지 않습니다')
            con.execute('PRAGMA journal_mode='+choose_journal())
            had_component=bool(con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='dim_conversion_component'").fetchone())
            material_remaps=[]
            migration_needed=False
            if versions:
                if con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='fact_valuation'").fetchone():
                    fact_cols={r[1] for r in con.execute('PRAGMA table_info(fact_valuation)')}
                    migration_needed=bool({'eq_dram_i','eq_flash_i'}-fact_cols)
                for domain in DOMAINS:
                    table=domain+'_current'
                    if con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone():
                        migration_needed=migration_needed or 'amount_i' not in {r[1] for r in con.execute(f'PRAGMA table_info({table})')}
                if not had_component:migration_needed=True
                if con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='source_state'").fetchone():
                    for d in config['splunk_sources']:
                        old=con.execute('SELECT * FROM source_state WHERE source_id=?',(d['id'],)).fetchone()
                        if not old or old['config_hash']==source_fingerprint(d) or not old['watermark']: continue
                        legacy=copy.deepcopy(d)
                        if d['id']=='inbound_dep' and d.get('fields',{}).get('material')=='MATNR':
                            legacy['fields']['material']='P_CODE'
                            if old['config_hash']==source_fingerprint(legacy):
                                material_remaps.append(d['id']);migration_needed=True
            if migration_needed:self.backup()
            con.executescript((self.root/'sql/001_schema.sql').read_text(encoding='utf-8'))
            existing={r[1] for r in con.execute('PRAGMA table_info(fact_valuation)')}
            for col in ('eq_dram_i','eq_flash_i'):
                if col not in existing: con.execute(f'ALTER TABLE fact_valuation ADD COLUMN {col} INTEGER')
            for domain in DOMAINS:
                table=domain+'_current'
                con.execute('CREATE TABLE IF NOT EXISTS '+table+FACT_DDL)
                if 'amount_i' not in {r[1] for r in con.execute(f'PRAGMA table_info({table})')}:
                    con.execute(f'ALTER TABLE {table} ADD COLUMN amount_i INTEGER NOT NULL DEFAULT 0')
                con.execute(f'CREATE INDEX IF NOT EXISTS ix_{domain}_date ON {table}(business_date,source_id,scope_ok,deleted)')
                con.execute(f'CREATE INDEX IF NOT EXISTS ix_{domain}_product ON {table}(material,business_date)')
                con.execute(f'CREATE INDEX IF NOT EXISTS ix_{domain}_box ON {table}(box_no,business_date)')
                con.execute(f'CREATE INDEX IF NOT EXISTS ix_{domain}_record ON {table}(record_key)')
                con.execute(f'CREATE INDEX IF NOT EXISTS ix_{domain}_report ON {table}(plant,scope_ok,deleted,business_date)')
            con.execute('CREATE INDEX IF NOT EXISTS ix_shipment_amount_latest ON shipment_amount_current(record_key,modified_us DESC,generated_us DESC,indexed_us DESC,source_id)')
            for source_id in material_remaps:
                missing=con.execute("""SELECT COUNT(*) FROM inbound_current
                  WHERE source_id=? AND COALESCE(TRIM(CAST(json_extract(payload_json,'$.MATNR') AS TEXT)),'')=''""",(source_id,)).fetchone()[0]
                if missing:
                    raise ConfigError(f'{source_id}: 기존 {missing}행에 MATNR가 없어 P_CODE→MATNR 자동이관을 중단합니다. 원천 backfill/reset이 필요합니다')
                con.execute("""UPDATE inbound_current SET material=TRIM(CAST(json_extract(payload_json,'$.MATNR') AS TEXT))
                  WHERE source_id=?""",(source_id,))
                con.execute('DELETE FROM fact_valuation WHERE source_id=?',(source_id,))
            for d in config['splunk_sources']:
                h=source_fingerprint(d)
                old=con.execute('SELECT * FROM source_state WHERE source_id=?',(d['id'],)).fetchone()
                if old and old['config_hash']!=h and old['watermark'] and d['id'] not in material_remaps:
                    raise ConfigError(f"{d['id']}: 원천/키/매핑 변경 감지. 중지 후 새 source id로 등록하거나 reset-source --confirm 실행하세요")
                con.execute('''INSERT INTO source_state(source_id,domain,enabled,config_hash) VALUES(?,?,?,?)
                  ON CONFLICT(source_id) DO UPDATE SET enabled=excluded.enabled,config_hash=excluded.config_hash''',
                  (d['id'],d['domain'],int(d.get('enabled',False)),h))
            for d in config['oracle_sources']:
                con.execute('''INSERT INTO reference_state(source_id,oracle_table,kind) VALUES(?,?,?)
                 ON CONFLICT(source_id) DO UPDATE SET oracle_table=excluded.oracle_table,kind=excluded.kind''',(d['id'],d['table'],d['kind']))
            if versions and not had_component:
                con.execute("""UPDATE reference_state SET projection_ready=0,projection_note='CONVERSION_RESYNC_REQUIRED'
                  WHERE source_id='conversion' AND snapshot_id IS NOT NULL""")
                con.execute("UPDATE meta SET value=CAST(value AS INTEGER)+1 WHERE key='reference_revision'")
            if material_remaps or (versions and not had_component):revalue_all(con)
            con.commit()
            con.executescript((self.root/'sql/002_views.sql').read_text(encoding='utf-8'))
        finally: con.close()
    def query(self,sql,params=()):
        with contextlib.closing(self.connect(readonly=True)) as con:
            return [dict(x) for x in con.execute(sql,params)]
    def state(self,id):
        rows=self.query('SELECT * FROM source_state WHERE source_id=?',(id,))
        return rows[0] if rows else None
    def start_run(self,source,kind):
        id=uuid.uuid4().hex
        with self.transaction() as con:
            con.execute('INSERT INTO etl_run(run_id,source_id,run_kind,started_at,status) VALUES(?,?,?,?,?)',(id,source,kind,stamp(),'RUNNING'))
        return id
    def fail_run(self,id,source,exc):
        msg=safe_error(exc)
        with self.transaction() as con:
            con.execute('UPDATE etl_run SET ended_at=?,status=?,detail=? WHERE run_id=?',(stamp(),'FAILED',msg,id))
            con.execute('UPDATE source_state SET last_error=?,last_run_id=? WHERE source_id=?',(msg,id,source))
    def ingest(self,source,events,upper,coverage_from,*,snapshot=None):
        from .normalize import normalize
        table=source['domain']+'_current'; id=source['id']
        run=self.start_run(id,'snapshot' if snapshot else 'splunk')
        count={'read':len(events),'written':0,'unchanged':0,'older':0,'rejected':0}
        normalized=[]; issues=[]; raw=[]; fields={}
        try:
            for e in events:
                hashed=digest(e)
                try:
                    row,payload=normalize(source,e)
                    raw.append((id,row['event_hash'],row['record_key'],int(float(e.get('event_epoch',0))*1e6),row['indexed_us'],stamp(),js(payload)))
                    normalized.append(row)
                    for name,val in payload.items(): fields.setdefault(name,set()).add(type(val).__name__)
                except (DataError,ValueError,TypeError,KeyError) as exc:
                    issues.append((id,run,'NORMALIZE_ERROR',hashed,safe_error(exc),stamp()))
                    raw.append((id,hashed,None,None,None,stamp(),js(e)))
            if issues:
                # Fail closed: raw evidence is kept, current values and cursor are NOT advanced.
                with self.transaction() as con:
                    con.executemany('INSERT OR IGNORE INTO raw_splunk_event VALUES(?,?,?,?,?,?,?)',raw)
                    con.executemany('INSERT INTO data_issue(source_id,run_id,issue_code,event_hash,detail,created_at) VALUES(?,?,?,?,?,?)',issues)
                count['rejected']=len(issues)
                raise DataError(f'{len(issues)}건 정규화 실패. 원문/오류 보존, 최신행·수집 커서 유지. STATUS 및 data_issue 확인')
            if snapshot:
                if not snapshot.get('complete'): raise DataError('불완전 스냅샷은 교체할 수 없습니다')
                if not normalized and not source.get('allow_empty_snapshot',False): raise DataError('빈 스냅샷 교체는 기본 차단합니다')
                if len({r['record_key'] for r in normalized})!=len(normalized): raise DataError('전체 스냅샷 업무키 중복')
            with self.transaction() as con:
                con.executemany('INSERT OR IGNORE INTO raw_splunk_event VALUES(?,?,?,?,?,?,?)',raw)
                if snapshot:
                    previous=con.execute("SELECT value FROM meta WHERE key=?",('snapshot:'+id,)).fetchone()
                    if previous and int(json.loads(previous[0])['as_of_us'])>=int(snapshot['as_of_us']): raise DataError('이미 적용했거나 더 오래된 스냅샷입니다')
                    con.execute(f'DELETE FROM {table} WHERE source_id=?',(id,))
                    con.execute('DELETE FROM fact_valuation WHERE source_id=?',(id,))
                for row in normalized:
                    old=con.execute(f'SELECT * FROM {table} WHERE source_id=? AND record_key=?',(id,row['record_key'])).fetchone()
                    version=lambda x:(x['modified_us'],x['generated_us'],x['indexed_us'])
                    if old and version(row)<version(old): count['older']+=1; continue
                    if old and row['event_hash']==old['event_hash']: count['unchanged']+=1; continue
                    if old and version(row)==version(old) and row['payload_json']!=old['payload_json']:
                        raise DataError('동일 버전 시각에 내용이 충돌합니다. 원천 정렬 필드를 확인하세요')
                    placeholders=','.join('?' for _ in FACT_COLUMNS)
                    update=','.join(f'{c}=excluded.{c}' for c in FACT_COLUMNS if c not in {'source_id','record_key'})
                    con.execute(f'INSERT INTO {table}({",".join(FACT_COLUMNS)}) VALUES({placeholders}) ON CONFLICT(source_id,record_key) DO UPDATE SET {update}',[row[c] for c in FACT_COLUMNS])
                    value_fact(con,row)
                    count['written']+=1
                if snapshot:
                    con.execute('INSERT INTO meta VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',('snapshot:'+id,js(snapshot)))
                for name,types in fields.items():
                    con.execute('''INSERT INTO field_catalog VALUES(?,?,?,?) ON CONFLICT(source_id,field_name)
                     DO UPDATE SET sample_types=excluded.sample_types,last_seen=excluded.last_seen''',(id,name,','.join(sorted(types)),stamp()))
                con.execute('''UPDATE source_state SET watermark=MAX(watermark,?),coverage_from=CASE WHEN ? IS NULL THEN coverage_from WHEN coverage_from IS NULL THEN ? ELSE MIN(coverage_from,?) END,
                  last_success=?,last_error=NULL,last_run_id=?,last_read=?,last_written=? WHERE source_id=?''',
                  (upper,coverage_from,coverage_from,coverage_from,stamp(),run,count['read'],count['written'],id))
                con.execute('''UPDATE etl_run SET ended_at=?,status='SUCCESS',rows_read=?,rows_written=?,rows_unchanged=?,rows_older=? WHERE run_id=?''',
                  (stamp(),count['read'],count['written'],count['unchanged'],count['older'],run))
            return count
        except BaseException as exc:
            self.fail_run(run,id,exc)
            if count['rejected']:
                with self.transaction() as con: con.execute('UPDATE etl_run SET rows_read=?,rows_rejected=? WHERE run_id=?',(len(events),count['rejected'],run))
            raise
    def backup(self,destination=None):
        dst=Path(destination) if destination else self.path.parent/'backups'/('scm_'+now_kst().strftime('%Y%m%d_%H%M%S_%f')+'.sqlite')
        dst.parent.mkdir(parents=True,exist_ok=True)
        if dst.resolve()==self.path.resolve(): raise ConfigError('백업 목적지가 원본과 같습니다')
        with contextlib.closing(self.connect(readonly=True)) as src, contextlib.closing(sqlite3.connect(dst)) as target:
            src.backup(target)
            if target.execute('PRAGMA quick_check').fetchone()[0]!='ok': raise DataError('백업 무결성 검사 실패')
        return dst
    def prune(self,days=30):
        cutoff=(now_kst()-timedelta(days=days)).astimezone(timezone.utc).isoformat(timespec='seconds')
        with self.transaction() as con:
            con.execute('DELETE FROM raw_splunk_event WHERE received_at<?',(cutoff,))
            con.execute('DELETE FROM etl_run WHERE ended_at<?',(cutoff,))
            con.execute('DELETE FROM data_issue WHERE created_at<?',(cutoff,))
            # Current facts and monthly targets are NEVER removed by raw-log retention.

def source_fingerprint(d):
    excluded={'poll_seconds','overlap_seconds','max_events','bootstrap','enabled','max_window_seconds','notes','mapping_confirmed'}
    return digest({k:v for k,v in d.items() if k not in excluded})

def value_fact(con,r):
    rev=int(con.execute("SELECT value FROM meta WHERE key='reference_revision'").fetchone()[0])
    rows=con.execute("""SELECT c.period_ym,c.material,c.conv_code,c.conv_family,c.eq_per_unit
       FROM dim_conversion_component c
       JOIN reference_state s ON s.source_id=c.reference_source AND s.projection_ready=1
       WHERE c.material IN (?,substr(?,1,18)) AND c.period_ym IN (?, '')
       ORDER BY (c.material=?) DESC,(c.period_ym=?) DESC,c.conv_code""",
       (r['material'],r['material'],r['business_date'][:6],r['material'],r['business_date'][:6])).fetchall()
    chosen={}
    for row in rows: chosen.setdefault(row['conv_code'],row)
    eq=dram=flash=None;note='CONVERSION_UNMAPPED'
    if r['unit'] not in ('PC','EA'):
        note='UNIT_MISMATCH'
    elif chosen:
        eq=0;dram=0;flash=0
        for row in chosen.values():
            v=scaled(Decimal(r['qty_i'])/SCALE*Decimal(row['eq_per_unit']),round_ok=True)
            eq+=v
            if row['conv_family']=='DRAM':dram+=v
            elif row['conv_family']=='FLASH':flash+=v
        note='OK'
    con.execute("""INSERT INTO fact_valuation
     (source_id,record_key,event_hash,reference_revision,eq_i,eq_dram_i,eq_flash_i,note)
     VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(source_id,record_key)
     DO UPDATE SET event_hash=excluded.event_hash,reference_revision=excluded.reference_revision,
     eq_i=excluded.eq_i,eq_dram_i=excluded.eq_dram_i,eq_flash_i=excluded.eq_flash_i,note=excluded.note""",
     (r['source_id'],r['record_key'],r['event_hash'],rev,eq,dram,flash,note))

def revalue_all(con):
    for domain in DOMAINS:
        cur=con.execute(f'SELECT * FROM {domain}_current')
        while True:
            rows=cur.fetchmany(2000)
            if not rows: break
            for r in rows: value_fact(con,r)
