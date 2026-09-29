"""Terminal-only mapping assistant. It never invents unconfirmed source columns."""
from __future__ import annotations
import copy, json, shutil
from pathlib import Path
from .common import *
from .reference import DIMENSIONS

def choose(columns,label,default=None,optional=False):
    print('\n'+label)
    if default is not None: print('현재:',js(default))
    raw=input('컬럼 번호/이름 입력, 상수는 =값'+(' / 비우면 미사용' if optional else '')+': ').strip()
    if not raw:
        if default is not None: return default
        if optional: return None
        raise ConfigError('필수 컬럼 선택을 취소했습니다. 설정을 저장하지 않습니다')
    if raw.startswith('='): return {'value':raw[1:]}
    if raw.isdigit():
        num=int(raw)
        if not 1<=num<=len(columns): raise ConfigError('컬럼 번호 범위 오류')
        return columns[num-1]
    matches=[c for c in columns if c.upper()==raw.upper()]
    if len(matches)!=1: raise ConfigError('목록에 없는 컬럼입니다. 설정을 저장하지 않습니다')
    return matches[0]

def save_config(s,config):
    path=s.root/'config/pipeline.json'
    backup=path.with_name('pipeline.before_'+now_kst().strftime('%Y%m%d_%H%M%S_%f')+'.json')
    shutil.copy2(path,backup)
    atomic_text(path,json.dumps(config,ensure_ascii=False,indent=2)+'\n')
    print('저장:',path,'\n이전 설정:',backup)

def map_oracle(s,db,source_id):
    config=copy.deepcopy(s.config)
    d=next((x for x in config['oracle_sources'] if x['id']==source_id),None)
    if not d: raise ConfigError('Oracle id를 확인하세요: product/conversion/customer/inbound_plan/shipment_plan')
    state=db.query('SELECT * FROM reference_state WHERE source_id=?',(source_id,))[0]
    cols=[c['name'] for c in json.loads(state['columns_json'])]
    if not cols:
        catalog=s.data_dir/'exports/oracle_schema_discovered.json'
        if catalog.exists(): cols=[c['name'] for c in json.loads(catalog.read_text(encoding='utf-8')).get(source_id,{}).get('columns',[])]
    if not cols: raise ConfigError('Oracle 구조 확인 또는 Oracle 최초 복제부터 실행하세요. 실제 컬럼 목록이 필요합니다')
    print('\n원천:',d['table'])
    for i,c in enumerate(cols,1): print(f'{i:3}. {c}')
    m=d['mapping']; f=m.setdefault('fields',{})
    kind=d['kind']
    if kind=='product':
        for k,label in [('material','자재번호'),('product_name','제품명'),('product_group','제품군')]: f[k]=choose(cols,label,f.get(k))
    elif kind=='conversion':
        f['material']=choose(cols,'자재 연결키 (Splunk MATNR과 연결되는 값)',f.get('material'))
        f['period_ym']=choose(cols,'환산 적용월 YYYYMM (월과 무관하면 = 입력)',f.get('period_ym'),True) or {'value':''}
        f['unit']=choose(cols,'원본 단위 (현재 입고는 PC이므로 =PC)',f.get('unit'))
        f['eq_per_unit']=choose(cols,'원본 수량 1개당 EQ 계수',f.get('eq_per_unit'))
        mul=input('계수를 기본 EQ 단위로 바꾸는 배수 [1]: ').strip() or '1'; decimal(mul); m['factor_multiplier']=mul
        if input('QTY × 계수 × 배수 = 기본 EQ 수량이 맞습니까? YES 입력: ').strip()!='YES': raise ConfigError('환산 산식 확인 전에는 활성화하지 않습니다')
    elif kind=='customer':
        f['customer_key']=choose(cols,'거래선 고유 연결키',f.get('customer_key'))
        f['customer_name']=choose(cols,'거래선명',f.get('customer_name'))
        f['customer_group']=choose(cols,'거래선/조직 그룹',f.get('customer_group'),True)
    else:
        f['period_ym']=choose(cols,'목표월 YYYYMM (일 목표로 나누지 않습니다)',f.get('period_ym'))
        f['plan_version']=choose(cols,'계획 버전. 단일 확정본만 있으면 =BASE',f.get('plan_version'))
        metric=input('목표 단위 EA / BOX / EQ / EQ_100M: ').strip().upper()
        if metric not in {'EA','BOX','EQ','EQ_100M'}: raise ConfigError('지원되지 않는 목표 단위')
        quantity=choose(cols,'월 목표 수량 컬럼')
        multiplier=input('기본 단위 환산 배수 [EQ_100M은 100000000, 그 외 1]: ').strip() or ('100000000' if metric=='EQ_100M' else '1')
        decimal(multiplier)
        m['metrics']=[{'field':quantity,'metric':'EQ' if metric=='EQ_100M' else metric,'display_unit':metric,'multiplier':multiplier}]
        grain={}
        for k,label in [('material','제품 코드'),('product_group','제품군'),('customer_key','거래선'),('plant','PLANT'),('warehouse','창고')]:
            grain[k]=choose(cols,f'목표 집계단위 - {label} (그 단위가 없으면 비움)',m.get('grain',{}).get(k),True)
        m['grain']=grain
        print('동일 차원의 여러 원천 행은 기본 오류로 처리합니다. 필요 시 JSON의 row_key_fields 및 aggregation=sum을 확인해 설정하세요.')
        print('연결할 실적:',', '.join(m.get('actual_sources',[])))
        print('입고의 현재 실적 범위는 P1M1, C_ID CO/GO 입니다. 다른 범위의 목표를 그대로 비교하면 안 됩니다.')
        if input('선택한 목표와 실적의 범위/단위가 동일합니까? YES 입력: ').strip()!='YES': raise ConfigError('목표·실적 범위 확인이 필요합니다')
        m['scope_confirmed']=True
    m['confirmed']=True
    print('\n적용 매핑:\n'+json.dumps(m,ensure_ascii=False,indent=2))
    if input('이 매핑을 저장하려면 SAVE 입력: ').strip()!='SAVE': print('취소했습니다.'); return
    save_config(s,config)
    print('로컬 기준정보 재매핑 명령을 실행하면 Oracle 재조회 없이 저장된 원본으로 검증합니다.')

