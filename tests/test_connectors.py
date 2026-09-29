import contextlib,json,threading,tempfile,time,unittest,urllib.parse
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch,MagicMock
from scm_db.connectors.splunk import SplunkClient,UpstreamError,ResultLimit
from scm_db.connectors.oracle import OracleClient,prepare_driver,cell,read_sql
from scm_db.settings import Settings
from scm_db.common import ConfigError,DataError
ROOT=Path(__file__).resolve().parents[1]

class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.state={'logins':0,'deleted':False,'empty_page':False,'reauth':False,'warning':False,'failed':False,'finalized':False,'preview':False,'count':2505}
        state=self.state
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def send(self,body,code=200,xml=False):
                raw=body.encode() if xml else json.dumps(body).encode()
                self.send_response(code);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
            def do_POST(self):
                data=self.rfile.read(int(self.headers.get('Content-Length',0)))
                if self.path=='/services/auth/login':
                    state['logins']+=1; self.send('<response><sessionKey>TEST_SESSION_ONLY</sessionKey></response>',xml=True);return
                if self.headers.get('Authorization')!='Splunk TEST_SESSION_ONLY': self.send({},401);return
                if state['reauth']:
                    state['reauth']=False;self.send({},401);return
                self.send({'sid':'test1'})
            def do_GET(self):
                parsed=urllib.parse.urlparse(self.path)
                if parsed.path.endswith('/results'):
                    q=urllib.parse.parse_qs(parsed.query); offset=int(q['offset'][0]);count=int(q['count'][0])
                    rows=[{'_raw':'{}','n':n} for n in range(offset,min(offset+count,state['count']))]
                    if state['empty_page'] and offset: rows=[]
                    self.send({'preview':state['preview'],'results':rows,'messages':[{'type':'WARN'}] if state['warning'] else []})
                else:self.send({'entry':[{'content':{'isDone':True,'isFailed':state['failed'],'isFinalized':state['finalized'],'resultCount':state['count']}}]})
            def do_DELETE(self): state['deleted']=True;self.send({})
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.server.server_close);self.addCleanup(self.server.shutdown)
        self.client=SplunkClient({'base_url':f'http://127.0.0.1:{self.server.server_port}','user':'TEST','password':'TEST_PASSWORD','verify':False,'proxy':'','ca':'','timeout':5})
    def test_paged_results_and_delete(self):
        rows=self.client.search('search test',3000);self.assertEqual(len(rows),2505);self.assertTrue(self.state['deleted'])
    def test_missing_page_fails(self):
        self.state['empty_page']=True
        with self.assertRaises(UpstreamError):self.client.search('search test',3000)
        self.assertTrue(self.state['deleted'])
    def test_limit_no_truncation(self):
        with self.assertRaises(ResultLimit):self.client.search('search test',100)
    def test_401_relogin_once(self):
        self.state['reauth']=True;self.client.search('search test',3000);self.assertEqual(self.state['logins'],2)
    def test_warning_no_partial(self):
        self.state['warning']=True
        with self.assertRaises(UpstreamError):self.client.search('search test',3000)
    def test_finalized_rejected(self):
        self.state['finalized']=True
        with self.assertRaises(UpstreamError):self.client.search('search test',3000)
    def test_preview_rejected(self):
        self.state['preview']=True
        with self.assertRaises(UpstreamError):self.client.search('search test',3000)
    def test_failed_job_rejected(self):
        self.state['failed']=True
        with self.assertRaises(UpstreamError):self.client.search('search test',3000)
    def test_zero_results_success(self):
        self.state['count']=0;self.assertEqual(self.client.search('search test'),[])
    def test_environment_proxy_not_used(self):
        with patch.dict('os.environ',{'HTTP_PROXY':'http://127.0.0.1:1','HTTPS_PROXY':'http://127.0.0.1:1','NO_PROXY':''}):
            self.client.search('search test',3000)

class OracleTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.s=Settings(ROOT,env={'ORACLE_USER':'TEST','ORACLE_PASSWORD':'TEST','ORACLE_DSN':'TEST'},data_dir=self.tmp.name)
    def test_exact_number_serialization(self):
        from decimal import Decimal
        self.assertEqual(cell(Decimal('123456789012345.123456')),'123456789012345.123456')
    def test_table_identifier_sql(self):
        self.assertEqual(read_sql(ROOT,{'table':'SCM_INFO.SCM_FABIN_CONV_FAM6_MST_M'}),'SELECT * FROM SCM_INFO.SCM_FABIN_CONV_FAM6_MST_M')
    def test_no_thin_fallback(self):
        module=MagicMock();module.is_thin_mode.return_value=True
        # This is a mocked driver test, not an installed-OCI integration test.
        # Mock only the file prerequisite; production must still reject Thin mode.
        with patch('scm_db.connectors.oracle._READY',None),patch('scm_db.connectors.oracle.driver_info',return_value=(module,'oracledb')),patch('scm_db.connectors.oracle.Path.is_file',return_value=True):
            with self.assertRaises(ConfigError):prepare_driver(self.s)
            module.init_oracle_client.assert_called_once()
    def test_missing_driver_explained(self):
        with patch('scm_db.connectors.oracle.importlib.import_module',side_effect=ImportError):
            from scm_db.connectors.oracle import driver_info
            with self.assertRaises(ConfigError):driver_info()
    def test_readonly_transaction_required(self):
        module=MagicMock();con=module.connect.return_value;cursor=con.cursor.return_value.__enter__.return_value
        cursor.execute.side_effect=RuntimeError('read-only unavailable')
        with patch('scm_db.connectors.oracle.prepare_driver',return_value=(module,'oracledb')):
            with self.assertRaises(RuntimeError):
                with OracleClient(self.s).connection():pass
        cursor.execute.assert_called_with('SET TRANSACTION READ ONLY');con.close.assert_called_once()
    def test_snapshot_fetches_all_batches(self):
        d=self.s.config['oracle_sources'][0];self.s.config['oracle_sources']=[d]
        con=MagicMock();cur=con.cursor.return_value.__enter__.return_value
        cur.description=[('ITEM','VARCHAR',None,None,None,None,None)]
        cur.fetchmany.side_effect=[[('A',)],[('B',)],[]]
        @contextlib.contextmanager
        def fakeconn():yield con
        with patch.object(OracleClient,'connection',lambda _:fakeconn()):
            path,meta=OracleClient(self.s).stage()
        self.assertEqual(meta[d['id']]['rows'],2);path.unlink()
    def test_snapshot_limit_does_not_publish(self):
        d=self.s.config['oracle_sources'][0];d['max_rows']=1;self.s.config['oracle_sources']=[d]
        con=MagicMock();cur=con.cursor.return_value.__enter__.return_value
        cur.description=[('ITEM','VARCHAR',None,None,None,None,None)];cur.fetchmany.side_effect=[[('A',),('B',)],[]]
        @contextlib.contextmanager
        def fakeconn():yield con
        with patch.object(OracleClient,'connection',lambda _:fakeconn()):
            with self.assertRaises(DataError):OracleClient(self.s).stage()
        self.assertEqual(list((Path(self.tmp.name)/'staging').glob('*.sqlite')),[])
