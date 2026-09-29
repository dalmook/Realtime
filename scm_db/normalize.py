from __future__ import annotations
import json
from decimal import Decimal
from .common import *

def normalize(d,event):
    raw=event.get('_raw',event.get('raw',event))
    if isinstance(raw,str):
        try: payload=json.loads(raw,parse_float=Decimal)
        except ValueError: raise DataError('원문 JSON 해석 실패') from None
    elif isinstance(raw,dict): payload=dict(raw)
    else: raise DataError('원문은 JSON 객체여야 합니다')
    if not isinstance(payload,dict): raise DataError('행별 원문 JSON 객체가 아닙니다')
    payload={k:scalar(v) for k,v in payload.items()}
    fields=d['fields']
    f=lambda key,default='': field_value(payload,fields.get(key,{'value':default}))
    keys=[require(payload,k,k) for k in d['key_fields']]
    material=require(payload,fields['material'],'자재')
    raw_date=text(f('business_date'))
    # 입고예정(I_DATE='00000000')은 business_date를 AEDAT(수정일)로 대체
    if raw_date and raw_date!='00000000':
        date=ymd(raw_date)
    elif text(moddate:=f('modified_date')):
        date=ymd(moddate)
    else:
        raise DataError('business_date와 modified_date 모두 누락/영값')
    clock=hms(f('business_time'))
    event_us=int(decimal(event.get('event_epoch',event.get('_time',0)))*1_000_000)
    indexed_us=int(decimal(event.get('indexed_epoch',event.get('_indextime',0)))*1_000_000)
    if event_us<=0 or indexed_us<=0: raise DataError('Splunk event_epoch/indexed_epoch가 필요합니다')
    moddate=f('modified_date'); modtime=f('modified_time')
    if text(moddate) and text(modtime): modified=local_us(moddate,modtime)
    elif d.get('allow_event_time_version',False): modified=event_us
    else: raise DataError('수정일시 누락. 임의 수집시각을 최신 버전으로 사용하지 않습니다')
    generated=f('generated_timestamp')
    if text(generated):
        s=text(generated)
        if not re.fullmatch(r'\d{14}',s): raise DataError('CURRENT_TIMESTAMP 형식 오류')
        # PowerConnect CURRENT_TIMESTAMP is UTC in the supplied examples.
        generated_us=int(datetime.strptime(s,'%Y%m%d%H%M%S').replace(tzinfo=timezone.utc).timestamp()*1e6)
    else: generated_us=indexed_us
    unit=require(payload,fields['unit'],'단위').upper()
    qty=scaled(f('quantity'))
    amount_val=scaled(f('amount', '0')) if 'amount' in fields else 0
    # KZWI3(ZTSDJK0120)는 이미 USD 금액이므로 KURSK 환산 불필요.
    # VBRP NETWR는 통화쌍에 따라 USD 또는 KRW. KURSK>1이면 KRW이므로 USD로 환산.
    is_usd_amount = d.get('id','') == 'shipment_amount_dep'
    if not is_usd_amount:
        kursk_val=decimal(f('exchange_rate','1')) if 'exchange_rate' in fields else decimal(text(f('KURSK','1'))) or 1
        if kursk_val and kursk_val>1 and amount_val:
            amount_val=int(Decimal(amount_val)/Decimal(kursk_val))
    scope=all(text(field_value(payload,k)) in {str(v).strip() for v in vals} for k,vals in d.get('scope_filters',{}).items())
    deleted=False
    deletion=d.get('delete_rule')
    if deletion:
        deleted=text(field_value(payload,deletion['field'])) in {str(v) for v in deletion['values']}
    # The key, not the reporting scope, decides replacement. Rows leaving scope stay as latest rows with scope_ok=0.
    row=dict(source_id=d['id'],record_key=js(keys),document_no=text(f('document_no')),box_no=text(f('box_no')),
       material=material,qty_i=qty,amount_i=amount_val,unit=unit,plant=text(f('plant')),warehouse=text(f('warehouse')),
       location=text(f('location')),customer_key=text(f('customer_key')),
       business_date=date,business_time=clock,business_us=local_us(date,clock),
       modified_us=modified,generated_us=generated_us,indexed_us=indexed_us,
       event_hash=digest({'payload':payload,'event_us':event_us,'indexed_us':indexed_us}),scope_ok=int(scope),deleted=int(deleted),payload_json=js(payload))
    return row,payload
