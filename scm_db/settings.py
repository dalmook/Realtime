from __future__ import annotations
import json, os, re
from pathlib import Path
from .common import ConfigError, truth, local_disk_only, identifier

def read_env(path):
    """Literal .env: no interpolation/escape expansion, so Windows paths/$ passwords survive."""
    values={}
    if not Path(path).exists(): return values
    for num,line in enumerate(Path(path).read_text(encoding='utf-8-sig').splitlines(),1):
        s=line.strip()
        if not s or s.startswith('#'): continue
        if s.startswith('export '): s=s[7:]
        key,sep,value=s.partition('=')
        if not sep or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',key.strip()): raise ConfigError(f'.env {num}행 형식 오류')
        value=value.strip()
        if value[:1] in {'"',"'"}:
            if len(value)<2 or value[-1]!=value[0]: raise ConfigError(f'.env {num}행 따옴표를 확인하세요')
            value=value[1:-1]
        else: value=re.split(r'\s+#',value,maxsplit=1)[0].rstrip()
        values[key.strip()]=value
    return values

class Settings:
    def __init__(self,root,*,env=None,config=None,data_dir=None):
        self.root=Path(root).resolve()
        project=read_env(self.root/'.env') if env is None else dict(env)
        # Defaults < process environment < explicit project .env.
        self.env={**read_env(self.root/'.env.example'), **os.environ, **project}
        self.config=config if config is not None else json.loads((self.root/'config/pipeline.json').read_text(encoding='utf-8-sig'))
        default=Path(os.getenv('LOCALAPPDATA',str(Path.home()/'.local/share')))/'SCMRealtimeDB'/'live'
        self.data_dir=Path(data_dir or self.get('DATA_DIR') or default).expanduser().resolve()
        local_disk_only(self.data_dir)
        self.db_path=self.data_dir/'scm_live.sqlite'
        self.validate()
    def get(self,key,default=''): return self.env.get(key,default)
    def flag(self,key,default=False): return truth(self.get(key,str(default)))
    def number(self,key,default,minimum=1,maximum=2**31):
        try: value=int(self.get(key,str(default)))
        except ValueError: raise ConfigError(f'{key}는 정수여야 합니다') from None
        if not minimum<=value<=maximum: raise ConfigError(f'{key} 범위 {minimum}..{maximum}')
        return value
    @property
    def splunk(self): return self.config['splunk_sources']
    @property
    def oracle(self): return self.config['oracle_sources']
    def source(self,id):
        for d in self.splunk:
            if d['id']==id: return d
        raise ConfigError('등록되지 않은 Splunk source id')
    def profile(self,name='DEP'):
        p=f'SPLUNK_{name}_'
        def get(k,default=''): return self.get(p+k,self.get('SPLUNK_'+k,default))
        from urllib.parse import urlsplit
        host=get('HOST').strip(); port=get('PORT','8089').strip()
        if not host: raise ConfigError('Splunk HOST가 비어 있습니다')
        try:
            u=urlsplit(host if '://' in host else 'https://'+host)
            if u.scheme!='https' or not u.hostname or u.username or u.password or u.path not in ('','/') or u.query or u.fragment:
                raise ValueError()
            if any(c.isspace() for c in u.netloc): raise ValueError()
            port_num=u.port or int(port)
            if not 1<=port_num<=65535: raise ValueError()
        except ValueError: raise ConfigError('Splunk HOST는 HTTPS 호스트 또는 https://호스트:포트 형식이어야 합니다') from None
        hostname='['+u.hostname+']' if ':' in u.hostname else u.hostname
        verify=truth(get('VERIFY_SSL','false')); ca=get('CA_BUNDLE')
        if verify and ca and not Path(ca).is_file(): raise ConfigError('Splunk CA_BUNDLE 파일을 찾을 수 없습니다')
        return {'base_url':f'https://{hostname}:{port_num}','user':get('USER'),'password':get('PASSWORD'),
                'verify':verify,'ca':ca if verify else '', 'proxy':get('PROXY'),
                'timeout':int(get('TIMEOUT','180'))}
    def validate(self):
        if self.config.get('schema_version')!=1: raise ConfigError('pipeline.json schema_version=1 필요')
        schedule=self.config.get('oracle_schedule',{})
        if not re.fullmatch(r'\d{2}:\d{2}',schedule.get('at','09:00')): raise ConfigError('Oracle 갱신 시각은 HH:MM')
        if schedule.get('timezone','Asia/Seoul')!='Asia/Seoul': raise ConfigError('이 버전의 스케줄 시간대는 Asia/Seoul입니다')
        if schedule.get('catch_up',True) is not True or schedule.get('scheduled_attempts_per_day',1)!=1:
            raise ConfigError('이 버전은 09시 이후 catch-up 및 하루 예약 1회 정책입니다')
        hh,mm=map(int,schedule.get('at','09:00').split(':'))
        if hh>23 or mm>59: raise ConfigError('Oracle 갱신 시각 오류')
        seen=set()
        for d in self.splunk:
            identifier(d['id'])
            if d['id'] in seen: raise ConfigError('source id 중복')
            seen.add(d['id'])
            if d['domain'] not in {'inbound','inventory','shipment','shipment_box','shipment_amount'}: raise ConfigError('업무 domain 오류')
            if not d.get('enabled'): continue
            if not d.get('mapping_confirmed'): raise ConfigError(f"{d['id']}: 원천 매핑을 확정해야 enabled=true 가능합니다")
            if not d.get('index') or not d.get('table') or not d.get('key_fields'): raise ConfigError(f"{d['id']}: index/table/key_fields 누락")
            if d.get('mode','upsert')!='upsert': raise ConfigError('자동 Splunk 수집은 upsert 모드만 지원합니다. 전체 스냅샷은 import-snapshot 명령 사용')
            if not 10<=int(d.get('poll_seconds',60))<=86400: raise ConfigError('poll_seconds는 10..86400')
            for key in d['key_fields']: identifier(key)
            for key in ['material','quantity','unit','business_date','business_time']:
                if d.get('fields',{}).get(key) is None: raise ConfigError(f"{d['id']}: {key} 필드 매핑 누락")
            if d['domain']=='inventory' and not d.get('inventory_semantics_confirmed'):
                raise ConfigError('재고는 삭제/스냅샷 의미를 확인한 후 inventory_semantics_confirmed=true 필요')
        for d in self.oracle:
            identifier(d['id']); identifier(d['table'],dotted=True)
            if d.get('kind') not in {'product','conversion','customer','inbound_plan','shipment_plan'}: raise ConfigError('Oracle kind 오류')
