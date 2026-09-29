"""Shared read model for KPI, charts, tables, manual targets and focus items.

Returned values are real EA / BOX / USD / EQ, never storage-scale values.
No network requests or source mutations are made by this module.
"""
from __future__ import annotations
import calendar, contextlib, json, math
from datetime import datetime, timedelta, date
from scm_db.common import KST, SCALE
from . import runtime

METRICS=('EA','EQ_DRAM','EQ_FLASH','BOX','USD')
EXCLUDED=('63D0','63J0','63P0','13H0')
WH_MAP={'1310':'온양','1380':'인천','13Z0':'아레나스(3F)','13Y0':'아레나스(6F)',
        '63N0':'소주','53P0':'클락','53G0':'홍콩','13V0':'베트남'}
FIELDS={'customer_name':('거래선명','s.customer_name'), 'customer_code':('거래선코드','s.customer_key'),
        'product_group':('제품군','s.product_group'),'item':('ITEM','s.item_key'),
        'item_prefix':('ITEM Prefix','s.item_key'),'plant':('Plant','s.plant'),
        'warehouse':('창고','s.warehouse'),'country':('국가',"json_extract(s.payload_json,'$.ALAND')"),
        'sales_org':('판매법인',"json_extract(s.payload_json,'$.VKORG_ANA')"),
        'ship_type':('출하유형',"json_extract(s.payload_json,'$.FKART_ANA')")}
ALIASES={'soname':'customer_name','kunag':'customer_code','material':'item','material_prefix':'item_prefix',
         'aland':'country','vkorg':'sales_org','fkart':'ship_type'}
OPS=('=','!=','IN','NOT IN','Starts With','Contains','BETWEEN')

def today(): return datetime.now(KST).strftime('%Y%m%d')
def param(p,k,default=None):
    v=p.get(k,default)
    return v[0] if isinstance(v,list) else v

def valid_day(value):
    if not isinstance(value,str) or len(value)!=8 or not value.isdigit(): raise ValueError('date must be YYYYMMDD')
    datetime.strptime(value,'%Y%m%d')
    return value

def valid_month(value):
    if not isinstance(value,str) or len(value)!=6 or not value.isdigit(): raise ValueError('period must be YYYYMM')
    datetime.strptime(value,'%Y%m')
    return value

def clean_params(p):
    out={k:param(p,k) for k in p}
    if out.get('date'): valid_day(out['date'])
    for k in ('month','period_ym'):
        if out.get(k): valid_month(out[k])
    if out.get('metric'):
        out['metric']=str(out['metric']).upper()
        if out['metric'] not in METRICS: raise ValueError('metric not supported')
    if out.get('limit'):
        n=int(out['limit'])
        if not 1<=n<=500: raise ValueError('limit must be 1..500')
    if out.get('range') and out['range'] not in ('daily','weekly','monthly'): raise ValueError('range not supported')
    return out

def normalize_rules(filters,direction):
    if direction not in ('inbound','shipment','inventory'): raise ValueError('invalid direction')
    if not isinstance(filters,list) or len(filters)>30: raise ValueError('filters must be a list (maximum 30)')
    result=[]
    for f in filters:
        if not isinstance(f,dict): raise ValueError('filter must be an object')
        key=ALIASES.get(f.get('field_key'),f.get('field_key'))
        op={'STARTS_WITH':'Starts With','CONTAINS':'Contains'}.get(f.get('operator'),f.get('operator'))
        val=f.get('filter_value','')
        if key not in FIELDS or op not in OPS: raise ValueError('invalid field or operator')
        if direction!='shipment' and key in ('country','sales_org','ship_type'): raise ValueError('field unavailable in this direction')
        if not isinstance(val,str) or not val.strip() or len(val)>2000: raise ValueError('invalid filter value')
        val=val.strip()
        if op in ('IN','NOT IN','BETWEEN'):
            parts=[x.strip() for x in val.split(',') if x.strip()]
            if not parts or len(parts)>100 or (op=='BETWEEN' and len(parts)!=2): raise ValueError('invalid filter list')
            if op!='BETWEEN': parts=sorted(set(parts))
            val=','.join(parts)
        result.append({'field_key':key,'operator':op,'filter_value':val})
    return result

