/* Portable UI configuration. No secrets or company connections belong here. */
window.SCM_CONFIG={
 apiBase:'',refreshSeconds:5,timeoutMs:30000,dailyRefreshSeconds:15,
 units:{verified:true,profile:'raw',overrides:{}},
 capabilities:{inventoryConnected:window.SCM_PREVIEW===true||new URLSearchParams(location.search).get('demo')==='1'||window.SCM_RUNTIME?.inventoryConnected===true,progressIsSimulation:false},
 endpointParameters:{
  kpi:['metric','date','customer','warehouse','product_group','item'],
  hourly:['metric','date','customer','warehouse','product_group','item'],
  customers:['metric','date','customer','warehouse','product_group','item','range','limit'],
  items:['metric','date','customer','warehouse','product_group','item'],
  events:['date','customer','warehouse','product_group','item','limit'],
  'inbound-progress':['date','customer','warehouse','product_group','item'],
  alerts:[],filters:[],
  'daily-trend':['metric','date','month','customer','warehouse','product_group','item']
 }
};
