// Pure chart/domain helpers. Tested with node --test; no DOM or hidden state.
export const FRAMES=[1,5,15,60,240,1440];
export const COLORS={long:'#089981',short:'#f23645',take:'#2979ff',cut:'#9958d7',stop:'#c62828',close:'#7c8798',flip:'#e88821',unknown:'#64748b'};
export function category(e){
 const s=e.event;
 if(s.startsWith('TACTICAL_CUT'))return 'CUT';
 if(s.startsWith('TAKE_PROFIT')||s.startsWith('TP_'))return 'TP';
 if(s.startsWith('NEAR_CLOSE'))return 'NEAR_CLOSE';
 if(s.startsWith('FLIP'))return 'FLIP';
 for(const k of ['ENTRY','ADD','STOP','CLOSE','REDUCE','INCREASE'])if(s.startsWith(k))return k;
 return 'UNKNOWN';
}
export function isIncrease(e){return ['ENTRY','ADD','FLIP','INCREASE'].includes(category(e));}
export function label(e){
 const d=e.direction==='Long'?'롱':'숏';
 return ({ENTRY:`${d} 진입`,ADD:`${d} 추가`,FLIP:`${d} 전환 후보`,INCREASE:`${d} 증가`,TP:`${d} 익절`,CUT:`${d} 추가분 철회?`,STOP:`${d} STOP`,CLOSE:`${d} 종료`,NEAR_CLOSE:`${d} 대부분 정리`,REDUCE:`${d} 감량`})[category(e)]||e.event;
}
export function color(e){let c=category(e);return ['ENTRY','ADD','INCREASE'].includes(c)?COLORS[e.direction==='Long'?'long':'short']:({TP:COLORS.take,CUT:COLORS.cut,STOP:COLORS.stop,CLOSE:COLORS.close,NEAR_CLOSE:COLORS.close,FLIP:COLORS.flip,REDUCE:COLORS.unknown})[c]||COLORS.unknown;}
export function bucket(t,tf){return Math.floor((t/1e6)/(tf*60))*(tf*60);}
export function qty(n){if(n==null)return '—';if(Math.abs(n)>=1e6)return (n/1e6).toLocaleString('en-US',{maximumFractionDigits:3})+'M';if(Math.abs(n)>=1e3)return (n/1e3).toLocaleString('en-US',{maximumFractionDigits:1})+'K';return n.toLocaleString('en-US');}
export function px(n){return n==null?'—':Number(n).toLocaleString('en-US',{maximumFractionDigits:2});}
export function eligible(e,filters){return e.qty>=filters.minQty&&filters.categories.has(category(e));}
export function groupMarkers(events,bars,tf,filters){
 const valid=new Set(bars.filter(x=>x.open!==undefined).map(x=>x.time));
 const groups=new Map();let missing=0;
 for(const e of events){
  if(!eligible(e,filters))continue;
  const t=bucket(e.time_us,tf);
  if(!valid.has(t)){missing++;continue;}
  const increase=isIncrease(e);
  const above=increase?e.direction==='Short':e.direction==='Long';
  const key=t+'|'+(above?'A':'B');
  if(!groups.has(key))groups.set(key,{time:t,above,events:[]});
  groups.get(key).events.push(e);
 }
 const output=[...groups.values()].sort((a,b)=>a.time-b.time||Number(a.above)-Number(b.above));
 for(const g of output){
  g.events.sort((a,b)=>a.time_us-b.time_us||a.id.localeCompare(b.id));
  const e=g.events[0],names=[...new Set(g.events.map(label))];
  const text=(names.length===1?names[0]:'복합 주문')+(g.events.length>1?' ×'+g.events.length:'')+(filters.showQty?' '+qty(g.events.reduce((n,e)=>n+e.qty,0)):'');
  g.marker={id:'bar-'+g.time+'-'+(g.above?'A':'B'),time:g.time,position:g.above?'aboveBar':'belowBar',shape:g.above?'arrowDown':'arrowUp',color:color(e),text};
 }
 return {groups:output,missing};
}
export function priceReturn(e){if(!(e.basis_before>0&&e.first_price>0))return null;return (e.direction==='Long'?1:-1)*(e.first_price/e.basis_before-1)*100;}
export function formatTime(us,tz='UTC',seconds=true){if(us==null)return '—';return new Intl.DateTimeFormat('sv-SE',{timeZone:tz,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',...(seconds?{second:'2-digit'}:{})}).format(new Date(us/1000));}
export function desiredRange(ep,tf,focus=null){
 const step=tf*60,pad=step*80,start=ep.start_us/1e6,end=ep.end_us/1e6;
 if(focus!=null)return {start:Math.floor(focus-step*100),end:Math.ceil(focus+step*140)};
 if((end-start+2*pad)/step<=2400)return {start:Math.floor(start-pad),end:Math.ceil(end+pad)};
 return {start:Math.floor(start-pad),end:Math.ceil(start+step*360),windowed:true};
}
export function safeCsv(value){const s=String(value??'');const t=/^[=+\-@\t\r]/.test(s)?"'"+s:s;return '"'+t.replaceAll('"','""')+'"';}