def filter_sql(filters,direction,prefix='f'):
    rules=normalize_rules(filters,direction); clauses=[]; bind={}
    for i,r in enumerate(rules):
        field=FIELDS[r['field_key']][1]; name=f'{prefix}{i}';val=r['filter_value'];op=r['operator']
        if op in ('IN','NOT IN','BETWEEN'):
            parts=val.split(',');ph=[]
            for j,x in enumerate(parts):bind[f'{name}_{j}']=x;ph.append(':'+f'{name}_{j}')
            clauses.append(f'{field} BETWEEN {ph[0]} AND {ph[1]}' if op=='BETWEEN' else f'{field} {op} ({",".join(ph)})')
        elif op in ('Starts With','Contains'):
            escaped=val.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
            bind[name]=('' if op=='Starts With' else '%')+escaped+'%'
            clauses.append(f"{field} LIKE :{name} ESCAPE '\\'")
        else:
            bind[name]=val;clauses.append(f'{field} {op} :{name}')
    return ' AND '.join(clauses) or '1=1',bind

def scope_rules(p):
    return [{'field_key':{'customer':'customer_code','item':'item'}.get(k,k),'operator':'=','filter_value':str(param(p,k))}
            for k in ('customer','warehouse','product_group','item') if param(p,k) not in (None,'','ALL')]

def canonical(filters,direction):
    return json.dumps(sorted(normalize_rules(filters,direction),key=lambda r:(r['field_key'],r['operator'],r['filter_value'])),sort_keys=True,ensure_ascii=False)

def cte(direction,metric,limit_start=False,limit_end=False):
    if direction not in ('inbound','shipment','inventory'): raise ValueError('invalid direction')
    if metric not in METRICS: raise ValueError('invalid metric')
    table='shipment_box_current' if direction=='shipment' and metric=='BOX' else direction+'_current'
    shipment=direction=='shipment' and metric!='BOX'
    # Restrict the expensive latest-amount window to the reporting period whenever possible.
    amount_where=''
    if shipment:
        clauses=[]
        if limit_start: clauses.append('business_date>=:cte_start')
        if limit_end: clauses.append('business_date<=:cte_end')
        if clauses: amount_where=' WHERE '+' AND '.join(clauses)
    amount_cte=(f"""WITH am AS (
      SELECT *,ROW_NUMBER() OVER(PARTITION BY record_key ORDER BY modified_us DESC,generated_us DESC,indexed_us DESC,source_id) rn
      FROM shipment_amount_current{amount_where}), """ if shipment else 'WITH ')
    joins=''
    customer="COALESCE(NULLIF(f.customer_key,''),'')"
    customer_name="COALESCE(NULLIF(c.customer_name,''),NULLIF(f.customer_key,''),'미분류')"
    usd='NULL';amount_source="'not_available'"
    if shipment:
        joins="""LEFT JOIN am a ON a.record_key=f.record_key AND a.rn=1
          LEFT JOIN shipment_amount_kzwi3 k ON k.vbeln=json_extract(f.record_key,'$[0]') AND k.posnr=json_extract(f.record_key,'$[1]')"""
        matched="a.deleted=0 AND a.scope_ok=1 AND a.document_no=f.document_no AND a.material=f.material"
        legacy_matched="k.vgbel=f.document_no AND k.matnr=f.material"
        usd=f"CASE WHEN a.record_key IS NOT NULL THEN CASE WHEN {matched} THEN a.amount_i END WHEN {legacy_matched} THEN k.kzwi3*{SCALE} END"
        customer="COALESCE(NULLIF(json_extract(a.payload_json,'$.KUNAG'),''),NULLIF(k.kunag,''),NULLIF(f.customer_key,''),'')"
        customer_name="COALESCE(NULLIF(json_extract(a.payload_json,'$.SONAME'),''),NULLIF(k.soname,''),NULLIF(c.customer_name,''),NULLIF(f.customer_key,''),'미분류')"
        amount_source="CASE WHEN a.record_key IS NOT NULL THEN 'CONTINUOUS' WHEN k.vbeln IS NOT NULL THEN 'LEGACY_SNAPSHOT' ELSE 'UNMATCHED' END"
    # Column list explicit: company DBs may have additional local columns.
    basecols=['source_id','record_key','document_no','box_no','material','qty_i','amount_i','unit','plant','warehouse','location',
              'business_date','business_time','business_us','modified_us','generated_us','indexed_us','scope_ok','deleted','payload_json']
    cols=','.join('f.'+c for c in basecols)
    # Product master key is exact first, normalized 18-char key second, deterministic one row.
    joins+=""" LEFT JOIN dim_product p ON p.material=COALESCE(
        (SELECT dp.material FROM dim_product dp WHERE dp.material=f.material),
        (SELECT dp.material FROM dim_product dp WHERE dp.material=substr(f.material,1,18)))
        AND EXISTS(SELECT 1 FROM reference_state r WHERE r.source_id=p.reference_source AND r.projection_ready=1)
       LEFT JOIN dim_customer c ON c.customer_key=f.customer_key
        AND EXISTS(SELECT 1 FROM reference_state r WHERE r.source_id=c.reference_source AND r.projection_ready=1)
       LEFT JOIN fact_valuation v ON v.source_id=f.source_id AND v.record_key=f.record_key
        AND v.event_hash=f.event_hash AND v.reference_revision=(SELECT CAST(value AS INTEGER) FROM meta WHERE key='reference_revision')"""
    return amount_cte+f"""r AS (SELECT {cols},substr(f.material,1,18) item_key,
      {customer} customer_key,{customer_name} customer_name,
      COALESCE(NULLIF(p.product_name,''),f.material) product_name,
      COALESCE(NULLIF(p.product_group,''),'UNMAPPED') product_group,
      COALESCE(json_extract(f.payload_json,'$.C_ID'),'') c_id,
      COALESCE(json_extract(f.payload_json,'$.I_TYPE'),'') i_type,
      v.eq_dram_i,v.eq_flash_i,{usd} usd_i,{amount_source} amount_source
      FROM {table} f {joins}) """

