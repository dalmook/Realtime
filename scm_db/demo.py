"""Synthetic demonstration only. No company rows or credentials are shipped."""
from __future__ import annotations
import contextlib, copy, json, os, sqlite3, time, uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from .common import *
from .settings import Settings
from .database import Database
from .reference import publish


def demo_config(root):
    cfg=json.loads((Path(root)/'config/pipeline.json').read_text(encoding='utf-8-sig'))
    inbound=cfg['splunk_sources'][0]
    inbound['fields']['customer_key']='CUSTOMER'
    for d in cfg['splunk_sources'][1:]:
        d.update(enabled=True,mapping_confirmed=True,inventory_semantics_confirmed=True,table='DEMO_'+d['domain'].upper(),allow_event_time_version=False,scope_filters={'PLANT':['P1M1']})
        if d['domain']=='inventory':
            d['key_fields']=['BIN','ITEM']; d['fields']={'material':'ITEM','quantity':'STOCK_QTY','unit':{'value':'PC'},'plant':'PLANT','warehouse':'WH',
             'location':'BIN','box_no':'BOX','document_no':None,'customer_key':'CUSTOMER','business_date':'SNAPDATE','business_time':'SNAPTIME',
             'modified_date':'CHANGE_DATE','modified_time':'CHANGE_TIME','generated_timestamp':'CURRENT_TIMESTAMP'}
        else:
            d['key_fields']=['DELIVERY','ITEMNO']; d['fields']={'material':'MATERIAL','quantity':'SHIP_QTY','unit':{'value':'PC'},'plant':'PLANT','warehouse':'WAREHOUSE',
             'location':None,'box_no':'BOX','document_no':'DELIVERY','customer_key':'CUSTOMER','business_date':'SHIP_DATE','business_time':'SHIP_TIME',
             'modified_date':'CHANGE_DATE','modified_time':'CHANGE_TIME','generated_timestamp':'CURRENT_TIMESTAMP'}
    for d in cfg['oracle_sources']:
        m=d['mapping']; m['confirmed']=True
        m['filters']={};m.pop('row_key_fields',None);m.pop('query_file',None);d['query_file']=None
        if d['kind']=='conversion': m['fields']={'material':'ITEM','period_ym':'YM','unit':{'value':'PC'},'eq_per_unit':'FACTOR'}
        elif d['kind']=='customer': m['fields']={'customer_key':'CODE','customer_name':'NAME','customer_group':'GROUP_NAME'}
        elif d['kind'].endswith('_plan'):
            m['fields']={'period_ym':'YM','plan_version':'VERSION'}
            m['scope_confirmed']=True
            m['grain']={'material':'ITEM','product_group':None,'customer_key':None,'plant':'PLANT','warehouse':None}
            m['metrics']=[{'field':'TARGET_BOX','metric':'BOX','multiplier':'1'},{'field':'TARGET_EA','metric':'EA','multiplier':'1'}]
    return cfg


def fake_tables(period=None):
    period=period or now_kst().strftime('%Y%m')
    return {
      'product':[{'ITEM':'DEMO_A','PRODUCT':'예시 제품 A','PRODUCTGROUP':'예시 DRAM'},{'ITEM':'DEMO_B','PRODUCT':'예시 제품 B','PRODUCTGROUP':'예시 NAND'}],
      'conversion':[{'ITEM':'DEMO_A','YM':period,'FACTOR':'2'},{'ITEM':'DEMO_B','YM':period,'FACTOR':'0.5'}],
      'customer':[{'CODE':'C01','NAME':'예시 거래선','GROUP_NAME':'예시 조직'}],
      'inbound_plan':[{'YM':period,'ITEM':'DEMO_A','PLANT':'P1M1','VERSION':'CONFIRMED','TARGET_BOX':'10','TARGET_EA':'2000'},
                      {'YM':period,'ITEM':'DEMO_B','PLANT':'P1M1','VERSION':'CONFIRMED','TARGET_BOX':'5','TARGET_EA':'1000'}],
      'shipment_plan':[{'YM':period,'ITEM':'DEMO_A','PLANT':'P1M1','VERSION':'CONFIRMED','TARGET_BOX':'8','TARGET_EA':'1200'}]
    }


