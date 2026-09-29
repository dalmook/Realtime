import copy, contextlib, json, os, sqlite3, tempfile, time, unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from scm_db.common import *
from scm_db.settings import Settings,read_env
from scm_db.database import Database,source_fingerprint
from scm_db.normalize import normalize
from scm_db.demo import demo_config,fake_tables,stage_tables,event
from scm_db.reference import publish,project_cached
from scm_db.engine import Engine,schedule_due
from scm_db.connectors.splunk import build_search,check_messages,SplunkClient,ResultLimit
ROOT=Path(__file__).resolve().parents[1]

class Base(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name); self.cfg=demo_config(ROOT)
        self.s=Settings(ROOT,env={'SPLUNK_HOST':'demo.invalid'},config=self.cfg,data_dir=self.path)
        self.db=Database(self.s.db_path,ROOT); self.db.initialize(self.cfg)
        self.d=self.cfg['splunk_sources'][0]
        self.at=now_kst().replace(microsecond=0)-timedelta(minutes=60)
    def ingest(self,rows,d=None): return self.db.ingest(d or self.d,rows,int(time.time())-10,month_start_epoch())
    def masters(self,tables=None):
        p=self.path/('stage_'+str(time.time_ns())+'.sqlite'); meta=stage_tables(p,tables or fake_tables())
        result=publish(self.db,self.s,p,meta,self.db.start_run('oracle_all','test')); p.unlink(); return result