def base_filter(direction):
    parts=["s.deleted=0","s.scope_ok=1","s.plant='P1M1'",
           "s.warehouse NOT IN ('63D0','63J0','63P0','13H0')"]
    if direction=='inbound':
        parts+= ["s.c_id IN ('CO','GO')","s.i_type!='34'",
                 "COALESCE(json_extract(s.payload_json,'$.I_DATE'),'VALID') NOT IN ('','00000000')"]
    elif direction=='shipment': parts+=["s.document_no LIKE '6%'"]
    return ' AND '.join(parts)

def value_expr(direction,metric):
    if metric=='EA': return "CASE WHEN s.unit IN ('PC','EA') THEN s.qty_i END"
    if metric=='USD': return 's.usd_i' if direction=='shipment' else 'NULL'
    if metric=='BOX': return 's.qty_i' if direction=='shipment' else 'NULL'
    return 's.eq_dram_i' if metric=='EQ_DRAM' else 's.eq_flash_i'

def supported(direction,metric,filters=()):
    if metric=='USD' and direction!='shipment': return False,'금액 미제공'
    if direction=='shipment' and metric=='BOX':
        if not runtime.DEMO and not runtime.settings().flag('SHIPMENT_BOX_CONFIRMED',False):
            return False,'CARTON 수량 의미 미검증: SHIPMENT_BOX_CONFIRMED 설정 확인'
        if any(f['field_key'] not in ('plant','warehouse') for f in filters):
            return False,'출하 BOX의 ITEM/거래선별 배분 매핑 미제공'
    return True,''

def source_available(con,direction,metric):
    domain='shipment_box' if direction=='shipment' and metric=='BOX' else direction
    state=con.execute('SELECT MAX(last_success) ok FROM source_state WHERE domain=? AND enabled=1',(domain,)).fetchone()
    if state and state['ok']: return True
    return con.execute(f'SELECT 1 FROM {domain}_current LIMIT 1').fetchone() is not None

