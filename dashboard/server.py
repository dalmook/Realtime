#!/usr/bin/env python3
"""Portable standard-library HTTP API. Same route names; local-only by default."""
from __future__ import annotations
import sys, json, logging, mimetypes, threading, time
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlsplit, parse_qs, unquote
if __package__ in (None,''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    __package__='dashboard'
from . import runtime, reporting, target_manager as tm, focus_manager as fm

STATIC_DIR=Path(__file__).resolve().parent/'static'
ROUTES=dict(reporting.ROUTES)
ROUTES.update({
 '/api/targets':lambda p:tm.list_targets(p.get('period_ym'),p.get('direction'),p.get('date')),
 '/api/targets/list':lambda p:tm.list_targets(p.get('period_ym'),p.get('direction'),p.get('date')),
 '/api/targets/get':lambda p:tm.get_target(int(p.get('target_id',0))),
 '/api/targets/meta':lambda p:tm.get_field_metadata(),
 '/api/targets/preview':lambda p:tm.preview_target({**p,'filters':json.loads(p.get('filters','[]'))}),
 '/api/targets/resolve':lambda p:tm.resolve_target_api({**p,'filters':json.loads(p.get('filters','[]'))}),
 '/api/focus':fm.handle_get,
})
for action in ('list','list_all','kpi','meta'):
    ROUTES['/api/focus/'+action]=lambda p,a=action:fm.handle_get({**p,'action':a})
POST={
 '/api/targets/create':tm.create_target,
 '/api/targets/update':lambda b:tm.update_target(b.get('target_id'),b),
 '/api/targets/delete':lambda b:tm.delete_target(b.get('target_id')),
 '/api/targets/copy':lambda b:tm.copy_target(b.get('target_id'),b),
 '/api/targets/copy-month':lambda b:tm.copy_month_targets(b.get('from_ym',''),b.get('to_ym',''),b.get('direction')),
 '/api/targets/preview':tm.preview_target,
}
for action in ('create','batch_create','delete','delete_batch','update'):
    POST['/api/focus/'+action]=lambda b,a=action:fm.handle_post({**b,'action':a})

_READ_CACHE_TTL={'/api/kpi':2.0,'/api/hourly':3.0,'/api/daily-trend':20.0,'/api/customers':10.0,
                 '/api/items':10.0,'/api/events':2.0,'/api/inbound-progress':2.0,'/api/alerts':10.0,
                 '/api/filters':300.0,'/api/health':3.0}
_read_cache={};_read_cache_lock=threading.Lock()
def _read_cache_key(path,p):return path+'?'+json.dumps(sorted(p.items()),ensure_ascii=False,separators=(',',':'))
def _read_cache_get(path,p):
    ttl=_READ_CACHE_TTL.get(path,0)
    if ttl<=0:return None
    key=_read_cache_key(path,p);now=time.monotonic()
    with _read_cache_lock:
        hit=_read_cache.get(key)
        if hit and now-hit[0]<ttl:return hit[1]
        if hit:_read_cache.pop(key,None)
    return None
def _read_cache_set(path,p,value):
    if path not in _READ_CACHE_TTL:return
    key=_read_cache_key(path,p)
    with _read_cache_lock:
        if len(_read_cache)>256:_read_cache.clear()
        _read_cache[key]=(time.monotonic(),value)
def clear_read_cache():
    with _read_cache_lock:_read_cache.clear()

class Handler(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def setup(self):
        super().setup();self.connection.settimeout(30)
    def log_message(self,*args):pass
    def allowed_origin(self):
        origin=self.headers.get('Origin')
        if not origin:return True
        scheme='http';host=self.headers.get('Host','')
        return origin==scheme+'://'+host or origin==runtime.settings().get('DASH_ALLOWED_ORIGIN','__NOT_SET__')
    def allowed_host(self):
        try:
            host=urlsplit('http://'+self.headers.get('Host','')).hostname
            bind=self.server.server_address[0]
            return bind not in ('127.0.0.1','::1') or host in ('127.0.0.1','localhost','::1')
        except ValueError:return False
    def send_bytes(self,body,status=200,mime='application/json; charset=utf-8'):
        self.send_response(status);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer');self.send_header('X-Frame-Options','DENY')
        if self.headers.get('Origin') and self.allowed_origin():self.send_header('Access-Control-Allow-Origin',self.headers['Origin']);self.send_header('Vary','Origin')
        self.end_headers()
        try:self.wfile.write(body)
        except (BrokenPipeError,ConnectionResetError):pass
    def send_json(self,obj,status=200):self.send_bytes(json.dumps(obj,ensure_ascii=False,allow_nan=False,default=str).encode('utf-8'),status)
    def do_GET(self):
        if not self.allowed_host() or not self.allowed_origin():self.send_json({'error':'Origin/Host not allowed'},403);return
        parsed=urlsplit(self.path);path=unquote(parsed.path)
        try:
            p=reporting.clean_params(parse_qs(parsed.query))
            if path in ROUTES:
                cached=_read_cache_get(path,p)
                if cached is not None:self.send_json(cached);return
                data=ROUTES[path](p);_read_cache_set(path,p,data);self.send_json(data);return
            if path=='/runtime-config.js':
                body='window.SCM_RUNTIME='+json.dumps({'demoBackend':runtime.DEMO,'inventoryConnected':reporting.health()['inventory_connected']})+';'
                self.send_bytes(body.encode(),mime='application/javascript; charset=utf-8');return
            path='/index.html' if path=='/' else path
            file=(STATIC_DIR/path.lstrip('/')).resolve()
            if not file.is_relative_to(STATIC_DIR.resolve()) or not file.is_file():self.send_json({'error':'Not found'},404);return
            mime=mimetypes.guess_type(file.name)[0] or 'application/octet-stream'
            if file.suffix in ('.js','.html','.css','.json'):mime+='; charset=utf-8'
            self.send_bytes(file.read_bytes(),mime=mime)
        except (ValueError,TypeError,KeyError) as e:self.send_json({'error':str(e)[:250]},400)
        except Exception:
            logging.exception('API failure: %s',path)
            self.send_json({'error':'Internal query error. Check local console; no data was substituted.'},500)
    def do_OPTIONS(self):
        if not self.allowed_origin() or not self.allowed_host():self.send_json({'error':'Origin not allowed'},403);return
        self.send_response(204);self.send_header('Content-Length','0')
        if self.headers.get('Origin'):self.send_header('Access-Control-Allow-Origin',self.headers['Origin'])
        self.send_header('Access-Control-Allow-Methods','GET, POST, OPTIONS');self.send_header('Access-Control-Allow-Headers','Content-Type');self.end_headers()
    def do_POST(self):
        if not self.allowed_origin() or not self.allowed_host():self.send_json({'error':'Origin/Host not allowed'},403);return
        if self.headers.get('Sec-Fetch-Site')=='cross-site' and not self.headers.get('Origin'):
            self.send_json({'error':'Cross-site write rejected'},403);return
        try:
            if self.headers.get_content_type()!='application/json':raise ValueError('Content-Type application/json required')
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=1024*1024:raise ValueError('Body must be 1 byte..1 MiB')
            if self.headers.get('Transfer-Encoding'):raise ValueError('Transfer-Encoding not supported')
            body=json.loads(self.rfile.read(length))
            if not isinstance(body,dict):raise ValueError('JSON object required')
            path=urlsplit(self.path).path
            if path not in POST:self.send_json({'error':'Not found'},404);return
            result=POST[path](body);clear_read_cache();self.send_json(result)
        except (ValueError,TypeError,KeyError) as e:self.send_json({'error':str(e)[:250]},400)
        except Exception:
            logging.exception('Local write failed');self.send_json({'error':'Local write failed; transaction rolled back'},500)

# Compatibility entrypoints for existing callers/tests.
api_kpi=reporting.kpi;api_hourly=reporting.hourly;api_customers=reporting.customers;api_items=reporting.items
api_daily_trend=reporting.daily;api_events=reporting.events;api_filters=reporting.filters
api_alerts=reporting.alerts;api_inbound_progress=reporting.progress
get_db=runtime.connect

def make_server(host=None,port=None):
    s=runtime.settings();host=host or s.get('DASH_HOST','127.0.0.1');port=int(port if port is not None else s.get('DASH_PORT','8765'))
    if host not in ('127.0.0.1','localhost','::1'):raise ValueError('This release is local-only. LAN access needs approved authentication/reverse proxy.')
    httpd=ThreadingHTTPServer((host,port),Handler);httpd.daemon_threads=True;return httpd

def main():
    from launcher import main as launch
    return launch(['serve'])
if __name__=='__main__':raise SystemExit(main())
