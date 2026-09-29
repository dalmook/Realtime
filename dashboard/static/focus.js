/* Focus list and KPI share the main selected date/metric. Writes use one event handler. */
(function(){
  'use strict';const C=window.SCMCore,$=(s,b=document)=>b.querySelector(s),esc=C.escapeHTML;
  const req=(p,b)=>window.SCMTransport.request(p,b);let items=[],data=null,currentMetric='EA',generation=0,error='';
  const units={EA:'EA',EQ_DRAM:'EQ·DRAM',EQ_FLASH:'EQ·FLASH',USD:'USD',BOX:'BOX'};
  function fmt(v){return v==null?'—':C.format(v,currentMetric==='USD'?2:0);}
  function toast(t){$('#toast').textContent=t;$('#toast').hidden=false;setTimeout(()=>$('#toast').hidden=true,3000);}
  function syncMetric(){currentMetric=window.SCM_DEBUG?.state.metric||$('.metric-control .active')?.dataset.metric||'EA';}
  async function load(metric){
    currentMetric=metric||currentMetric;const n=++generation,p=new URLSearchParams({action:'kpi',metric:currentMetric});
    const date=window.SCM_DEBUG?.state.filters.date;if(date)p.set('date',date);
    try{const [list,kpis]=await Promise.all([req('/api/focus?action=list'),req('/api/focus?'+p)]);if(n!==generation)return;items=list.items||[];data=kpis;error='';}
    catch(e){if(n!==generation)return;error=e.message;data=null;}
    renderAll();
  }
  function renderSection(view,direction){
    let s=$('#focusSection_'+direction);
    if(!s){s=document.createElement('section');s.id='focusSection_'+direction;s.className='panel focus-section';$('#'+view).appendChild(s);}
    const keys=direction==='overview'?['inbound','shipment']:[direction];
    const header=keys.map(k=>`<th class="num">${k==='inbound'?'입고':'출하'} MTD (${units[currentMetric]})</th><th class="num">기준일 실적</th><th class="num">목표 / 달성률</th>`).join('');
    const rows=(data?.items||[]).map(k=>`<tr><td>${esc(k.label)}<small class="row-sub">${esc(k.item_code||k.customer_code||'')}</small></td>${keys.map(key=>{const d=k[key];return `<td class="num">${fmt(d?.mtd)}</td><td class="num">${fmt(d?.today)}</td><td class="num">${fmt(d?.target)} / ${d?.achievement==null?'—':C.format(d.achievement,1)+'%'}</td>`;}).join('')}<td>${esc(C.dateLabel(k.shipment?.date))}</td></tr>`).join('');
    s.innerHTML=`<header class="panel-header"><div><span class="eyebrow">FOCUS ITEMS</span><h2>집중관리 아이템</h2></div><button type="button" class="secondary-button" data-focus-manage>관리 / 등록</button></header>${error?`<div class="panel-error">조회 실패: ${esc(error)}</div>`:''}<div class="table-wrap"><table class="data-table"><thead><tr><th>아이템 / 거래선</th>${header}<th>기준일</th></tr></thead><tbody>${rows||`<tr><td colspan="8"><div class="empty-state">등록된 항목이 없습니다. 관리 / 등록을 눌러 추가하세요.</div></td></tr>`}</tbody></table></div>`;
  }
  function renderManagePanel(){
    if(!$('#focusDialog').open)return;
    const list=$('#focusManageRows');if(!list)return;
    list.innerHTML=items.map(x=>`<tr><td><input type="checkbox" data-focus-select="${x.focus_id}" aria-label="${esc(x.label)} 선택"></td><td>${esc(x.label)}</td><td>${esc(x.item_code||'—')}</td><td>${esc(x.customer_code||'—')}</td><td><button class="text-button" data-focus-delete="${x.focus_id}">삭제</button></td></tr>`).join('');
    $('#focusManageStatus').textContent=error?'조회 실패: '+error:`${items.length}개 등록 · ${units[currentMetric]}`;
  }
  function renderAll(){renderSection('overviewView','overview');renderSection('inboundView','inbound');renderSection('shipmentView','shipment');renderManagePanel();}
  function openManage(){
    const dlg=$('#focusDialog');if(dlg.open)return;
    $('#focusDialogBody').innerHTML=`<p id="focusManageStatus"></p><div class="form-grid"><label>유형<select id="focusType"><option value="item">아이템</option><option value="customer">거래선</option><option value="customer_item">거래선 + 아이템</option></select></label><label>아이템 코드<input id="focusItemCode" list="itemList"></label><label>거래선 코드<input id="focusCustomerCode" placeholder="DEMO-C01"></label><label class="span2">표시명<input id="focusLabel" maxlength="200"></label><button type="button" class="primary-button" id="focusAddSubmitBtn">개별 등록</button></div><details class="batch-details"><summary>일괄 등록</summary><p>유형,아이템,거래선,표시명 순서로 한 줄에 하나씩. 형식이 잘못된 경우 전체 요청을 취소합니다.</p><textarea id="focusBatchText" rows="5" placeholder="item,DEMO-001-MEMORY,,중점 품목&#10;customer,,DEMO-C01,중점 거래선"></textarea><button type="button" class="secondary-button" id="focusBatchSubmitBtn">일괄 등록</button></details><div class="table-tools"><button type="button" class="secondary-button" id="focusDeleteSelected">선택 삭제</button><button type="button" class="secondary-button" id="focusRefreshBtn">새로고침</button></div><div class="table-wrap"><table class="data-table"><thead><tr><th>선택</th><th>표시명</th><th>아이템</th><th>거래선</th><th>관리</th></tr></thead><tbody id="focusManageRows"></tbody></table></div>`;
    dlg.showModal();renderManagePanel();
    $('#focusAddSubmitBtn').onclick=async()=>{try{const res=await req('/api/focus/create',{focus_type:$('#focusType').value,item_code:$('#focusItemCode').value.trim()||null,customer_code:$('#focusCustomerCode').value.trim()||null,label:$('#focusLabel').value.trim()||null});toast(res.ok?'등록 완료':'이미 등록된 항목입니다.');await load();}catch(e){toast(e.message);}};
    $('#focusBatchSubmitBtn').onclick=async()=>{try{const text=$('#focusBatchText').value.trim();if(!text)throw new Error('등록할 내용을 입력하세요.');const list=text.split('\n').filter(x=>x.trim()).map(l=>{const [focus_type,item_code,customer_code,...label]=l.split(',').map(x=>x.trim());return {focus_type,item_code:item_code||null,customer_code:customer_code||null,label:label.join(',')||null};});const res=await req('/api/focus/batch_create',{items:list});toast(`${res.results.filter(x=>x.ok).length}건 등록`);$('#focusBatchText').value='';load();}catch(e){toast(e.message);}};
    $('#focusDeleteSelected').onclick=async()=>{const ids=[...dlg.querySelectorAll('[data-focus-select]:checked')].map(e=>Number(e.dataset.focusSelect));if(!ids.length)return;try{await req('/api/focus/delete_batch',{focus_ids:ids});load();}catch(e){toast(e.message);}};
    $('#focusRefreshBtn').onclick=()=>load();
  }
  document.addEventListener('click',async e=>{
    if(e.target.closest('[data-focus-manage]'))openManage();
    if(e.target.closest('[data-close-focus-dialog]'))$('#focusDialog').close();
    const del=e.target.closest('[data-focus-delete]');if(del){try{await req('/api/focus/delete',{focus_id:Number(del.dataset.focusDelete)});load();}catch(err){toast(err.message);}}
  });
  window.SCMFocus={load,renderAll,syncMetric,openManage};
})();