def aggregate(con,direction,metric,start,end,filters=(),group=None):
    ok,note=supported(direction,metric,filters)
    if not ok: return {'value':None,'observed':None,'count':0,'missing':0,'status':'not_available','note':note} if not group else []
    # Absence of a successful source is not an observed zero.
    if not source_available(con,direction,metric):
        return [] if group else {'value':None,'observed':None,'count':0,'missing':0,'status':'not_available','note':'원천 미수집'}
    where,bind=filter_sql(list(filters),direction)
    clause=base_filter(direction)+' AND '+where+' AND s.business_date BETWEEN :start AND :end'
    bind.update(start=start,end=end,cte_start=start,cte_end=end)
    group_expr={'date':'s.business_date','hour':"CASE WHEN s.business_time GLOB '[0-2][0-9][0-5][0-9][0-5][0-9]' AND substr(s.business_time,1,2)<'24' THEN substr(s.business_time,1,2) ELSE 'UNKNOWN' END",
                'item':'s.item_key','customer':'s.customer_key'}.get(group)
    if group and group_expr is None: raise ValueError('invalid grouping')
    if metric=='BOX' and direction!='shipment':
        val="COUNT(DISTINCT NULLIF(s.box_no,''))"; missing="SUM(CASE WHEN s.box_no='' THEN 1 ELSE 0 END)";scale=1
    else:
        ve=value_expr(direction,metric);val=f'SUM({ve})';missing=f'SUM(CASE WHEN {ve} IS NULL THEN 1 ELSE 0 END)';scale=SCALE
    extra=(f'{group_expr} group_key,MIN(s.product_name) product_name,MIN(s.product_group) product_group,MIN(s.customer_name) customer_name,' if group else '')
    sql=cte(direction,metric,True,True)+f'SELECT {extra} COUNT(*) count,{val} val,{missing} missing FROM r s WHERE {clause}'
    if group: sql+=' GROUP BY '+group_expr+' ORDER BY '+group_expr
    rows=con.execute(sql,bind).fetchall();result=[]
    for row in rows:
        d=dict(row);miss=d['missing'] or 0;v=float(d['val'] or 0)/scale
        d.update(value=None if miss else v,observed=v,missing=miss,status='partial' if miss else 'ok')
        d.pop('val');result.append(d)
    return result if group else result[0]

def latest(con,direction,metric='EA'):
    table='shipment_box_current' if direction=='shipment' and metric=='BOX' else direction+'_current'
    parts=["deleted=0","scope_ok=1","plant='P1M1'",
           "warehouse NOT IN ('63D0','63J0','63P0','13H0')","business_date<=:today"]
    if direction=='inbound':
        parts+=["COALESCE(json_extract(payload_json,'$.C_ID'),'') IN ('CO','GO')",
                "COALESCE(json_extract(payload_json,'$.I_TYPE'),'')!='34'",
                "COALESCE(json_extract(payload_json,'$.I_DATE'),'VALID') NOT IN ('','00000000')"]
    elif direction=='shipment':
        parts+=["document_no LIKE '6%'"]
    row=con.execute(f"SELECT MAX(business_date) d FROM {table} WHERE "+' AND '.join(parts),{'today':today()}).fetchone()
    return row['d']

def latest_dates(con):
    return {'inbound':latest(con,'inbound'),'shipment':latest(con,'shipment'),
            'shipment_box':latest(con,'shipment','BOX')}

def asof(con,p,dates=None):
    requested=param(p,'date')
    if requested:return min(valid_day(requested),today())
    dates=dates or latest_dates(con)
    return max((x for x in dates.values() if x),default=today())

def aggregate_windows(con,direction,metric,mstart,as_of,prev,filters=()):
    ok,note=supported(direction,metric,filters)
    def unavailable(status,note):
        item={'value':None,'observed':None,'count':0,'missing':0,'status':status,'note':note}
        return {'mtd':dict(item),'today':dict(item),'yesterday':dict(item)}
    if not ok:return unavailable('not_available',note)
    if not source_available(con,direction,metric):return unavailable('not_available','원천 미수집')
    where,bind=filter_sql(list(filters),direction)
    scan_start=min(mstart,prev)
    conds={'mtd':"s.business_date BETWEEN :mstart AND :asof",'today':"s.business_date=:asof",'yesterday':"s.business_date=:prev"}
    cols=[];inbound_box=metric=='BOX' and direction!='shipment';ve=None if inbound_box else value_expr(direction,metric)
    for name,cond in conds.items():
        cols.append(f"COALESCE(SUM(CASE WHEN {cond} THEN 1 ELSE 0 END),0) {name}_count")
        if inbound_box:
            cols.append(f"COUNT(DISTINCT CASE WHEN {cond} THEN NULLIF(s.box_no,'') END) {name}_val")
            cols.append(f"COALESCE(SUM(CASE WHEN {cond} AND s.box_no='' THEN 1 ELSE 0 END),0) {name}_missing")
        else:
            cols.append(f"COALESCE(SUM(CASE WHEN {cond} THEN {ve} END),0) {name}_val")
            cols.append(f"COALESCE(SUM(CASE WHEN {cond} AND {ve} IS NULL THEN 1 ELSE 0 END),0) {name}_missing")
    bind.update(mstart=mstart,asof=as_of,prev=prev,scan_start=scan_start,cte_start=scan_start,cte_end=as_of)
    sql=cte(direction,metric,True,True)+f"""SELECT {','.join(cols)} FROM r s
      WHERE {base_filter(direction)} AND {where} AND s.business_date BETWEEN :scan_start AND :asof"""
    row=con.execute(sql,bind).fetchone();scale=1 if inbound_box else SCALE;out={}
    for name in conds:
        count=row[name+'_count'] or 0;missing=row[name+'_missing'] or 0;observed=float(row[name+'_val'] or 0)/scale
        out[name]={'value':None if missing else observed,'observed':observed,'count':count,'missing':missing,
                   'status':'partial' if missing else 'ok','note':''}
    return out

