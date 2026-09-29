"""Oracle is read-only and strictly Thick. Driver is reused from the selected Python."""
from __future__ import annotations
import contextlib, importlib, json, os, re, sqlite3, threading, uuid
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from ..common import *
_LOCK=threading.Lock(); _READY=None

def driver_info():
    for name in ('oracledb','cx_Oracle'):
        try:
            module=importlib.import_module(name)
            return module,name
        except ImportError: pass
    raise ConfigError('현재 Python에 oracledb/cx_Oracle가 없습니다. Python 선택에서 기존 Oracle 설치 Python을 선택하세요. 자동 pip 설치는 하지 않습니다')

def read_sql(root,d):
    if d.get('query_file'):
        path=(Path(root)/d['query_file']).resolve()
        if not path.is_relative_to(Path(root).resolve()): raise ConfigError('Oracle SQL은 프로젝트 폴더 안의 파일이어야 합니다')
        sql=path.read_text(encoding='utf-8-sig')
        clean=re.sub(r'/\*.*?\*/|--[^\n]*','',sql,flags=re.S).strip().rstrip(';').strip()
        if not re.match(r'^(SELECT|WITH)\b',clean,re.I) or ';' in clean: raise ConfigError('단일 Oracle SELECT/WITH만 허용합니다')
        if re.search(r'\b(INSERT|UPDATE|DELETE|MERGE|DROP|ALTER|CREATE|TRUNCATE|EXECUTE|COMMIT|ROLLBACK)\b',clean,re.I): raise ConfigError('Oracle 변경 SQL은 허용하지 않습니다')
        return clean
    return 'SELECT * FROM '+identifier(d['table'],dotted=True)

def prepare_driver(settings):
    global _READY
    module,name=driver_info()
    lib=Path(settings.get('ORACLE_CLIENT_LIB_DIR',r'C:\instantclient')).expanduser()
    if os.name=='nt' and not (lib/'oci.dll').is_file(): raise ConfigError(f'oci.dll 없음: {lib}')
    with _LOCK:
        if _READY and _READY!=(name,str(lib)): raise ConfigError('Oracle Client 경로 변경 후 프로그램을 재시작하세요')
        if not _READY:
            init=getattr(module,'init_oracle_client',None)
            if not callable(init): raise ConfigError('Thick 초기화 지원 드라이버가 필요합니다')
            init(lib_dir=str(lib)); _READY=(name,str(lib))
        if callable(getattr(module,'is_thin_mode',None)) and module.is_thin_mode(): raise ConfigError('Thick 모드가 아닙니다. Thin으로 전환하지 않습니다')
    return module,name

def cell(value):
    if value is None: return None
    if hasattr(value,'read'): value=value.read()
    if isinstance(value,(bytes,bytearray)): return 'hex:'+bytes(value).hex()
    if isinstance(value,datetime): return value.isoformat(sep=' ',timespec='microseconds')
    if isinstance(value,date): return value.isoformat()
    out=str(value)
    if len(out.encode('utf-8'))>2*1024*1024: raise DataError('Oracle 단일 셀 2 MiB 한도 초과. 승인된 SELECT로 컬럼을 제한하세요')
    return out

class OracleClient:
    def __init__(self,settings): self.s=settings
    @contextlib.contextmanager
    def connection(self):
        s=self.s; module,name=prepare_driver(s)
        user=s.get('ORACLE_USER'); password=s.get('ORACLE_PASSWORD') or s.get('ORACLE_PW'); dsn=s.get('ORACLE_DSN')
        if not user or not password or not dsn: raise ConfigError('.env Oracle USER/PASSWORD/DSN 누락')
        con=None
        try:
            con=module.connect(user=user,password=password,dsn=dsn)
            con.call_timeout=s.number('ORACLE_TIMEOUT_MS',30000,1000,300000)
            # Avoid binary floating-point conversion for Oracle NUMBER, including old DB-API drivers.
            number=getattr(module,'DB_TYPE_NUMBER',getattr(module,'NUMBER',None))
            if name=='oracledb':
                def handler(cursor,metadata):
                    if metadata.type_code==number:
                        return cursor.var(str,size=180,arraysize=cursor.arraysize,outconverter=Decimal)
            else:
                def handler(cursor,col_name,default_type,size,precision,scale):
                    if default_type==number:
                        return cursor.var(str,size=180,arraysize=cursor.arraysize,outconverter=Decimal)
            con.outputtypehandler=handler
            with con.cursor() as cur: cur.execute('SET TRANSACTION READ ONLY')
            yield con
        finally:
            if con is not None:
                with contextlib.suppress(Exception): con.rollback()
                with contextlib.suppress(Exception): con.close()
    def discover(self):
        result={}
        with self.connection() as con:
            for d in self.s.oracle:
                if not d.get('enabled',True): continue
                with con.cursor() as cur:
                    cur.execute('SELECT * FROM ('+read_sql(self.s.root,d)+') WHERE 1=0')
                    result[d['id']]={'oracle_table':d['table'],'columns':[{'name':c[0],'oracle_type':str(c[1]),'precision':c[4],'scale':c[5]} for c in cur.description]}
        return result
    def stage(self):
        """All 5 tables use the same Oracle read-only transaction (one consistent database snapshot)."""
        path=self.s.data_dir/'staging'/('oracle_'+uuid.uuid4().hex+'.sqlite')
        path.parent.mkdir(parents=True,exist_ok=True)
        stage=sqlite3.connect(path)
        metadata={}
        try:
            with self.connection() as con:
                for d in self.s.oracle:
                    if not d.get('enabled',True): continue
                    table='raw_oracle_'+identifier(d['id'])
                    with con.cursor() as cur:
                        cur.arraysize=1000
                        cur.execute(read_sql(self.s.root,d))
                        columns=[str(c[0]) for c in cur.description]
                        if len({c.upper() for c in columns})!=len(columns): raise DataError(f"{d['id']}: Oracle 결과 컬럼 중복")
                        if any(c.upper().startswith('__SCM_') for c in columns): raise DataError('예약 컬럼 __SCM_ 충돌')
                        descr=[{'name':c[0],'oracle_type':str(c[1]),'precision':c[4],'scale':c[5]} for c in cur.description]
                        ddl=','.join(qname(c)+' TEXT' for c in columns)
                        stage.execute(f'CREATE TABLE {table}(__scm_row_no INTEGER PRIMARY KEY,__scm_json TEXT NOT NULL,{ddl})')
                        rowcount=0; placeholders=','.join('?' for _ in range(len(columns)+2))
                        while True:
                            batch=cur.fetchmany(1000)
                            if not batch: break
                            transformed=[]
                            for values in batch:
                                rowcount+=1
                                if rowcount>int(d.get('max_rows',500000)): raise DataError(f"{d['id']}: max_rows 초과. 잘린 결과는 반영하지 않습니다")
                                vals=[cell(v) for v in values]
                                transformed.append((rowcount,js(dict(zip(columns,vals))),*vals))
                            stage.executemany(f'INSERT INTO {table} VALUES({placeholders})',transformed)
                        if rowcount==0 and not d.get('allow_empty',False): raise DataError(f"{d['id']}: 빈 조회 결과. 이전 Oracle 전체 스냅샷 유지")
                        metadata[d['id']]={'table':table,'columns':descr,'rows':rowcount}
            stage.commit(); stage.close(); return path,metadata
        except BaseException:
            stage.close()
            with contextlib.suppress(OSError): path.unlink()
            raise
