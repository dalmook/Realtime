"""Manual target CRUD. Exact-scope priority, shared reporting, no live DB paths."""
from __future__ import annotations
import contextlib, math
from datetime import datetime
from . import runtime, reporting as r
from scm_db.common import KST

FIELD_WHITELIST=r.FIELDS
OPERATOR_WHITELIST=r.OPS
VALID_METRICS=set(r.METRICS)
VALID_DIRECTIONS={'inbound','shipment'}

def get_db(): return runtime.connect(False)
def _now():return datetime.now(KST).isoformat(timespec='seconds')
def _rules(con,tid):
    return [dict(x) for x in con.execute('SELECT field_key,operator,filter_value FROM manual_target_filter WHERE target_id=? ORDER BY seq',(tid,))]

def _validate(data,old=None):
    if not isinstance(data,dict):raise ValueError('body must be an object')
    d=dict(old or {});d.update(data)
    ym=r.valid_month(str(d.get('period_ym','')).strip());direction=d.get('direction','');metric=str(d.get('metric','EA')).upper()
    if direction not in VALID_DIRECTIONS or metric not in VALID_METRICS:raise ValueError('invalid direction/metric')
    name=str(d.get('target_name','')).strip()
    if not name or len(name)>200:raise ValueError('target_name required (max 200)')
    value=float(d.get('target_value',0))
    if not math.isfinite(value) or not 0<=value<=9e12:raise ValueError('target_value must be finite, 0..9 trillion')
    priority=int(d.get('priority',10))
    if not 0<=priority<=100000:raise ValueError('priority must be 0..100000')
    for f in ('enabled','additive'):
        if d.get(f,1 if f=='enabled' else 0) not in (0,1,False,True):raise ValueError(f+' must be boolean')
    return dict(period_ym=ym,direction=direction,metric=metric,target_name=name,target_value=value,priority=priority,
                enabled=int(d.get('enabled',1)),additive=int(d.get('additive',0)),memo=str(d.get('memo',''))[:2000],
                filters=r.normalize_rules(d.get('filters',[]),direction))

def _write(con,d,tid=None):
    now=_now();cols=['period_ym','direction','metric','target_name','target_value','priority','enabled','additive','memo']
    if tid is None:
        cur=con.execute('INSERT INTO manual_target('+','.join(cols)+',created_at,updated_at) VALUES('+','.join('?' for _ in range(len(cols)+2))+')',[d[k] for k in cols]+[now,now]);tid=cur.lastrowid
    else:
        con.execute('UPDATE manual_target SET '+','.join(k+'=?' for k in cols)+',updated_at=? WHERE target_id=?',[d[k] for k in cols]+[now,tid])
        con.execute('DELETE FROM manual_target_filter WHERE target_id=?',(tid,))
    con.executemany('INSERT INTO manual_target_filter(target_id,seq,field_key,operator,filter_value) VALUES(?,?,?,?,?)',
                    [(tid,i,x['field_key'],x['operator'],x['filter_value']) for i,x in enumerate(d['filters'])])
    return tid

def create_target(data):
    d=_validate(data)
    with contextlib.closing(get_db()) as con, con:
        tid=_write(con,d)
        return {'ok':True,'target_id':tid}

def update_target(tid,data):
    with contextlib.closing(get_db()) as con, con:
        row=con.execute('SELECT * FROM manual_target WHERE target_id=?',(int(tid),)).fetchone()
        if row is None:raise ValueError('Target not found')
        old=dict(row);old['filters']=_rules(con,tid)
        _write(con,_validate(data,old),tid)
        return {'ok':True,'target_id':tid}

def delete_target(tid):
    with contextlib.closing(get_db()) as con, con:
        con.execute('DELETE FROM manual_target_filter WHERE target_id=?',(int(tid),))
        cur=con.execute('DELETE FROM manual_target WHERE target_id=?',(int(tid),))
        return {'ok':True,'deleted':cur.rowcount>0,'target_id':tid}

def _compute_actual(con,period_ym,direction,metric,filters,as_of=None):
    r.valid_month(period_ym)
    import calendar
    end=period_ym+str(calendar.monthrange(int(period_ym[:4]),int(period_ym[4:]))[1])
    end=min(end,as_of or r.today())
    obj=r.aggregate(con,direction,metric,period_ym+'01',end,filters)
    return {'actual':obj['value'],'actual_value':obj['value'],'count':obj['count'],'status':obj['status'],
            'missing_count':obj['missing'],'note':obj.get('note',''),'as_of':end}