def system_target(con,direction,metric,ym,filters):
    if metric=='BOX': return None,'목표 없음'
    # Only exact dimensions can filter system plans. Unknown/all-level plans cannot be apportioned.
    clauses=['direction=:direction','period_ym=:ym','metric=:metric','scope_confirmed=1',
             'EXISTS(SELECT 1 FROM reference_state r WHERE r.source_id=plan_monthly.reference_source AND r.projection_ready=1)']
    bind={'direction':direction,'ym':ym,'metric':'EA' if metric.startswith('EQ_') else metric}
    for i,f in enumerate(normalize_rules(filters,direction)):
        key={'item':'material','customer_code':'customer_key'}.get(f['field_key'],f['field_key'])
        if key not in ('material','customer_key','warehouse','plant','product_group') or f['operator']!='=':
            return None,'이 조건에 대응하는 시스템 목표 범위 없음'
        clauses.append(key+'=:p'+str(i));bind['p'+str(i)]=f['filter_value']
    rows=con.execute('SELECT * FROM plan_monthly WHERE '+' AND '.join(clauses),bind).fetchall()
    if not rows:return None,'목표 없음'
    # Inbound FWEEK are non-overlapping buckets of one PLANID snapshot, not revision versions.
    versions={r['plan_version'] for r in rows}
    if direction=='shipment' and len(versions)>1:return None,'계획 버전이 여러 개: 승인 버전 선택 필요'
    total=0.0
    for r in rows:
        value=r['target_i']/SCALE
        if metric.startswith('EQ_'):
            unit='PC-DRAM' if metric=='EQ_DRAM' else 'PC-FLASH'
            coeff=con.execute("""SELECT eq_per_unit FROM dim_conversion c WHERE material=? AND unit=? AND period_ym IN (?,'')
             AND EXISTS(SELECT 1 FROM reference_state rs WHERE rs.source_id=c.reference_source AND rs.projection_ready=1)
             ORDER BY period_ym DESC LIMIT 1""",(r['material'][:18],unit,ym)).fetchone()
            # A mapped material belonging to the other family legitimately contributes zero.
            if not coeff:
                other=con.execute("SELECT 1 FROM dim_conversion WHERE material=? AND period_ym IN (?,'')",(r['material'][:18],ym)).fetchone()
                if not other:return None,'목표 환산 마스터 누락'
                value=0
            else:value*=float(coeff['eq_per_unit'])
        total+=value
    return total,'Oracle plan_monthly'

def resolve_target(con,ym,direction,metric,filters=()):
    key=canonical(list(filters),direction)
    rows=con.execute('SELECT * FROM manual_target WHERE period_ym=? AND direction=? AND metric=? AND enabled=1 ORDER BY priority,target_id',(ym,direction,metric)).fetchall()
    matched=[]
    for r in rows:
        ff=[dict(x) for x in con.execute('SELECT field_key,operator,filter_value FROM manual_target_filter WHERE target_id=? ORDER BY seq',(r['target_id'],))]
        if canonical(ff,direction)==key:matched.append(r)
    if matched:
        # Same-scope targets overlap by definition. Pick one, never add overlapping amounts.
        r=matched[0]
        return {'source':'MANUAL','target_value':r['target_value'],'target_id':r['target_id'],'target_name':r['target_name'],
                'info':'동일 조건의 최우선 수기 목표','target_available':True}
    value,note=system_target(con,direction,metric,ym,list(filters))
    return {'source':'SYSTEM' if value is not None else 'NONE','target_value':value,'target_id':None,
            'target_name':'Oracle 목표' if value is not None else '목표 없음','target_available':value is not None,'info':note}