def map_source(s,db,source_id):
    from .connectors.splunk import SplunkClient
    config=copy.deepcopy(s.config)
    d=next((x for x in config['splunk_sources'] if x['id']==source_id),None)
    if not d: raise ConfigError('등록된 source id를 지정하세요')
    if db.state(source_id)['watermark']: raise ConfigError('기수집 원천은 새로운 source id로 등록하거나 reset-source 후 매핑하세요')
    print('등록:',source_id,'업무:',d['domain'])
    d['table']=input('확인된 Splunk TABNAME: ').strip(); identifier(d['table'])
    name=d.get('connection','DEP'); client=SplunkClient(s.profile(name))
    q=lambda x:json.dumps(str(x))
    spl=f'search index={d["index"]} source={q(d["source"])} EVENT_TYPE={q(d.get("event_type","TREAD_DYN"))} TABNAME={q(d["table"])} earliest=-7d latest=now | head 50 | table _raw'
    sample=client.search(spl,100)
    cols=set()
    for e in sample:
        try: obj=json.loads(e['_raw']); cols.update(obj.keys())
        except (KeyError,ValueError,AttributeError): continue
    cols=sorted(cols)
    if not cols: raise ConfigError('표본에 JSON 컬럼이 없습니다. 원천 테이블/시간 범위를 확인하세요')
    for i,c in enumerate(cols,1): print(f'{i:3}. {c}')
    raw=input('행 고유키 컬럼명을 쉼표로 입력 (예: MANDT,CHIT,CHARG): ').strip()
    keys=[x.strip() for x in raw.split(',') if x.strip()]
    if not keys or any(x not in cols for x in keys): raise ConfigError('고유키 선택 오류')
    d['key_fields']=keys
    for k,label,optional in [('material','자재번호',False),('quantity','원수량',False),('unit','원단위',False),
       ('business_date','업무일자 (YYYYMMDD)',False),('business_time','업무시간 (HHMMSS)',False),
       ('modified_date','수정일자',False),('modified_time','수정시간',False),('generated_timestamp','수집 생성시각 UTC YYYYMMDDHHMMSS',True),
       ('box_no','BOX 번호 (없으면 비움)',True),('document_no','문서번호',True),('plant','PLANT',True),
       ('warehouse','창고',True),('location','저장위치',True),('customer_key','거래선 연결키 (ACCOUNT라고 임의 추정 금지)',True)]:
        d['fields'][k]=choose(cols,label,d.get('fields',{}).get(k),optional)
    if d['domain']=='inventory':
        print('증분 재고는 삭제/0수량 상태도 완전하게 전송되어야 합니다. 전체 스냅샷 원천은 이 모드를 쓰지 않습니다.')
        if input('이 원천이 최신행 UPSERT 방식이며 사라지는 재고도 전달됩니까? YES: ').strip()!='YES': raise ConfigError('재고 스냅샷/삭제 규칙 확인 후 등록하세요')
        d['inventory_semantics_confirmed']=True
    deletion=choose(cols,'삭제/취소 플래그 컬럼 (확인된 경우만)',None,True)
    if deletion:
        if not isinstance(deletion,str): raise ConfigError('삭제 플래그는 실제 컬럼이어야 합니다')
        vals=[x.strip() for x in input('삭제로 처리할 값, 쉼표 구분: ').split(',') if x.strip()]
        if not vals: raise ConfigError('삭제 상태값 누락')
        d['delete_rule']={'field':deletion,'values':vals}
    d['mapping_confirmed']=True; d['enabled']=True
    print(json.dumps(d,ensure_ascii=False,indent=2))
    if input('실적일/키/단위/삭제 의미를 확인했고 저장하려면 SAVE 입력: ').strip()=='SAVE': save_config(s,config)
