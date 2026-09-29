/* Complete browser-only demo API. No fetch/XHR, no real endpoints or credentials.
   Demo targets/foci live only in this browser's localStorage, never company SQLite. */
(function(){
'use strict';
const C=window.SCMCore,F=window.SCM_FIXTURES,KEY='scm-synthetic-demo-v2';if(!F?.synthetic)return;
const copy=o=>JSON.parse(JSON.stringify(o)),metrics=['EA','EQ_DRAM','EQ_FLASH','BOX','USD'];
const fields=[['customer_name','거래선명'],['customer_code','거래선코드'],['product_group','제품군'],['item','ITEM'],['item_prefix','ITEM Prefix'],['plant','Plant'],['warehouse','창고'],['country','국가'],['sales_org','판매법인'],['ship_type','출하유형']];
const ops=['=','!=','IN','NOT IN','Starts With','Contains','BETWEEN'];let tick=0;
function initial(){return {targets:copy(F.targets).map(t=>({...t,period_ym:C.today().slice(0,6)})),focus:copy(F.focus),nextTarget:100,nextFocus:100};}
let state=initial();try{const stored=JSON.parse(localStorage.getItem(KEY)||'null');if(stored?.targets&&stored?.focus)state=stored;}catch(_){}
function save(){try{localStorage.setItem(KEY,JSON.stringify(state));}catch(_){/* Session still works in privacy mode. */}}
function rules(p){return ['customer','warehouse','product_group','item'].filter(k=>p[k]&&p[k]!=='ALL').map(k=>({field_key:k==='customer'?'customer_code':k,operator:'=',filter_value:p[k]}));}
function normalize(rs=[]){
 if(!Array.isArray(rs)||rs.length>30)throw new Error('조건은 최대 30개입니다.');
 return rs.map(r=>{const f={...r};if(!fields.some(x=>x[0]===f.field_key)||!ops.includes(f.operator)||!String(f.filter_value||'').trim())throw new Error('조건 필드/연산자/값을 확인하세요.');
 f.filter_value=String(f.filter_value).trim();if(['IN','NOT IN'].includes(f.operator))f.filter_value=[...new Set(f.filter_value.split(',').map(x=>x.trim()).filter(Boolean))].sort().join(',');return f;});
}
function canon(rs){return JSON.stringify(normalize(rs).sort((a,b)=>JSON.stringify(a).localeCompare(JSON.stringify(b))));}
function match(row,rs){return normalize(rs).every(f=>{
 const k={item:'material',item_prefix:'material'}[f.field_key]||f.field_key,val=String(row[k]??''),v=f.filter_value,parts=v.split(',').map(x=>x.trim());
 switch(f.operator){case '=':return val===v;case '!=':return val!==v;case 'IN':return parts.includes(val);case 'NOT IN':return !parts.includes(val);case 'Starts With':return val.startsWith(v);case 'Contains':return val.includes(v);case 'BETWEEN':return parts.length===2&&val>=parts[0]&&val<=parts[1];default:return false;}
 });}
function date(p){return C.validDate(p.date)?p.date.replace(/-/g,''):C.today();}
function unsupported(dir,m,rs){return (m==='USD'&&dir!=='shipment')||(m==='BOX'&&dir==='shipment'&&rs.some(f=>!['warehouse','plant'].includes(f.field_key)));}
function selected(dir,m,start,end,rs=[]){
 if(unsupported(dir,m,rs))return [];
 const src=dir==='shipment'&&m==='BOX'?'shipment_box':dir,rows=F.records[src]||[],month=end.slice(0,6),current=C.today();
 return rows.filter(x=>month+String(x.day).padStart(2,'0')>=start&&month+String(x.day).padStart(2,'0')<=end&&match(x,rs)).map((x,i)=>{
  const row={...x,date:month+String(x.day).padStart(2,'0')};
  if(row.date===current&&dir!=='inventory'&&i%5===0){const add=tick*12;row.EA=(row.EA??0)+add;row.USD=row.USD==null?null:row.USD+add*2.4;row.EQ_DRAM=(row.EQ_DRAM??0)+(row.product_group==='DRAM'?add*1.25:0);row.EQ_FLASH=(row.EQ_FLASH??0)+(row.product_group==='FLASH'?add*4.5:0);}
  return row;
 });
}
function total(dir,m,start,end,rs=[]){
 if(unsupported(dir,m,rs))return null;
 return selected(dir,m,start,end,rs).reduce((a,x)=>a+(Number(x[m])||0),0);
}
function previous(d){const x=new Date(C.isoDate(d)+'T12:00:00Z');x.setUTCDate(x.getUTCDate()-1);return x.toISOString().slice(0,10).replace(/-/g,'');}
function resolve(ym,dir,m,rs=[]){
 const candidates=state.targets.filter(t=>t.enabled&&t.period_ym===ym&&t.direction===dir&&t.metric===m&&canon(t.filters)===canon(rs)).sort((a,b)=>a.priority-b.priority||a.target_id-b.target_id);
 if(candidates.length){const t=candidates[0];return {source:'MANUAL',target_value:t.target_value,target_id:t.target_id,target_name:t.target_name,target_available:true};}
 if(m==='BOX'||(m==='USD'&&dir!=='shipment'))return {source:'NONE',target_value:null,target_available:false};
 const plans=F.plans.filter(p=>p.direction===dir&&p.metric===(m.startsWith('EQ_')?'EA':m)&&rs.every(f=>{
  const map={material:p.material,customer_code:p.customer_key,warehouse:p.warehouse,product_group:p.product_group,plant:p.plant};return match(map,[f]);
 }));
 if(!plans.length)return {source:'NONE',target_value:null,target_available:false};
 const value=plans.reduce((v,p)=>{let n=p.target_i/1e6;if(m==='EQ_DRAM')n*=p.product_group==='DRAM'?1.25:0;if(m==='EQ_FLASH')n*=p.product_group==='FLASH'?4.5:0;return v+n;},0);
 return {source:'SYSTEM',target_value:value,target_available:true,target_name:'예시 시스템 목표'};
}
function kpi(p){const d=date(p),m=p.metric||'EA',rs=rules(p),start=d.slice(0,6)+'01',prev=previous(d),out={};
 for(const [dir,key] of [['inbound','production'],['shipment','shipment']]){const a=total(dir,m,start,d,rs),t=total(dir,m,d,d,rs),y=total(dir,m,prev,prev,rs),target=resolve(d.slice(0,6),dir,m,rs),tv=target.target_value;
 out[key]={target:tv,target_available:target.target_available,target_source:target.source,actual_mtd:a,actual_today:t,yesterday:y,achievement:C.pct(a,tv),yoy_change:C.change(t,y),date:d,previous_business_date:prev,count_mtd:selected(dir,m,start,d,rs).length,count_today:selected(dir,m,d,d,rs).length,status:unsupported(dir,m,rs)?'not_available':'ok'};}
 const stock=F.records.inventory.filter(x=>match(x,rs)),inv=m==='USD'?null:stock.reduce((n,x)=>n+(x[m]||0),0);
 return {...out,inventory:{current:inv,available:null,count:stock.length,status:inv==null?'not_available':'ok'},metric:m,date:d,inbound_as_of:d,shipment_as_of:d,latest_inbound_date:d,latest_shipment_date:d,demo:true,timestamp:new Date().toISOString()};
}
function hourly(p){const d=date(p),m=p.metric||'EA',rs=rules(p),out={};for(const [dir,key] of [['inbound','production'],['shipment','shipment']]){out[key]=Array(24).fill(unsupported(dir,m,rs)?null:0);for(const x of selected(dir,m,d,d,rs))out[key][Number(x.hour)]+=x[m]||0;}
 return {...out,hours:Array.from({length:24},(_,h)=>String(h).padStart(2,'0')),metric:m,current_hour:Number(C.kstParts().hour),inbound_date:d,shipment_date:d};}
function daily(p){const ym=p.month||date(p).slice(0,6),m=p.metric||'EA',rs=rules(p),end=p.date||C.today(),n=new Date(Number(ym.slice(0,4)),Number(ym.slice(4)),0).getDate(),out=[];
 for(let day=1;day<=n;day++){const d=ym+String(day).padStart(2,'0');if(d>end)break;out.push({date:d,production:total('inbound',m,d,d,rs),shipment:total('shipment',m,d,d,rs),shipment_amount:total('shipment','USD',d,d,rs)});}return {daily:out,month:ym,metric:m};}
function items(p){const d=date(p),m=p.metric||'EA',rs=rules(p),maps=new Map();
 for(const [dir,key] of [['inbound','production'],['shipment','shipment']])for(const x of selected(dir,m,d,d,rs)){
 const row=maps.get(x.material)||{material:x.material,name:x.name,product_group:x.product_group,production:0,shipment:0,shipment_amount:0,inventory:null,count:0};row[key]+=x[m]||0;if(dir==='shipment')row.shipment_amount+=x.USD||0;row.count++;maps.set(x.material,row);}
 const rows=[...maps.values()].sort((a,b)=>Math.max(b.production,b.shipment)-Math.max(a.production,a.shipment));return {items:rows.slice(0,Number(p.limit||30)),date:d,shipment_date:d,metric:m,total_materials:rows.length};}
function customers(p){const d=date(p),m=p.metric||'EA',rs=rules(p),rg=p.range||'daily';let start=d;if(rg==='monthly')start=d.slice(0,6)+'01';if(rg==='weekly')for(let i=0;i<6;i++)start=previous(start);
 const map=new Map();for(const x of selected('shipment',m,start,d,rs)){const row=map.get(x.customer_code)||{customer_key:x.customer_code,name:x.customer_name,production:null,shipment:0,shipment_amount:0,inventory:null,count:0};row.shipment+=x[m]||0;row.shipment_amount+=x.USD||0;row.count++;map.set(x.customer_code,row);}
 const all=[...map.values()].sort((a,b)=>b.shipment-a.shipment),value=total('shipment',m,start,d,rs),amount=total('shipment','USD',start,d,rs),limit=Number(p.limit||20),rows=all.slice(0,limit);
 if(all.length>limit){const rest=all.slice(limit);rows.push({customer_key:'__OTHERS__',name:'기타',shipment:rest.reduce((n,x)=>n+x.shipment,0),shipment_amount:rest.reduce((n,x)=>n+x.shipment_amount,0),production:null,inventory:null,count:rest.reduce((n,x)=>n+x.count,0)});}
 rows.forEach(x=>x.share=value?x.shipment/value*100:null);return {customers:rows,total_shipment:value,total_shipment_amount:amount,total_production:total('inbound',m,start,d,rs),inbound_date:d,shipment_date:d,range:rg,metric:m};}
function filters(){const unique=(rows,key,name)=>[...new Map(rows.map(x=>[x[key],{key:x[key],name:x[name]||x[key]}])).values()];return {customers:unique(F.records.shipment,'customer_code','customer_name'),items:unique(F.records.inbound,'material','name'),product_groups:unique(F.records.inbound,'product_group','product_group'),warehouses:unique(F.records.inbound,'warehouse','warehouse')};}
function events(p){const d=date(p),rs=rules(p),all=[];for(const [dir,type] of [['inbound','입고등록'],['shipment','출하']])for(const x of selected(dir,'EA',p.date?d:d.slice(0,6)+'01',d,rs)){all.push({date:x.date,time:x.hour+':15:00',type,detail:`${x.material} ${C.format(x.EA)} EA · 합성 데이터`,warehouse:x.warehouse,material:x.material,qty:x.EA,id:x.id});}all.sort((a,b)=>(b.date+b.time).localeCompare(a.date+a.time));return {events:all.slice(0,Number(p.limit||50)),timestamp:new Date().toISOString()};}
function focusKpi(p){const d=date(p),m=p.metric||'EA',items=state.focus.filter(f=>f.enabled).map(f=>{const rs=[];if(f.focus_type!=='customer')rs.push({field_key:'item',operator:'=',filter_value:f.item_code});if(f.focus_type!=='item')rs.push({field_key:'customer_code',operator:'=',filter_value:f.customer_code});const out={...f};for(const dir of ['inbound','shipment']){const a=total(dir,m,d.slice(0,6)+'01',d,rs),t=resolve(d.slice(0,6),dir,m,rs);out[dir]={mtd:a,today:total(dir,m,d,d,rs),count:selected(dir,m,d.slice(0,6)+'01',d,rs).length,date:d,target:t.target_value,target_source:t.source,achievement:C.pct(a,t.target_value)};}return out;});return {metric:m,date:d,items,count:items.length};}
function actual(t,p={}){const m=t.metric,start=t.period_ym+'01',end=p.date||t.period_ym+'31';const val=total(t.direction,m,start,end,t.filters);return {actual:val,actual_value:val,count:selected(t.direction,m,start,end,t.filters).length,match_count:selected(t.direction,m,start,end,t.filters).length};}
function validateTarget(b){if(!/^\d{6}$/.test(b.period_ym)||Number(b.period_ym.slice(4))<1||Number(b.period_ym.slice(4))>12||!['inbound','shipment'].includes(b.direction)||!metrics.includes(b.metric)||!b.target_name?.trim()||!Number.isFinite(Number(b.target_value))||Number(b.target_value)<0)throw new Error('목표의 기간/이름/값을 확인하세요.');b.filters=normalize(b.filters||[]);return {...b,target_value:Number(b.target_value),priority:Number(b.priority??10),enabled:b.enabled??true,additive:false};}
function validateFocus(b){const f={...b,focus_type:b.focus_type||'item'};if(!['item','customer','customer_item'].includes(f.focus_type))throw new Error('유형을 확인하세요.');if(f.focus_type==='item')f.customer_code=null;if(f.focus_type==='customer')f.item_code=null;if((f.focus_type!=='customer'&&!f.item_code)||(f.focus_type!=='item'&&!f.customer_code))throw new Error('필수 아이템/거래선 코드가 없습니다.');f.enabled=f.enabled??1;f.label=f.label||f.item_code||f.customer_code;return f;}
function addFocus(f){const dup=state.focus.find(x=>x.focus_type===f.focus_type&&(x.item_code||null)===(f.item_code||null)&&(x.customer_code||null)===(f.customer_code||null));if(dup)return {focus_id:dup.focus_id,ok:false,reason:'duplicate'};f.focus_id=state.nextFocus++;state.focus.push(f);return {focus_id:f.focus_id,ok:true};}
function request(path,body){const u=new URL(path,'https://demo.invalid'),p=Object.fromEntries(u.searchParams),key=u.pathname.replace(/^\/api\//,'');
 if(body!==undefined){const b=copy(body);let res;
  switch(key){
  case 'targets/create':{const t=validateTarget(b);t.target_id=state.nextTarget++;state.targets.push(t);res={ok:true,target_id:t.target_id};break;}
  case 'targets/update':{const i=state.targets.findIndex(t=>t.target_id===Number(b.target_id));if(i<0)throw new Error('목표 없음');state.targets[i]=validateTarget({...state.targets[i],...b});res={ok:true,target_id:b.target_id};break;}
  case 'targets/delete':state.targets=state.targets.filter(t=>t.target_id!==Number(b.target_id));res={ok:true,deleted:true};break;
  case 'targets/preview':return actual({...b,filters:normalize(b.filters||[])});
  case 'targets/copy-month':{if(b.from_ym===b.to_ym||!/^\d{6}$/.test(b.to_ym))throw new Error('서로 다른 유효 기간이 필요합니다.');const rows=copy(state.targets.filter(t=>t.period_ym===b.from_ym&&(!b.direction||t.direction===b.direction)));rows.forEach(t=>{t.target_id=state.nextTarget++;t.period_ym=b.to_ym;state.targets.push(t);});res={ok:true,copied_count:rows.length};break;}
  case 'focus/create':res=addFocus(validateFocus(b));break;
  case 'focus/batch_create':{const fs=b.items.map(validateFocus);res={results:fs.map(addFocus),count:fs.length};break;}
  case 'focus/delete':state.focus=state.focus.filter(f=>f.focus_id!==Number(b.focus_id));res={ok:true,deleted:true};break;
  case 'focus/delete_batch':{const old=state.focus.length;state.focus=state.focus.filter(f=>!b.focus_ids.includes(f.focus_id));res={ok:true,deleted:old-state.focus.length};break;}
  case 'focus/update':{const f=state.focus.find(x=>x.focus_id===Number(b.focus_id));if(!f)throw new Error('항목 없음');for(const k of ['label','enabled','sort_order'])if(b[k]!==undefined)f[k]=b[k];res={ok:true};break;}
  default:throw new Error('지원하지 않는 데모 작업');}
  save();return res;
 }
 switch(key){case 'kpi':return kpi(p);case 'hourly':return hourly(p);case 'daily-trend':return daily(p);case 'items':return items(p);case 'customers':return customers(p);case 'filters':return filters();case 'events':return events(p);
 case 'inbound-progress':return {simulated:false,progress:events({...p,limit:500}).events.filter(e=>e.type==='입고등록').slice(0,15).map(e=>({material:e.material,item_name:e.material,qty:e.qty,time:e.time,date:e.date,line:'DEMO',warehouse:e.warehouse,stage:'예시 입고완료',stage_index:5})),timestamp:new Date().toISOString()};
 case 'alerts':return {alerts:[{level:'info',msg:'합성 데이터 데모 · 목표/집중관리 변경은 현재 브라우저에만 저장됩니다.'}]};
 case 'targets/meta':return {fields:fields.map(([key,label])=>({key,label,shipment_available:true,inbound_available:!['country','sales_org','ship_type'].includes(key)})),operators:ops};
 case 'targets':case 'targets/list':return {targets:state.targets.filter(t=>(!p.period_ym||t.period_ym===p.period_ym)&&(!p.direction||t.direction===p.direction)).map(t=>({...t,...actual(t,p),source:'MANUAL'}))};
 case 'targets/get':{const t=state.targets.find(t=>t.target_id===Number(p.target_id));if(!t)throw new Error('목표 없음');return {...copy(t),...actual(t),source:'MANUAL'};}
 case 'targets/resolve':return resolve(p.period_ym,p.direction,p.metric||'EA',JSON.parse(p.filters||'[]'));
 case 'focus':if(p.action==='kpi')return focusKpi(p);return {items:copy(state.focus.filter(x=>p.action==='list_all'||x.enabled)),count:state.focus.length};
 default:throw new Error('지원하지 않는 데모 API: '+key);
 }
}
window.SCMOffline={request,reset(){state=initial();save();},setTick(n){tick=n;}};
window.SCMDemo={get(endpoint,p={},n=0){tick=n;return request('/api/'+endpoint+'?'+new URLSearchParams(p));}};
})();
