import {TF,bucket,ACTIONS,fmtQty,sideOf,displayAction} from './core.mjs';
import {completedOrder,safeAction,firstEvent} from './study-core.mjs';
export function studyMarkers(events,bars,tf,{cutoff=null,selected=null,endpoint='first',legacy=false,allEvents=events}={}){
  const actual=new Set(bars.filter(b=>b.open!=null).map(b=>b.time)),groups=new Map();let missing=0;
  const first=firstEvent(allEvents)?.id;
  for(const e of events){
    if(cutoff!=null&&e.first_us>=cutoff*1e6)continue;
    const t=bucket(cutoff==null&&endpoint==='last'&&e.last_observed?e.end_time:e.time,tf);
    if(!actual.has(t)){missing++;continue;}
    const action=cutoff==null?displayAction(e,legacy):safeAction(e,cutoff),position=sideOf(e);
    const k=[t,position,action,e.direction].join('|');
    if(!groups.has(k))groups.set(k,{time:t,position,action,direction:e.direction,items:[]});groups.get(k).items.push(e);
  }
  let rows=[...groups.values()].sort((a,b)=>a.time-b.time||a.position.localeCompare(b.position));const total=rows.length;
  if(total>800){const selectedGroup=rows.find(g=>g.items.some(e=>e.id===selected));const head=rows[0];rows=rows.slice(-798);for(const g of [head,selectedGroup])if(g&&!rows.includes(g))rows.push(g);rows.sort((a,b)=>a.time-b.time);}
  const markers=rows.map((g,i)=>{const known=g.items.every(e=>completedOrder(e,cutoff));
    const initial=g.items.some(e=>e.id===first);const actionLabel=initial&&g.action==='INCREASE'?'첫 관측 진입':ACTIONS[g.action]?.label||g.action;
    const qty=known?' '+fmtQty(g.items.reduce((n,e)=>n+e.qty,0)):'';
    return {id:'g'+i,time:g.time,position:g.position,shape:g.position==='aboveBar'?'arrowDown':'arrowUp',
      color:g.items.some(e=>e.id===selected)?'#c9860a':g.action==='ENTRY'||g.action==='ADD'||g.action==='INCREASE'?g.direction==='Short'?'#df535f':'#069879':ACTIONS[g.action]?.color||'#65778c',
      text:`${g.direction==='Short'?'숏':'롱'} ${actionLabel}${qty}${g.items.length>1?' ·'+g.items.length+'건':''}`,size:1.25};});
  return {markers,groups:rows,missing,truncated:Math.max(0,total-rows.length)};
}
