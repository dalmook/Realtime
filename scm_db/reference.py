from __future__ import annotations
import contextlib, json, sqlite3, uuid
from decimal import Decimal
from .common import *
from .database import revalue_all

DIMENSIONS=('material','product_group','customer_key','plant','warehouse')

def mapping_fields(spec):
    if isinstance(spec,str): return {spec}
    if isinstance(spec,dict) and 'year_field' in spec: return {spec['year_field'],spec['month_field']}
    return set()

def precheck(d,columns):
    m=d.get('mapping',{})
    if not m.get('confirmed'): return 'MAPPING_REQUIRED'
    wanted=set()
    for spec in m.get('fields',{}).values(): wanted |= mapping_fields(spec)
    for spec in m.get('grain',{}).values(): wanted |= mapping_fields(spec)
    for x in m.get('metrics',[]): wanted |= mapping_fields(x.get('field'))
    wanted |= set(m.get('filters',{}))
    wanted |= set(m.get('row_key_fields',[]))
    missing=wanted-set(columns)
    if missing: raise DataError(f"{d['id']}: 없는 매핑 컬럼 {', '.join(sorted(missing))}")
    return ''

def project(con,d,snapshot_id,config):
    m=d.get('mapping',{}); kind=d['kind']; id=d['id']; table='raw_oracle_'+identifier(id)
    columns=[r[1] for r in con.execute(f'PRAGMA table_info({table})') if not r[1].startswith('__scm_')]
    note=precheck(d,columns)
    if note: return note,0
    if kind in {'inbound_plan','shipment_plan'}:
        if not m.get('scope_confirmed'): return 'TARGET_SCOPE_CONFIRMATION_REQUIRED',0
        if not m.get('actual_sources'): return 'ACTUAL_SOURCE_MAPPING_REQUIRED',0
        domain='inbound' if kind=='inbound_plan' else 'shipment'
        configured={s['id']:s for s in config['splunk_sources']}
        for actual in m['actual_sources']:
            if actual not in configured or configured[actual]['domain']!=domain: raise DataError('목표와 실적 원천 domain 불일치')
            if m.get('grain',{}).get('customer_key') and not configured[actual].get('fields',{}).get('customer_key'):
                raise DataError('거래선 목표를 비교하려면 실적의 customer_key 필드도 매핑해야 합니다')
    rows=con.execute(f'SELECT __scm_json FROM {table}')
    records={}; source_keys=set(); line_count=0
    for r in rows:
        row=json.loads(r[0])
        if any(text(row.get(k)) not in {str(x) for x in v} for k,v in m.get('filters',{}).items()): continue
        f=lambda name,default=None: field_value(row,m.get('fields',{}).get(name,{'value':default}))
        if kind=='product':
            key=require(row,m['fields']['material'],'자재')
            value=(key,text(f('product_name')),text(f('product_group')),id,snapshot_id)
        elif kind=='customer':
            key=require(row,m['fields']['customer_key'],'거래선 키')
            value=(key,text(f('customer_name')),text(f('customer_group')),id,snapshot_id)
        elif kind=='conversion':
            material=require(row,m['fields']['material'],'환산 자재')
            period=text(f('period_ym')); period=ym(period) if period else ''
            unit=text(f('unit','PC')).upper()
            if not unit: raise DataError('환산 기준 단위 누락')
            factor=decimal(f('eq_per_unit'))*decimal(m.get('factor_multiplier','1'))
            if factor<0: raise DataError('환산계수가 음수입니다')
            key=(period,material,unit)
            value=(*key,str(factor),id,snapshot_id)
        else:
            period=ym(f('period_ym'))
            version=text(f('plan_version','BASE'))
            if not version: raise DataError('계획 버전 누락')
            grain={k:require(row,m['grain'][k],k) if m.get('grain',{}).get(k) is not None else '*' for k in DIMENSIONS}
            line_key=tuple(require(row,k,'목표 원천키') for k in m.get('row_key_fields',[]))
            if line_key:
                if line_key in source_keys: raise DataError('목표 원천 row_key_fields 중복. 계획 버전/행 키를 확인하세요')
                source_keys.add(line_key)
            for metric in m.get('metrics',[]):
                name=metric['metric']; display=metric.get('display_unit',name)
                if name not in {'EA','BOX','EQ','USD'}: raise ConfigError('목표 metric은 EA/BOX/EQ/USD만 지원합니다')
                qty=decimal(field_value(row,metric['field']))*decimal(metric.get('multiplier','1'))
                if qty<0: raise DataError('월 목표는 음수일 수 없습니다')
                if name=='BOX' and qty!=qty.to_integral_value(): raise DataError('BOX 월목표는 정수여야 합니다')
                quantity=scaled(qty)
                key=(id,period,version,name,*[grain[k] for k in DIMENSIONS])
                pid=digest(key)
                value=(pid,id,snapshot_id,domain,period,version,name,quantity,display,*[grain[k] for k in DIMENSIONS],1)
                if key in records:
                    if m.get('aggregation','reject')=='sum' and line_key:
                        old=records[key]; new=old[7]+quantity
                        if abs(new)>MAX_INT: raise DataError('월 목표 합계 범위 초과')
                        records[key]=(*old[:7],new,*old[8:])
                    else: raise DataError('같은 월·버전·단위·집계차원의 목표가 중복입니다. 승인된 원천키와 aggregation=sum 설정이 필요합니다')
                else: records[key]=value
            if not m.get('metrics'): raise ConfigError('목표 metrics 매핑이 비어 있습니다')
            line_count+=1; continue
        if key in records and records[key]!=value:
            raise DataError(f'{id}: 동일 키의 기준정보 값 충돌. MAX로 임의 선택하지 않습니다')
        records[key]=value; line_count+=1
    if not records and not d.get('allow_empty_projection',False): raise DataError(f'{id}: 매핑 후 0행. 이전 정규화 테이블 유지')
    targets={'product':('dim_product',5),'customer':('dim_customer',5),'conversion':('dim_conversion',6),
             'inbound_plan':('plan_monthly',15),'shipment_plan':('plan_monthly',15)}
    dest,n=targets[kind]
    con.execute(f'DELETE FROM {dest} WHERE reference_source=?',(id,))
    if records: con.executemany(f'INSERT INTO {dest} VALUES({",".join("?" for _ in range(n))})',records.values())
    if kind.endswith('_plan'):
        con.execute('DELETE FROM plan_actual_source WHERE plan_source=?',(id,))
        con.executemany('INSERT INTO plan_actual_source VALUES(?,?)',[(id,x) for x in m['actual_sources']])
    return 'READY',len(records)

