"""Splunk session-key login and checked, paginated v2 search results. Standard library only."""
from __future__ import annotations
import json, re, ssl, time, urllib.error, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from ..common import ConfigError, UpstreamError, truth

class ResultLimit(UpstreamError): pass
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl): return None

def check_messages(body):
    for msg in body.get('messages',[]):
        if str(msg.get('type','')).upper() in {'ERROR','FATAL','WARN','WARNING'}:
            raise UpstreamError('Splunk 검색 경고/오류. 부분 결과를 반영하지 않습니다. Splunk 작업 검사기를 확인하세요')

def build_search(d,lower,upper):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+',d['index']): raise ConfigError('Splunk index 형식 오류')
    quoted=lambda x:json.dumps(str(x),ensure_ascii=True)
    # DO NOT put mutable PLANT/C_ID/date/status filters before latest-row selection.
    # Otherwise a row that leaves the report scope would remain incorrectly counted locally.
    spl=(f'search index={d["index"]} source={quoted(d["source"])} '
         f'EVENT_TYPE={quoted(d.get("event_type","TREAD_DYN"))} TABNAME={quoted(d["table"])} '
         f'earliest=0 latest={int(upper)+86400} _index_earliest={int(lower)} _index_latest={int(upper)}\n'
         f'| where _indextime>={int(lower)} AND _indextime<{int(upper)}\n'
         '| eval event_epoch=_time, indexed_epoch=_indextime\n'
         '| table _raw event_epoch indexed_epoch')
    return spl

class SplunkClient:
    def __init__(self,profile):
        self.p=profile; self.key=''; self.key_at=0
        context=ssl.create_default_context(cafile=profile.get('ca') or None) if profile['verify'] else ssl._create_unverified_context()
        proxy=profile.get('proxy','')
        self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({'http':proxy,'https':proxy} if proxy else {}),
                         urllib.request.HTTPSHandler(context=context),NoRedirect())
    def _http(self,method,path,form=None,params=None,authorized=True):
        url=self.p['base_url']+path
        if params: url+='?'+urllib.parse.urlencode(params)
        headers={'Accept':'application/json','User-Agent':'SCMRealtimeDB/1.0'}
        if authorized: headers['Authorization']='Splunk '+self.key
        data=None
        if form is not None:
            data=urllib.parse.urlencode(form).encode('utf-8'); headers['Content-Type']='application/x-www-form-urlencoded'
        req=urllib.request.Request(url,data=data,headers=headers,method=method)
        try:
            with self.opener.open(req,timeout=self.p['timeout']) as resp:
                limit=80*1024*1024
                raw=resp.read(limit+1)
                if len(raw)>limit: raise ResultLimit('Splunk 응답 크기 한도를 초과했습니다')
                return raw
        except urllib.error.HTTPError: raise
        except (ssl.SSLError,urllib.error.URLError,TimeoutError,OSError) as exc:
            if isinstance(exc,ssl.SSLError) or 'CERTIFICATE_VERIFY' in str(exc):
                raise UpstreamError('Splunk SSL 검증 오류. 현재 환경에서는 SPLUNK_VERIFY_SSL=false로 설정하고 재시작하세요') from None
            raise UpstreamError('Splunk 통신 실패/시간 초과. 원본·커서를 유지합니다') from None
    def login(self):
        if not self.p.get('user') or not self.p.get('password'): raise ConfigError('.env Splunk USER/PASSWORD가 비어 있습니다')
        try:
            raw=self._http('POST','/services/auth/login',{'username':self.p['user'],'password':self.p['password']},authorized=False)
        except urllib.error.HTTPError as e: raise UpstreamError(f'Splunk 로그인 HTTP {e.code}') from None
        try: key=ET.fromstring(raw).findtext('sessionKey')
        except ET.ParseError: raise UpstreamError('Splunk 로그인 XML 응답 오류') from None
        if not key: raise UpstreamError('Splunk sessionKey 없음')
        self.key=key; self.key_at=time.monotonic()
    def request(self,method,path,form=None,params=None):
        if not self.key or time.monotonic()-self.key_at>3000: self.login()
        for attempt in range(2):
            try: raw=self._http(method,path,form,params)
            except urllib.error.HTTPError as e:
                if e.code==401 and attempt==0: self.login(); continue
                raise UpstreamError(f'Splunk API HTTP {e.code}') from None
            if not raw: return {}
            try: body=json.loads(raw)
            except ValueError: raise UpstreamError('Splunk JSON 응답 오류') from None
            check_messages(body); return body
        raise UpstreamError('Splunk 재인증 실패')
    def search(self,spl,max_events=50000):
        sid=None
        try:
            body=self.request('POST','/services/search/jobs',form={'search':spl,'output_mode':'json','exec_mode':'normal',
               'max_count':max_events+1,'status_buckets':0})
            sid=body.get('sid')
            if not sid: raise UpstreamError('Splunk SID 없음')
            path='/services/search/jobs/'+urllib.parse.quote(str(sid),safe='')
            deadline=time.monotonic()+self.p['timeout']
            while True:
                b=self.request('GET',path,params={'output_mode':'json'})
                entries=b.get('entry',[])
                if not entries: raise UpstreamError('Splunk 검색 상태 누락')
                c=entries[0]['content']; check_messages(c)
                if truth(c.get('isFailed',False)) or c.get('dispatchState') in {'FAILED','BAD_INPUT_CANCEL'}: raise UpstreamError('Splunk 검색 실패')
                if truth(c.get('isFinalized',False)): raise UpstreamError('Splunk 검색 조기 종료. 결과 미반영')
                if truth(c.get('isDone',False)): break
                if time.monotonic()>deadline: raise UpstreamError('Splunk 검색 완료 시간 초과')
                time.sleep(0.5)
            total=int(c.get('resultCount',0))
            if total>max_events: raise ResultLimit('Splunk 건수 한도 초과: 수집 시간창을 분할합니다')
            result=[]
            while len(result)<total:
                n=min(2000,total-len(result))
                b=self.request('GET','/services/search/v2/jobs/'+urllib.parse.quote(str(sid),safe='')+'/results',
                  params={'output_mode':'json','offset':len(result),'count':n})
                if truth(b.get('preview',False)): raise UpstreamError('미리보기 결과는 적재하지 않습니다')
                page=b.get('results',[])
                if not page or len(page)>n: raise UpstreamError('Splunk 결과 페이지 누락/건수 불일치')
                result.extend(page)
            if len(result)!=total: raise UpstreamError('Splunk 결과 총건수 불일치')
            return result
        finally:
            if sid:
                try: self.request('DELETE','/services/search/jobs/'+urllib.parse.quote(str(sid),safe=''))
                except Exception: pass
    def windows(self,d,lower,upper):
        """Yield complete half-open index-time windows. Only successful windows advance the checkpoint."""
        max_window=int(d.get('max_window_seconds',3600))
        cursor=lower
        while cursor<upper:
            end=min(upper,cursor+max_window)
            yield from self._window(d,cursor,end)
            cursor=end
    def _window(self,d,lower,upper):
        try: rows=self.search(build_search(d,lower,upper),int(d.get('max_events',50000)))
        except ResultLimit:
            if upper-lower<=1: raise UpstreamError('1초 구간도 수집 한도 초과. max_events 또는 원천 분할이 필요합니다') from None
            mid=(lower+upper)//2
            yield from self._window(d,lower,mid); yield from self._window(d,mid,upper)
            return
        yield lower,upper,rows