def kpi(p):
    p=clean_params(p);metric=p.get('metric','EA');filters=scope_rules(p)
    with contextlib.closing(runtime.connect()) as con:
        con.execute('BEGIN');dates=latest_dates(con);d=asof(con,p,dates)
        prev=(datetime.strptime(d,'%Y%m%d')-timedelta(days=1)).strftime('%Y%m%d');out={}
        for direction,name in [('inbound','production'),('shipment','shipment')]:
            windows=aggregate_windows(con,direction,metric,d[:6]+'01',d,prev,filters)
            m,t,y=windows['mtd'],windows['today'],windows['yesterday']
            target=resolve_target(con,d[:6],direction,metric,filters);tv=target['target_value'];actual=m['value']
            if direction=='inbound' and metric=='USD':target.update(target_available=False,target_value=None,source='NONE');tv=None
            out[name]={'target':tv,'target_available':target['target_available'],'target_source':target['source'],'target_id':target['target_id'],
                       'actual_mtd':actual,'actual_today':t['value'],'observed_actual_mtd':m['observed'],
                       'count_mtd':m['count'],'count_today':t['count'],'missing_count':m['missing'],'status':m['status'],'note':m.get('note',''),
                       'achievement':round(actual/tv*100,1) if actual is not None and tv is not None and tv>0 else None,
                       'yesterday':y['value'],'yoy_change':((t['value']-y['value'])/abs(y['value'])*100 if t['value'] is not None and y['value'] else None),
                       'date':d,'previous_business_date':prev}
        invcnt=con.execute('SELECT COUNT(*) FROM inventory_current WHERE deleted=0 AND scope_ok=1').fetchone()[0]
        inv=aggregate(con,'inventory',metric,'00010101','99991231',filters) if invcnt else {'value':None,'count':0,'status':'not_available'}
        out.update(inventory={'current':inv['value'],'available':None,'count':inv['count'],'status':inv['status'],
                              'note':'현재 스냅샷. 가용재고/과거재고 산출 규칙 미제공'},
                   metric=metric,date=d,inbound_as_of=d,shipment_as_of=d,latest_inbound_date=dates['inbound'],latest_shipment_date=dates['shipment'],
                   timestamp=datetime.now(KST).isoformat(),demo=runtime.DEMO)
        return out

def hourly(p):
    p=clean_params(p);metric=p.get('metric','EA');filters=scope_rules(p)
    with contextlib.closing(runtime.connect()) as con:
        con.execute('BEGIN');d=asof(con,p);out={};unknown={}
        for direction,name in [('inbound','production'),('shipment','shipment')]:
            ok,_=supported(direction,metric,filters);available=ok and source_available(con,direction,metric)
            rows=aggregate(con,direction,metric,d,d,filters,'hour') if available else []
            data={r['group_key']:r['value'] for r in rows}
            out[name]=[data.get(f'{h:02d}',0) if available else None for h in range(24)]
            unknown[name]=data.get('UNKNOWN',0) if available else None
        return {**out,'hours':[f'{h:02d}' for h in range(24)],'unknown_time':unknown,'current_hour':datetime.now(KST).hour,
                'inbound_date':d,'shipment_date':d,'metric':metric}

def daily(p):
    p=clean_params(p);metric=p.get('metric','EA');filters=scope_rules(p)
    with contextlib.closing(runtime.connect()) as con:
        con.execute('BEGIN');d=asof(con,p);ym=valid_month(p.get('month') or d[:6]);last=ym+str(calendar.monthrange(int(ym[:4]),int(ym[4:]))[1])
        end=min(last,p.get('date') or today());start=ym+'01';series={}
        for direction,name in [('inbound','production'),('shipment','shipment')]:
            series[name]={r['group_key']:r['value'] for r in aggregate(con,direction,metric,start,end,filters,'date')}
        usd={r['group_key']:r['value'] for r in aggregate(con,'shipment','USD',start,end,filters,'date')}
        dates=sorted(set().union(*[set(v) for v in series.values()],set(usd)))
        return {'month':ym,'metric':metric,'as_of':end,'daily':[{'date':x,'production':series['production'].get(x,0),'shipment':series['shipment'].get(x,0),'shipment_amount':usd.get(x)} for x in dates]}

