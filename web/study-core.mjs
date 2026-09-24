// Research navigation/visibility rules; independently testable without a DOM.
import {TF,bucket} from './core.mjs';
export function firstEvent(events){return events.find(e=>e.role==='Entry')||events[0]||null;}
export function knownEvents(events,cutoff=null){return events.filter(e=>cutoff==null||e.first_us<cutoff*1e6);}
export function completedOrder(e,cutoff=null){return cutoff==null||!!e.last_observed&&e.last_us<cutoff*1e6;}
export function criticalIds(events,selected=null,cutoff=null){
  const known=knownEvents(events,cutoff),ids=new Set();const first=firstEvent(known);
  if(first)ids.add(first.id);
  // Last OBSERVED reduction is retained in history; never look forward in replay.
  const exits=known.filter(e=>e.role==='Exit');if(exits.length)ids.add(exits.at(-1).id);
  if(selected&&known.some(e=>e.id===selected))ids.add(selected);return ids;
}
export function visibleStudyEvents(events,{minQty=0,selected=null,cutoff=null,increases=true,reductions=true}={}){
  const known=knownEvents(events,cutoff),critical=criticalIds(events,selected,cutoff);
  return known.filter(e=>(e.role==='Entry'?increases:reductions)&&(cutoff!=null||critical.has(e.id)||e.qty>=minQty));
}
export function episodeRange(ep,tf,events=[]){
  const step=TF[tf],first=firstEvent(events)?.time??ep.focus??ep.start;
  const last=Math.max(first,...events.map(e=>e.end_time??e.time));
  const lo=Math.max(ep.year_floor||0,bucket(first,tf)-30*step),hi=bucket(last,tf)+31*step;
  return (hi-lo)/step<=3500&&hi-lo<179*86400?[lo,hi]:[Math.max(ep.year_floor||0,bucket(first,tf)-40*step),bucket(first,tf)+160*step];
}
export function newlyRevealed(events,oldCutoff,newCutoff){
  return events.filter(e=>e.first_us>=oldCutoff*1e6&&e.first_us<newCutoff*1e6).sort((a,b)=>a.first_us-b.first_us);
}
export function markerDiagnostics(events,bars,tf,cutoff=null){
  const actual=new Set(bars.filter(b=>b.open!=null).map(b=>b.time));
  const start=bars[0]?.time,end=(bars.at(-1)?.time??0)+TF[tf];
  let outside=0,gap=0,notYet=0;
  for(const e of events){if(cutoff!=null&&e.first_us>=cutoff*1e6){notYet++;continue;}
    const t=bucket(e.time,tf);if(start==null||t<start||t>=end)outside++;else if(!actual.has(t))gap++;}
  return {outside,gap,notYet};
}
export function safeAction(e,cutoff=null){
  if(cutoff==null)return e.action;
  if(e.role==='Entry')return e.position_before===0?'ENTRY':e.position_before>0?'ADD':'INCREASE';
  if(String(e.order_type||'').toLowerCase().includes('stop'))return 'STOP';
  if(completedOrder(e,cutoff)&&e.position_after===0)return 'CLOSE';
  const s=e.direction==='Long'?1:e.direction==='Short'?-1:0;
  const m=s&&e.first_price>0&&e.basis_before>0?s*(e.first_price/e.basis_before-1):null;
  return m>0?'TP':m<0?'LOSS_REDUCE':'REDUCE';
}
