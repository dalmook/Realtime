/* DEMO ONLY. Synthetic fixtures; never selected automatically on an API failure. */
(function(){
  'use strict';
  const C=window.SCMCore;
  const streamBase=Date.now()-300000;
  const mod=(n,m)=>((n%m)+m)%m;
  const names=['거래선 A · 북미','거래선 B · 국내','거래선 C · 유럽','거래선 D · 중국','거래선 E · 대만','거래선 F · 일본','거래선 G · 동남아','거래선 H · 국내'];
  const groups=['DRAM','DRAM','FLASH','DRAM','FLASH','DDI'];
  const products=Array.from({length:30},(_,i)=>({material:`${groups[i%6]==='FLASH'?'K9':'K4'}D${String(423252+i*271).padStart(6,'0')}F-DEMO${String(i+1).padStart(3,'0')}`,name:`${groups[i%6]} ${i%2?'16Gb':'8Gb'} · 예시 품목 ${String(i+1).padStart(2,'0')}`,product_group:groups[i%6]}));
  const distribute=(total,weights)=>{const sum=weights.reduce((a,b)=>a+b,0);let acc=0;return weights.map((w,i)=>{const v=i===weights.length-1?total-acc:Math.round(total*w/sum);acc+=v;return v;});};
  function dataset(date,tick){
    const day=Number(date.slice(6,8)), isToday=date===C.today(), t=isToday?tick:0;
    const pToday=12780000+t*18000, sToday=11160000+t*12000;
    const priorP=Array.from({length:Math.max(0,day-1)},(_,i)=>6.7+Math.sin(i*.75)*1.5+i*.14);
    const priorS=Array.from({length:Math.max(0,day-1)},(_,i)=>6.2+Math.cos(i*.65)*1.4+i*.12);
    const pHist=distribute(Math.round(241281000*Math.max(0,day-1)/27),priorP);
    const sHist=distribute(Math.round(223720000*Math.max(0,day-1)/27),priorS);
    const daily=[...Array(day)].map((_,i)=>({date:date.slice(0,6)+String(i+1).padStart(2,'0'),production:i===day-1?pToday:pHist[i],shipment:i===day-1?sToday:sHist[i],shipment_amount:(i===day-1?sToday:sHist[i])*3.18}));
    const hour=isToday?Number(C.kstParts().hour):23;
    const hp=distribute(pToday,Array.from({length:hour+1},(_,i)=>.6+(Math.sin(i*.9)+1)*.6+i*.045));
    const hs=distribute(sToday,Array.from({length:hour+1},(_,i)=>.5+(Math.cos(i*.8)+1)*.5+i*.055));
    const hourly={hours:Array.from({length:24},(_,i)=>String(i).padStart(2,'0')),production:Array.from({length:24},(_,i)=>hp[i]??0),shipment:Array.from({length:24},(_,i)=>hs[i]??0),current_hour:hour,inbound_date:date,shipment_date:date};
    return {daily,hourly,pToday,sToday,pMtd:C.sum(daily.map(d=>d.production)),sMtd:C.sum(daily.map(d=>d.shipment)),pYesterday:pHist.at(-1)??0,sYesterday:sHist.at(-1)??0};
  }
  function get(endpoint,params={},tick=0){
    const date=C.validDate(params.date)?params.date.replace(/-/g,''):C.today();
    const d=dataset(date,tick), now=C.kstParts(), timestamp=`${now.year}-${now.month}-${now.day}T${now.hour}:${now.minute}:${now.second}+09:00`;
    if(endpoint==='filters')return {customers:Array.from({length:20},(_,i)=>({key:`C${i+1}`,name:names[i]||`거래선 ${String.fromCharCode(65+i)} · 예시`})),warehouses:[{key:'1310',name:'온양'},{key:'1380',name:'인천'},{key:'13Z0',name:'아레나스 (3F)'},{key:'53P0',name:'클락'}],product_groups:['DRAM','FLASH','DDI'].map(key=>({key,name:key})),items:products.map(p=>({key:p.material,name:p.name}))};
    if(endpoint==='kpi'){
      const metric=params.metric||'EA';
      let ratio=1;
      if(params.warehouse)ratio*=.42;
      if(params.product_group)ratio*=({DRAM:.58,FLASH:.33,DDI:.09}[params.product_group]||0);
      if(params.item)ratio*=products.some(p=>p.material===params.item)?.043:0;
      const shipmentRatio=ratio*(params.customer?.startsWith('C')?.17:1);
      const factors={EA:1,EQ_DRAM:1.23,EQ_FLASH:5.41,BOX:1/12000,USD:3.18};const f=factors[metric]||1;
      const make=(p,today,yesterday,target,count,r)=>({target:metric==='BOX'?null:target*f*r,actual_mtd:metric==='BOX'?Math.round(p*f*r):p*f*r,actual_today:metric==='BOX'?Math.round(today*f*r):today*f*r,yesterday:metric==='BOX'?Math.round(yesterday*f*r):yesterday*f*r,count_mtd:Math.round(count*r),count_today:Math.round(768*r),achievement:target?p/target*100:null,yoy_change:yesterday?(today-yesterday)/yesterday*100:null,date});
      const production=make(d.pMtd,d.pToday,d.pYesterday,264454000,15420,ratio),shipment=make(d.sMtd,d.sToday,d.sYesterday,270000000,21474,shipmentRatio);
      if(metric==='USD'){for(const key of ['target','actual_mtd','actual_today','yesterday','achievement','yoy_change'])production[key]=null;}
      return {metric,production,shipment,inventory:{current:0,available:0,count:0,yoy_change:0,shortage:0,excess:0},date,latest_inbound_date:date,latest_shipment_date:date,timestamp};
    }
    if(endpoint==='hourly')return d.hourly;
    if(endpoint==='daily-trend'){
      const month=/^\d{6}$/.test(params.month||'')?params.month:date.slice(0,6);
      const isCurrent=month===C.today().slice(0,6);
      const day=isCurrent?Number(C.today().slice(6)):new Date(Number(month.slice(0,4)),Number(month.slice(4)),0).getDate();
      if(month>C.today().slice(0,6))return {daily:[],month};
      return {daily:dataset(month+String(day).padStart(2,'0'),tick).daily,month};
    }
    if(endpoint==='customers'){
      const mult=params.range==='monthly'?d.sMtd/d.sToday:params.range==='weekly'?5.8:1;
      const total=d.sToday*mult;const weights=[19,15,11,9,7,5.5,4.5,3.5,3,2.7,2.2,2,1.8,1.5,1.3,1.2,1,.8,.7,.5];
      const shipped=distribute(Math.round(total*.92),weights);
      return {customers:shipped.map((v,i)=>({customer_key:`C${i+1}`,name:names[i]||`거래선 ${String.fromCharCode(65+i)} · 예시`,group:'예시 거래선',production:0,shipment:v,shipment_amount:v*3.18,inventory:0,share:v/total*100,count:Math.round(v/18000)})),total_production:d.pToday,total_shipment:total,total_shipment_amount:total*3.18,range:params.range||'daily',inbound_date:date,shipment_date:date};
    }
    if(endpoint==='items'){
      const pp=distribute(Math.round(d.pToday*.84),products.map((_,i)=>Math.max(1,30-i))),ss=distribute(Math.round(d.sToday*.73),products.map((_,i)=>Math.max(1,25-i)+Math.sin(i)*.8));
      return {items:products.map((p,i)=>({...p,production:pp[i],shipment:ss[i],shipment_amount:ss[i]*3.18,inventory:0,count:Math.round(pp[i]/12000),stage:'입고등록'})),date,shipment_date:date};
    }
    if(endpoint==='events'){
      const events=Array.from({length:50},(_,i)=>{
        const seq=tick-i, p=products[mod(seq,products.length)], k=C.kstParts(new Date(streamBase+seq*5000)), shipment=mod(seq,3)===0;
        return {date:k.year+k.month+k.day,time:`${k.hour}:${k.minute}:${k.second}`,type:shipment?'출하':'입고등록',detail:`${p.material} · ${C.format((shipment?12:18)*1000)} EA ${shipment?'출하':'입고'} · 예시`,warehouse:shipment?null:['1310','1380','13Z0'][mod(seq,3)]};
      });return {events,timestamp};
    }
    if(endpoint==='inbound-progress')return {progress:Array.from({length:15},(_,i)=>{const seq=tick-i,idx=mod(i+tick,6),p=products[mod(seq,30)],k=C.kstParts(new Date(streamBase+seq*5000));return {line:`M${mod(seq,3)+1} Line`,material:p.material,item_name:p.name,customer:'생산입고',qty:(mod(seq,5)+1)*12000,warehouse:['온양','인천','아레나스'][mod(seq,3)],stage:['대기','생산완료','입고등록','검수중','적치중','완료'][idx],stage_index:idx,is_new:i===0,time:`${k.hour}${k.minute}${k.second}`};}),timestamp};
    if(endpoint==='alerts')return {alerts:[{level:'info',msg:'재고 데이터 미연동 · 현재고와 가용재고는 표시하지 않습니다.'},{level:'info',msg:'입고 진행 단계는 모의 값입니다. 실제 공정 진행 상태로 사용하지 마세요.'}]};
    throw new Error('지원하지 않는 데모 endpoint');
  }
  window.SCMDemo={get};
})();