def stage_tables(path,tables):
    metadata={}
    with contextlib.closing(sqlite3.connect(path)) as con:
        for id,rows in tables.items():
            columns=list(rows[0]) if rows else []
            table='raw_oracle_'+id
            con.execute(f'CREATE TABLE {table}(__scm_row_no INTEGER PRIMARY KEY,__scm_json TEXT NOT NULL,'+','.join(qname(c)+' TEXT' for c in columns)+')')
            for i,row in enumerate(rows,1):
                con.execute(f'INSERT INTO {table} VALUES('+','.join('?' for _ in range(len(columns)+2))+')',(i,js(row),*[row.get(c) for c in columns]))
            metadata[id]={'table':table,'columns':[{'name':c,'oracle_type':'DEMO_ONLY','precision':None,'scale':None} for c in columns],'rows':len(rows)}
        con.commit()
    return metadata


def event(d,*,key='000001',box='BOX001',material='DEMO_A',qty='375',at=None,changed=None,**extras):
    at=at or now_kst().replace(microsecond=0)-timedelta(minutes=10)
    changed=changed or at+timedelta(seconds=2)
    generated=changed+timedelta(seconds=1)
    vals={'document_no':key,'box_no':box,'material':material,'quantity':qty,'unit':'PC','plant':'P1M1','warehouse':'63N0','location':'FC6N','customer_key':'C01',
          'business_date':at.strftime('%Y%m%d'),'business_time':at.strftime('%H%M%S'),'modified_date':changed.strftime('%Y%m%d'),'modified_time':changed.strftime('%H%M%S'),
          'generated_timestamp':generated.astimezone(timezone.utc).strftime('%Y%m%d%H%M%S')}
    raw={'EVENT_TYPE':'TREAD_DYN','TABNAME':d['table'],'C_ID':'CO','MANDT':'100'}
    for name,spec in d['fields'].items():
        if isinstance(spec,str): raw[spec]=vals.get(name,'')
    for field in d['key_fields']:
        raw.setdefault(field,key)
    raw.update(extras)
    return {'_raw':json.dumps(raw,ensure_ascii=False),'event_epoch':changed.timestamp(),'indexed_epoch':generated.timestamp()}


def run_demo(root):
    base=Path(os.getenv('LOCALAPPDATA',str(Path.home()/'.local/share')))/'SCMRealtimeDB'/'demo'
    # A timestamped directory prevents accidental replacement of previous demo or live databases.
    path=base/now_kst().strftime('%Y%m%d_%H%M%S_%f')
    cfg=demo_config(root); s=Settings(root,env={},config=cfg,data_dir=path)
    db=Database(s.db_path,root); db.initialize(cfg)
    staging=path/'synthetic.sqlite'; metadata=stage_tables(staging,fake_tables())
    run=db.start_run('oracle_all','SYNTHETIC_DEMO'); publish(db,s,staging,metadata,run); staging.unlink()
    now=now_kst(); at=now-timedelta(minutes=30)
    d=cfg['splunk_sources'][0]
    rows=[event(d,key='R1',box='BOX001',qty='100',at=at),event(d,key='R1',box='BOX001',qty='375',at=at,changed=at+timedelta(minutes=5)),
          event(d,key='R2',box='BOX002',qty='375',at=at+timedelta(minutes=10)),
          event(d,key='R3',box='BOX003',material='DEMO_B',qty='500',at=at+timedelta(minutes=15))]
    db.ingest(d,rows,int(time.time())-10,month_start_epoch())
    for d in cfg['splunk_sources'][1:]: db.ingest(d,[event(d,key='D01',qty='200',at=at)],int(time.time())-10,month_start_epoch())
    print('SYNTHETIC DEMO ONLY · 외부 DB/API 호출 없음')
    print('DB:',db.path)
    for view in ('v_inbound_daily','v_inventory_balance','v_shipment_daily','v_monthly_progress'):
        print('\n['+view+']')
        for row in db.query('SELECT * FROM '+view): print(js(row))
