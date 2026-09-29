"""Focus items: transactional CRUD and dashboard-aligned date/metric semantics."""
from __future__ import annotations
import contextlib
from . import reporting as r, runtime

def _get_db():return runtime.connect(False)
def list_all_focus():
    with contextlib.closing(runtime.connect()) as con:
        return [dict(x) for x in con.execute('SELECT * FROM focus_item ORDER BY sort_order,focus_id')]
def list_focus():return [x for x in list_all_focus() if x['enabled']]

def _validate(f):
    if not isinstance(f,dict):raise ValueError('focus must be an object')
    kind=f.get('focus_type','item')
    if kind not in ('item','customer','customer_item'):raise ValueError('invalid focus_type')
    item=str(f.get('item_code') or '').strip() if kind!='customer' else ''
    cust=str(f.get('customer_code') or '').strip() if kind!='item' else ''
    if (kind!='customer' and not item) or (kind!='item' and not cust):raise ValueError('item/customer code required')
    if len(item)>100 or len(cust)>100:raise ValueError('code too long')
    if f.get('enabled',1) not in (0,1,False,True):raise ValueError('enabled must be boolean')
    label=str(f.get('label') or (f'ITEM {item}' if kind=='item' else f'거래선 {cust}' if kind=='customer' else f'{cust} / {item}')).strip()
    return kind,item or None,cust or None,label[:200],int(f.get('enabled',1))

def _insert(con,v):
    old=con.execute('SELECT focus_id FROM focus_item WHERE focus_type=? AND item_code IS ? AND customer_code IS ?',v[:3]).fetchone()
    if old:return {'focus_id':old['focus_id'],'ok':False,'reason':'duplicate'}
    cur=con.execute('INSERT INTO focus_item(focus_type,item_code,customer_code,label,enabled) VALUES(?,?,?,?,?)',v)
    return {'focus_id':cur.lastrowid,'ok':True}

def create_focus(focus_type,item_code=None,customer_code=None,label=None,enabled=1):
    v=_validate(locals())
    with contextlib.closing(_get_db()) as con,con:
        con.execute('BEGIN IMMEDIATE');return _insert(con,v)

def batch_create(items):
    if not isinstance(items,list) or len(items)>500:raise ValueError('items must be a list, maximum 500')
    vals=[_validate(x) for x in items]
    with contextlib.closing(_get_db()) as con,con:
        con.execute('BEGIN IMMEDIATE');res=[_insert(con,v) for v in vals]
        return {'results':res,'count':len(res)}

def delete_focus(focus_id):return {**delete_batch([focus_id]),'focus_id':focus_id}
def delete_batch(ids):
    if not isinstance(ids,list) or len(ids)>500:raise ValueError('invalid focus_ids')
    ids=[int(i) for i in ids]
    with contextlib.closing(_get_db()) as con,con:
        n=0
        for i in ids:n+=con.execute('DELETE FROM focus_item WHERE focus_id=?',(i,)).rowcount
        return {'ok':True,'deleted':n,'count':len(ids)}

def update_focus(focus_id,label=None,enabled=None,sort_order=None):
    clauses=[];bind=[]
    for k,v in [('label',label),('enabled',enabled),('sort_order',sort_order)]:
        if v is None:continue
        if k=='label':v=str(v).strip()[:200]
        elif k=='enabled':
            if v not in (0,1,False,True):raise ValueError('enabled must be boolean')
            v=int(v)
        else:v=int(v)
        clauses.append(k+'=?');bind.append(v)
    if not clauses:raise ValueError('no fields to update')
    with contextlib.closing(_get_db()) as con,con:
        cur=con.execute('UPDATE focus_item SET '+','.join(clauses)+",updated_at=datetime('now') WHERE focus_id=?",bind+[int(focus_id)])
        if not cur.rowcount:raise ValueError('Focus not found')
        return {'ok':True,'focus_id':focus_id}

def compute_focus_kpi(focus,con,metric='EA',as_of=None):
    day=as_of or r.asof(con,{})
    rules=[]
    if focus['focus_type']!='customer':rules.append({'field_key':'item','operator':'=','filter_value':focus['item_code'][:18]})
    if focus['focus_type']!='item':rules.append({'field_key':'customer_code','operator':'=','filter_value':focus['customer_code']})
    out={k:focus.get(k) for k in ('focus_id','label','focus_type','item_code','customer_code')}
    for direction in ('inbound','shipment'):
        m=r.aggregate(con,direction,metric,day[:6]+'01',day,rules);t=r.aggregate(con,direction,metric,day,day,rules)
        target=r.resolve_target(con,day[:6],direction,metric,rules);tv=target['target_value']
        out[direction]={'mtd':m['value'],'today':t['value'],'count':m['count'],'date':day,'status':m['status'],
                        'target':tv,'target_source':target['source'],'achievement':m['value']/tv*100 if m['value'] is not None and tv is not None and tv>0 else None}
    return out

def get_focus_kpi_all(metric='EA',as_of=None):
    if metric not in r.METRICS:raise ValueError('invalid metric')
    with contextlib.closing(runtime.connect()) as con:
        con.execute('BEGIN');day=r.asof(con,{'date':as_of} if as_of else {})
        rows=con.execute('SELECT * FROM focus_item WHERE enabled=1 ORDER BY sort_order,focus_id').fetchall()
        return {'metric':metric,'date':day,'count':len(rows),'items':[compute_focus_kpi(dict(f),con,metric,day) for f in rows]}

def handle_get(p):
    action=p.get('action','list')
    if action in ('list','list_all'):
        items=list_focus() if action=='list' else list_all_focus();return {'items':items,'count':len(items)}
    if action=='kpi':return get_focus_kpi_all(p.get('metric','EA'),p.get('date'))
    if action=='meta':return {'focus_types':['item','customer','customer_item'],'fields':['item_code','customer_code','label']}
    raise ValueError('unknown focus action')

def handle_post(b):
    action=b.get('action')
    if action=='create':return create_focus(b.get('focus_type','item'),b.get('item_code'),b.get('customer_code'),b.get('label'),b.get('enabled',1))
    if action=='batch_create':return batch_create(b.get('items',[]))
    if action=='delete':return delete_focus(b.get('focus_id'))
    if action=='delete_batch':return delete_batch(b.get('focus_ids',[]))
    if action=='update':return update_focus(b.get('focus_id'),b.get('label'),b.get('enabled'),b.get('sort_order'))
    raise ValueError('unknown focus action')