def publish(db,settings,stage_path,metadata,run_id):
    sid=uuid.uuid4().hex; when=stamp(); outcomes={}
    con=db.connect()
    try:
        con.execute('ATTACH DATABASE ? AS incoming',(str(stage_path),))
        con.execute('BEGIN IMMEDIATE')
        for d in settings.oracle:
            if d['id'] not in metadata: continue
            item=metadata[d['id']]; table=item['table']
            con.execute(f'DROP TABLE IF EXISTS main.{table}')
            create=con.execute("SELECT sql FROM incoming.sqlite_master WHERE type='table' AND name=?",(table,)).fetchone()[0]
            con.execute(create)
            con.execute(f'INSERT INTO {table} SELECT * FROM incoming.{table}')
            con.execute('''UPDATE reference_state SET snapshot_id=?,loaded_at=?,row_count=?,columns_json=?,projection_ready=0,projection_note='PROJECTING' WHERE source_id=?''',
              (sid,when,item['rows'],js(item['columns']),d['id']))
            con.execute('INSERT INTO reference_snapshot_log VALUES(?,?,?,?,?)',(sid,d['id'],when,item['rows'],digest(item['columns'])))
        for d in settings.oracle:
            if d['id'] not in metadata: continue
            con.execute('SAVEPOINT project_one')
            try:
                note,n=project(con,d,sid,settings.config)
                con.execute('RELEASE project_one')
            except Exception as exc:
                con.execute('ROLLBACK TO project_one'); con.execute('RELEASE project_one')
                note='MAPPING_ERROR: '+safe_error(exc); n=0
            con.execute('UPDATE reference_state SET projection_ready=?,projection_note=? WHERE source_id=?',(int(note=='READY'),note,d['id']))
            outcomes[d['id']]={'raw_rows':metadata[d['id']]['rows'],'mapped_rows':n,'status':note}
        con.execute("UPDATE meta SET value=CAST(value AS INTEGER)+1 WHERE key='reference_revision'")
        revalue_all(con)
        con.execute("UPDATE etl_run SET status='SUCCESS',ended_at=?,rows_read=?,rows_written=?,detail=? WHERE run_id=?",(when,sum(x['rows'] for x in metadata.values()),sum(x['mapped_rows'] for x in outcomes.values()),js(outcomes),run_id))
        con.commit()
    except BaseException:
        con.rollback(); raise
    finally: con.close()
    return outcomes

def project_cached(db,settings):
    result={}
    with db.transaction() as con:
        for d in settings.oracle:
            state=con.execute('SELECT snapshot_id FROM reference_state WHERE source_id=?',(d['id'],)).fetchone()
            if not state or not state[0]: result[d['id']]={'status':'NOT_LOADED'}; continue
            con.execute('SAVEPOINT mapping')
            try:
                note,n=project(con,d,state[0],settings.config); con.execute('RELEASE mapping')
            except Exception as exc:
                con.execute('ROLLBACK TO mapping'); con.execute('RELEASE mapping'); note='MAPPING_ERROR: '+safe_error(exc); n=0
            con.execute('UPDATE reference_state SET projection_ready=?,projection_note=? WHERE source_id=?',(int(note=='READY'),note,d['id']))
            result[d['id']]={'status':note,'mapped_rows':n}
        con.execute("UPDATE meta SET value=CAST(value AS INTEGER)+1 WHERE key='reference_revision'")
        revalue_all(con)
    return result