def customers(p):
    p=clean_params(p);metric=p.get('metric','EA');filters=scope_rules(p)
    with contextlib.closing(runtime.connect()) as con:
        con.execute('BEGIN');d=asof(con,p);rg=p.get('range','daily');start=d[:6]+'01' if rg=='monthly' else (datetime.strptime(d,'%Y%m%d')-timedelta(days=6)).strftime('%Y%m%d') if rg=='weekly' else d
        rows=aggregate(con,'shipment',metric,start,d,filters,'customer');usd={r['group_key']:r['value'] for r in aggregate(con,'shipment','USD',start,d,filters,'customer')}
        total=aggregate(con,'shipment',metric,start,d,filters);amount=aggregate(con,'shipment','USD',start,d,filters)
        rows.sort(key=lambda r: (r['value'] is not None,r['value'] or 0),reverse=True);limit=int(p.get('limit',20));out=[]
        for r in rows[:limit]:
            out.append({'customer_key':r['group_key'],'name':r['customer_name'],'group':'','production':None,'shipment':r['value'],
                        'shipment_amount':usd.get(r['group_key']),'inventory':None,'count':r['count'],
                        'share':r['value']/total['value']*100 if r['value'] is not None and total['value'] else None})
        rest=rows[limit:]
        if rest:
            values=[r['value'] for r in rest];amounts=[usd.get(r['group_key']) for r in rest]
            v=sum(values) if all(v is not None for v in values) else None
            out.append({'customer_key':'__OTHERS__','name':'기타','group':'기타','production':None,'shipment':v,
                        'shipment_amount':sum(amounts) if all(x is not None for x in amounts) else None,
                        'inventory':None,'count':sum(r['count'] for r in rest),'share':v/total['value']*100 if v is not None and total['value'] else None})
        return {'customers':out,'total_production':aggregate(con,'inbound',metric,start,d,filters)['value'],
                'total_shipment':total['value'],'total_shipment_amount':amount['value'],'range':rg,'inbound_date':d,'shipment_date':d,'metric':metric}

def items(p):
    p=clean_params(p);metric=p.get('metric','EA');filters=scope_rules(p)
    with contextlib.closing(runtime.connect()) as con:
        con.execute('BEGIN');d=asof(con,p);maps={}
        for direction,name in [('inbound','production'),('shipment','shipment')]:
            maps[name]={r['group_key']:r for r in aggregate(con,direction,metric,d,d,filters,'item')}
        usd={r['group_key']:r['value'] for r in aggregate(con,'shipment','USD',d,d,filters,'item')};rows=[]
        for key in set(maps['production'])|set(maps['shipment']):
            i=maps['production'].get(key,{});s=maps['shipment'].get(key,{});r=i or s
            rows.append({'material':key,'name':r['product_name'],'product_group':r['product_group'],'production':i.get('value',0),
                         'shipment':s.get('value',0),'shipment_amount':usd.get(key),'inventory':None,'count':i.get('count',0)+s.get('count',0)})
        rows.sort(key=lambda r:max(r['production'] or 0,r['shipment'] or 0),reverse=True)
        return {'items':rows[:int(p.get('limit',30))],'date':d,'shipment_date':d,'metric':metric,'total_materials':len(rows),
                'total_production':aggregate(con,'inbound',metric,d,d,filters)['value'],
                'total_shipment':aggregate(con,'shipment',metric,d,d,filters)['value']}

