"""Shared, dependency-free helpers. No business rules are inferred here."""
from __future__ import annotations
import contextlib, ctypes, hashlib, json, os, re, sqlite3, time
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
from pathlib import Path

KST = timezone(timedelta(hours=9), 'Asia/Seoul')
SCALE = 1_000_000
MAX_INT = 9_000_000_000_000_000_000
class ConfigError(ValueError): pass
class DataError(ValueError): pass
class UpstreamError(RuntimeError): pass

def now_kst(): return datetime.now(KST)
def stamp(): return datetime.now(timezone.utc).isoformat(timespec='seconds')
def js(value): return json.dumps(value, ensure_ascii=False, separators=(',', ':'), sort_keys=True, default=str)
def digest(value): return hashlib.sha256((value if isinstance(value,str) else js(value)).encode('utf-8')).hexdigest()
def truth(value): return str(value).strip().lower() in {'true','1','yes','y'}
def scalar(value):
    if isinstance(value, list):
        unique = {js(x):x for x in value}
        if len(unique) > 1: raise DataError('서로 다른 다중값 필드입니다')
        return next(iter(unique.values()), None)
    if isinstance(value, dict): raise DataError('스칼라 필드에 JSON 객체가 있습니다')
    return value

def text(value):
    value = scalar(value)
    return '' if value is None else str(value).strip()

def decimal(value):
    try: v=Decimal(text(value))
    except (InvalidOperation, ValueError): raise DataError('수량/환산값이 숫자가 아닙니다') from None
    if not v.is_finite(): raise DataError('NaN/Infinity는 허용하지 않습니다')
    return v

def scaled(value, *, round_ok=False):
    v=decimal(value)*SCALE
    if round_ok: v=v.to_integral_value(rounding=ROUND_HALF_EVEN)
    if v != v.to_integral_value(): raise DataError('소수점 6자리를 초과했습니다. 원문을 보존하고 반영을 중단합니다')
    if abs(v)>MAX_INT: raise DataError('정수 수량 저장 범위를 초과했습니다')
    return int(v)

def qname(name):
    if not isinstance(name,str) or not name or '\x00' in name: raise ConfigError('빈/잘못된 컬럼명')
    return '"'+name.replace('"','""')+'"'

def identifier(value, dotted=False):
    pat=r'[A-Za-z_][A-Za-z0-9_$#]*'
    if dotted: pat += r'(?:\.[A-Za-z_][A-Za-z0-9_$#]*)?'
    if not re.fullmatch(pat,str(value)): raise ConfigError(f'식별자 형식 오류: {value!r}')
    return str(value)

def ymd(value):
    if isinstance(value, datetime): return value.strftime('%Y%m%d')
    s=text(value).split('T')[0].split(' ')[0].replace('-','').replace('/','')
    if not re.fullmatch(r'\d{8}',s): raise DataError('일자는 YYYYMMDD여야 합니다')
    datetime.strptime(s,'%Y%m%d')
    return s

def ym(value):
    if isinstance(value, datetime): return value.strftime('%Y%m')
    s=text(value).split('T')[0].split(' ')[0].replace('-','').replace('/','')
    if len(s)==8: s=ymd(s)[:6]
    if not re.fullmatch(r'\d{6}',s): raise DataError('목표월은 YYYYMM이어야 합니다')
    datetime.strptime(s,'%Y%m'); return s

def hms(value):
    s=text(value).replace(':','')
    if not re.fullmatch(r'\d{1,6}',s): raise DataError('시간은 HHMMSS여야 합니다')
    s=s.zfill(6); datetime.strptime(s,'%H%M%S'); return s

def local_us(date_value,time_value):
    return int(datetime.strptime(ymd(date_value)+hms(time_value),'%Y%m%d%H%M%S').replace(tzinfo=KST).timestamp()*1_000_000)

def month_start_epoch(at=None):
    at=at or now_kst()
    return int(at.replace(day=1,hour=0,minute=0,second=0,microsecond=0).timestamp())

def period_bounds(period):
    d=datetime.strptime(ym(period),'%Y%m').replace(tzinfo=KST)
    end=(d.replace(day=28)+timedelta(days=4)).replace(day=1)
    return int(d.timestamp()), int(end.timestamp())

def field_value(row,spec):
    """A spec is a column name, {value: ...}, or {year_field, month_field}."""
    if spec is None: return None
    if isinstance(spec,str):
        if spec not in row: raise DataError(f'매핑 컬럼이 없습니다: {spec}')
        return scalar(row[spec])
    if isinstance(spec,dict) and 'value' in spec: return spec['value']
    if isinstance(spec,dict) and 'year_field' in spec:
        return text(row[spec['year_field']]).zfill(4)+text(row[spec['month_field']]).zfill(2)
    raise ConfigError('필드 매핑은 컬럼명 또는 {"value": ...} 형식이어야 합니다')

def require(row,spec,label):
    v=text(field_value(row,spec))
    if not v: raise DataError(f'{label} 필수값 누락')
    return v

def atomic_text(path:Path,value:str):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+f'.{os.getpid()}.tmp')
    try:
        tmp.write_text(value,encoding='utf-8'); os.replace(tmp,path)
    finally:
        with contextlib.suppress(OSError): tmp.unlink()

def local_disk_only(path:Path):
    if str(path).startswith(('\\\\','//')): raise ConfigError('DB는 공유폴더가 아닌 C:/D: 로컬 디스크에 두세요')
    if os.name=='nt':
        drive=path.resolve().anchor
        if ctypes.windll.kernel32.GetDriveTypeW(drive)==4:
            raise ConfigError('매핑된 네트워크 드라이브에는 DB를 만들지 않습니다. DATA_DIR을 로컬로 지정하세요')

def safe_error(exc):
    if isinstance(exc,(ConfigError,DataError,UpstreamError)): return str(exc)[:1200]
    # Never dump connection strings, request bodies, SQL data, credentials, or upstream response bodies.
    code=re.search(r'(?:ORA|DPI|DPY)-\d+',str(exc))
    return f'{type(exc).__name__}'+(' · '+code.group(0) if code else '')

class ProcessLock:
    """OS-owned lock: automatically released on crash, including on Windows."""
    def __init__(self,path): self.path=Path(path); self.fp=None
    def __enter__(self):
        self.path.parent.mkdir(parents=True,exist_ok=True); self.fp=open(self.path,'a+b')
        self.fp.seek(0); self.fp.write(b'0'); self.fp.flush(); self.fp.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(self.fp.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.fp.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except (OSError,BlockingIOError):
            self.fp.close(); self.fp=None
            raise ConfigError('수집기가 이미 실행 중입니다. 상태/조회는 가능하며 별도 수집 명령은 종료 후 실행하세요') from None
        return self
    def __exit__(self,*args):
        if self.fp:
            if os.name=='nt':
                import msvcrt
                self.fp.seek(0); msvcrt.locking(self.fp.fileno(),msvcrt.LK_UNLCK,1)
            self.fp.close()
