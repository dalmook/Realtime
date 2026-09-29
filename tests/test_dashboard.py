"""Offline acceptance tests. Only temporary synthetic SQLite and loopback HTTP."""
import contextlib,json,tempfile,threading,unittest,urllib.request,urllib.error
from pathlib import Path
from unittest.mock import patch
from datetime import datetime
from scm_db.settings import Settings
from scm_db.demo_seed import seed
from scm_db.common import KST,SCALE
from scm_db.database import value_fact,Database
from dashboard import runtime,reporting as r,target_manager as tm,focus_manager as fm
from dashboard.server import make_server
ROOT=Path(__file__).resolve().parents[1]

class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.s=Settings(ROOT,env={'ORACLE_ENABLED':'false','SPLUNK_HOST':'demo.invalid','SHIPMENT_BOX_CONFIRMED':'true'},data_dir=self.tmp.name)
        runtime.configure(self.s,demo=True);self.db=seed(self.s);runtime.ensure_runtime()
        self.day=r.today();self.ym=self.day[:6]
    def con(self,write=False):return runtime.connect(not write)
    def test_initialize_twice_preserves_facts(self):
        before=r.kpi({})['shipment']['actual_mtd'];self.db.initialize(self.s.config);runtime.ensure_runtime()
        self.assertEqual(before,r.kpi({})['shipment']['actual_mtd'])
    def test_kpi_hourly_ea(self):
        k=r.kpi({});h=r.hourly({})
        for key in ('production','shipment'):self.assertAlmostEqual(k[key]['actual_today'],sum(h[key]),places=4)
    def test_kpi_hourly_all_metrics(self):
        for metric in r.METRICS:
            k=r.kpi({'metric':metric});h=r.hourly({'metric':metric})
            for key in ('production','shipment'):
                if k[key]['actual_today'] is None:self.assertTrue(all(x is None for x in h[key]))
                else:self.assertAlmostEqual(k[key]['actual_today'],sum(h[key]),places=4)
    def test_daily_sum_matches_mtd(self):
        for metric in r.METRICS:
            p={'metric':metric,'date':self.day};k=r.kpi(p);d=r.daily(p)
            for key in ('production','shipment'):
                if k[key]['actual_mtd'] is not None:self.assertAlmostEqual(k[key]['actual_mtd'],sum(x[key] for x in d['daily']),places=3)
    def test_customer_top_and_others(self):
        for metric in ('EA','USD','EQ_DRAM','EQ_FLASH'):
            p={'range':'monthly','metric':metric,'limit':'2'};c=r.customers(p);k=r.kpi(p)
            self.assertEqual(c['customers'][-1]['customer_key'],'__OTHERS__')
            self.assertAlmostEqual(sum(x['shipment'] for x in c['customers']),k['shipment']['actual_mtd'],places=3)
    def test_items_all_equal_total(self):
        p={'limit':'500'};items=r.items(p);k=r.kpi(p)
        for key in ('production','shipment'):self.assertAlmostEqual(sum(i[key] for i in items['items']),k[key]['actual_today'],places=3)
    def test_customer_filter_consistency(self):
        p={'customer':'DEMO-C01','date':self.day};k=r.kpi(p);h=r.hourly(p)
        for key in ('production','shipment'):self.assertAlmostEqual(k[key]['actual_today'],sum(h[key]),places=3)
    def test_item_filter_consistency(self):
        p={'item':'DEMO-001-MEMORY','date':self.day};k=r.kpi(p);items=r.items(p)
        self.assertEqual(len(items['items']),1)
        self.assertEqual(k['production']['actual_today'],items['items'][0]['production'])
    def test_warehouse_filter_consistency(self):
        p={'warehouse':'1310'};k=r.kpi(p);h=r.hourly(p)
        self.assertEqual(k['shipment']['actual_today'],sum(h['shipment']))
    def test_past_date_not_future_mtd(self):
        day=self.ym+'01';p={'date':day};k=r.kpi(p);d=r.daily(p)
        self.assertTrue(all(x['date']<=day for x in d['daily']))
        self.assertEqual(k['shipment']['actual_mtd'],k['shipment']['actual_today'])
    def test_invalid_calendar_date(self):
        for d in ('20260230','20261301','123','2026-01-01'):
            with self.assertRaises(ValueError):r.kpi({'date':d})
    def test_invalid_metric_and_limit(self):
        for p in ({'metric':'EQ'},{'limit':'0'},{'limit':'501'}):
            with self.assertRaises(ValueError):r.kpi(p)
    def test_inventory_has_no_target_or_inferred_available(self):
        inv=r.kpi({})['inventory'];self.assertNotIn('target',inv);self.assertIsNone(inv['available']);self.assertGreater(inv['current'],0)
    def test_missing_amount_is_unknown_not_netwr(self):
        with contextlib.closing(self.con(True)) as c,c:c.execute('DELETE FROM shipment_amount_current')
        k=r.kpi({'metric':'USD'})['shipment'];self.assertIsNone(k['actual_mtd']);self.assertEqual(k['status'],'partial')
        self.assertNotIn('$',str(r.events({})['events']))
    def test_legacy_amount_fallback_is_not_netwr(self):
        with contextlib.closing(self.con(True)) as c,c:
            row=c.execute('SELECT * FROM shipment_current LIMIT 1').fetchone();v,p=json.loads(row['record_key'])
            c.execute('DELETE FROM shipment_amount_current WHERE record_key=?',(row['record_key'],))
            c.execute('INSERT INTO shipment_amount_kzwi3(vbeln,posnr,vgbel,matnr,kzwi3) VALUES(?,?,?,?,?)',(v,p,row['document_no'],row['material'],123))
        self.assertIsNotNone(r.kpi({'metric':'USD'})['shipment']['actual_mtd'])
    def test_new_amount_overrides_legacy(self):
        before=r.kpi({'metric':'USD'})['shipment']['actual_mtd']
        with contextlib.closing(self.con(True)) as c,c:
            row=c.execute('SELECT * FROM shipment_current LIMIT 1').fetchone();v,p=json.loads(row['record_key'])
            c.execute('INSERT INTO shipment_amount_kzwi3(vbeln,posnr,vgbel,matnr,kzwi3) VALUES(?,?,?,?,?)',(v,p,row['document_no'],row['material'],999999))
        self.assertEqual(before,r.kpi({'metric':'USD'})['shipment']['actual_mtd'])
    def test_eq_conversion_does_not_duplicate_ea(self):
        before=r.kpi({})['production']['actual_mtd']
        with contextlib.closing(self.con(True)) as c,c:c.execute("INSERT INTO dim_conversion VALUES(?,?,?,?,?,?)",(self.ym,'DEMO-001-MEMORY','PC-DRAM','2.0','conversion','demo'))
        self.assertEqual(before,r.kpi({})['production']['actual_mtd'])
    def test_monthly_conversion_overrides_default(self):
        with contextlib.closing(self.con(True)) as c,c:
            row=c.execute("SELECT * FROM inbound_current WHERE material='DEMO-001-MEMORY' LIMIT 1").fetchone()
            c.execute('INSERT INTO dim_conversion VALUES(?,?,?,?,?,?)',(self.ym,row['material'],'PC-DRAM','2.0','conversion','demo'))
            value_fact(c,row);v=c.execute('SELECT eq_dram_i FROM fact_valuation WHERE source_id=? AND record_key=?',(row['source_id'],row['record_key'])).fetchone()[0]
            self.assertEqual(v,row['qty_i']*2)
    def test_scope_leaving_row_excluded(self):
        before=r.kpi({})['production']['actual_mtd']
        with contextlib.closing(self.con(True)) as c,c:
            row=c.execute('SELECT * FROM inbound_current LIMIT 1').fetchone();c.execute('UPDATE inbound_current SET scope_ok=0 WHERE record_key=?',(row['record_key'],))
        self.assertAlmostEqual(before-row['qty_i']/SCALE,r.kpi({})['production']['actual_mtd'])
    def test_box_scope_unsupported_is_null(self):
        self.assertIsNone(r.kpi({'metric':'BOX','item':'DEMO-001-MEMORY'})['shipment']['actual_mtd'])
    def test_manual_target_scope_never_global_override(self):
        before=r.kpi({})['shipment']['target']
        tm.create_target({'period_ym':self.ym,'direction':'shipment','metric':'EA','target_name':'Customer only','target_value':123,'priority':0,
                          'filters':[{'field_key':'customer_code','operator':'=','filter_value':'DEMO-C01'}]})
        self.assertEqual(before,r.kpi({})['shipment']['target']);self.assertEqual(r.kpi({'customer':'DEMO-C01'})['shipment']['target'],123)
    def test_manual_target_update_immediate(self):
        tid=tm.create_target({'period_ym':self.ym,'direction':'shipment','metric':'EA','target_name':'Global','target_value':456,'priority':0})['target_id']
        self.assertEqual(r.kpi({})['shipment']['target'],456);tm.update_target(tid,{'target_value':789});self.assertEqual(r.kpi({})['shipment']['target'],789)
    def test_target_crud_copy_disable_delete(self):
        t=tm.create_target({'period_ym':self.ym,'direction':'shipment','metric':'USD','target_name':'t','target_value':100})['target_id']
        self.assertEqual(tm.get_target(t)['target_value'],100)
        copy=tm.copy_target(t)['target_id'];self.assertNotEqual(t,copy)
        tm.update_target(t,{'enabled':False});self.assertFalse(tm.get_target(t)['enabled']);tm.delete_target(t)
        with self.assertRaises(ValueError):tm.get_target(t)
    def test_target_zero_valid_nonfinite_rejected(self):
        base={'period_ym':self.ym,'direction':'shipment','metric':'EA','target_name':'zero','target_value':0}
        self.assertTrue(tm.create_target(base)['ok'])
        for v in (float('nan'),float('inf'),-1):
            with self.assertRaises(ValueError):tm.create_target({**base,'target_value':v})
    def test_filter_operators(self):
        for op,val in [('=','DRAM'),('IN','DRAM,FLASH'),('NOT IN','FLASH'),('Starts With','D'),('Contains','RA'),('BETWEEN','A,Z')]:
            x=tm.preview_target({'period_ym':self.ym,'direction':'shipment','metric':'EA','filters':[{'field_key':'product_group','operator':op,'filter_value':val}]})
            self.assertGreater(x['actual'],0,op)
    def test_injection_treated_as_literal(self):
        x=tm.preview_target({'period_ym':self.ym,'direction':'shipment','metric':'EA','filters':[{'field_key':'customer_name','operator':'=','filter_value':"' OR 1=1 --"}]})
        self.assertEqual(x['actual'],0);self.assertGreater(r.kpi({})['shipment']['actual_mtd'],0)
    def test_focus_matches_item_kpi(self):
        f={'focus_id':99,'focus_type':'item','item_code':'DEMO-001-MEMORY','customer_code':None,'label':'t'}
        with contextlib.closing(self.con()) as c:
            for metric in r.METRICS:
                a=fm.compute_focus_kpi(f,c,metric,self.day);k=r.kpi({'item':f['item_code'],'metric':metric,'date':self.day})
                self.assertEqual(a['shipment']['mtd'],k['shipment']['actual_mtd'])
    def test_focus_batch_atomic(self):
        before=len(fm.list_focus())
        with self.assertRaises(ValueError):fm.batch_create([{'focus_type':'item','item_code':'X'},{'focus_type':'invalid'}])
        self.assertEqual(before,len(fm.list_focus()))
    def test_focus_crud_duplicate(self):
        a=fm.create_focus('customer',customer_code='Z');self.assertTrue(a['ok']);self.assertFalse(fm.create_focus('customer',customer_code='Z')['ok'])
        fm.update_focus(a['focus_id'],label='updated');self.assertTrue(any(x['label']=='updated' for x in fm.list_focus()))
        fm.delete_focus(a['focus_id']);self.assertFalse(any(x['focus_id']==a['focus_id'] for x in fm.list_focus()))
    def test_blank_kunag_falls_back_to_customer(self):
        with contextlib.closing(self.con(True)) as c,c:c.execute("UPDATE shipment_amount_current SET payload_json=json_set(payload_json,'$.KUNAG','')")
        self.assertGreater(r.kpi({'customer':'DEMO-C01'})['shipment']['actual_mtd'],0)
    def test_demo_refuses_live_db(self):
        with contextlib.closing(self.con(True)) as c,c:c.execute("DELETE FROM meta WHERE key='demo_dataset'")
        with self.assertRaises(ValueError):seed(self.s)
    def test_host_url_normalization(self):
        self.s.env['SPLUNK_HOST']='https://demo.invalid:8089';self.assertEqual(self.s.profile()['base_url'],'https://demo.invalid:8089')
        for host in ['https://user:pass@demo.invalid','http://demo.invalid','demo.invalid/path']:
            self.s.env['SPLUNK_HOST']=host
            with self.assertRaises(ValueError):self.s.profile()
    def test_uncollected_source_not_zero(self):
        with contextlib.closing(self.con(True)) as c,c:
            c.execute('DELETE FROM inbound_current')
            c.execute("UPDATE source_state SET last_success=NULL WHERE domain='inbound'")
        self.assertIsNone(r.kpi({})['production']['actual_mtd'])
        self.assertTrue(all(v is None for v in r.hourly({})['production']))
    def test_http_routes_and_security(self):
        http=make_server(port=0);worker=threading.Thread(target=http.serve_forever,daemon=True);worker.start()
        base=f'http://127.0.0.1:{http.server_port}'
        try:
            for ep in ('/api/kpi','/api/hourly','/api/items','/api/customers','/api/focus?action=kpi','/api/targets','/api/health'):
                with urllib.request.urlopen(base+ep) as res:self.assertEqual(res.status,200)
            for ep,headers in [('/.env',{}),('/../config/pipeline.json',{}),('/api/kpi?date=20260230',{}),('/api/kpi',{'Host':'evil.invalid'}),('/api/kpi',{'Origin':'https://evil.invalid'})]:
                with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(urllib.request.Request(base+ep,headers=headers))
            payload={'period_ym':self.ym,'direction':'shipment','metric':'EA','target_name':'http-test','target_value':123}
            request=urllib.request.Request(base+'/api/targets/create',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','Origin':base},method='POST')
            with urllib.request.urlopen(request) as res:self.assertTrue(json.load(res)['ok'])
            request=urllib.request.Request(base+'/api/targets/create',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','Origin':'https://evil.invalid'},method='POST')
            with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(request)
        finally:http.shutdown();http.server_close();worker.join()

if __name__=='__main__':unittest.main()