def events(p):
    p=clean_params(p);filters=scope_rules(p);limit=int(p.get('limit',50));out=[]
    with contextlib.closing(runtime.connect()) as con:
        con.execute('BEGIN');d=asof(con,p)
        for direction in ('inbound','shipment'):
            wh,bind=filter_sql(filters,direction);bind.update(end=d,lim=limit)
            extra=' AND s.business_date=:end' if p.get('date') else ' AND s.business_date<=:end'
            rows=con.execute(cte(direction,'EA')+f'SELECT * FROM r s WHERE {base_filter(direction)} AND {wh} {extra} ORDER BY s.business_us DESC LIMIT :lim',bind).fetchall()
            for r in rows:
                tm=r['business_time'];amt=r['usd_i'];qty=r['qty_i']/SCALE
                out.append({'time':f'{tm[:2]}:{tm[2:4]}:{tm[4:6]}','date':r['business_date'],'type':'출하' if direction=='shipment' else '입고등록',
                    'detail':f"{r['item_key']} {qty:,.0f} EA"+(f' (${amt/SCALE:,.2f})' if direction=='shipment' and amt is not None else ' · 금액 미매칭' if direction=='shipment' else ''),
                    'warehouse':r['warehouse'],'customer':r['customer_name'],'us':r['business_us'],
                    'material':r['item_key'],'qty':qty,'id':r['source_id']+':'+r['record_key']})
    out.sort(key=lambda r:r['us'],reverse=True)
    for r in out:r.pop('us')
    return {'events':out[:limit],'timestamp':datetime.now(KST).isoformat()}

def progress(p):
    data=events({**p,'limit':'500'})
    return {'progress':[{'line':'P1M1','material':r['material'],'item_name':r['material'],'customer':r['customer'],
                         'qty':r['qty'],'warehouse':WH_MAP.get(r['warehouse'],r['warehouse']),'stage':'입고완료',
                         'stage_index':5,'is_new':False,'date':r['date'],'time':r['time'].replace(':','')}
                        for r in data['events'] if r['type']=='입고등록'][:15],
            'timestamp':data['timestamp'],'simulated':False,'note':'진행 단계 추정 없이 실제 수신 입고완료만 표시'}

def filters(p):
    with contextlib.closing(runtime.connect()) as con:
        con.execute('BEGIN')
        cust=con.execute(cte('shipment','EA')+f'SELECT customer_key,MIN(customer_name) name FROM r s WHERE {base_filter("shipment")} GROUP BY customer_key ORDER BY name LIMIT 500').fetchall()
        wh=con.execute("SELECT DISTINCT warehouse FROM inbound_current WHERE deleted=0 AND scope_ok=1 UNION SELECT DISTINCT warehouse FROM shipment_current WHERE deleted=0 AND scope_ok=1").fetchall()
        groups=con.execute("SELECT DISTINCT product_group FROM dim_product WHERE product_group!='' ORDER BY product_group").fetchall()
        prod=con.execute('SELECT material,product_name FROM dim_product ORDER BY material LIMIT 500').fetchall()
        return {'customers':[{'key':r['customer_key'],'name':r['name']} for r in cust if r['customer_key']],
                'warehouses':[{'key':r['warehouse'],'name':WH_MAP.get(r['warehouse'],r['warehouse'])} for r in wh if r['warehouse'] and r['warehouse'] not in EXCLUDED],
                'product_groups':[{'key':r[0],'name':r[0]} for r in groups],
                'items':[{'key':r['material'][:18],'name':r['product_name']} for r in prod]}

def health(p=None):
    with contextlib.closing(runtime.connect()) as con:
        rows=[dict(r) for r in con.execute('SELECT * FROM v_source_health')]
        return {'demo':runtime.DEMO,'sqlite_version':__import__('sqlite3').sqlite_version,'journal_mode':con.execute('PRAGMA journal_mode').fetchone()[0],
                'sources':rows,'inventory_connected':any(r['kind']=='inventory' and r.get('last_success') for r in rows)}

def alerts(p):
    h=health();out=[]
    for s in h['sources']:
        if s.get('last_error'):out.append({'level':'warning','msg':f"{s['source_id']}: {s['last_error']}"})
    if runtime.DEMO:out.append({'level':'info','msg':'합성 데이터 데모입니다. 회사 원천 서버에 접속하지 않습니다.'})
    elif not h['inventory_connected']:out.append({'level':'info','msg':'재고 미연동. 미수집 값을 0으로 보지 마세요.'})
    if not out:out.append({'level':'info','msg':'수집 상태는 수신 상태 메뉴에서 확인하세요. API 연결과 SAP 정합성 검증은 별개입니다.'})
    return {'alerts':out}

ROUTES={'/api/kpi':kpi,'/api/hourly':hourly,'/api/daily-trend':daily,'/api/customers':customers,
        '/api/items':items,'/api/events':events,'/api/inbound-progress':progress,'/api/alerts':alerts,
        '/api/filters':filters,'/api/health':health}