class Helpers(unittest.TestCase):
    def test_decimal_exact(self): self.assertEqual(scaled('0.000001'),1)
    def test_decimal_reject_extra(self):
        with self.assertRaises(DataError): scaled('0.0000001')
    def test_decimal_nonfinite(self):
        for n in ('nan','inf','-Infinity'):
            with self.assertRaises(DataError): scaled(n)
    def test_overflow(self):
        with self.assertRaises(DataError): scaled('10000000000000000000')
    def test_time_leading_zero(self): self.assertEqual(hms('25525'),'025525')
    def test_bad_date(self):
        with self.assertRaises(ValueError): ymd('20260230')
    def test_yearmonth(self): self.assertEqual(ym('2026-09'),'202609')
    def test_yearmonth_oracle_date_text(self): self.assertEqual(ym('2026-09-01 00:00:00.000000'),'202609')
    def test_kst(self):
        self.assertEqual(datetime.fromtimestamp(local_us('20260923','090000')/1e6,timezone.utc).hour,0)
    def test_scalar_duplicate(self): self.assertEqual(scalar(['PC','PC']),'PC')
    def test_scalar_conflict(self):
        with self.assertRaises(DataError): scalar(['PC','EA'])
    def test_no_network_db_path(self):
        with self.assertRaises(ConfigError): local_disk_only(Path('//server/share/db'))
    def test_env_literal(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'.env';p.write_text("S='a$#\\b'\nX=C:\\instantclient\nY=val # note\n",encoding='utf-8')
            self.assertEqual(read_env(p),{'S':'a$#\\b','X':'C:\\instantclient','Y':'val'})
    def test_identifier_injection(self):
        with self.assertRaises(ConfigError): identifier('X;DROP TABLE A',True)
    def test_scheduled_before9(self): self.assertFalse(schedule_due(datetime(2026,9,23,8,59,tzinfo=KST),'09:00'))
    def test_scheduled_at9(self): self.assertTrue(schedule_due(datetime(2026,9,23,9,0,tzinfo=KST),'09:00'))
    def test_scheduled_restart(self): self.assertFalse(schedule_due(datetime(2026,9,23,11,0,tzinfo=KST),'09:00',True))
    def test_error_redaction(self): self.assertEqual(safe_error(RuntimeError('password=secret ORA-01017')),'RuntimeError · ORA-01017')

class Facts(Base):
    def test_integrity(self): self.assertEqual(self.db.query('PRAGMA quick_check')[0]['quick_check'],'ok')
    def test_initialize_without_migration_skips_backup(self):
        with patch.object(self.db,'backup',side_effect=AssertionError('unchanged schema must not trigger a full DB backup')):
            self.db.initialize(self.cfg)
    def test_inbound_material_mapping_uses_matnr(self):
        self.assertEqual(self.d['fields']['material'],'MATNR')
    def test_legacy_pcode_database_migrates_to_matnr(self):
        with tempfile.TemporaryDirectory() as td:
            cfg=demo_config(ROOT);legacy=copy.deepcopy(cfg)
            old=next(x for x in legacy['splunk_sources'] if x['id']=='inbound_dep')
            old['fields']['material']='P_CODE'
            db=Database(Path(td)/'legacy.sqlite',ROOT);db.initialize(legacy)
            at=now_kst().replace(microsecond=0)-timedelta(minutes=5)
            db.ingest(old,[event(old,key='LEG1',material='OLD-P-CODE',at=at,MATNR='DEMO_A')],int(time.time())-10,month_start_epoch())
            self.assertEqual(db.query('SELECT material FROM inbound_current')[0]['material'],'OLD-P-CODE')
            db.initialize(cfg)
            row=db.query('SELECT material FROM inbound_current')[0]
            self.assertEqual(row['material'],'DEMO_A')
            self.assertIn('PAYLOAD_REMAP',db.state('inbound_dep')['projection_note'])
    def test_shipment_mapping_drift_reprojects_preserved_payload(self):
        with tempfile.TemporaryDirectory() as td:
            cfg=demo_config(ROOT);legacy=copy.deepcopy(cfg)
            current=next(x for x in cfg['splunk_sources'] if x['id']=='shipment_dep')
            old=next(x for x in legacy['splunk_sources'] if x['id']=='shipment_dep')
            old['fields']['customer_key']='OLD_CUSTOMER'
            db=Database(Path(td)/'legacy.sqlite',ROOT);db.initialize(legacy)
            at=now_kst().replace(microsecond=0)-timedelta(minutes=5)
            e=event(old,key='SHIP1',at=at,OLD_CUSTOMER='OLD-CUST',CUSTOMER='NEW-CUST')
            db.ingest(old,[e],int(time.time())-10,month_start_epoch())
            self.assertEqual(db.query('SELECT customer_key FROM shipment_current')[0]['customer_key'],'OLD-CUST')
            db.initialize(cfg)
            row=db.query('SELECT customer_key FROM shipment_current')[0]
            self.assertEqual(row['customer_key'],'NEW-CUST')
            self.assertEqual(db.state('shipment_dep')['config_hash'],source_fingerprint(current))
            self.assertIn('PAYLOAD_REMAP',db.state('shipment_dep')['projection_note'])
    def test_metadata_only_legacy_hash_rebases_without_payload_rewrite(self):
        d=next(x for x in self.cfg['splunk_sources'] if x['id']=='shipment_dep')
        self.ingest([event(d,key='SHIPMETA',at=self.at)],d)
        legacy=copy.deepcopy(d);legacy.pop('inventory_semantics_confirmed',None);legacy.pop('allow_payload_migration',None)
        with self.db.transaction() as con:
            con.execute('UPDATE source_state SET config_hash=? WHERE source_id=?',(legacy_source_fingerprint(legacy),d['id']))
        self.db.initialize(self.cfg)
        self.assertEqual(self.db.state(d['id'])['config_hash'],source_fingerprint(d))
        self.assertEqual(self.db.state(d['id'])['projection_note'],'FINGERPRINT_METADATA_REBASE')
    def test_payload_migration_rejects_business_key_change(self):
        d=next(x for x in self.cfg['splunk_sources'] if x['id']=='shipment_dep')
        self.ingest([event(d,key='SHIPKEY',at=self.at)],d)
        changed=copy.deepcopy(self.cfg)
        x=next(x for x in changed['splunk_sources'] if x['id']=='shipment_dep');x['key_fields']=['ITEMNO']
        with self.assertRaises(ConfigError):self.db.initialize(changed)
    def test_latest_row_full(self):
        first=event(self.d,key='1',qty='100',at=self.at,PALLET='old')
        last=event(self.d,key='1',qty='200',at=self.at,changed=self.at+timedelta(minutes=5),PALLET='')
        self.ingest([first,last]); row=self.db.query('SELECT * FROM inbound_current')[0]
        self.assertEqual(row['qty_i'],200*SCALE);self.assertEqual(json.loads(row['payload_json'])['PALLET'],'')
    def test_older_arrival_no_rollback(self):
        a=event(self.d,qty='100',at=self.at); b=event(self.d,qty='200',at=self.at,changed=self.at+timedelta(minutes=5))
        self.ingest([b,a]);self.assertEqual(self.db.query('SELECT qty_i FROM inbound_current')[0]['qty_i'],200*SCALE)
    def test_idempotent_replay(self):
        e=event(self.d,at=self.at);self.ingest([e]);r=self.ingest([e]);self.assertEqual(r['unchanged'],1)
        self.assertEqual(self.db.query('SELECT COUNT(*) n FROM raw_splunk_event')[0]['n'],1)
    def test_scope_leave(self):
        self.ingest([event(self.d,at=self.at),event(self.d,at=self.at,changed=self.at+timedelta(minutes=10),C_ID='XX')])
        self.assertEqual(len(self.db.query('SELECT * FROM v_inbound_detail')),0)
        self.assertEqual(len(self.db.query('SELECT * FROM inbound_current')),1)
    def test_scope_plant(self):
        self.ingest([event(self.d,at=self.at,PLANT='P2M1')]);self.assertEqual(len(self.db.query('SELECT * FROM v_inbound_detail')),0)
    def test_go_included(self):
        self.ingest([event(self.d,at=self.at,C_ID='GO')]);self.assertEqual(len(self.db.query('SELECT * FROM v_inbound_detail')),1)
    def test_distinct_box_not_rows(self):
        self.ingest([event(self.d,key='1',at=self.at),event(self.d,key='2',at=self.at)])
        r=self.db.query('SELECT * FROM v_inbound_daily')[0]; self.assertEqual(r['box_count'],1);self.assertEqual(r['latest_rows'],2)
    def test_pc_display_ea_only(self):
        self.ingest([event(self.d,at=self.at)]);r=self.db.query('SELECT * FROM v_inbound_detail')[0]
        self.assertEqual((r['unit'],r['display_unit']),('PC','EA'))
    def test_other_units_not_ea(self):
        self.ingest([event(self.d,at=self.at,UNIT='KG')]);self.assertIsNone(self.db.query('SELECT ea_i FROM v_inbound_detail')[0]['ea_i'])
    def test_business_time_not_modified(self):
        self.ingest([event(self.d,at=self.at,changed=self.at+timedelta(minutes=20))]);r=self.db.query('SELECT * FROM inbound_current')[0]
        self.assertEqual(r['business_us'],int(self.at.timestamp()*1e6))
    def test_missing_key_stops_batch(self):
        self.ingest([event(self.d,at=self.at)]);old=self.db.state(self.d['id'])['watermark']
        bad=event(self.d,key='2',at=self.at,CHIT='')
        with self.assertRaises(DataError): self.db.ingest(self.d,[bad],old+100,month_start_epoch())
        self.assertEqual(self.db.state(self.d['id'])['watermark'],old)
        self.assertEqual(self.db.query('SELECT COUNT(*) n FROM data_issue')[0]['n'],1)
    def test_bad_qty_not_zeroed(self):
        with self.assertRaises(DataError): self.ingest([event(self.d,at=self.at,QTY='NaN')])
        self.assertEqual(self.db.query('SELECT COUNT(*) n FROM inbound_current')[0]['n'],0)
    def test_same_version_conflict(self):
        self.ingest([event(self.d,at=self.at,qty='10')])
        with self.assertRaises(DataError): self.ingest([event(self.d,at=self.at,qty='11')])
    def test_leading_zero_key(self):
        self.ingest([event(self.d,key='00012',at=self.at,box='000009')]);r=self.db.query('SELECT * FROM inbound_current')[0]
        self.assertEqual(r['document_no'],'00012');self.assertEqual(r['box_no'],'000009')
    def test_explicit_tombstone(self):
        self.d['delete_rule']={'field':'D_FLAG','values':['1']}
        self.ingest([event(self.d,at=self.at,D_FLAG='0'),event(self.d,at=self.at,changed=self.at+timedelta(minutes=5),D_FLAG='1')])
        self.assertFalse(self.db.query('SELECT * FROM v_inbound_detail'))
    def test_flag_not_assumed(self):
        self.ingest([event(self.d,at=self.at,D_FLAG='1')]);self.assertEqual(len(self.db.query('SELECT * FROM v_inbound_detail')),1)
    def test_domain_specific_mappings(self):
        for d in self.cfg['splunk_sources'][1:]: self.ingest([event(d,at=self.at,qty='55')],d)
        self.assertEqual(self.db.query('SELECT qty_i FROM inventory_current')[0]['qty_i'],55*SCALE)
        self.assertEqual(self.db.query('SELECT qty_i FROM shipment_current')[0]['qty_i'],55*SCALE)
    def test_snapshot_no_history_sum(self):
        d=self.cfg['splunk_sources'][1]
        a=event(d,at=self.at,qty='100');b=event(d,at=self.at+timedelta(minutes=2),qty='30')
        self.ingest([a],d)
        self.db.ingest(d,[b],int(time.time()),month_start_epoch(),snapshot={'complete':True,'as_of_us':123,'token':'snap'})
        self.assertEqual(self.db.query('SELECT qty_i FROM inventory_current')[0]['qty_i'],30*SCALE)
    def test_snapshot_incomplete_rejected(self):
        d=self.cfg['splunk_sources'][1];self.ingest([event(d,at=self.at)],d)
        with self.assertRaises(DataError):self.db.ingest(d,[],int(time.time()),None,snapshot={'complete':False,'as_of_us':123})
        self.assertEqual(len(self.db.query('SELECT * FROM inventory_current')),1)
    def test_snapshot_empty_rejected(self):
        d=self.cfg['splunk_sources'][1]
        with self.assertRaises(DataError): self.db.ingest(d,[],int(time.time()),None,snapshot={'complete':True,'as_of_us':123})
    def test_backup(self):
        self.ingest([event(self.d,at=self.at)]);p=self.db.backup()
        with contextlib.closing(sqlite3.connect(p)) as con:self.assertEqual(con.execute('SELECT COUNT(*) FROM inbound_current').fetchone()[0],1)
    def test_readonly_sql(self):
        with self.assertRaises(sqlite3.OperationalError):self.db.query('DELETE FROM inbound_current')
    def test_config_change_guard(self):
        self.ingest([event(self.d,at=self.at)]);c=copy.deepcopy(self.cfg);c['splunk_sources'][0]['key_fields']=['CHARG']
        with self.assertRaises(ConfigError):self.db.initialize(c)
    def test_poll_change_allowed(self):
        self.ingest([event(self.d,at=self.at)]);c=copy.deepcopy(self.cfg);c['splunk_sources'][0]['poll_seconds']=30;self.db.initialize(c)
    def test_date_index_used(self):
        plan=self.db.query("EXPLAIN QUERY PLAN SELECT * FROM inbound_current WHERE business_date='20260923'")
        self.assertTrue(any('ix_inbound_date' in r['detail'] for r in plan))
    def test_raw_retention_keeps_current(self):
        self.ingest([event(self.d,at=self.at)])
        with self.db.transaction() as con:con.execute("UPDATE raw_splunk_event SET received_at='2000-01-01'")
        self.db.prune(30);self.assertEqual(len(self.db.query('SELECT * FROM inbound_current')),1);self.assertEqual(len(self.db.query('SELECT * FROM raw_splunk_event')),0)

class References(Base):
    def test_five_raw_tables(self):
        result=self.masters();self.assertEqual(len(result),5)
        for name in fake_tables(): self.assertTrue(self.db.query(f'SELECT * FROM raw_oracle_{name}'))
    def test_product_join(self):
        self.masters();self.ingest([event(self.d,at=self.at)])
        self.assertEqual(self.db.query('SELECT product_name FROM v_inbound_detail')[0]['product_name'],'예시 제품 A')
    def test_identical_master_duplicates(self):
        tables=fake_tables();tables['product'].append(dict(tables['product'][0]))
        result=self.masters(tables);self.assertEqual(result['product']['status'],'READY')
        self.assertEqual(len(self.db.query('SELECT * FROM dim_product')),2)
    def test_conflicting_master_not_max(self):
        self.masters();tables=fake_tables();tables['product'].append({**tables['product'][0],'PRODUCT':'WRONG'})
        result=self.masters(tables);self.assertTrue(result['product']['status'].startswith('MAPPING_ERROR'))
        self.assertEqual(self.db.query("SELECT product_name FROM dim_product WHERE material='DEMO_A'")[0]['product_name'],'예시 제품 A')
        self.ingest([event(self.d,at=self.at)])
        self.assertEqual(self.db.query('SELECT product_mapped FROM v_inbound_detail')[0]['product_mapped'],0)
    def test_unconfirmed_raw_only(self):
        self.cfg['oracle_sources'][0]['mapping']['confirmed']=False
        result=self.masters();self.assertEqual(result['conversion']['status'],'MAPPING_REQUIRED')
        self.assertTrue(self.db.query('SELECT * FROM raw_oracle_conversion'))
        self.assertFalse(self.db.query('SELECT * FROM dim_conversion_component'))
    def test_conversion_exact(self):
        self.masters();self.ingest([event(self.d,at=self.at,qty='0.125')])
        self.assertEqual(self.db.query('SELECT eq_i FROM v_inbound_detail')[0]['eq_i'],250000)
    def test_conversion_refresh_revalues(self):
        self.masters();self.ingest([event(self.d,at=self.at,qty='100')])
        t=fake_tables();t['conversion'][0]['CONVEQQTY']='3';self.masters(t)
        self.assertEqual(self.db.query('SELECT eq_i FROM v_inbound_detail')[0]['eq_i'],300*SCALE)
    def test_conversion_split_components_do_not_duplicate_raw_fact(self):
        t=fake_tables();t['conversion'].append({'ITEM':'DEMO_A','YM':self.at.strftime('%Y%m'),'CONV_CODE':'K9-COMBO','CONVEQQTY':'3'})
        self.masters(t);self.ingest([event(self.d,at=self.at,qty='100',box='BOX-COMBO')])
        row=self.db.query("SELECT qty_i,ea_i,eq_i,eq_dram_i,eq_flash_i FROM v_inbound_detail WHERE material='DEMO_A'")[0]
        self.assertEqual(row['qty_i'],100*SCALE);self.assertEqual(row['ea_i'],100*SCALE)
        self.assertEqual(row['eq_dram_i'],200*SCALE);self.assertEqual(row['eq_flash_i'],300*SCALE)
        self.assertEqual(row['eq_i'],500*SCALE)
        daily=self.db.query('SELECT box_count,quantity FROM v_inbound_daily')[0]
        self.assertEqual(daily['box_count'],1);self.assertEqual(daily['quantity'],100)
    def test_conversion_is_common_to_shipment(self):
        self.masters();ship=next(x for x in self.cfg['splunk_sources'] if x['domain']=='shipment')
        self.ingest([event(ship,key='S1',material='DEMO_A',qty='50',at=self.at)],ship)
        row=self.db.query("SELECT qty_i,eq_dram_i FROM v_shipment_detail WHERE material='DEMO_A'")[0]
        self.assertEqual(row['qty_i'],50*SCALE);self.assertEqual(row['eq_dram_i'],100*SCALE)
    def test_conversion_query_uses_requested_columns_without_product_prefilter(self):
        sql=(ROOT/'config/queries/conversion.sql').read_text(encoding='utf-8')
        self.assertIn('CONV_CODE',sql);self.assertIn('CONVEQQTY',sql)
        self.assertNotIn('MST_PAX_ITEM',sql);self.assertNotIn(' EQQTY',sql.replace('CONVEQQTY',''))
    def test_no_refresh_on_local_select(self):
        self.masters()
        with patch('scm_db.connectors.oracle.OracleClient.stage',side_effect=AssertionError('external call')):
            self.db.query('SELECT * FROM v_inbound_daily'); self.db.query('SELECT * FROM v_monthly_progress')
    def test_monthly_target_not_prorated(self):
        self.masters();self.ingest([event(self.d,at=self.at,qty='400')])
        rows=self.db.query("SELECT * FROM v_monthly_progress WHERE direction='inbound' AND material='DEMO_A' AND metric='EA'")
        self.assertEqual(rows[0]['monthly_target'],2000)
        self.assertEqual(rows[0]['actual_to_date'],400)
        self.assertEqual(rows[0]['progress_pct'],20)
        self.assertEqual(rows[0]['progress_status'],'READY')
    def test_distinct_box_progress(self):
        self.masters();self.ingest([event(self.d,at=self.at,key='1'),event(self.d,at=self.at,key='2')])
        row=self.db.query("SELECT * FROM v_monthly_progress WHERE direction='inbound' AND material='DEMO_A' AND metric='BOX'")[0]
        self.assertEqual(row['actual_to_date'],1);self.assertEqual(row['progress_pct'],10)
    def test_plan_not_multiplied_by_facts(self):
        self.masters();self.ingest([event(self.d,at=self.at,key=str(i),box=f'B{i}') for i in range(5)])
        row=self.db.query("SELECT * FROM v_monthly_progress WHERE direction='inbound' AND material='DEMO_A' AND metric='BOX'")[0]
        self.assertEqual(row['monthly_target'],10);self.assertEqual(row['actual_to_date'],5)
    def test_disabled_shipment_is_unknown_not_zero(self):
        self.masters()
        with self.db.transaction() as con:con.execute("UPDATE source_state SET enabled=0 WHERE source_id='shipment_dep'")
        row=self.db.query("SELECT * FROM v_monthly_progress WHERE direction='shipment'")[0]
        self.assertEqual(row['progress_status'],'ACTUAL_SOURCE_NOT_CONFIGURED');self.assertIsNone(row['actual_to_date'])
    def test_partial_history_ratio_null(self):
        self.masters();self.ingest([event(self.d,at=self.at)])
        with self.db.transaction() as con: con.execute('UPDATE source_state SET coverage_from=? WHERE source_id=?',(month_start_epoch()+86400,self.d['id']))
        row=self.db.query("SELECT * FROM v_monthly_progress WHERE direction='inbound'")[0]
        self.assertEqual(row['progress_status'],'PARTIAL_HISTORY');self.assertIsNone(row['progress_pct'])
    def test_backfill_watermark_not_caught_up(self):
        self.masters();self.ingest([event(self.d,at=self.at)])
        with self.db.transaction() as con:con.execute('UPDATE source_state SET watermark=? WHERE source_id=?',(int(time.time())-1000,self.d['id']))
        row=self.db.query("SELECT * FROM v_monthly_progress WHERE direction='inbound'")[0]
        self.assertEqual(row['progress_status'],'SOURCE_LAG_OR_BACKFILL');self.assertIsNone(row['progress_pct'])
    def test_zero_target(self):
        t=fake_tables();t['inbound_plan'][0]['TARGET_BOX']='0';self.masters(t);self.ingest([event(self.d,at=self.at)])
        row=self.db.query("SELECT * FROM v_monthly_progress WHERE direction='inbound' AND material='DEMO_A' AND metric='BOX'")[0]
        self.assertEqual(row['progress_status'],'ZERO_TARGET');self.assertIsNone(row['progress_pct'])
    def test_multiple_plan_versions_not_summed(self):
        t=fake_tables(); t['inbound_plan'].append({**t['inbound_plan'][0],'VERSION':'V2','TARGET_BOX':'20'})
        self.masters(t);self.ingest([event(self.d,at=self.at)])
        r=self.db.query("SELECT * FROM v_monthly_progress WHERE direction='inbound' AND material='DEMO_A' AND metric='BOX'")
        self.assertEqual(len(r),2);self.assertEqual({x['monthly_target'] for x in r},{10,20})
    def test_duplicate_target_rejected(self):
        t=fake_tables();t['inbound_plan'].append(dict(t['inbound_plan'][0]))
        result=self.masters(t);self.assertTrue(result['inbound_plan']['status'].startswith('MAPPING_ERROR'))
    def test_target_line_sum_needs_keys(self):
        t=fake_tables()
        for i,r in enumerate(t['inbound_plan']):r['LINEID']=str(i)
        t['inbound_plan'].append({**t['inbound_plan'][0],'LINEID':'9','TARGET_BOX':'2','TARGET_EA':'100'})
        m=next(d for d in self.cfg['oracle_sources'] if d['id']=='inbound_plan')['mapping']
        m['row_key_fields']=['LINEID'];m['aggregation']='sum'
        self.masters(t);self.ingest([event(self.d,at=self.at)])
        r=self.db.query("SELECT * FROM v_monthly_progress WHERE direction='inbound' AND material='DEMO_A' AND metric='BOX'")[0]
        self.assertEqual(r['monthly_target'],12)
    def test_product_not_joined_by_display_unit(self):
        self.masters();self.ingest([event(self.d,at=self.at)])
        r=self.db.query('SELECT * FROM v_inbound_detail')[0]
        self.assertEqual((r['display_unit'],r['product_mapped']),('EA',1))
    def test_mismatched_qty_unit_holds_ratio(self):
        self.masters();self.ingest([event(self.d,at=self.at,UNIT='KG')])
        r=self.db.query("SELECT * FROM v_monthly_progress WHERE direction='inbound' AND material='DEMO_A' AND metric='EA'")[0]
        self.assertEqual(r['progress_status'],'UNIT_MISMATCH')
    def test_group_target_missing_product_mapping_is_not_zero(self):
        m=next(d for d in self.cfg['oracle_sources'] if d['id']=='inbound_plan')['mapping']
        m['grain']['product_group']={'value':'예시 DRAM'}
        self.masters();self.ingest([event(self.d,at=self.at)])
        with self.db.transaction() as con:con.execute("UPDATE reference_state SET projection_ready=0 WHERE source_id='product'")
        r=self.db.query("SELECT * FROM v_monthly_progress WHERE direction='inbound' AND material='DEMO_A' AND metric='EA'")[0]
        self.assertEqual(r['progress_status'],'DIMENSION_MAPPING_MISSING');self.assertIsNone(r['progress_pct'])
    def test_customer_target_missing_actual_key_is_not_zero(self):
        m=next(d for d in self.cfg['oracle_sources'] if d['id']=='inbound_plan')['mapping']
        m['grain']['customer_key']={'value':'C01'}
        self.masters();self.ingest([event(self.d,at=self.at,CUSTOMER='')])
        r=self.db.query("SELECT * FROM v_monthly_progress WHERE direction='inbound' AND material='DEMO_A' AND metric='EA'")[0]
        self.assertEqual(r['progress_status'],'DIMENSION_MAPPING_MISSING')
    def test_apply_cached_does_not_query_oracle(self):
        self.masters()
        with patch('scm_db.connectors.oracle.OracleClient.stage',side_effect=AssertionError('external')):
            result=project_cached(self.db,self.s)
            self.assertEqual(result['product']['status'],'READY')
    def test_failed_publish_atomic(self):
        self.masters();old=self.db.query('SELECT * FROM reference_state')
        p=self.path/'bad_stage.sqlite';metadata=stage_tables(p,fake_tables());metadata['product']['table']='does_not_exist'
        with self.assertRaises(Exception):publish(self.db,self.s,p,metadata,self.db.start_run('oracle_all','test'))
        self.assertEqual(self.db.query('SELECT * FROM reference_state'),old)

class ScheduleAndSearch(Base):
    def test_daily_once_across_restart(self):
        when=datetime(2026,9,23,9,0,tzinfo=KST)
        with patch.object(Engine,'sync_oracle',return_value={}) as f:
            self.assertTrue(Engine(self.s,self.db).run_scheduled_oracle(when))
            self.assertFalse(Engine(self.s,self.db).run_scheduled_oracle(when+timedelta(hours=2)))
            self.assertEqual(f.call_count,1)
    def test_no_automatic_retry_same_day(self):
        with patch.object(Engine,'sync_oracle',side_effect=DataError('test')) as f:
            Engine(self.s,self.db).run_scheduled_oracle(datetime(2026,9,23,9,0,tzinfo=KST))
            Engine(self.s,self.db).run_scheduled_oracle(datetime(2026,9,23,12,0,tzinfo=KST))
            self.assertEqual(f.call_count,1)
    def test_next_day_runs(self):
        with patch.object(Engine,'sync_oracle',return_value={}) as f:
            e=Engine(self.s,self.db);e.run_scheduled_oracle(datetime(2026,9,23,9,tzinfo=KST));e.run_scheduled_oracle(datetime(2026,9,24,9,tzinfo=KST))
            self.assertEqual(f.call_count,2)
    def test_before9_no_call(self):
        with patch.object(Engine,'sync_oracle',return_value={}) as f:
            Engine(self.s,self.db).run_scheduled_oracle(datetime(2026,9,23,8,59,tzinfo=KST));f.assert_not_called()
    def test_spl_has_index_time_overlap(self):
        spl=build_search(self.d,100,200)
        self.assertIn('_index_earliest=100',spl);self.assertIn('_indextime<200',spl)
    def test_spl_not_prefilter_mutable_scope(self):
        spl=build_search(self.d,100,200);self.assertNotIn('PLANT=',spl);self.assertNotIn('C_ID=',spl)
    def test_warning_fail_closed(self):
        with self.assertRaises(UpstreamError):check_messages({'messages':[{'type':'WARN','text':'x'}]})
    def test_profile_default_ssl_off(self):self.assertFalse(self.s.profile()['verify'])
    def test_ignore_ca_when_ssl_off(self):
        self.s.env['SPLUNK_VERIFY_SSL']='false';self.s.env['SPLUNK_CA_BUNDLE']='not_a_file';self.assertEqual(self.s.profile()['ca'],'')
    def test_process_lock(self):
        with ProcessLock(self.path/'writer.lock'):
            with self.assertRaises(ConfigError):
                with ProcessLock(self.path/'writer.lock'):pass
    def test_incomplete_window_coverage_not_advanced(self):
        self.db.ingest(self.d,[event(self.d,at=self.at)],100,None)
        self.assertIsNone(self.db.state(self.d['id'])['coverage_from'])
    def test_empty_poll_is_success(self):
        r=self.ingest([]);self.assertEqual(r['read'],0);self.assertIsNotNone(self.db.state(self.d['id'])['last_success'])