def _decorate(con,row,as_of=None):
    d=dict(row);d['filters']=_rules(con,d['target_id'])
    a=_compute_actual(con,d['period_ym'],d['direction'],d['metric'],d['filters'],as_of)
    d.update(actual=a['actual'],actual_value=a['actual'],actual_count=a['count'],status=a['status'],note=a['note'],
             achievement=a['actual']/d['target_value']*100 if a['actual'] is not None and d['target_value']>0 else None,
             remaining=d['target_value']-a['actual'] if a['actual'] is not None else None,source='MANUAL',as_of=a['as_of'])
    d['enabled']=bool(d['enabled']);d['additive']=bool(d['additive'])
    return d

def list_targets(period_ym=None,direction=None,as_of=None):
    clauses=[];bind=[]
    if period_ym:clauses.append('period_ym=?');bind.append(r.valid_month(period_ym))
    if direction:
        if direction not in VALID_DIRECTIONS:raise ValueError('invalid direction')
        clauses.append('direction=?');bind.append(direction)
    with contextlib.closing(runtime.connect()) as con:
        con.execute('BEGIN')
        rows=con.execute('SELECT * FROM manual_target'+(' WHERE '+' AND '.join(clauses) if clauses else '')+' ORDER BY period_ym DESC,priority,target_id',bind).fetchall()
        return {'targets':[_decorate(con,x,as_of) for x in rows]}

def get_target(tid):
    with contextlib.closing(runtime.connect()) as con:
        con.execute('BEGIN');row=con.execute('SELECT * FROM manual_target WHERE target_id=?',(int(tid),)).fetchone()
        if row is None:raise ValueError('Target not found')
        return _decorate(con,row)

def copy_target(tid,data=None):
    d=get_target(tid);d['target_name']+=' (복사)';d.update(data or {});res=create_target(d);res['copied_from']=tid;return res

def copy_month_targets(from_ym,to_ym,direction=None):
    r.valid_month(from_ym);r.valid_month(to_ym)
    if from_ym==to_ym:raise ValueError('source and target months must differ')
    if direction and direction not in VALID_DIRECTIONS:raise ValueError('invalid direction')
    with contextlib.closing(get_db()) as con, con:
        con.execute('BEGIN IMMEDIATE')
        rows=con.execute('SELECT * FROM manual_target WHERE period_ym=?'+(' AND direction=?' if direction else ''),[from_ym]+([direction] if direction else [])).fetchall()
        for row in rows:
            d=dict(row);d['filters']=_rules(con,d['target_id']);d['period_ym']=to_ym;_write(con,_validate(d))
        return {'ok':True,'copied_count':len(rows),'copied':len(rows),'from_ym':from_ym,'to_ym':to_ym}

def preview_target(data):
    ym=r.valid_month(data.get('period_ym',''));direction=data.get('direction','');metric=data.get('metric','EA').upper()
    filters=r.normalize_rules(data.get('filters',[]),direction)
    if metric not in VALID_METRICS:raise ValueError('invalid metric')
    with contextlib.closing(runtime.connect()) as con:
        con.execute('BEGIN');a=_compute_actual(con,ym,direction,metric,filters,data.get('date'))
        return {**a,'match_count':a['count'],'metric':metric,'direction':direction,'period_ym':ym}

def resolve_target(con,period_ym,direction,metric,filters=()):
    return r.resolve_target(con,period_ym,direction,metric,filters)

def resolve_target_api(p):
    return _resolve(r.valid_month(p.get('period_ym','')),p.get('direction'),p.get('metric','EA'),p.get('filters',[]))

def _resolve(ym,direction,metric,filters):
    if direction not in VALID_DIRECTIONS or metric not in VALID_METRICS:raise ValueError('invalid direction/metric')
    with contextlib.closing(runtime.connect()) as con:return resolve_target(con,ym,direction,metric,filters)

def build_filter_sql(filters,direction,param_prefix='tf'):return r.filter_sql(filters,direction,param_prefix)
def get_field_metadata():
    return {'fields':[{'key':k,'label':v[0],'shipment_available':True,'inbound_available':k not in ('country','sales_org','ship_type')} for k,v in r.FIELDS.items()],
            'operators':list(r.OPS),'note':'동일 조건은 우선순위 1건 적용. 겹치는 조건의 합산은 하지 않습니다.'}
