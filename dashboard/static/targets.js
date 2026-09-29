/* Dynamic target editor. Canonical field/operator names are provided by the API. */
(function(){
  'use strict';
  const C=window.SCMCore,esc=C.escapeHTML,$=(s,b=document)=>b.querySelector(s);
  const request=(p,b)=>window.SCMTransport.request(p,b);
  let editingId=null,metadata=null,loadId=0;
  const metrics=['EA','EQ_DRAM','EQ_FLASH','BOX','USD'];
  const fmt=(v,m)=>v==null?'—':C.format(v,m==='USD'?2:0)+' '+m;
  const notify=msg=>{const el=$('#toast');el.textContent=msg;el.hidden=false;setTimeout(()=>el.hidden=true,3500);};
  async function load(){
    const generation=++loadId;
    try{
      const p=new URLSearchParams();if($('#tgtPeriod').value)p.set('period_ym',$('#tgtPeriod').value.replace('-',''));
      if($('#tgtDirection').value)p.set('direction',$('#tgtDirection').value);
      const selected=window.SCM_DEBUG?.state?.filters?.date;if(selected)p.set('date',selected);
      const d=await request('/api/targets?'+p);if(generation!==loadId)return;
      render(d.targets||[]);
    }catch(e){$('#tgtEmpty').hidden=false;$('#tgtEmpty').textContent='목표 조회 실패: '+e.message;}
  }
  function render(rows){
    $('#tgtEmpty').hidden=rows.length>0;$('#tgtEmpty').textContent="목표가 없습니다. '신규 목표'로 등록하세요.";
    $('#tgtTableBody').innerHTML=rows.map(t=>{
      const actual=t.actual_value??t.actual,pct=actual!=null&&t.target_value>0?actual/t.target_value*100:null;
      return `<tr data-id="${t.target_id}"><td>${esc(t.target_name)}</td><td>${esc(t.period_ym)}</td><td>${t.direction==='inbound'?'입고':'출하'}</td><td>${esc(t.metric)}</td><td class="num">${fmt(t.target_value,t.metric)}</td><td class="num">${fmt(actual,t.metric)}</td><td class="num">${pct===null?'—':C.format(pct,1)+'%'}</td><td class="num">${fmt(actual==null?null:t.target_value-actual,t.metric)}</td><td>수기</td><td>${t.enabled?'활성':'비활성'}</td><td>${(t.filters||[]).map(f=>esc(`${f.field_key} ${f.operator} ${f.filter_value}`)).join('<br>')||'전체'}</td><td class="target-actions"><button data-target-action="edit" data-id="${t.target_id}">수정</button><button data-target-action="copy" data-id="${t.target_id}">복사</button><button data-target-action="toggle" data-id="${t.target_id}">${t.enabled?'비활성':'활성'}</button><button data-target-action="del" data-id="${t.target_id}">삭제</button></td></tr>`;
    }).join('');
  }
  async function openModal(target){
    try{metadata=metadata||await request('/api/targets/meta');}catch(e){notify(e.message);return;}
    closeModal();editingId=target?.target_id??null;
    const dlg=document.createElement('dialog');dlg.id='tgtModal';dlg.className='info-dialog wide-dialog';
    const ym=$('#tgtPeriod').value.replace('-','')||C.today().slice(0,6);
    dlg.innerHTML=`<form id="targetEditor"><div class="dialog-header"><h2>${editingId?'목표 수정':'신규 목표 등록'}</h2><button type="button" data-tgt-close aria-label="닫기">×</button></div><div class="dialog-body"><div class="form-grid"><label>기간 (YYYYMM)<input id="mtPeriod" required pattern="[0-9]{6}" value="${esc(target?.period_ym||ym)}"></label><label>구분<select id="mtDirection"><option value="shipment">출하</option><option value="inbound">입고</option></select></label><label>지표<select id="mtMetric">${metrics.map(m=>`<option>${m}</option>`).join('')}</select></label><label class="span2">목표명<input id="mtName" required maxlength="200" value="${esc(target?.target_name||'')}"></label><label>목표값 (원단위)<input id="mtValue" type="number" min="0" max="9000000000000" step="any" required value="${target?.target_value??''}"></label><label>우선순위 (작을수록 우선)<input id="mtPriority" type="number" min="0" max="100000" value="${target?.priority??10}"></label><label class="check-label"><input id="mtEnabled" type="checkbox" ${target?.enabled===false?'':'checked'}> 활성</label><label class="span2">메모<input id="mtMemo" maxlength="2000" value="${esc(target?.memo||'')}"></label></div><h3>적용 조건</h3><p>조건은 AND로 결합됩니다. 같은 범위의 목표는 우선순위 1개만 적용합니다. 겹치는 목표를 합산하지 않습니다.</p><div id="mtFilters"></div><button type="button" class="secondary-button" data-add-filter>+ 조건 추가</button><div id="mtPreview" class="notice" hidden></div></div><footer class="dialog-footer"><button type="button" class="secondary-button" data-preview>실적 미리보기</button><button type="button" class="secondary-button" data-tgt-close>취소</button><button type="submit" class="primary-button">저장</button></footer></form>`;
    document.body.appendChild(dlg);$('#mtDirection').value=target?.direction||'shipment';$('#mtMetric').value=target?.metric||'EA';
    (target?.filters||[]).forEach(addFilterRow);
    dlg.querySelectorAll('[data-tgt-close]').forEach(b=>b.onclick=closeModal);
    $('[data-add-filter]',dlg).onclick=()=>addFilterRow();$('[data-preview]',dlg).onclick=preview;
    $('#targetEditor').onsubmit=e=>{e.preventDefault();save();};dlg.showModal();
  }
  function closeModal(){const d=$('#tgtModal');if(d){d.close();d.remove();}}
  function addFilterRow(f={}){
    const row=document.createElement('div');row.className='filter-rule';row.innerHTML=`<select class="mtf-field" aria-label="조건 필드">${metadata.fields.map(x=>`<option value="${esc(x.key)}">${esc(x.label)}</option>`).join('')}</select><select class="mtf-op" aria-label="연산자">${metadata.operators.map(x=>`<option>${esc(x)}</option>`).join('')}</select><input class="mtf-val" aria-label="조건 값" placeholder="값 · IN은 쉼표로 구분" value="${esc(f.filter_value||'')}"><button type="button" class="icon-button" aria-label="조건 삭제">×</button>`;
    $('#mtFilters').appendChild(row);$('.mtf-field',row).value=f.field_key||'customer_code';$('.mtf-op',row).value=f.operator||'=';$('button',row).onclick=()=>row.remove();
  }
  function collectBody(){
    return {period_ym:$('#mtPeriod').value.trim(),direction:$('#mtDirection').value,metric:$('#mtMetric').value,target_name:$('#mtName').value.trim(),target_value:Number($('#mtValue').value),priority:Number($('#mtPriority').value),enabled:$('#mtEnabled').checked,additive:false,memo:$('#mtMemo').value,
      filters:[...document.querySelectorAll('#mtFilters .filter-rule')].map(row=>({field_key:$('.mtf-field',row).value,operator:$('.mtf-op',row).value,filter_value:$('.mtf-val',row).value.trim()}))};
  }
  async function save(){
    try{const b=collectBody();await request(editingId?'/api/targets/update':'/api/targets/create',{...b,...(editingId?{target_id:editingId}:{})});closeModal();notify('목표 저장 완료');await load();window.SCM_DEBUG?.refresh(true);}
    catch(e){notify('저장 실패: '+e.message);}
  }
  async function preview(){
    const el=$('#mtPreview');el.hidden=false;
    try{const b=collectBody(),res=await request('/api/targets/preview',b);el.textContent=`매칭 ${res.match_count??res.count}건 · 실적 ${fmt(res.actual_value??res.actual,b.metric)}${res.note?' · '+res.note:''}`;}
    catch(e){el.textContent='미리보기 오류: '+e.message;}
  }
  async function action(name,id){
    try{
      if(name==='del'){if(!confirm('이 목표를 삭제할까요?'))return;await request('/api/targets/delete',{target_id:id});}
      else{const d=await request('/api/targets/get?target_id='+id);
        if(name==='edit')return openModal(d);
        if(name==='copy'){delete d.target_id;d.target_name+=' (복사)';return openModal(d);}
        if(name==='toggle')await request('/api/targets/update',{target_id:id,enabled:!d.enabled});}
      await load();window.SCM_DEBUG?.refresh(true);
    }catch(e){notify(e.message);}
  }
  async function copyMonth(){
    const d=C.kstParts(),prev=new Date(Date.UTC(Number(d.year),Number(d.month)-2,15));
    const from=prompt('원본 기간 (YYYYMM)',prev.toISOString().slice(0,7).replace('-',''));if(!from)return;
    const to=prompt('대상 기간 (YYYYMM)',$('#tgtPeriod').value.replace('-',''));if(!to)return;
    try{const res=await request('/api/targets/copy-month',{from_ym:from,to_ym:to});notify(`${res.copied_count}개 복사 완료`);load();}catch(e){notify(e.message);}
  }
  function init(){
    $('#tgtPeriod').value=C.today().slice(0,6).replace(/(....)(..)/,'$1-$2');
    $('#tgtNewBtn').onclick=()=>openModal();$('#tgtRefreshBtn').onclick=load;$('#tgtCopyMonthBtn').onclick=copyMonth;
    $('#tgtPeriod').onchange=load;$('#tgtDirection').onchange=load;
    $('#tgtTableBody').onclick=e=>{const b=e.target.closest('[data-target-action]');if(b)action(b.dataset.targetAction,Number(b.dataset.id));};
  }
  window.SCMTargets={load,init,openModal,closeModal,addFilterRow,save,preview,copyMonth,edit:id=>action('edit',id),copy:id=>action('copy',id),toggle:id=>action('toggle',id),del:id=>action('del',id)};
  init();
})();
