"""Local read-only audit for MATNR -> ITEM -> CONV_CODE -> CONVEQQTY conversion."""
from __future__ import annotations
import argparse, contextlib
from pathlib import Path
from scm_db.settings import Settings
from scm_db.database import Database
from scm_db.common import SCALE

ROOT=Path(__file__).resolve().parents[1]

def fmt(value):
    if value is None:return 'NULL'
    if isinstance(value,(int,float)):return f'{value:,.6f}'.rstrip('0').rstrip('.')
    return str(value)

def main():
    p=argparse.ArgumentParser(description='Read-only conversion audit')
    p.add_argument('--item',help='Splunk MATNR / Oracle ITEM')
    args=p.parse_args()
    s=Settings(ROOT);db=Database(s.db_path,ROOT)
    if not db.path.exists():
        raise SystemExit('DB가 없습니다. SETUP.cmd 후 실제 데이터 수집 또는 기존 DATA_DIR을 확인하세요.')
    item=(args.item or input('확인할 MATNR (비우면 복합환산 ITEM 목록): ').strip()).strip()
    with contextlib.closing(db.connect(readonly=True)) as con:
        state=con.execute("SELECT projection_ready,projection_note,loaded_at FROM reference_state WHERE source_id='conversion'").fetchone()
        print('\n[conversion 상태]')
        print(dict(state) if state else 'NOT_LOADED')
        if not state or not state['projection_ready']:
            print('환산마스터가 READY가 아닙니다. SYNC_ORACLE.cmd를 먼저 실행하세요.')
        if not item:
            rows=con.execute("""SELECT material,
              GROUP_CONCAT(DISTINCT conv_family) families,
              COUNT(*) component_rows,
              SUM(CASE WHEN conv_family='DRAM' THEN 1 ELSE 0 END) dram_rows,
              SUM(CASE WHEN conv_family='FLASH' THEN 1 ELSE 0 END) flash_rows
              FROM dim_conversion_component
              GROUP BY material
              HAVING dram_rows>0 AND flash_rows>0
              ORDER BY component_rows DESC,material LIMIT 50""").fetchall()
            print('\n[DRAM+FLASH 복합 ITEM 최대 50개]')
            for r in rows:print(dict(r))
            return
        comps=con.execute("""SELECT period_ym,material,conv_code,conv_family,eq_per_unit
          FROM dim_conversion_component
          WHERE material IN (?,substr(?,1,18))
          ORDER BY period_ym DESC,conv_family,conv_code""",(item,item)).fetchall()
        print('\n[환산 구성]')
        if not comps:print('매핑 없음:',item)
        for r in comps:print(dict(r))
        for domain in ('inbound','shipment','inventory'):
            table=domain+'_current'
            rows=con.execute(f"""SELECT f.business_date,f.document_no,f.box_no,f.material,
              f.qty_i,v.eq_i,v.eq_dram_i,v.eq_flash_i,v.note
              FROM {table} f LEFT JOIN fact_valuation v
                ON v.source_id=f.source_id AND v.record_key=f.record_key
              WHERE f.material IN (?,substr(?,1,18)) AND f.deleted=0
              ORDER BY f.business_us DESC LIMIT 10""",(item,item)).fetchall()
            print(f'\n[{domain} 최근 fact 최대 10건]')
            if not rows:print('(없음)');continue
            for r in rows:
                d=dict(r)
                for k in ('qty_i','eq_i','eq_dram_i','eq_flash_i'):
                    d[k[:-2] if k.endswith('_i') else k]=None if d[k] is None else d[k]/SCALE
                    d.pop(k,None)
                print(d)

if __name__=='__main__':main()
