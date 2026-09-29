/* Static demo never performs API fetches. Live writes are JSON, same origin by default. */
(function(){
  'use strict';
  function isDemo(){return window.SCM_PREVIEW===true||new URLSearchParams(location.search).get('demo')==='1';}
  async function request(path,body){
    if(isDemo()){
      if(!window.SCMOffline)throw new Error('데모 저장소가 준비되지 않았습니다.');
      return window.SCMOffline.request(path,body);
    }
    const base=String(window.SCM_CONFIG?.apiBase||'').replace(/\/$/,'');
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),30000);
    try{
      const res=await fetch(base+path,{method:body===undefined?'GET':'POST',cache:'no-store',credentials:'same-origin',signal:controller.signal,
        headers:{Accept:'application/json',...(body===undefined?{}:{'Content-Type':'application/json'})},...(body===undefined?{}:{body:JSON.stringify(body)})});
      const data=await res.json();if(!res.ok||data.error)throw new Error(data.error||'HTTP '+res.status);return data;
    }finally{clearTimeout(timer);}
  }
  window.SCMTransport={request,isDemo};
})();
