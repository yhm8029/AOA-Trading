// Pure functions shared with node:test. Stored times are always UNIX UTC seconds.
export const TF = { '1m':60,'5m':300,'15m':900,'1h':3600,'4h':14400,'1d':86400 };
export const ACTIONS = {
  ENTRY:{label:'진입',color:'#0e9f7b'}, ADD:{label:'추가',color:'#0e9f7b'}, INCREASE:{label:'진입/추가',color:'#0e9f7b'},
  TP:{label:'익절*',color:'#2864df'}, LOSS_REDUCE:{label:'손실감량*',color:'#9860d4'}, REDUCE:{label:'감량',color:'#6b7280'},
  STOP:{label:'스톱',color:'#dc3545'}, CLOSE:{label:'종료 주문',color:'#64748b'}, CUT:{label:'CUT?',color:'#9860d4'}, FLIP:{label:'전환?',color:'#e99c21'}
};
export function fmtQty(n) {
  if (n == null || !Number.isFinite(+n)) return '—';
  return Math.abs(n)>=1e6 ? `${+(n/1e6).toFixed(3)}M` : Math.abs(n)>=1000 ? `${+(n/1000).toFixed(2)}K` : String(n);
}
export function bucket(time, tf) { return Math.floor(time / TF[tf]) * TF[tf]; }
export function displayAction(e, legacy=false) {
  if (legacy && e.legacy_label?.startsWith('TACTICAL_CUT')) return 'CUT';
  if (legacy && e.legacy_label?.startsWith('FLIP')) return 'FLIP';
  return e.action;
}
export function sideOf(e) {
  // Short entry belongs above; covering a short belongs below, independently of profit/loss.
  return (e.role==='Entry') === (e.direction==='Short') ? 'aboveBar' : 'belowBar';
}
export function filterEvents(events,{direction='',minQty=0,actions=null,legacy=false,cutoff=null}={}) {
  return events.filter(e => (!direction || e.direction===direction) && (cutoff==null ? e.qty>=minQty : true)
    && (cutoff==null || e.first_us<=cutoff*1e6)
    && (!actions || actions.has(displayAction(e,legacy))));
}
export function completeAt(bars,tf,cutoff=null) {
  return cutoff==null ? bars : bars.filter(b => b.time+TF[tf]<=cutoff);
}
export function buildMarkers(events,bars,tf,{legacy=false,cutoff=null,selected=null,endpoint='first'}={}) {
  const actual = new Set(bars.filter(b=>b.open!=null).map(b=>b.time));
  const groups = new Map(); let missing=0;
  for (const e of events) {
    const stamp=endpoint==='last' && e.last_observed ? e.end_time : e.time;
    if (cutoff!=null && e.first_us>cutoff*1e6) continue;
    const t=bucket(stamp,tf);
    if (!actual.has(t)) { missing++; continue; }
    const action=cutoff!=null ? (e.role==='Entry'?'INCREASE':'REDUCE') : displayAction(e,legacy);
    const side=sideOf(e), key=`${t}|${side}|${action}|${e.direction}`;
    if (!groups.has(key)) groups.set(key,{time:t,position:side,action,direction:e.direction,items:[],qty:0});
    const g=groups.get(key); g.items.push(e); g.qty+=e.qty;
  }
  const result=[...groups.values()].sort((a,b)=>a.time-b.time || a.position.localeCompare(b.position));
  const markers=result.slice(0,800).map((g,i)=>({
    id:`g${i}`,time:g.time,position:g.position,
    shape:g.position==='aboveBar'?'arrowDown':'arrowUp',
    color: selected && g.items.some(e=>e.id===selected) ? '#d38a08' : g.action==='ENTRY'||g.action==='ADD'||g.action==='INCREASE' ? g.direction==='Short'?'#e05050':'#0e9f7b' : ACTIONS[g.action]?.color || '#6b7280',
    text:`${g.direction==='Short'?'숏':'롱'} ${ACTIONS[g.action]?.label||g.action}${cutoff==null?' '+fmtQty(g.qty):''}${g.items.length>1?' ·'+g.items.length+'건':''}`,
    size:1
  }));
  return {markers,groups:result.slice(0,800),missing,truncated:Math.max(0,result.length-800)};
}
export function relativeVolume(bars,index,n=20) {
  if (index<n || !bars[index] || bars[index].volume==null) return null;
  const preceding=bars.slice(index-n,index);
  if (preceding.some(b=>b.volume==null)) return null;
  const avg=preceding.reduce((s,b)=>s+b.volume,0)/n;
  return avg>0 ? bars[index].volume/avg : null;
}
export function localDateInput(timestamp,zone) {
  return new Date((timestamp+(zone==='KST'?32400:0))*1000).toISOString().slice(0,16);
}
export function parseDateInput(text,zone) {
  const ms=Date.parse(text+'Z');
  return Number.isFinite(ms) ? ms/1000-(zone==='KST'?32400:0) : null;
}
