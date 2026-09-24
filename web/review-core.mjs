import {TF,bucket} from './core.mjs';
export const isBar=b=>b!=null && ['open','high','low','close'].every(k=>Number.isFinite(b[k]));
export const validBars=bars=>bars.filter(isBar);
export function candleMetrics(b,prev=null,seconds=null){
  if(!isBar(b)||b.open<=0)return null;
  const contiguous=prev && isBar(prev) && prev.close>0 && (!seconds||b.time-prev.time===seconds);
  return {bodyPct:(b.close/b.open-1)*100,previousPct:contiguous?(b.close/prev.close-1)*100:null,rangePct:(b.high-b.low)/b.open*100};
}
export function pct(n,digits=2){return n==null||!Number.isFinite(n)?'미확보':`${n>0?'+':''}${n.toFixed(digits)}%`;}
export function windowRange(anchor,tf,floor=null){
  if(!TF[tf]||!Number.isFinite(anchor))throw Error('올바른 기준 시각/시간봉이 필요합니다.');
  const n=tf==='1d'?[30,90]:tf==='4h'?[60,180]:[60,180];
  const t=bucket(anchor,tf),start=Math.max(t-n[0]*TF[tf],floor||0);
  return [Math.floor(start/TF[tf])*TF[tf],t+n[1]*TF[tf]];
}
export function replayStart(bars,tf,anchor,preRoll=3){
  const actual=validBars(bars);
  if(!actual.length)return {index:-1,cutoff:null,warning:'이 구간에 완성된 실제 캔들이 없습니다. 실제 시세 보완이 필요합니다.'};
  const target=bucket(anchor,tf)-Math.max(0,preRoll)*TF[tf];
  let i=-1;
  for(let j=0;j<actual.length;j++){if(actual[j].time+TF[tf]<=target)i=j;else break;}
  const warning=i<0?'진입 직전 완성 봉이 부족하여 첫 확보 봉부터 표시합니다.':null;
  i=Math.max(0,i);
  return {index:i,cutoff:actual[i].time+TF[tf],warning};
}
export function indexAtCutoff(bars,tf,cutoff){
  const actual=validBars(bars);let i=-1;
  for(let j=0;j<actual.length;j++){if(actual[j].time+TF[tf]<=cutoff)i=j;else break;}
  return i;
}
export function nextValidStep(bars,tf,index){
  const actual=validBars(bars),next=index+1;
  if(next>=actual.length)return null;
  const skipped=index>=0?Math.max(0,Math.round((actual[next].time-actual[index].time)/TF[tf])-1):0;
  return {index:next,cutoff:actual[next].time+TF[tf],skipped};
}
