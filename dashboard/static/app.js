/* SCM Executive UI — four routes, one unchanged REST contract. */
(function () {
  'use strict';
  const C=window.SCMCore, esc=C.escapeHTML, $=(s,b=document)=>b.querySelector(s), $$=(s,b=document)=>[...b.querySelectorAll(s)];
  const cfg=window.SCM_CONFIG, url=new URLSearchParams(location.search);
  const demo=window.SCM_PREVIEW===true || url.get('demo')==='1';
  const VIEWS=['overview','inbound','shipment','inventory','targets'];
  const TITLES={overview:'전체 운영 현황',inbound:'입고 운영 현황',shipment:'출하 운영 현황',inventory:'재고 운영 현황',targets:'목표 관리'};
  const FILTER_IDS={customer:'filterCustomer',warehouse:'filterWarehouse',product_group:'filterProductGroup',item:'filterItem'};
  const FILTER_NAMES={customer:'거래선',warehouse:'창고',product_group:'제품군',item:'ITEM'};
  const TYPE_DIVISORS={EA:[1,1e3,1e6],EQ:[1,1e3,1e6,1e8],BOX:[1,1e3,1e6],USD:[1,1e6,1e8,1e9]};
  const state={
    view:VIEWS.includes(location.hash.slice(1))?location.hash.slice(1):'overview',
    metric:C.METRICS[url.get('metric')]?url.get('metric'):'EA',
    filters:{date:C.validDate(url.get('date'))?url.get('date').replace(/-/g,''):'',customer:url.get('customer')||'ALL',warehouse:url.get('warehouse')||'ALL',product_group:url.get('product_group')||'ALL',item:url.get('item')||'ALL'},
    units:{EA:1e6,EQ:1e8,BOX:1e3,USD:1e8},range:'daily',month:'',overviewPeriod:'hourly',shipmentTab:'customers',inboundTab:'progress',
    refresh:cfg.refreshSeconds||5,busy:false,data:{},statuses:{},tick:0,search:{inboundTable:'',shipmentTable:''},sort:{},tables:{},chartExport:[],
    previousEvents:[],eventInitialized:false,newEvents:new Set(),previousProgress:new Set(),progressInitialized:false,newProgress:new Set(),lastIdentity:''
  };
  state.month=(state.filters.date||C.today()).slice(0,6);
  const units=demo?{verified:true,profile:'raw',overrides:{}}:cfg.units;
  const verified=demo||units.verified;
  const charts={};const previousValues=new WeakMap();const animationFrames=new WeakMap();
  const reducedMotion=window.matchMedia('(prefers-reduced-motion: reduce)');
  let pollTimer=null, cycleTimer=null, generation=0, controller=null, toastTimer=null, filterOptionsSignature='';
  let focusLoadedAt=0,focusMetric='';
  let identity=()=>JSON.stringify([state.filters,state.metric]);
  const suffix=div=>({1:'',1000:'K',1000000:'M',100000000:'억',1000000000:'B'}[div]||'');
  function unitLabel(metric=state.metric, full=false){
    const m=C.METRICS[metric]||C.METRICS.EA,div=state.units[m.type];
    return `${suffix(div)} ${verified?m.unit:'API값'}`.trim()+(full&&!verified?` (${metric})`:'');
  }
  const rawUnit=metric=>verified?(C.METRICS[metric]||C.METRICS.EA).unit:`API 원값 · ${metric}`;
  function formatMetric(value,metric=state.metric,include=false){
    const n=C.number(value);if(n===null)return '—';
    const m=C.METRICS[metric]||C.METRICS.EA, div=state.units[m.type];
    const dec=div===1?(metric==='USD'?2:0):div===1000?0:div===100000000?1:2;
    return C.format(n/div,dec)+(include?' '+unitLabel(metric):'');
  }
  const scaled=(value,endpoint,metric='EA')=>C.scale(value,endpoint,metric,units);
  function replaceIfChanged(el,html){if(el._lastHTML!==html){el.innerHTML=html;el._lastHTML=html;}}
  function setText(selector,text){$$(selector).forEach(el=>{if(el.textContent!==String(text))el.textContent=String(text);});}
  function toast(message){$('#toast').textContent=message;$('#toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('#toast').hidden=true,4200);}
  function setTheme(theme){
    document.documentElement.dataset.theme=theme==='dark'?'dark':'light';
    $('#themeToggle').setAttribute('aria-label',theme==='dark'?'라이트 테마로 전환':'다크 테마로 전환');
    try{localStorage.setItem('scm-theme',theme);}catch(_){/* Storage is optional in locked-down browsers. */}
    Object.values(charts).forEach(c=>c.draw());
  }
  function updateUnitSelector(){
    const type=C.METRICS[state.metric].type,select=$('#filterUnit');
    select.innerHTML=TYPE_DIVISORS[type].map(div=>`<option value="${div}">${({1:'원본',1000:'K · 천',1000000:'M · 백만',100000000:'억',1000000000:'B · 십억'})[div]}</option>`).join('');
    select.value=String(state.units[type]);
    $$('[data-metric]').forEach(b=>{const active=b.dataset.metric===state.metric;b.classList.toggle('active',active);b.setAttribute('aria-pressed',String(active));});
  }
  function fitNumbers(){
    $$('.hero-value strong').forEach(el=>{
      if(!el.getClientRects().length)return;
      el.style.fontSize='';
      const parent=el.parentElement;let available=parent.clientWidth-8;
      [...parent.children].filter(e=>e!==el&&!e.classList.contains('delta-flash')).forEach(e=>available-=e.getBoundingClientRect().width+8);
      const actual=el.getBoundingClientRect().width;
      if(actual>available&&available>0){const original=parseFloat(getComputedStyle(el).fontSize);el.style.fontSize=Math.max(19,original*available/actual)+'px';}
    });
  }
  function updateNumber(el,value,formatter,animate){
    const n=C.number(value),old=previousValues.get(el);
    cancelAnimationFrame(animationFrames.get(el));
    previousValues.set(el,n);
    el.title=n===null?'미제공 / 미연동':`${C.format(n,3)} ${rawUnit(state.metric)}`;
    if(!animate||reducedMotion.matches||old===undefined||old===null||n===null||old===n||!el.getClientRects().length){el.textContent=formatter(n);return;}
    const start=performance.now(),duration=620;
    el.classList.remove('value-changed');void el.offsetWidth;el.classList.add('value-changed');
    const step=now=>{const t=Math.min(1,(now-start)/duration),e=1-Math.pow(1-t,3);el.textContent=formatter(old+(n-old)*e);if(t<1)animationFrames.set(el,requestAnimationFrame(step));else{el.textContent=formatter(n);fitNumbers();}};
    animationFrames.set(el,requestAnimationFrame(step));
    const card=el.closest('[data-entity]');if(card){card.classList.remove('pulse');void card.offsetWidth;card.classList.add('pulse');}
    if(el.dataset.kpi?.endsWith('.actual')){
      const flash=$('[data-delta]',el.parentElement);if(flash){flash.textContent=(n>old?'+':'−')+formatMetric(Math.abs(n-old),state.metric,true);flash.classList.remove('show');void flash.offsetWidth;flash.classList.add('show');}
    }
  }
  function renderKPI(animate=false){
    const raw=state.data.kpi;const k=C.normalizeKPI(raw,state.metric,units);state.kpi=k;
    $$('[data-kpi]').forEach(el=>{const [entity,key]=el.dataset.kpi.split('.');updateNumber(el,k[entity]?.[key],v=>formatMetric(v,state.metric,el.hasAttribute('data-with-unit')),animate);});
    setText('[data-metric-unit]',unitLabel());
    for(const entity of ['production','shipment']){
      const d=k[entity],na=entity==='production'&&state.metric==='USD';
      setText(`[data-date="${entity}"]`,raw?C.dateLabel(d.date).slice(5):'');
      setText(`[data-percent="${entity}"]`,d.achievement===null?'—':C.format(d.achievement,1)+'%');
      setText(`[data-ach-badge="${entity}"]`,na?'금액 미제공':d.target===null||d.target<=0?'목표 미제공':d.achievement>=100?'목표 달성':'월간 누적');
      $$(`[data-progress="${entity}"]`).forEach(el=>{
        const value=d.achievement;
        $('.bullet-fill',el).style.width=(value===null?0:Math.max(0,Math.min(100,value)))+'%';
        if(value!==null){el.setAttribute('aria-valuenow',String(Math.max(0,Math.min(100,value))));el.setAttribute('aria-valuetext',C.format(value,1)+'%');}
        else{el.removeAttribute('aria-valuenow');el.setAttribute('aria-valuetext','달성률 미제공');}
      });
      $$(`[data-change="${entity}"]`).forEach(el=>{
        el.className=d.change===null?'neutral':d.change>0?'positive':d.change<0?'negative':'neutral';
        el.textContent=d.change===null?(d.yesterday===0&&d.today!==null?'전일 0 · 비교 불가':'—'):(d.change>0?'↑ +':d.change<0?'↓ −':'')+C.format(Math.abs(d.change),1)+'%';
        el.title='기준일 실적과 전일 전체 실적의 비교입니다. 전일 동시간대 비교가 아닙니다.';
      });
      let gap='목표 데이터 미제공';
      if(na)gap='입고 금액 데이터 없음';
      else if(d.target!==null&&d.actual!==null&&d.target>0){const rest=d.target-d.actual;gap=(rest>=0?'잔여 ':'초과 ')+formatMetric(Math.abs(rest),state.metric,true);}
      setText(`[data-gap="${entity}"]`,gap);
      setText(`[data-records="${entity}"]`,d.todayCount===null?'—':C.format(d.todayCount)+'건');
    }
    const usdRaw=state.metric==='USD'?raw:state.data.usdKpi;
    const usd=usdRaw?C.normalizeKPI(usdRaw,'USD',units).shipment:null;
    $('#shipmentUSD').textContent=usd?formatMetric(usd.today,'USD',true):'—';
    $('#shipmentUSDNote').textContent=state.statuses.usdKpi?.error&&state.metric!=='USD'?'금액 조회 실패 · 마지막 수신값':usd?`기준일 ${C.dateLabel(usd.date)}`:'USD KPI 수신 대기';
    renderInventory(k,animate);
    const pDate=k.production.date,sDate=k.shipment.date;
    if(!state.filters.date&&C.validDate(raw?.date))$('#filterDate').value=C.isoDate(raw.date);
    $('#latestButton').setAttribute('aria-pressed',String(!state.filters.date));
    $('#latestButton').title=state.filters.date?'API 최신 기준일로 돌아가기':'최신 데이터 기준일을 자동으로 사용 중';
    $('#periodLabel').textContent=raw?(pDate===sDate?`${C.dateLabel(pDate)} 기준 · 월간 누적`:`입고 ${C.dateLabel(pDate)} / 출하 ${C.dateLabel(sDate)}`):'최신 기준일 조회';
    $('#dataDate').textContent=raw?`입고 ${C.dateLabel(pDate)} / 출하 ${C.dateLabel(sDate)}`:'데이터 기준일 —';
    requestAnimationFrame(fitNumbers);
  }
  function renderInventory(k,animate){
    const connected=cfg.capabilities.inventoryConnected===true, supported=state.metric!=='USD', ready=connected&&!!state.data.kpi&&supported;
    const hasValue=ready&&k.inventory.current!==null;
    $$('[data-inv]').forEach(el=>{
      const key=el.dataset.inv;
      const v=key==='count'?k.inventory.count:ready?k.inventory[key]:null;
      updateNumber(el,v,n=>key==='count'?(n===null?'—':C.format(n)+'건'):formatMetric(n,state.metric,!el.closest('.hero-value')),animate&&ready);
    });
    setText('[data-inv-unit]',hasValue?unitLabel():'');
    setText('[data-inventory-status]',!supported?'금액 미제공':!connected?'미연동':hasValue?'수신됨':'수신 대기');
    $('[data-inventory-state]').hidden=hasValue;$('[data-inventory-values]').hidden=!hasValue;
    let title='재고 데이터 연결 대기',text='현재 API에는 재고 실적이 연결되지 않았습니다. 실제 연결 이후 현재고와 가용재고를 표시합니다.';
    if(!supported){title='재고 금액은 제공되지 않습니다';text='금액 지표는 출하에만 제공됩니다. 재고는 EA·BOX·개별 EQ 지표에서 연결 상태를 확인하세요.';}
    else if(hasValue){title='현재 재고 스냅샷 수신',text='현재고와 가용재고는 API 수신값입니다. 전일 재고와 적정재고 기준, 품목·창고별 상세 데이터는 현재 API에서 제공되지 않습니다.';}
    else if(connected){title='재고 수신값 확인 필요',text='연결 설정은 활성화되어 있으나 현재 표시할 유효한 재고 수신값이 없습니다. 수신 상태에서 API 응답을 확인하세요.';}
    replaceIfChanged($('#inventoryStatePanel'),`<div class="stock-symbol"><svg aria-hidden="true"><use href="#i-box"/></svg></div><div><span class="eyebrow">${hasValue?'CURRENT SNAPSHOT':'AWAITING VERIFIED DATA'}</span><h3>${title}</h3><p>${text}</p></div>`);
    $('#inventoryDefinition').textContent=hasValue?'API 수신값':!supported?'USD 미제공':'연결 확인 필요';
    const info=$('.inventory-info-body');$('h3',info).textContent=hasValue?'현재 스냅샷의 범위': '미연동 ≠ 재고 없음';
    $('p',info).textContent=hasValue?'현재고와 가용재고만 확인할 수 있습니다. 0은 실제 수신값일 때만 0으로 표시하며, 미제공 지표는 —로 구분합니다.':'실제 재고 수신이 검증되기 전에는 수량을 0으로 표시하지 않습니다. config.js의 재고 연결 설정과 API 수신 상태를 함께 확인하세요.';
  }
  function chartData(id){
    const hourly=id.endsWith('Hourly')||(id==='overviewChart'&&state.overviewPeriod==='hourly');
    const inbound=id.startsWith('inbound'),shipment=id.startsWith('shipment');
    const metric=state.metric;
    const raw=state.data[hourly?'hourly':'daily-trend'];
    let labels,series=[],currentIndex=null;
    const keys=inbound?['production']:shipment?['shipment']:metric==='USD'?['shipment']:['production','shipment'];
    if(hourly){
      labels=Array.from({length:24},(_,h)=>String(h).padStart(2,'0')+':00');
      for(const key of keys){
        const values=C.hourlyValues(raw,key,units,metric);
        const date=raw?.[key==='production'?'inbound_date':'shipment_date'];
        if(date===C.today())values.forEach((_,h)=>{if(h>Number(C.kstParts().hour))values[h]=null;});
        series.push({key,name:key==='production'?'입고':'출하',color:key==='production'?'--production':'--shipment',values});
      }
      if(raw&&keys.every(key=>raw[key==='production'?'inbound_date':'shipment_date']===C.today()))currentIndex=Number(C.kstParts().hour);
    }else{
      const month=raw?.month||state.month;
      const base=C.dailySeries(raw,month,'production',units,metric);
      labels=base.map(p=>C.isoDate(p.date));
      for(const key of keys){
        const field=metric==='USD'?'shipment_amount':key;
        series.push({key,name:metric==='USD'?'출하 금액':key==='production'?'입고':'출하',color:key==='production'?'--production':'--shipment',values:C.dailySeries(raw,month,field,units,metric).map(p=>p.value)});
      }
    }
    const type=C.METRICS[metric].type;
    const title=$(`#${id}`).closest('.panel').querySelector('h2').textContent;
    return {period:hourly?'hourly':'daily',title,labels,series,kind:hourly?'bar':'line',currentIndex,unit:unitLabel(metric),rawUnit:rawUnit(metric),divisor:state.units[type],format:v=>formatMetric(v,metric,true),shortLabel:v=>hourly?v.slice(0,2)+'시':v.slice(8)+'일'};
  }
  function renderCharts(){
    const ids=state.view==='overview'?['overviewChart']:state.view==='inbound'?['inboundHourly','inboundDaily']:state.view==='shipment'?['shipmentHourly','shipmentDaily']:[];
    ids.forEach(id=>{
      const d=chartData(id);const c=charts[id]||(charts[id]=new window.SCMChart(id));c.set(d);
      const panel=$(`#${id}`).closest('.panel');panel.dataset.api=d.period==='hourly'?'hourly':'daily-trend';
      const fixed='';
      $(`[data-chart-scope="${id}"]`).textContent=`선택 조건 · ${d.unit}${fixed}`;
      if(d.period==='hourly'){
        const raw=state.data.hourly;
        const inDate=raw?.inbound_date,shDate=raw?.shipment_date;
        $(`[data-chart-date="${id}"]`).textContent=id.startsWith('inbound')?C.dateLabel(inDate):id.startsWith('shipment')?C.dateLabel(shDate):inDate===shDate?C.dateLabel(inDate):`입고 ${C.dateLabel(inDate)} / 출하 ${C.dateLabel(shDate)}`;
      }else $(`[data-chart-date="${id}"]`).textContent=(state.data['daily-trend']?.month||state.month).replace(/^(\d{4})(\d{2})$/,'$1.$2')+' · 빈 구간 = 미제공';
    });
  }
  function renderRanking(){
    const raw=state.data.customers,metric=state.metric,field=metric==='USD'?'shipment_amount':'shipment';
    const list=(raw?.customers||[]).filter(c=>c.customer_key!=='__OTHERS__').map(c=>({...c,value:scaled(c[field],'customers',metric)})).sort((a,b)=>(b.value??-Infinity)-(a.value??-Infinity)).slice(0,5);
    const total=C.number(raw?.[metric==='USD'?'total_shipment_amount':'total_shipment']);
    const max=Math.max(1,...list.map(c=>c.value??0));
    const html=list.length?list.map((c,i)=>{
      const share=total>0?C.number(c[field])/total*100:metric==='EA'?C.number(c.share):null;
      return `<button type="button" class="rank-row" data-customer="${esc(c.customer_key)}" title="${esc(c.name||c.customer_key)} · 출하 공통 필터"><span class="rank-num">${String(i+1).padStart(2,'0')}</span><span><span class="rank-name">${esc(c.name||c.customer_key)}</span><span class="rank-track"><span class="rank-fill" style="display:block;width:${Math.max(0,(c.value||0)/max*100)}%"></span></span></span><span class="rank-value">${formatMetric(c.value,metric)}<small>${share===null?'—':C.format(share,1)+'%'}</small></span></button>`;
    }).join(''):'<div class="empty-state">표시할 거래선 데이터가 없습니다.</div>';
    replaceIfChanged($('#customerRanking'),html);
    $('#rankScope').textContent=`전체 출하 · ${{daily:'기준일',weekly:'주간',monthly:'월간'}[state.range]} · ${metric==='USD'?'금액':'수량'}`;
    $('#rankUnit').textContent=unitLabel(metric);
  }
  function renderNotes(){
    const k=state.kpi,notes=[];
    if(state.statuses.kpi?.error)notes.push({title:'KPI 수신 확인 필요',body:'마지막 수신값이 남아 있을 수 있습니다. 상단 수신 상태를 확인하세요.',level:'danger'});
    if(state.filters.customer!=='ALL')notes.push({title:'원천별 거래선 코드 확인',body:'입고 GC_CODE와 출하 KUNAG의 동일 거래선 매핑은 회사 기준정보와 대조해야 합니다.',level:'warning'});
    if(k&&state.data.kpi){
      for(const [entity,label] of [['production','입고'],['shipment','출하']]){
        const d=k[entity];if(d.actual===null)continue;
        const gap=d.target===null?null:d.target-d.actual;
        notes.push({title:d.achievement===null?`${label} 월간 목표 미제공`:`${label} ${d.achievement>=100?'목표 달성':'달성률'} ${C.format(d.achievement,1)}%`,body:gap===null?'현재 API에서 목표 대비 비교를 할 수 없습니다.':(gap>=0?'월간 목표까지 ':'월간 목표보다 ')+formatMetric(Math.abs(gap),state.metric,true)+(gap>=0?' 남았습니다.':' 초과했습니다.'),level:''});
      }
    }
    if(!cfg.capabilities.inventoryConnected)notes.push({title:'재고 가시성 연결 필요',body:'현재고·가용재고 미연동. ‘0’과 구분합니다.',level:'warning'});
    const dates=[k?.production.date,k?.shipment.date].filter(Boolean);
    if(dates.some(d=>d!==C.today())&&!state.filters.date)notes.unshift({title:'최신 실적 기준일 확인',body:dates.map(C.dateLabel).filter((v,i,a)=>a.indexOf(v)===i).join(' / ')+' 실적입니다. API 연결 상태와 실적 기준일은 별개입니다.',level:'warning'});
    const serverDanger=(state.data.alerts?.alerts||[]).find(a=>a.level==='danger');
    if(serverDanger)notes.unshift({title:'서버 경고',body:serverDanger.msg,level:'danger'});
    const shown=notes.slice(0,3);state.notes=notes;
    replaceIfChanged($('#managementNotes'),shown.length?shown.map((n,i)=>`<div class="management-note ${n.level}"><span class="note-index">${String(i+1).padStart(2,'0')}</span><div><b>${esc(n.title)}</b><p>${esc(n.body)}</p></div></div>`).join(''):'<div class="empty-state">데이터 수신 후 확인 사항을 표시합니다.</div>');
    $('#noteCount').textContent=notes.length?String(notes.length):'—';$('#noteCount').title='전체 확인 사항과 서버 알림은 수신 상태에서 확인합니다.';
  }
  function tableModel(id){
    const metric=state.metric;
    const qtyLabel=unitLabel(state.metric),moneyLabel=unitLabel('USD');
    const col=(key,label,type='text',metric)=>({key,label,type,metric});
    if(id==='inboundTable')return {source:'items',description:`선택 조건 · ${C.dateLabel(state.data.items?.date)} · 수량 ${qtyLabel}`,action:'item',
      columns:[col('material','ITEM'),col('name','품목명'),col('product_group','제품군'),col('production',`입고 (${qtyLabel})`,'metric',state.metric),col('count','레코드','number')],
      rows:(state.data.items?.items||[]).map(it=>({...it,key:it.material,production:scaled(it.production,'items'),count:C.number(it.count)}))};
    if(state.shipmentTab==='customers'){
      const raw=state.data.customers,total=C.number(raw?.[metric==='USD'?'total_shipment_amount':'total_shipment']);
      return {source:'customers',description:`선택 조건 · ${C.dateLabel(raw?.shipment_date)} · 수량 ${qtyLabel} / 금액 ${moneyLabel}`,action:'customer',
        columns:[col('name','거래선'),col('shipment',`출하 (${qtyLabel})`,'metric',state.metric),col('shipment_amount',`금액 (${moneyLabel})`,'metric','USD'),col('share',metric==='USD'?'금액 비중':'수량 비중','percent'),col('count','레코드','number')],
        rows:(raw?.customers||[]).map(c=>({...c,key:c.customer_key,name:c.name||c.customer_key,shipment:scaled(c.shipment,'customers'),shipment_amount:scaled(c.shipment_amount,'customers','USD'),share:total>0?C.number(c[metric==='USD'?'shipment_amount':'shipment'])/total*100:metric==='EA'?C.number(c.share):null,count:C.number(c.count)}))};
    }
    if(state.shipmentTab==='items')return {source:'items',description:'선택 조건 · 입고/출하 합집합 상위 품목',action:'item',
      columns:[col('material','ITEM'),col('name','품목명'),col('product_group','제품군'),col('shipment',`출하 (${qtyLabel})`,'metric',state.metric),col('shipment_amount',`금액 (${moneyLabel})`,'metric','USD')],
      rows:(state.data.items?.items||[]).map(it=>({...it,key:it.material,shipment:scaled(it.shipment,'items'),shipment_amount:scaled(it.shipment_amount,'items','USD')}))};
    const raw=state.data['daily-trend'],month=raw?.month||state.month;
    const qs=C.dailySeries(raw,month,'shipment',units,metric), amounts=C.dailySeries(raw,month,'shipment_amount',units,'USD');
    return {source:'daily-trend',description:`선택 조건 · ${month.slice(0,4)}.${month.slice(4)} · 미제공 일자는 —`,action:null,
      columns:[col('date','기준일'),col('shipment',`출하 (${qtyLabel})`,'metric',state.metric),col('shipment_amount',`금액 (${moneyLabel})`,'metric','USD')],
      rows:qs.map((p,i)=>({date:C.isoDate(p.date),shipment:p.value,shipment_amount:amounts[i]?.value??null}))};
  }
  function renderTable(id){
    const model=tableModel(id);let rows=model.rows;
    const search=state.search[id].trim().toLocaleLowerCase();
    if(search)rows=rows.filter(row=>model.columns.some(c=>String(row[c.key]??'').toLocaleLowerCase().includes(search)));
    const sort=state.sort[id];
    if(sort){const col=model.columns.find(c=>c.key===sort.key);if(col)rows=[...rows].sort((a,b)=>{
      const x=a[sort.key],y=b[sort.key];if(x===null||x===undefined)return y===null||y===undefined?0:1;if(y===null||y===undefined)return -1;
      return (col.type==='text'?String(x).localeCompare(String(y),'ko'):Number(x)-Number(y))*sort.dir;
    });}
    state.tables[id]={...model,rows};
    const table=$('#'+id);table.closest('.panel').dataset.api=model.source;
    const thead='<tr>'+model.columns.map(col=>`<th class="${col.type==='text'?'':'num'}" aria-sort="${sort?.key===col.key?(sort.dir===1?'ascending':'descending'):'none'}"><button type="button" data-sort-table="${id}" data-sort-key="${col.key}">${esc(col.label)} <span aria-hidden="true">${sort?.key===col.key?(sort.dir===1?'↑':'↓'):'↕'}</span></button></th>`).join('')+'</tr>';
    replaceIfChanged($('thead',table),thead);
    const display=(v,col)=>col.type==='metric'?formatMetric(v,col.metric):col.type==='percent'?(C.number(v)===null?'—':C.format(v,1)+'%'):col.type==='number'?C.format(v):v??'—';
    const html=rows.length?rows.map(row=>`<tr ${model.action?`data-key="${esc(row.key)}" data-action="${model.action}" tabindex="0" role="button" aria-label="${esc(row.name||row.material||row.key)} 공통 필터"`:''} class="${model.action&&state.filters[model.action]===row.key?'selected':''}">${model.columns.map(col=>`<td class="${col.type!=='text'?'num':col.key==='material'?'material':col.key==='name'?'name-cell':''}" title="${esc(col.type==='metric'?C.format(row[col.key],3)+' '+rawUnit(col.metric):row[col.key])}">${esc(display(row[col.key],col))}</td>`).join('')}</tr>`).join(''):`<tr><td colspan="${model.columns.length}"><div class="empty-state">${search?'검색 결과가 없습니다.':'표시할 수신 데이터가 없습니다.'}</div></td></tr>`;
    replaceIfChanged($('tbody',table),html);
    $(`[data-table-description="${id}"]`).textContent=model.description;
    $(`[data-table-foot="${id}"]`).textContent=`${rows.length} / ${model.rows.length}행 · ${!verified?'배율 미확정 · ':''}— 미제공`;
    if(id==='shipmentTable')$('#customerRange').hidden=state.shipmentTab!=='customers';
  }
  function renderEvents(){
    const all=state.data.events?.events||[];
    const render=(id,kind)=>{
      const events=all.filter(e=>kind==='shipment'?String(e.type).includes('출하'):!String(e.type).includes('출하'));
      const html=events.length?events.map(e=>`<div class="event-row ${state.newEvents.has(C.eventKey(e))?'new-event':''}"><span class="event-time">${esc(e.time||'—')}<small>${esc(C.dateLabel(e.date).slice(5))}</small></span><div class="event-content"><span class="event-type ${kind==='shipment'?'shipment':''}">${esc(e.type||'유형 미제공')}</span><p class="event-detail">${esc(e.detail||'상세 미제공')}</p></div></div>`).join(''):'<div class="empty-state">최근 전체 50건 중 해당 이벤트가 없습니다.</div>';
      replaceIfChanged($('#'+id),html);
    };
    render('inboundEvents','inbound');render('shipmentEvents','shipment');
    const e=all[0];$('#latestEvent').textContent=e?`${C.dateLabel(e.date)} ${e.time||''} · ${e.type||''} · ${e.detail||''}`:'수신 이벤트가 없습니다.';
  }
  function progressKey(p){return JSON.stringify([p.material,p.time,p.warehouse,p.qty]);}
  function renderProgress(){
    const list=state.data['inbound-progress']?.progress||[],stages=['대기','생산완료','입고등록','검수중','적치중','완료'],isSim=cfg.capabilities.progressIsSimulation;
    $('#progressBadge').textContent=state.inboundTab==='progress'?(isSim?'모의 단계':'입고완료'):'수신 로그';
    $('#inboundScope').textContent=state.inboundTab==='progress'?`최근 입고 최대 15건 · ${isSim?'실제 단계 상태 아님':'수신 완료 이벤트'}`:'선택 조건의 최근 입고';
    const html=list.length?list.map(p=>{
      const index=C.number(p.stage_index),valid=Number.isInteger(index)&&index>=0&&index<=5;
      const stage=p.stage||'단계 미제공';
      return `<div class="progress-row ${state.newProgress.has(progressKey(p))?'new-event':''}"><div class="progress-top"><span class="progress-material" title="${esc(p.item_name||p.material)}">${esc(p.material||'ITEM 미제공')}</span><b class="progress-qty">${formatMetric(scaled(p.qty,'inbound-progress'),'EA',true)}</b></div><div class="progress-meta"><span>${esc(p.line||'—')} · ${esc(p.warehouse||'—')}</span><span>${esc(String(p.time||'').replace(/^(\d{2})(\d{2})(\d{2})$/,'$1:$2:$3'))}</span></div><div class="progress-stages" aria-label="${isSim?'모의 단계 ':''}${esc(stage)}">${stages.map((s,i)=>`<span aria-hidden="true" class="stage-segment ${valid&&i<index?'done':valid&&i===index?'current':''}" title="${s}"></span>`).join('')}<span class="stage-label">${isSim?'모의 · ':''}${esc(stage)}</span></div></div>`;
    }).join(''):'<div class="empty-state">입고 진행 데이터가 없습니다.</div>';
    replaceIfChanged($('#inboundProgress'),html);
    $('#inboundProgress').hidden=state.inboundTab!=='progress';$('#inboundEvents').hidden=state.inboundTab!=='events';
    $('#inboundProgress').closest('.panel').dataset.api=state.inboundTab==='progress'?'inbound-progress':'events';
  }
  function renderFilters(){
    const options=state.data.filters;if(!options)return;
    const sig=JSON.stringify(options);
    if(sig!==filterOptionsSignature){
      for(const [key,id] of Object.entries(FILTER_IDS)){
        const field={customer:'customers',warehouse:'warehouses',product_group:'product_groups',item:'items'}[key];
        const list=Array.isArray(options[field])?options[field]:[];
        if(key==='item'){
          const dl=$('#itemList');dl.innerHTML=`<option value="ALL">전체 ${FILTER_NAMES[key]}</option>`;
          list.forEach(item=>{const opt=document.createElement('option');opt.value=String(item.key);opt.textContent=item.name?`${item.name} · ${item.key}`:String(item.key);dl.appendChild(opt);});
        } else {
          const select=$('#'+id);select.innerHTML=`<option value="ALL">전체 ${FILTER_NAMES[key]}</option>`;
          list.forEach(item=>{const opt=document.createElement('option');opt.value=String(item.key);opt.textContent=item.name?`${item.name}${key==='item'?' · '+item.key:''}`:String(item.key);select.appendChild(opt);});
        }
      }
      filterOptionsSignature=sig;
    }
    for(const [key,id] of Object.entries(FILTER_IDS)){
      const value=state.filters[key];
      if(key==='item'){
        const input=$('#'+id);if(input.value!==value)input.value=value;
      } else {
        const select=$('#'+id);
        if(![...select.options].some(o=>o.value===value)){const opt=document.createElement('option');opt.value=value;opt.textContent=value;select.appendChild(opt);}
        select.value=value;
      }
    }
  }
  function renderFilterChips(){
    const active=Object.entries(state.filters).filter(([k,v])=>k!=='date'&&v&&v!=='ALL');
    $('#filterCount').hidden=!active.length;$('#filterCount').textContent=String(active.length);
    $('#filterChips').hidden=!active.length;
    const html='<span class="muted">공통 필터</span>'+active.map(([key,v])=>{
      const selected=$('#'+FILTER_IDS[key]);const name=selected?.selectedOptions?.[0]?.textContent||v;
      return `<span class="filter-chip">${FILTER_NAMES[key]} · ${esc(name)}<button type="button" data-remove-filter="${key}" aria-label="${FILTER_NAMES[key]} 필터 해제">×</button></span>`;
    }).join('')+'<span class="muted">차트·순위·로그는 각 영역의 선택 조건 표시를 확인하세요.</span>';
    replaceIfChanged($('#filterChips'),html);
  }
  function markErrors(){
    $$('.panel[data-api]').forEach(panel=>{
      const status=state.statuses[panel.dataset.api];let strip=$('.panel-error',panel);
      if(status?.error){if(!strip){strip=document.createElement('div');strip.className='panel-error';panel.prepend(strip);}strip.textContent=status.data?'갱신 실패 · 마지막 수신값 표시':'수신 실패 · 데이터를 표시할 수 없습니다.';}
      else if(strip)strip.remove();
    });
  }
  function renderStatus(){
    const statuses=Object.values(state.statuses).filter(s=>s.name!=='filters');
    const failed=statuses.filter(s=>s.error), good=statuses.filter(s=>s.data),main=state.statuses.kpi;
    const stale=main?.time&&Date.now()-main.time>Math.max(30000,state.refresh*3000);
    let status=demo?'demo':state.refresh===0?'paused':stale?'partial':failed.length?(good.length?'partial':'error'):good.length?'online':'waiting';
    $('#connectionButton').dataset.status=status;
    $('#connectionText').textContent=demo?'DEMO':state.refresh===0?'일시정지':stale?'수신 지연':status==='online'?'API 연결':status==='partial'?'일부 수신 실패':status==='error'?'연결 실패':state.busy?'조회 중':'수신 대기';
    $('#connectionButton').title='API 통신 상태입니다. 원천 데이터의 수집시각은 응답에 별도로 제공되지 않습니다.';
    if(main?.time){const p=C.kstParts(new Date(main.time));$('#lastUpdate').textContent=`${demo?'예시 갱신':'KPI 조회'} ${p.hour}:${p.minute}:${p.second} KST`+(main.error?' · 갱신 실패':'');}
    const notice=$('#loadNotice');
    if(failed.length&&!demo){notice.hidden=false;replaceIfChanged(notice,`<span>${failed.map(s=>esc(s.name)).join(', ')} 수신 실패 · ${good.length?'같은 조건의 마지막 수신값만 유지합니다.':'API 서버에서 접속했는지 확인하세요.'}</span><button type="button" class="text-button" data-open-info>상세 보기 →</button>${!good.length?'<button type="button" class="text-button" data-enter-demo>예시 데이터로 보기</button>':''}`);}
    else if(!state.busy)notice.hidden=true;
    $('#refreshButton').disabled=state.busy;
    markErrors();
  }
  function renderAll(animate=false){
    renderFilters();renderFilterChips();renderKPI(animate);renderRanking();renderNotes();renderEvents();renderProgress();renderTable('inboundTable');renderTable('shipmentTable');renderCharts();renderStatus();
  }
  function goView(view,updateHash=true){
    if(!VIEWS.includes(view))return;state.view=view;document.body.dataset.view=view;
    VIEWS.forEach(v=>$('#'+v+'View').hidden=v!==view);
    $$('.primary-nav [data-view]').forEach(b=>{const yes=b.dataset.view===view;b.classList.toggle('active',yes);yes?b.setAttribute('aria-current','page'):b.removeAttribute('aria-current');});
    $('#pageTitle').textContent=TITLES[view];$('#pageNumber').textContent=`0${VIEWS.indexOf(view)+1} / 0${VIEWS.length}`;
    document.title=`SCM | ${TITLES[view]}`;
    if(updateHash&&location.hash!=='#'+view)location.hash=view;
    renderCharts();markErrors();requestAnimationFrame(fitNumbers);
    if(updateHash)window.scrollTo({top:0,behavior:'instant'});
    if(view==='targets'&&window.SCMTargets&&typeof window.SCMTargets.load==='function')window.SCMTargets.load();
  }
  function stepView(delta){goView(VIEWS[(VIEWS.indexOf(state.view)+delta+VIEWS.length)%VIEWS.length]);}
  function paramsFor(endpoint,snapshot,metricOverride){
    const params=C.requestParams(endpoint,snapshot,cfg.endpointParameters);
    if(metricOverride)params.metric=metricOverride;
    return params;
  }
  function requestKey(endpoint,params){return endpoint+'?'+new URLSearchParams(params).toString();}
  async function fetchOne(name,endpoint,params,signal,force=false,ttl=0){
    const key=requestKey(endpoint,params),old=state.statuses[name];
    if(!force&&old?.key===key&&old.data&&!old.error&&Date.now()-old.time<ttl)return {...old,cached:true};
    const abort=new AbortController();const onAbort=()=>abort.abort();signal.addEventListener('abort',onAbort,{once:true});
    const timeout=setTimeout(()=>abort.abort(),cfg.timeoutMs||12000);
    try{
      if(signal.aborted)throw new DOMException('Aborted','AbortError');
      let raw;
      if(demo){raw=window.SCMDemo.get(endpoint,params,state.tick);await Promise.resolve();}
      else{
        const query=new URLSearchParams(params).toString();
        const base=String(cfg.apiBase||'').replace(/\/$/,'');
        const response=await fetch(`${base}/api/${endpoint}${query?'?'+query:''}`,{method:'GET',cache:'no-store',credentials:'same-origin',signal:abort.signal,headers:{Accept:'application/json'}});
        if(!response.ok)throw new Error(`HTTP ${response.status}`);
        raw=await response.json();
      }
      C.validate(endpoint,raw,params.metric);
      return {name,endpoint,key,data:raw,time:Date.now(),error:null,attempt:Date.now(),params};
    }catch(error){
      return {name,endpoint,key,data:old?.key===key?old.data:null,time:old?.key===key?old.time:null,error:signal.aborted?'요청 취소':error.name==='AbortError'?'응답 시간 초과':error.message||'통신 실패',attempt:Date.now(),params};
    }finally{clearTimeout(timeout);signal.removeEventListener('abort',onAbort);}
  }
  function schedule(){
    clearTimeout(pollTimer);if(state.refresh>0&&!document.hidden)pollTimer=setTimeout(()=>refresh(),state.refresh*1000);
  }
  function applyResults(results){
    const oldEvents=state.data.events?.events||[],oldProgress=state.data['inbound-progress']?.progress||[];
    results.forEach(r=>{state.statuses[r.name]=r;state.data[r.name]=r.data;});
    const events=state.data.events?.events||[];
    state.newEvents=C.newEventKeys(oldEvents,events,state.eventInitialized);if(state.data.events)state.eventInitialized=true;
    const pkeys=new Set(oldProgress.map(progressKey));
    state.newProgress=new Set(state.progressInitialized?(state.data['inbound-progress']?.progress||[]).map(progressKey).filter(k=>!pkeys.has(k)):[]);
    if(state.data['inbound-progress'])state.progressInitialized=true;
  }
  function viewTaskSpecs(snapshot){
    const tasks=[],add=(name,endpoint=name,ttl=0,metricOverride=null)=>tasks.push([name,endpoint,ttl,metricOverride]);
    add('filters','filters',600000);
    if(state.view==='overview'){
      add('hourly','hourly',0);add('customers','customers',5000);add('events','events',2000);add('alerts','alerts',10000);
      if(state.overviewPeriod==='daily')add('daily-trend','daily-trend',(cfg.dailyRefreshSeconds||30)*1000);
    }else if(state.view==='inbound'){
      add('hourly','hourly',0);add('daily-trend','daily-trend',(cfg.dailyRefreshSeconds||30)*1000);
      add('items','items',5000);add('events','events',2000);add('inbound-progress','inbound-progress',2000);
    }else if(state.view==='shipment'){
      add('hourly','hourly',0);add('daily-trend','daily-trend',(cfg.dailyRefreshSeconds||30)*1000);
      add('customers','customers',5000);add('items','items',5000);add('events','events',2000);
      if(snapshot.metric!=='USD')add('usdKpi','kpi',3000,'USD');
    }
    return tasks;
  }
  function deferFocus(){
    if(!['overview','inbound','shipment'].includes(state.view)||!window.SCMFocus)return;
    if(focusMetric===state.metric&&Date.now()-focusLoadedAt<30000)return;
    const expectedView=state.view,run=()=>{
      if(expectedView!==state.view||!window.SCMFocus)return;
      focusMetric=state.metric;focusLoadedAt=Date.now();window.SCMFocus.syncMetric();window.SCMFocus.load(state.metric);
    };
    if('requestIdleCallback' in window)requestIdleCallback(run,{timeout:1200});else setTimeout(run,250);
  }
  async function refresh(force=false){
    if(state.busy&&!force)return;
    clearTimeout(pollTimer);controller?.abort();controller=new AbortController();const signal=controller.signal,token=++generation;
    state.busy=true;renderStatus();
    const snapshot=JSON.parse(JSON.stringify({metric:state.metric,filters:state.filters,range:state.range,month:state.month}));
    const main=await fetchOne('kpi','kpi',paramsFor('kpi',snapshot),signal,force,0);
    if(token!==generation||signal.aborted)return;
    applyResults([main]);
    if(snapshot.metric==='USD'){state.statuses.usdKpi={...main,name:'usdKpi'};state.data.usdKpi=main.data;}
    const actualMonth=!snapshot.filters.date&&C.validDate(main?.data?.date)?main.data.date.replace(/-/g,'').slice(0,6):snapshot.month;
    if(actualMonth!==snapshot.month){snapshot.month=actualMonth;state.month=actualMonth;}
    renderKPI(false);renderStatus();
    const specs=viewTaskSpecs(snapshot);
    const results=await Promise.all(specs.map(([name,endpoint,ttl,metricOverride])=>
      fetchOne(name,endpoint,paramsFor(endpoint,snapshot,metricOverride),signal,force&&name!=='filters',ttl)));
    if(token!==generation||signal.aborted)return;
    applyResults(results);state.busy=false;
    const currentIdentity=identity(),animate=currentIdentity===state.lastIdentity&&!main?.error;
    renderAll(animate);state.lastIdentity=currentIdentity;
    if(demo)state.tick++;
    if(state.view==='targets')window.SCMTargets?.load();
    deferFocus();
    if($('#infoDialog').open)renderInfo();
    schedule();
  }
  function invalidate(){
    // Clear differently scoped values immediately; a slow old response cannot repopulate them.
    controller?.abort();++generation;state.busy=false;state.lastIdentity='';
    state.month=(state.filters.date||C.today()).slice(0,6);
    for(const [name,s] of Object.entries(state.statuses)){
      const endpoint=s.endpoint||name,p=paramsFor(endpoint,state,name==='usdKpi'?'USD':undefined);
      if(requestKey(endpoint,p)!==s.key){delete state.statuses[name];delete state.data[name];}
    }
    renderAll(false);refresh(true);
  }
  function selectFilter(key,value){
    if(!FILTER_IDS[key]||value==='__OTHERS__')return;state.filters[key]=state.filters[key]===value?'ALL':value;
    renderFilters();invalidate();
    toast(`${FILTER_NAMES[key]} ${state.filters[key]==='ALL'?'필터 해제':'공통 필터 적용'} · 차트·상세표에 동일 조건을 적용합니다.`);
  }
  function exportRows(rows,name){
    const blob=new Blob([C.csv(rows)],{type:'text/csv;charset=utf-8'}),link=document.createElement('a'),href=URL.createObjectURL(blob);
    link.href=href;link.download=`${demo?'DEMO_':''}SCM_${name}_${state.filters.date||C.today()}.csv`;document.body.appendChild(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(href),1000);
  }
  function exportTable(id){
    const t=state.tables[id];if(!t)return;
    const header=t.columns.map(c=>c.type==='metric'?`${c.label.split(' (')[0]} (${rawUnit(c.metric)})`:c.label);
    exportRows([header,...t.rows.map(r=>t.columns.map(c=>r[c.key]??null))],id);
  }
  function showChartTable(id){
    const c=charts[id];if(!c?.data)return;
    state.chartExport=c.exportRows();$('#chartDialogTitle').textContent=c.data.title+(c.cumulative?' · 누적':'')+(c.zoom?' · 확대 구간':'');
    const rows=state.chartExport;
    $('#chartDataTable').innerHTML=`<p>원단위 수신값입니다. —는 미제공이며 0과 다릅니다.${demo?' · 예시 데이터':''}</p><table class="data-table"><thead><tr>${rows[0].map(v=>`<th>${esc(v)}</th>`).join('')}</tr></thead><tbody>${rows.slice(1).map(row=>'<tr>'+row.map((v,i)=>`<td class="${i?'num':''}">${esc(i?(v===null?'—':C.format(v,2)):v)}</td>`).join('')+'</tr>').join('')}</tbody></table>`;
    $('#chartDialog').showModal();
  }
  function renderInfo(){
    const rows=Object.values(state.statuses).map(s=>`<tr><td><code>${esc(s.name)}</code></td><td>${esc(s.error?'실패 · '+s.error:s.data?'수신 완료':'수신 대기')}</td><td>${s.time?new Date(s.time).toLocaleTimeString('ko-KR',{timeZone:'Asia/Seoul'}):'—'}</td><td>${esc(Object.keys(s.params||{}).join(', ')||'없음')}</td></tr>`).join('');
    const alerts=state.data.alerts?.alerts||[];
    $('#infoContent').innerHTML=`${demo||window.SCM_RUNTIME?.demoBackend?'<p class="notice notice-demo"><b>합성 데이터 데모</b> 회사 원천에 접속하지 않습니다. 브라우저 데모의 목표/집중관리는 현재 브라우저에만 저장됩니다.</p>':''}<h3>단위와 비교 기준</h3><p>API는 원단위 EA·BOX·USD·EQ를 반환합니다. 표시 단위만 K/M/억/B로 바뀝니다. 달성률은 월 누적 실적 ÷ 월 전체 목표이며, 전일 비교는 전날 전체 실적 기준입니다. DRAM EQ와 FLASH EQ는 합산하지 않습니다.</p><h3>공통 조건</h3><p>KPI·시간별·일별·품목별·거래선별에 같은 기준일과 상세 필터, 지표를 적용합니다. 등록한 집중관리 항목은 해당 범위와 선택 기준일/지표로 계산합니다. 미제공은 —, 관측값 0은 0으로 구분합니다. 출하 BOX는 ITEM/거래선 배분 매핑이 없으면 해당 조건 실적을 미제공합니다.</p><h3>목표</h3><p>기간·구분·지표·정규화한 조건이 같은 경우에만 수기 목표가 시스템 목표에 우선합니다. 겹치는 목표를 임의 합산하지 않습니다. 시스템 목표에 대응 차원이 없으면 목표 비교를 보류합니다.</p><h3>재고와 수집</h3><p>재고는 현재 스냅샷이며 과거 조회일 재고가 아닙니다. 가용재고·전일재고·회전일수는 확인된 산출 규칙이 없어 제공하지 않습니다. API 연결은 원천 수집 성공이나 회사 SAP 수치 검증을 보장하지 않습니다.</p><h3>API 수신 상태 · KST</h3><div class="table-wrap"><table class="data-table"><thead><tr><th>영역</th><th>최근 요청</th><th>마지막 성공</th><th>조건</th></tr></thead><tbody>${rows}</tbody></table></div><h3>알림</h3>${alerts.map(a=>`<p>${esc(a.msg)}</p>`).join('')}`;
  }
  function openInfo(){renderInfo();if(!$('#infoDialog').open)$('#infoDialog').showModal();}
  async function togglePresentation(){
    const active=!document.body.classList.contains('presentation');document.body.classList.toggle('presentation',active);
    if(active){try{await document.documentElement.requestFullscreen();}catch(_){toast('전체화면 권한 없이 발표 레이아웃으로 전환했습니다.');}}
    else if(document.fullscreenElement){try{await document.exitFullscreen();}catch(_){/* Presentation layout still exits. */}}
    requestAnimationFrame(()=>{Object.values(charts).forEach(c=>c.draw());fitNumbers();});
  }
  function clock(){const p=C.kstParts();$('#clock').textContent=`${p.hour}:${p.minute}:${p.second} KST`;renderStatus();}
  function bind(){
    document.addEventListener('click',e=>{
      const b=e.target.closest('button,a,tr[data-key]');if(!b)return;
      if(b.dataset.view){e.preventDefault();goView(b.dataset.view);}
      else if(b.hasAttribute('data-open-info'))openInfo();
      else if(b.hasAttribute('data-close-dialog'))b.closest('dialog').close();
      else if(b.dataset.metric){if(state.metric===b.dataset.metric)return;state.metric=b.dataset.metric;updateUnitSelector();invalidate();}
      else if(b.dataset.customer){goView('shipment');selectFilter('customer',b.dataset.customer);}
      else if(b.dataset.key&&b.dataset.action)selectFilter(b.dataset.action,b.dataset.key);
      else if(b.dataset.removeFilter){state.filters[b.dataset.removeFilter]='ALL';renderFilters();invalidate();}
      else if(b.dataset.period){state.overviewPeriod=b.dataset.period;$('[data-period]').forEach(x=>{const a=x===b;x.classList.toggle('active',a);x.setAttribute('aria-pressed',String(a));});renderCharts();markErrors();if(state.overviewPeriod==='daily'&&!state.data['daily-trend'])refresh(true);}
      else if(b.dataset.shipmentTab){state.shipmentTab=b.dataset.shipmentTab;state.sort.shipmentTable=null;state.search.shipmentTable='';$('[data-search="shipmentTable"]').value='';$$('[data-shipment-tab]').forEach(x=>{const a=x===b;x.classList.toggle('active',a);x.setAttribute('aria-pressed',String(a));});renderTable('shipmentTable');markErrors();}
      else if(b.dataset.inboundTab){state.inboundTab=b.dataset.inboundTab;$$('[data-inbound-tab]').forEach(x=>{const a=x===b;x.classList.toggle('active',a);x.setAttribute('aria-pressed',String(a));});renderProgress();markErrors();}
      else if(b.dataset.range){state.range=b.dataset.range;$$('[data-range]').forEach(x=>{const a=x===b;x.classList.toggle('active',a);x.setAttribute('aria-pressed',String(a));});invalidate();}
      else if(b.dataset.sortTable){const id=b.dataset.sortTable,old=state.sort[id];state.sort[id]={key:b.dataset.sortKey,dir:old?.key===b.dataset.sortKey?-old.dir:-1};renderTable(id);}
      else if(b.dataset.exportTable)exportTable(b.dataset.exportTable);
      else if(b.dataset.chartTable)showChartTable(b.dataset.chartTable);
      else if(b.dataset.exportEvents){const kind=b.dataset.exportEvents;const list=(state.data.events?.events||[]).filter(v=>kind==='shipment'?String(v.type).includes('출하'):!String(v.type).includes('출하'));exportRows([['기준일','시각','유형','상세','창고'],...list.map(v=>[v.date,v.time,v.type,v.detail,v.warehouse])],kind+'_events');}
      else if(b.hasAttribute('data-enter-demo')){const u=new URL(location.href);u.searchParams.set('demo','1');location.href=u.href;}
    });
    $('#filterToggle').addEventListener('click',()=>{const panel=$('#filterPanel');panel.hidden=!panel.hidden;$('#filterToggle').setAttribute('aria-expanded',String(!panel.hidden));});
    Object.entries(FILTER_IDS).forEach(([key,id])=>{
      if(key==='item'){$('#'+id).addEventListener('input',e=>{state.filters[key]=e.target.value||'ALL';invalidate();});}
      else{$('#'+id).addEventListener('change',e=>{state.filters[key]=e.target.value;invalidate();});}
    });
    $('#resetFilters').addEventListener('click',()=>{Object.keys(FILTER_IDS).forEach(k=>state.filters[k]='ALL');renderFilters();invalidate();});
    $('#filterDate').addEventListener('change',e=>{if(e.target.value&&!C.validDate(e.target.value)){toast('유효한 날짜를 선택하세요.');return;}state.filters.date=e.target.value.replace(/-/g,'');invalidate();});
    $('#latestButton').addEventListener('click',()=>{state.filters.date='';$('#filterDate').value='';invalidate();});
    $('#filterUnit').addEventListener('change',e=>{const type=C.METRICS[state.metric].type,div=Number(e.target.value);if(TYPE_DIVISORS[type].includes(div)){state.units[type]=div;renderAll(false);}});
    $('#refreshRate').addEventListener('change',e=>{state.refresh=Math.max(0,Number(e.target.value));schedule();renderStatus();});
    $('#refreshButton').addEventListener('click',()=>refresh(true));
    $('#themeToggle').addEventListener('click',()=>setTheme(document.documentElement.dataset.theme==='dark'?'light':'dark'));
    $('#connectionButton').addEventListener('click',openInfo);
    $('#presentationToggle').addEventListener('click',togglePresentation);
    $('#prevPage').addEventListener('click',()=>stepView(-1));$('#nextPage').addEventListener('click',()=>stepView(1));
    $('#cycleButton').addEventListener('click',()=>{
      if(cycleTimer){clearInterval(cycleTimer);cycleTimer=null;}else cycleTimer=setInterval(()=>{if(!document.hidden&&!$('dialog[open]')&&!$('#filterPanel').matches(':focus-within'))stepView(1);},20000);
      $('#cycleButton').setAttribute('aria-pressed',String(!!cycleTimer));$('#cycleButton').textContent=cycleTimer?'자동 넘김 중 · 정지':'자동 넘김';
    });
    $('#exportChart').addEventListener('click',()=>exportRows(state.chartExport,'chart'));
    $$('[data-search]').forEach(input=>input.addEventListener('input',()=>{state.search[input.dataset.search]=input.value;renderTable(input.dataset.search);}));
    document.addEventListener('keydown',e=>{
      if(e.target.matches('tr[data-key]')&&['Enter',' '].includes(e.key)){e.preventDefault();selectFilter(e.target.dataset.action,e.target.dataset.key);return;}
      if(e.target.closest('input,select,textarea,button,a,dialog,[contenteditable="true"],.chart-frame'))return;
      if(['1','2','3','4','5'].includes(e.key)){goView(VIEWS[Number(e.key)-1]);}
      else if(e.key==='ArrowRight'){e.preventDefault();stepView(1);}else if(e.key==='ArrowLeft'){e.preventDefault();stepView(-1);}
    });
    window.addEventListener('hashchange',()=>{const next=location.hash.slice(1),changed=VIEWS.includes(next)&&next!==state.view;goView(next,false);if(changed&&state.statuses.kpi?.data)refresh(true);});
    window.addEventListener('resize',()=>requestAnimationFrame(fitNumbers));
    document.addEventListener('visibilitychange',()=>{if(document.hidden){clearTimeout(pollTimer);controller?.abort();++generation;state.busy=false;}else if(state.refresh>0)refresh(true);});
    document.addEventListener('fullscreenchange',()=>{if(!document.fullscreenElement)document.body.classList.remove('presentation');requestAnimationFrame(fitNumbers);});
  }
  function init(){
    let theme='light';try{theme=localStorage.getItem('scm-theme')||'light';}catch(_){}setTheme(theme);
    $('#refreshRate').value=String(state.refresh);$('#filterDate').value=C.isoDate(state.filters.date);
    $('#unitNotice').hidden=verified;
    if(demo||window.SCM_RUNTIME?.demoBackend){$('#modeNotice').hidden=false;$('#modeNotice').innerHTML='<b>DEMO / 예시 데이터</b><span>화면·동작 검토용입니다. 실제 업무 실적이 아니며, 운영 서버와 통신하지 않습니다.</span>';}
    bind();updateUnitSelector();goView(state.view,false);renderAll(false);clock();setInterval(clock,1000);refresh();
    // Read-only diagnostics, useful for automated acceptance tests and operational troubleshooting.
    window.SCM_DEBUG={get state(){return state;},get charts(){return charts;},refresh,goView};
  }
  init();
})();
