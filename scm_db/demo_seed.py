"""Deterministic synthetic DB, isolated from all company configuration and data."""
from __future__ import annotations
import contextlib,json,random
from datetime import datetime,timedelta
from .common import KST,SCALE,js,digest,stamp,local_us,month_start_epoch
from .database import Database,FACT_COLUMNS,value_fact

def seed(settings,at=None):
    db=Database(settings.db_path,settings.root)
    if db.path.exists():
        with contextlib.closing(db.connect(True)) as c:
            table=c.execute("SELECT 1 FROM sqlite_master WHERE name='meta'").fetchone()
            flag=c.execute("SELECT value FROM meta WHERE key='demo_dataset'").fetchone() if table else None
            if not flag:raise ValueError('Refusing to seed a non-demo database. Choose an empty demo directory.')
            return db
    db.initialize(settings.config)
    from dashboard import runtime
    runtime.configure(settings,demo=True);runtime.ensure_runtime()
    at=at or datetime.now(KST);today=at.strftime('%Y%m%d');ym=today[:6];rng=random.Random(260929)
    with db.transaction() as c:
        c.execute("INSERT INTO meta VALUES('demo_dataset','synthetic-v1')")
        c.execute("UPDATE reference_state SET projection_ready=1,projection_note='SYNTHETIC',loaded_at=?,snapshot_id='demo'",(stamp(),))
        for i in range(1,9):c.execute('INSERT INTO dim_customer VALUES(?,?,?,?,?)',(f'DEMO-C{i:02}',f'예시 거래선 {chr(64+i)}','합성 거래선','customer','demo'))
        materials=[]
        for i in range(1,13):
            mat=f'DEMO-{i:03}-MEMORY';family='DRAM' if i%2 else 'FLASH';cust=f'DEMO-C{(i-1)%8+1:02}'
            materials.append((mat,family,cust))
            c.execute('INSERT INTO dim_product VALUES(?,?,?,?,?)',(mat,f'예시 {family} {i:02}',family,'product','demo'))
            c.execute('INSERT INTO dim_conversion VALUES(?,?,?,?,?,?)',('',mat,'PC-'+family,str(1.25 if family=='DRAM' else 4.5),'conversion','demo'))
            for direction,ps in [('inbound','inbound_plan'),('shipment','shipment_plan')]:
                for metric,value in [('EA',950000+i*15000)]+([('USD',(950000+i*15000)*(2+i*.13))] if direction=='shipment' else []):
                    c.execute('INSERT INTO plan_monthly VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                              (f'{ps}:{mat}:{metric}',ps,'demo',direction,ym,'BASE',metric,round(value*SCALE),metric,mat,family,cust,'P1M1','*',1))
            for ps,src in [('inbound_plan','inbound_dep'),('shipment_plan','shipment_dep')]:c.execute('INSERT OR IGNORE INTO plan_actual_source VALUES(?,?)',(ps,src))
        seq=0
        def put(domain,row):
            c.execute(f'INSERT INTO {domain}_current({",".join(FACT_COLUMNS)}) VALUES({",".join("?" for _ in FACT_COLUMNS)})',[row[k] for k in FACT_COLUMNS]);value_fact(c,row)
        def fact(src,key,mat,qty,day,hh,cust,wh,payload,doc,box='',amount=0,unit='EA'):
            tm=f'{hh:02}1500';us=local_us(day,tm)
            return dict(source_id=src,record_key=js(key),document_no=doc,box_no=box,material=mat,qty_i=round(qty*SCALE),amount_i=round(amount*SCALE),
                        unit=unit,plant='P1M1',warehouse=wh,location='',customer_key=cust,business_date=day,business_time=tm,
                        business_us=us,modified_us=us,generated_us=us,indexed_us=us,event_hash=digest(payload),scope_ok=1,deleted=0,payload_json=js(payload))
        for daynum in range(1,at.day+1):
            day=ym+f'{daynum:02}'
            for j,(mat,family,cust) in enumerate(materials):
                hh=(j*2+6)%24
                if daynum==at.day:hh=min(hh,max(0,at.hour-1))
                wh=['1310','1380','13Z0'][j%3];qty=18000+rng.randint(0,18000);seq+=1
                pay={'C_ID':'CO' if j%2 else 'GO','I_TYPE':'10','I_DATE':day,'GC_CODE':cust,'synthetic':True}
                put('inbound',fact('inbound_dep',[f'R{seq}',f'BOX-{seq}'],mat,qty,day,hh,cust,wh,pay,f'R{seq}',f'BOX-{seq}'))
                amount=(qty-2000)*(2+j*.13);key=[f'{seq:010}', '000010'];doc=f'6{seq:09}'
                pay={'KUNAG_ANA':cust,'VKORG_ANA':'DEMO','ALAND':'ZZ','FKART_ANA':'DEMO','synthetic':True}
                put('shipment',fact('shipment_dep',key,mat,qty-2000,day,hh,cust,wh,pay,doc))
                ap={'KUNAG':cust,'SONAME':f'예시 거래선 {chr(65+j%8)}','KZWI3':amount,'FKDAT':day,'synthetic':True}
                put('shipment_amount',fact('shipment_amount_dep',key,mat,0,day,hh,cust,wh,ap,doc,amount=amount,unit='USD'))
                put('shipment_box',fact('shipment_box_dep',[doc,str(12+j)],'N/A',12+j,day,hh,'',wh,{'synthetic':True},doc,box=str(12+j),unit='BOX'))
        for i,(mat,family,cust) in enumerate(materials):
            put('inventory',fact('inventory_dep',['BIN'+str(i),mat],mat,80000+i*1234,today,max(0,at.hour-1),cust,'1310',{'synthetic':True},'STOCK',box='STOCK-'+str(i)))
        c.execute('UPDATE source_state SET enabled=1,last_success=?,coverage_from=?,watermark=?,last_error=NULL',(stamp(),month_start_epoch(at),int(at.timestamp())))
        for direction,value in [('inbound',13900000),('shipment',13100000)]:
            cur=c.execute('INSERT INTO manual_target(period_ym,direction,metric,target_name,target_value,priority,enabled,additive,memo,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
              (ym,direction,'EA','예시 '+('입고' if direction=='inbound' else '출하')+' 전체 목표',value,10,1,0,'합성 데이터 / 자유롭게 수정 가능',stamp(),stamp()))
        for mat,_,cust in materials[:2]:c.execute('INSERT INTO focus_item(focus_type,item_code,label) VALUES(?,?,?)',('item',mat,'집중관리 '+mat))
    return db
