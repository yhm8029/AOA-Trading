import {TF,ACTIONS,fmtQty,bucket,completeAt,relativeVolume,parseDateInput,localDateInput} from './core.mjs';
import {isBar,validBars,candleMetrics,pct,windowRange,replayStart,indexAtCutoff,nextValidStep} from './review-core.mjs';
import {firstEvent,knownEvents,completedOrder,visibleStudyEvents,episodeRange,newlyRevealed,markerDiagnostics,safeAction} from './study-core.mjs';
import {studyMarkers} from './study-markers.mjs';
import {renderStudy,UI_VERSION} from './study-ui.mjs';
import {renderOutcome,outcomeAvailable,returnText,finalResultMarker} from './pnl-ui.mjs';
import {renderSizing,seedLabel,seedReturnText} from './seed-ui.mjs';
const $=id=>document.getElementById(id);
const S={token:'',episodes:[],episode:null,events:[],bars:[],visible:[],tf:'5m',loadedTf:null,zone:'UTC',start:0,end:0,anchor:null,selected:null,cutoff:null,replayIndex:-1,request:0,listRequest:0,viewRequest:0,markerGroups:[],timer:null,playing:false,playEpoch:0,loading:false,uploading:false,downloading:false,jobId:null,coverage:null,performance:null,attempts:new Set(),autoBlocked:false,noteDirty:false,hover:null,study:null,studySerial:0,studyKey:null};
let chart,candles,volume,markerApi,aborter,toastTimer,priceLines=[];
const node=(tag,text,cls)=>{const e=document.createElement(tag);if(text!=null)e.textContent=text;if(cls)e.className=cls;return e;};
const money=n=>n==null||!Number.isFinite(+n)?'미확보':Number(n).toLocaleString('en-US',{maximumFractionDigits:2});
const dirLabel=d=>d==='Short'?'숏':d==='Long'?'롱':'방향 미확보';
function date(t,full=false){return t==null?'—':new Date((t+(S.zone==='KST'?32400:0))*1000).toISOString().slice(full?0:5,full?19:16).replace('T',' ');}
function toast(t){$('toast').textContent=t;$('toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').hidden=true,7500);}
function error(e){if(e.name==='AbortError')return;console.error(e);toast(e.message||String(e));}
function preference(k,f){try{return localStorage.getItem(k)??f;}catch{return f;}}
function savePreference(k,v){try{localStorage.setItem(k,v);}catch{}}
async function api(path,opts={}){const headers={...opts.headers};if(opts.method&&opts.method!=='GET')headers['X-AOA-Token']=S.token;const r=await fetch('/api/'+path,{...opts,headers});const d=await r.json();if(!r.ok)throw Error(d.error||r.statusText);return d;}
const post=(path,body)=>api(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
function busy(v){S.loading=v;$('loading').hidden=!v;}
function initChart(){
  const L=window.LightweightCharts;if(!L)throw Error('차트 라이브러리 미확보. start_windows.bat를 다시 실행하세요.');
  chart=L.createChart($('chart'),{autoSize:true,layout:{background:{type:L.ColorType.Solid,color:'#fff'},textColor:'#798599',fontSize:11,attributionLogo:true,panes:{separatorColor:'#e8edf4',enableResize:true}},grid:{vertLines:{color:'#f0f3f7'},horzLines:{color:'#edf1f6'}},rightPriceScale:{borderColor:'#e4eaf2'},timeScale:{timeVisible:true,secondsVisible:false,borderColor:'#e4eaf2',rightOffset:9,barSpacing:7},crosshair:{mode:L.CrosshairMode.Normal},localization:{locale:'en-US',timeFormatter:t=>date(t,true)}});
  candles=chart.addSeries(L.CandlestickSeries,{upColor:'#18a88a',downColor:'#e45260',borderVisible:false,wickUpColor:'#18a88a',wickDownColor:'#e45260',priceLineVisible:false,lastValueVisible:true});
  volume=chart.addSeries(L.HistogramSeries,{priceFormat:{type:'volume'},priceLineVisible:false,lastValueVisible:false},1);chart.panes()[1].setHeight(110);markerApi=L.createSeriesMarkers(candles,[],{autoScale:true});
  chart.subscribeCrosshairMove(p=>{
    const card=$('hoverCard');if(!p.time||!p.point||p.point.x<0||p.point.y<0){card.hidden=true;S.hover=null;return;}
    const i=S.visible.findIndex(x=>x.time===p.time),b=S.visible[i];if(!isBar(b)){card.hidden=true;S.hover=null;$('ohlcv').textContent=`${date(p.time)} · 실제 캔들 미확보`;return;}
    const m=candleMetrics(b,S.visible[i-1],TF[S.tf]),rv=relativeVolume(S.visible,i);S.hover={time:b.time,...m};
    $('ohlcv').textContent=`${date(b.time)} ${S.zone} · O ${money(b.open)} H ${money(b.high)} L ${money(b.low)} C ${money(b.close)} · 봉 ${pct(m.bodyPct)} · 전봉 ${pct(m.previousPct)} · 고저폭 ${pct(m.rangePct)} · 거래량 ${money(b.volume)} · RV20 ${rv==null?'—':rv.toFixed(2)+'배'}`;
    card.textContent=`${date(b.time,true)} ${S.zone}\n봉 등락률 ${pct(m.bodyPct)}\n전봉 대비 ${pct(m.previousPct)}\n고저폭/시가 ${pct(m.rangePct)}\n거래량 ${money(b.volume)} · RV20 ${rv==null?'—':rv.toFixed(2)+'배'}\n완성 봉의 최종값`;card.hidden=false;
    const rect=$('chart').getBoundingClientRect();card.style.left=Math.max(4,Math.min(p.point.x+16,rect.width-card.offsetWidth-8))+'px';card.style.top=Math.max(4,Math.min(p.point.y+16,rect.height-card.offsetHeight-8))+'px';
  });
  chart.subscribeClick(p=>{if(!p.time||S.loading)return;const hits=allowedEvents().filter(e=>bucket(eventTime(e),S.tf)===p.time);if(hits.length){const i=hits.findIndex(e=>e.id===S.selected);selectEvent(hits[(i+1)%hits.length],false).catch(error);}});updateZone();
}
function eventTime(e){return S.cutoff==null&&$('endpoint').value==='last'&&e.last_observed?e.end_time:e.time;}
function allowedEvents(){return visibleStudyEvents(S.events,{minQty:Math.max(0,Number($('minQty').value||0))*1e6,selected:S.selected,cutoff:S.cutoff,increases:$('increases').checked,reductions:$('reductions').checked});}
function updateZone(){chart.applyOptions({localization:{timeFormatter:t=>date(t,true)}});chart.timeScale().applyOptions({tickMarkFormatter:(t,type)=>{const d=date(t,true);return S.tf==='1d'||[0,1,2].includes(type)?d.slice(5,10):d.slice(11,16);}});}
function renderReferences(){for(const x of priceLines)candles.removePriceLine(x);priceLines=[];if(S.cutoff!=null||!$('referenceLines').checked)return;const e=S.events.find(e=>e.id===S.selected);if(!e)return;for(const [p,title,color] of [[e.price,'BitMEX 체결 (대체시장과 다름)','#c98916'],[e.basis_before,'BitMEX 직전 평균단가','#718297']])if(Number.isFinite(p)&&p>0)priceLines.push(candles.createPriceLine({price:p,color,lineWidth:1,lineStyle:2,axisLabelVisible:true,title}));}
function renderMarkers(){
  const selected=allowedEvents();const out=studyMarkers(selected,S.visible,S.tf,{legacy:$('legacy').checked,cutoff:S.cutoff,selected:S.selected,endpoint:$('endpoint').value,allEvents:S.events});const selectedEvent=S.events.find(e=>e.id===S.selected);
  const sl=seedLabel(selectedEvent,S.cutoff,$('seedMode')?.value||'initial');
  if(sl){const gi=out.groups.findIndex(g=>g.items.some(e=>e.id===S.selected));const mark=out.markers.find(m=>m.id==='g'+gi);if(mark)mark.text+=' · '+(out.groups[gi].items.length>1?'선택 주문 ':'')+sl;}
  const resultMark=finalResultMarker(S.performance,S.visible,S.tf,S.cutoff);if(resultMark)out.markers.push(resultMark);out.markers.sort((a,b)=>a.time-b.time);markerApi.setMarkers(out.markers);S.markerGroups=out.groups;
  const missing=S.visible.filter(b=>!isBar(b)).length,d=markerDiagnostics(selected,S.visible,S.tf,S.cutoff);
  $('coverage').textContent=`${S.visible.filter(isBar).length.toLocaleString()}개 완성 ${S.tf}봉 · 누락/불완전 ${missing.toLocaleString()}봉 · 원본 보간 없음${out.truncated?' · 마커 '+out.truncated+'개 생략':''}${S.cutoff!=null?(outcomeAvailable(S.performance,S.cutoff)?' · 복기: 종료 포지션 성과 공개':' · 복기: 미래 봉·최종 성과 숨김'):''}`;
  $('markerStatus').textContent=`차트 대상 ${selected.length}주문 · 화면 밖 ${d.outside} · 누락 봉 ${d.gap} · 필터 제외 ${knownEvents(S.events,S.cutoff).length-selected.length}. 첫 진입·마지막 관측 감량·선택 주문은 수량 필터 보호.`;
  renderReferences();
}
function safeFit(){const b=validBars(S.visible);if(!b.length)return;if(b.length===1){const i=S.visible.indexOf(b[0]);chart.timeScale().setVisibleLogicalRange({from:i-10,to:i+10});}else chart.timeScale().setVisibleRange({from:b[0].time,to:b.at(-1).time});}
function followReplay(){if(S.visible.some(isBar))chart.timeScale().setVisibleLogicalRange({from:Math.max(-3,S.visible.length-100),to:S.visible.length+8});}
function renderChart(fit=false){S.visible=completeAt(S.bars,S.tf,S.cutoff);$('hoverCard').hidden=true;S.hover=null;markerApi.setMarkers([]);candles.setData(S.visible.map(b=>isBar(b)?{time:b.time,open:b.open,high:b.high,low:b.low,close:b.close}:{time:b.time}));volume.setData(S.visible.map(b=>b.volume==null?{time:b.time}:{time:b.time,value:b.volume,color:b.close>=b.open?'#18a88a66':'#e4526066'}));renderMarkers();if(fit)safeFit();}
async function refreshStatus(){const d=await api('status');S.token=d.token;$('dbStatus').textContent=`v${d.version} · 주문 ${d.orders.toLocaleString()}건`;$('empty').hidden=d.orders>0;$('versionWarning').hidden=d.version===UI_VERSION;if(d.version!==UI_VERSION)$('versionWarning').textContent=`앱 화면 ${UI_VERSION} / 실행 서버 ${d.version}: 버전이 다릅니다. 옛 실행 창을 종료하고 최신 폴더에서 다시 시작하세요.`;return d;}
function stopPlaying(){S.playing=false;S.playEpoch++;clearTimeout(S.timer);S.timer=null;$('play').textContent='▶ 재생';}
function resetReplay(){stopPlaying();S.cutoff=null;S.replayIndex=-1;S.studyKey=null;$('replayEnabled').checked=false;$('replayTime').textContent='꺼짐';for(const id of ['result','minQty','legacy','endpoint','export','notesTab','referenceLines'])$(id).disabled=false;renderEvents();renderStats();renderEpisodes();drawDetail(S.events.find(e=>e.id===S.selected));}
function clearView(){S.viewRequest++;S.request++;S.studySerial++;aborter?.abort();resetReplay();Object.assign(S,{episode:null,events:[],bars:[],loadedTf:null,coverage:null,performance:null,selected:null,anchor:null,study:null,studyKey:null,noteDirty:false});busy(false);renderChart();renderStats();renderEvents();drawDetail(null);renderStudy($('studyPanel'),null,showEvidence);$('chartTitle').textContent='조건에 맞는 포지션 없음';$('chartRange').textContent='';$('eventBanner').textContent='연도·방향·검색 조건을 확인하세요.';$('marketStatus').textContent='포지션을 먼저 선택하세요.';}
async function loadEpisodes(reselect=false){const serial=++S.listRequest;const p=new URLSearchParams({symbol:$('symbol').value,year:$('year').value,year_mode:$('carry').checked?'overlap':'entry',direction:$('direction').value,result:S.cutoff==null?$('result').value:'',search:$('search').value});const rows=await api('episodes?'+p);if(serial!==S.listRequest)return;S.episodes=rows;renderEpisodes();if(reselect){if(rows.length)await selectEpisode(rows[0]);else clearView();}}
function renderEpisodes(){
  $('episodeCount').textContent=S.episodes.length.toLocaleString();$('episodeList').replaceChildren();if(!S.episodes.length)$('episodeList').append(node('p','조건에 맞는 포지션이 없습니다.','hint'));
  for(const ep of S.episodes){const b=node('button',null,'episode-item'+(S.episode?.id===ep.id?' selected':''));b.dataset.episode=ep.id;const r=node('div',null,'row');r.append(node('strong','#'+ep.id),node('span',(ep.carried?'이월 · ':'')+(ep.direction||'미확보'),'badge '+(ep.direction||'').toLowerCase()));b.append(r,node('small',date(ep.start,true)+(S.cutoff==null?' · '+ep.count+'주문':'')));if(S.cutoff==null&&ep.pnl_btc!=null)b.append(node('small',`${ep.pnl_btc>0?'+':''}${ep.pnl_btc.toFixed(3)} BTC`,ep.pnl_btc>=0?'positive':'negative'));if(S.cutoff==null&&(ep.net_return_pct!=null||ep.net_return_estimate_pct!=null))b.append(node('small',returnText(ep)+(ep.net_return_pct==null?' · 참고':' · 순손익률'),'episode-return'));if(S.cutoff==null&&ep.seed_return_pct!=null)b.append(node('small','초기 시드 '+seedReturnText(ep),'seed-return'));b.onclick=()=>selectEpisode(ep).catch(error);$('episodeList').append(b);}
}
function renderStats(){
  $('positionOutcome').hidden=!S.episode;if(S.episode)renderOutcome($('positionOutcome'),S.performance,S.cutoff,()=>{$('importDialog').showModal();});
  $('episodeStats').replaceChildren();$('performanceNote').textContent='';$('marginBox').hidden=S.cutoff!=null||!S.episode;if(!S.episode)return;const ep=S.episode,p=S.performance;
  const vals=S.cutoff!=null&&!outcomeAvailable(p,S.cutoff)?[['방향',dirLabel(ep.direction)],['복기 모드','최종 성과 숨김']]:[['방향',dirLabel(ep.direction)],['관측 주문',S.events.length+'건'],['관측 최대 보유',fmtQty(ep.max_observed_qty)],['원장 순손익',p?.net_pnl_btc==null?'미확보':p.net_pnl_btc.toFixed(3)+' BTC'],['감량 가격성과*',pct(p?.price_return_pct,3)],['증거금 참고 ROI',pct(p?.reference_roi_pct,3)]];
  for(const [label,value] of vals){const b=node('div',null,'stat');b.append(node('small',label),node('strong',value));$('episodeStats').append(b);}if(outcomeAvailable(p,S.cutoff)){$('performanceNote').textContent=`* 감량 근거 ${p.covered_exit_orders}/${p.observed_exit_orders}주문, 수량 ${pct(p.coverage_pct,1)}. ${p.note}`;$('marginInput').value=p.reference_margin_btc??'';}
}
async function selectEpisode(ep){
  if(S.noteDirty&&!confirm('저장하지 않은 연구 메모가 있습니다. 이동할까요?'))return;
  const serial=++S.viewRequest;S.request++;S.studySerial++;aborter?.abort();resetReplay();Object.assign(S,{episode:ep,selected:null,events:[],bars:[],loadedTf:null,coverage:null,performance:null,noteDirty:false,anchor:ep.focus,study:null,studyKey:null});busy(true);renderChart();renderEpisodes();renderEvents();renderStats();drawDetail(null);renderStudy($('studyPanel'),null,showEvidence);$('detailTitle').textContent='포지션 #'+ep.id;
  try{const [events,note,p]=await Promise.all([api('events?episode='+encodeURIComponent(ep.id)),api('note?episode='+encodeURIComponent(ep.id)),api('performance?episode='+encodeURIComponent(ep.id))]);if(serial!==S.viewRequest)return;S.events=events;S.performance=p;$('noteText').value=note.text;$('noteTags').value=note.tags;$('noteState').textContent=note.updated?'마지막 저장 '+note.updated:'';
    const first=events.find(e=>e.role==='Entry'&&e.time>=ep.focus)||events.find(e=>e.time>=ep.focus)||firstEvent(events);S.selected=first?.id||null;S.anchor=first?.time??ep.focus;
    renderEvents();renderStats();drawDetail(first);await loadWindow(S.anchor,episodeRange(ep,S.tf,events));if(serial===S.viewRequest)await loadStudy(true);
  }finally{if(serial===S.viewRequest&&S.loadedTf===null)busy(false);}
}
async function loadWindow(center,range=null,{preserveReplay=false,noAuto=false}={}){
  if(!S.episode?.pair){S.bars=[];S.coverage=null;renderChart();toast('대체시장 매핑이 없습니다.');return;}
  const serial=++S.request,view=S.viewRequest,pair=S.episode.pair,tf=S.tf;aborter?.abort();aborter=new AbortController();busy(true);S.anchor=center;
  let [start,end]=range||windowRange(center,tf,S.episode.year_floor);end=Math.min(end,Math.floor(Date.now()/60000)*60);start=Math.min(start,end-TF[tf]);S.start=start;S.end=end;$('gotoDate').value=localDateInput(center,S.zone);
  try{const p=new URLSearchParams({pair,tf,start:Math.floor(start),end:Math.floor(end)});const d=await api('candles?'+p,{signal:aborter.signal});if(serial!==S.request||view!==S.viewRequest||tf!==S.tf)return;
    S.start=d.start;S.end=d.end;S.bars=d.bars;S.loadedTf=tf;S.coverage=d.coverage;$('empty').hidden=true;$('chartTitle').textContent=`${pair} · ${tf} · #${S.episode.id} ${S.episode.direction}`;$('chartRange').textContent=`${date(S.start)} → ${date(S.end)} ${S.zone}`;
    if(preserveReplay&&S.cutoff!=null){S.replayIndex=indexAtCutoff(S.bars,S.tf,S.cutoff);syncReplay();renderChart();followReplay();}else{S.replayIndex=-1;syncReplay();renderChart(true);}
    if(!d.complete_bars)$('ohlcv').textContent='실제 완성 봉 미확보 · 아래 보완 상태를 확인하세요.';showMarketSummary();if(!noAuto)queueMicrotask(maybeAutoFill);
  }catch(e){if(e.name!=='AbortError')throw e;}finally{if(serial===S.request)busy(false);}
}
function showMarketSummary(){if(S.downloading)return;const c=S.coverage;if(!c)return;$('marketStatus').textContent=c.missing_minutes?`현재 ${S.tf} 구간: 누락 ${c.missing_minutes.toLocaleString()}분, 충돌 ${c.conflict_minutes}분. ${S.autoBlocked?'자동 보완 중단: 다시 보완 버튼을 누르세요.':$('autoFill').checked?'없는 실제 분봉을 자동 보완합니다.':'자동 보완 꺼짐'}`:`현재 구간 ${c.valid_minutes.toLocaleString()}분 연속 확보 · 보간 없음`;}
async function pollJob(id,market=false){while(true){const j=await api('job');if(id&&j.id!==id)throw Error('다른 작업으로 변경되었습니다.');$('jobStatus').textContent=JSON.stringify(j,null,2);if(j.progress!=null)$('jobProgress').value=j.progress;if(market)$('marketStatus').textContent=j.message||'보완 중';if(['error','cancelled'].includes(j.state))throw Error(j.message);if(j.state==='done')return j.report;await new Promise(r=>setTimeout(r,350));}}
function maybeAutoFill(){if(!$('autoFill').checked||S.autoBlocked||S.uploading||S.downloading||!S.episode?.pair||!S.coverage?.fetchable_minutes)return;const key=`${S.episode.pair}:${S.start}:${S.end}`;if(!S.attempts.has(key))repairWindow(false).catch(error);}
async function repairWindow(manual=true,contextOnly=false){
  if(!S.episode?.pair)return toast('먼저 포지션을 선택하세요.');if(S.uploading||S.downloading)return toast('현재 작업 완료/중단 후 시도하세요.');
  const request=S.request,view=S.viewRequest,pair=S.episode.pair,range=[S.start,S.end],anchor=S.anchor;let target=range;
  if(contextOnly){const e=S.events.find(e=>e.id===S.selected);if(!e)return toast('해설할 주문을 선택하세요.');const end=Math.floor(e.time/60)*60;target=[end-2881*60,end];}
  if(manual)S.autoBlocked=false;S.attempts.add(`${pair}:${range.join(':')}`);S.downloading=true;stopPlaying();$('cancelJob').hidden=false;
  for(const id of ['repairWindow','repairContext','fetchMarket','files'])$(id).disabled=true;
  try{const r=await post('fetch',{pair,start:target[0],end:target[1]});S.jobId=r.job_id;const report=await pollJob(r.job_id,true);await refreshStatus();
    if(request===S.request&&view===S.viewRequest){await loadWindow(anchor,range,{preserveReplay:S.cutoff!=null,noAuto:true});await loadStudy(true);}
    $('marketStatus').textContent=`실제 ${report.received.toLocaleString()}분 보완 · 남은 공백 ${report.remaining_missing_minutes}분 · 충돌 ${report.conflict_minutes}분${report.complete?' · 연속 확보':' · 원본 공백/충돌은 만들지 않음'}`;
  }catch(e){S.autoBlocked=true;$('marketStatus').textContent=e.message;toast(e.message);}finally{S.downloading=false;S.jobId=null;$('cancelJob').hidden=true;for(const id of ['repairWindow','repairContext','fetchMarket','files'])$(id).disabled=false;if(request!==S.request)queueMicrotask(maybeAutoFill);}
}
function renderEvents(){
  const known=knownEvents(S.events,S.cutoff),allowed=new Set(allowedEvents().map(e=>e.id));$('eventCount').textContent=S.cutoff==null?`${known.length}주문 · 차트 ${allowed.size}`:`현재까지 ${known.length}주문`;$('eventList').replaceChildren();
  for(const e of known){const a=safeAction(e,S.cutoff),b=node('button',null,'event-item'+(e.id===S.selected?' selected':'')+(!allowed.has(e.id)?' filtered':''));b.dataset.event=e.id;const top=node('div',null,'event-top');top.append(node('strong',`${dirLabel(e.direction)} ${ACTIONS[a]?.label||a}`),node('span',completedOrder(e,S.cutoff)?fmtQty(e.qty):'분할체결 중'));
    b.append(top,node('span',`${date(eventTime(e),true)} ${S.zone}${e.first_price?' · $'+money(e.first_price):''}${!allowed.has(e.id)?' · 차트 필터 제외':''}`,'event-sub'));const sl=seedLabel(e,S.cutoff,$('seedMode')?.value||'initial');if(sl)b.append(node('small',sl,'seed-note'));b.onclick=()=>selectEvent(e).catch(error);$('eventList').append(b);}
}
function detailRow(k,v){const r=node('div',null,'detail-row');r.append(node('span',k),node('span',v));return r;}
function drawDetail(e){
  if($('seedPanel'))renderSizing($('seedPanel'),e,S.cutoff,$('seedMode')?.value||'initial',()=>$('importDialog').showModal());
  const root=$('eventDetail');root.replaceChildren();if(!e){root.append(node('p','주문을 클릭하면 해당 봉으로 이동합니다.','hint'));return;}
  root.append(node('h3',`${dirLabel(e.direction)} · ${e.role==='Entry'?'진입/추가':'감량/종료'}`),detailRow('첫 체결',date(e.time,true)+' '+S.zone),detailRow('첫 체결가',money(e.first_price)),detailRow('첫 체결 전 보유',fmtQty(e.position_before)),detailRow('첫 체결 전 평균단가',money(e.basis_before)));
  if(completedOrder(e,S.cutoff)){for(const [k,v] of [['마지막 체결',e.last_observed?date(e.end_time,true):'미확보'],['주문 총수량',fmtQty(e.qty)],['산술평균',money(e.avg_price)],['역수가중평균',money(e.inverse_price)],['종료 후 보유',fmtQty(e.position_after)],['스톱 발동가격',e.stop_trigger?money(e.stop_trigger):'미기록'],['주문유형',e.order_type||'미확보']])root.append(detailRow(k,v));}
  else root.append(node('p','이 주문의 최종 집계값은 아직 숨겨져 있습니다. 아래 해설은 첫 체결 이전 정보만 사용합니다.','warning'));
  if(S.cutoff==null){for(const w of e.warnings||[])root.append(node('p',w,'warning'));const d=node('details');d.append(node('summary','원본 연결'),node('pre',JSON.stringify({order_id:e.order_id,sources:e.sources},null,2)));root.append(d);}
}
async function loadStudy(force=false){
  if(!S.episode)return;const known=knownEvents(S.events,S.cutoff),selected=known.find(e=>e.id===S.selected)||null;
  const key=[S.episode.id,S.selected,S.cutoff==null,known.length,selected&&completedOrder(selected,S.cutoff)].join('|');if(!force&&key===S.studyKey)return;
  const serial=++S.studySerial,view=S.viewRequest;S.studyKey=key;S.study=null;const p=new URLSearchParams({episode:S.episode.id});if(selected)p.set('event',selected.id);if(S.cutoff!=null)p.set('cutoff',S.cutoff);
  $('studyPanel').textContent='사전 캔들·거래량·주문 흐름 해설 계산 중…';
  try{const d=await api('study?'+p);if(serial!==S.studySerial||view!==S.viewRequest)return;S.study=d;renderStudy($('studyPanel'),d,showEvidence);const e=d.event;
    $('eventBanner').textContent=e?`${date(e.time,true)} ${S.zone} · ${e.title} | ${e.summary}`:'아직 공개된 주문이 없습니다. 진입 봉에 도달하면 마커와 해설이 나옵니다.';
  }catch(e){if(serial!==S.studySerial||view!==S.viewRequest)return;S.studyKey=null;$('studyPanel').textContent='해설 계산 실패: '+e.message;$('eventBanner').textContent='해설 계산 실패. 해설 새로고침으로 재시도하세요.';error(e);}
}
async function showEvidence(f){
  if(S.loading)return;stopPlaying();const center=(f.start+f.end)/2,tf=f.tf||S.tf;setTF(tf);let range=[f.start-10*TF[tf],f.end+5*TF[tf]];if(S.cutoff!=null)range[1]=Math.min(range[1],S.cutoff);if(range[1]<=range[0])return;
  try{await loadWindow(center,range,{preserveReplay:S.cutoff!=null});$('eventBanner').textContent='근거 구간: '+f.text+' · 첫 진입으로 버튼으로 돌아갈 수 있습니다.';}catch(e){error(e);}
}
async function selectEvent(e,jump=true){
  if(!S.events.some(x=>x.id===e.id)||S.cutoff!=null&&e.first_us>=S.cutoff*1e6)return;const view=S.viewRequest;S.selected=e.id;S.anchor=eventTime(e);renderEvents();drawDetail(e);renderMarkers();
  if(jump){const t=eventTime(e);if(t<S.start||t>=S.end)await loadWindow(t,null,{preserveReplay:S.cutoff!=null});if(view!==S.viewRequest||S.selected!==e.id)return;const from=bucket(t,S.tf)-35*TF[S.tf],to=S.cutoff==null?bucket(t,S.tf)+65*TF[S.tf]:Math.min(bucket(t,S.tf)+65*TF[S.tf],S.cutoff-TF[S.tf]);if(to>from&&S.visible.some(isBar))chart.timeScale().setVisibleRange({from,to});$('gotoDate').value=localDateInput(t,S.zone);}
  await loadStudy();[...$('eventList').children].find(x=>x.dataset.event===e.id)?.scrollIntoView({block:'nearest'});
}
function syncReplay(){const b=validBars(S.bars);$('replaySlider').max=Math.max(0,b.length-1);$('replaySlider').value=Math.max(0,S.replayIndex);$('replaySlider').disabled=!b.length;if(S.cutoff!=null)$('replayTime').textContent=date(S.cutoff,true)+' '+S.zone;}
function applyReplay(follow=true){
  if(!$('replayEnabled').checked){resetReplay();renderChart();loadStudy().catch(error);return;}if(S.cutoff==null)return;$('endpoint').value='first';for(const id of ['result','minQty','legacy','endpoint','export','notesTab','referenceLines'])$(id).disabled=true;
  $('notesPanel').hidden=true;$('timelinePanel').hidden=false;$('timelineTab').classList.add('active');$('notesTab').classList.remove('active');if(S.events.find(e=>e.id===S.selected)?.first_us>=S.cutoff*1e6)S.selected=null;
  syncReplay();$('ohlcv').textContent=`복기 시각 ${date(S.cutoff,true)} ${S.zone} · 이 시각 전에 완성된 봉만 표시`;renderChart();renderEvents();renderStats();renderEpisodes();drawDetail(S.events.find(e=>e.id===S.selected));if(follow)followReplay();loadStudy().catch(error);
}
function replayReady(){if(S.loading||S.uploading||S.downloading){toast('현재 데이터 작업을 마친 뒤 재생하세요.');return false;}if(!S.episode||S.loadedTf!==S.tf||!S.bars.some(isBar)){toast('재생할 실제 완성 봉이 없습니다. 시세를 보완하세요.');return false;}return true;}
function beginReplay(){
  stopPlaying();if(!replayReady()){$('replayEnabled').checked=S.cutoff!=null;return false;}const anchor=S.anchor??S.episode.focus;
  if(anchor<S.start||anchor>=S.end){toast('선택 주문이 현재 구간 밖입니다. 첫 진입으로 이동하세요.');return false;}
  const r=replayStart(S.bars,S.tf,anchor,3);if(r.index<0){resetReplay();toast(r.warning);return false;}S.replayIndex=r.index;S.cutoff=r.cutoff;$('replayEnabled').checked=true;$('replayNotice').textContent=r.warning||`${date(anchor,true)}의 3봉 전부터 · 주문 봉에서 자동 멈춤 선택 가능`;applyReplay();return true;
}
async function nextStep(){
  if(!replayReady())return false;if(S.cutoff==null&&!beginReplay())return false;const old=S.cutoff;let next=nextValidStep(S.bars,S.tf,S.replayIndex);
  if(!next&&S.episode&&old<S.episode.end+3*TF[S.tf]){const view=S.viewRequest,tf=S.tf;await loadWindow(old,[old-(tf==='1d'?30:60)*TF[tf],Math.min(old+(tf==='1d'?90:240)*TF[tf],S.episode.end+5*TF[tf])],{preserveReplay:true});if(view!==S.viewRequest||tf!==S.tf||S.cutoff==null)return false;next=nextValidStep(S.bars,S.tf,S.replayIndex);}
  if(!next){stopPlaying();$('replayNotice').textContent='현재 확보한 재생 구간 끝. 누락 시세를 확인하세요.';return false;}S.replayIndex=next.index;S.cutoff=next.cutoff;
  const hits=newlyRevealed(S.events,old,S.cutoff);if(hits.length)S.selected=hits.at(-1).id;
  if(next.skipped)$('replayNotice').textContent=`실제 ${next.skipped}개 ${S.tf} 구간 누락을 건너뜀. 누락 중 주문은 정확한 캔들 마커를 만들지 않습니다.`;
  applyReplay();if(hits.length&&$('pauseOnEvent').checked){stopPlaying();$('replayNotice').textContent=`새 주문 ${hits.length}건 · ${date(hits.at(-1).time,true)}에서 멈춤. 오른쪽 해설 확인 후 재생.`;}return true;
}
function startPlaying(){if(!replayReady())return;if(S.cutoff==null&&!beginReplay())return;S.playing=true;const epoch=++S.playEpoch;$('play').textContent='Ⅱ 일시정지';const tick=async()=>{if(!S.playing||S.playEpoch!==epoch)return;try{const ok=await nextStep();if(epoch!==S.playEpoch)return;if(ok&&S.playing)S.timer=setTimeout(tick,1000/Number($('speed').value));else stopPlaying();}catch(e){if(epoch===S.playEpoch)stopPlaying();error(e);}};S.timer=setTimeout(tick,1000/Number($('speed').value));}
async function importFiles(fileList){
  if(S.uploading||S.downloading)return toast('현재 작업을 먼저 완료/중단하세요.');const files=Array.from(fileList);if(!files.length)return;S.uploading=true;stopPlaying();$('files').disabled=true;$('fetchMarket').disabled=true;
  try{for(const f of files){if(f.size>512*1024*1024)throw Error('파일당 512MB 제한');$('jobStatus').textContent=f.name+' 로컬 전송 중…';const r=await api('import?name='+encodeURIComponent(f.name),{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:f});S.jobId=r.job_id;await pollJob(r.job_id);}
    $('jobProgress').value=100;S.attempts.clear();await refreshStatus();await loadEpisodes();const ep=S.episodes.find(e=>e.id===S.episode?.id)||S.episodes[0];if(ep)await selectEpisode(ep);else clearView();toast('가져오기 완료. 기존 메모는 유지됩니다.');
  }catch(e){$('jobStatus').textContent='실패: '+e.message;error(e);}finally{S.uploading=false;S.jobId=null;$('files').disabled=false;$('files').value='';$('fetchMarket').disabled=false;maybeAutoFill();}
}
async function capture(){if(!S.visible.some(isBar))return toast('실제 캔들이 없습니다.');const source=chart.takeScreenshot(true,false),canvas=document.createElement('canvas');canvas.width=source.width;canvas.height=source.height+80;const ctx=canvas.getContext('2d');ctx.fillStyle='#fff';ctx.fillRect(0,0,canvas.width,canvas.height);ctx.fillStyle='#17263a';ctx.font='bold 14px sans-serif';ctx.fillText($('chartTitle').textContent+' · '+S.zone+(S.cutoff!=null?' · REPLAY '+date(S.cutoff):''),14,25);ctx.drawImage(source,0,40);ctx.font='10px sans-serif';ctx.fillText('Binance spot proxy / BitMEX recorded orders / assumed UTC / no interpolation / research hypotheses only',14,canvas.height-14);canvas.toBlob(blob=>{if(!blob)return;const url=URL.createObjectURL(blob),a=node('a');a.href=url;a.download=`AOA_${S.episode.id}_${S.tf}.png`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});}
async function changeFilters(){S.viewRequest++;S.request++;aborter?.abort();stopPlaying();resetReplay();await loadEpisodes(true);}
function setTF(tf){S.tf=tf;for(const b of $('tfButtons').children)b.classList.toggle('active',b.dataset.tf===tf);updateZone();}
function initSeedControls(){
 const style=document.createElement('link');style.rel='stylesheet';style.href='/seed.css?v=040';document.head.append(style);
 const controls=node('div',null,'seed-mode');controls.append(node('label','주문 비중 기준'));
 const select=node('select');select.id='seedMode';
 for(const [value,text] of [['initial','최초 진입 시드 고정'],['current','각 주문 직전 시드']]){const o=node('option',text);o.value=value;select.append(o);}
 select.value=preference('aoa.seedMode','initial');if(!select.value)select.value='initial';controls.append(select);
 const connect=node('button','잔고 연결','small');connect.id='seedImport';connect.onclick=()=>$('importDialog').showModal();controls.append(connect);$('positionOutcome').after(controls);
 const panel=node('section');panel.id='seedPanel';$('eventDetail').after(panel);
 select.onchange=()=>{savePreference('aoa.seedMode',select.value);renderEvents();drawDetail(S.events.find(e=>e.id===S.selected));renderMarkers();};
}
function bind(){
 initSeedControls();
  $('autoFill').checked=preference('aoa.autoFill','1')==='1';
  for(const id of ['importOpen','emptyImport'])$(id).onclick=()=>$('importDialog').showModal();$('closeImport').onclick=()=>$('importDialog').close();$('closeQuality').onclick=()=>$('qualityDialog').close();
  $('qualityOpen').onclick=async()=>{try{$('qualityContent').textContent=JSON.stringify({status:await api('status'),current_range:S.coverage,markers:markerDiagnostics(allowedEvents(),S.visible,S.tf,S.cutoff),study:S.study,issues:await api('issues')},(k,v)=>k==='token'?undefined:v,2);$('qualityDialog').showModal();}catch(e){error(e);}};
  for(const id of ['symbol','year','direction','result','carry'])$(id).onchange=()=>changeFilters().catch(error);let debounce;$('search').oninput=()=>{clearTimeout(debounce);debounce=setTimeout(()=>changeFilters().catch(error),200);};
  for(const [id,d] of [['prevEpisode',-1],['nextEpisode',1]])$(id).onclick=()=>{const i=S.episodes.findIndex(e=>e.id===S.episode?.id),ep=S.episodes[i+d];if(ep)selectEpisode(ep).catch(error);};
  for(const [id,d] of [['prevEvent',-1],['nextEvent',1]])$(id).onclick=()=>{const rows=knownEvents(S.events,S.cutoff),i=rows.findIndex(e=>e.id===S.selected),e=rows[i+d];if(e)selectEvent(e).catch(error);};
  $('tfButtons').onclick=async e=>{const b=e.target.closest('[data-tf]');if(!b||b.dataset.tf===S.tf)return;stopPlaying();const cursor=S.cutoff,center=cursor??S.anchor??S.episode?.focus;setTF(b.dataset.tf);try{if(center!=null){await loadWindow(center,null,{preserveReplay:cursor!=null});if(cursor!=null)applyReplay();}}catch(err){error(err);}};
  $('timezone').onchange=()=>{S.zone=$('timezone').value;updateZone();$('chartRange').textContent=`${date(S.start)} → ${date(S.end)} ${S.zone}`;if(S.anchor!=null)$('gotoDate').value=localDateInput(S.anchor,S.zone);syncReplay();renderEvents();renderEpisodes();drawDetail(S.events.find(e=>e.id===S.selected));loadStudy(true).catch(error);};
  $('jump').onclick=()=>{const t=parseDateInput($('gotoDate').value,S.zone);if(t==null)return toast('날짜를 입력하세요.');resetReplay();S.selected=null;loadWindow(t).then(()=>loadStudy()).catch(error);};
  $('entryFocus').onclick=()=>{if(!S.episode)return;resetReplay();const e=S.events.find(e=>e.role==='Entry'&&e.time>=S.episode.focus)||firstEvent(S.events);if(e)selectEvent(e).catch(error);};
  $('lastFocus').onclick=()=>{if(!S.episode)return;resetReplay();const e=S.events.filter(e=>e.role==='Exit').at(-1)||S.events.at(-1);if(e)selectEvent(e).catch(error);};
  for(const [id,d] of [['earlier',-1],['later',1]])$(id).onclick=()=>{if(!S.episode)return;resetReplay();S.selected=null;loadWindow((S.anchor??S.episode.focus)+d*(S.end-S.start)*.75).then(()=>loadStudy()).catch(error);};
  $('fullEpisode').onclick=async()=>{if(!S.episode)return;resetReplay();const ep=S.episode,a=Math.max(ep.start-3600,ep.year_floor||0),b=Math.min(ep.end+3600,a+179*86400),tf=Object.keys(TF).find(k=>(b-a)/TF[k]<=3500)||'1d';setTF(tf);try{await loadWindow(ep.focus,[a,b]);await loadStudy();if(ep.end+3600>b)toast('첫 179일을 표시합니다. 다음 구간으로 이어서 보세요.');}catch(e){error(e);}};
  $('fit').onclick=safeFit;$('screenshot').onclick=()=>capture().catch(error);
  // Apply numeric filters during input, not during blur between pointerdown/click.
  // A duplicate change must not replace the clicked timeline node and swallow its click.
  const filterIDs=['minQty','increases','reductions','legacy','endpoint','referenceLines'];
  const filterSignature=()=>JSON.stringify(filterIDs.map(id=>$(id).type==='checkbox'?$(id).checked:$(id).value));
  let appliedFilters=filterSignature();
  const applyFilters=()=>{const key=filterSignature();if(key===appliedFilters)return;appliedFilters=key;renderEvents();renderMarkers();};
  for(const id of filterIDs)$(id).onchange=applyFilters;$('minQty').oninput=applyFilters;
  $('replayEnabled').onchange=()=>{if($('replayEnabled').checked)beginReplay();else{resetReplay();renderChart(true);loadStudy(true).catch(error);}};$('replayStart').onclick=beginReplay;
  $('replaySlider').oninput=()=>{stopPlaying();if(!replayReady())return;if(S.cutoff==null&&!beginReplay())return;const b=validBars(S.bars),i=Math.min(Number($('replaySlider').value),b.length-1);if(i<0)return;S.replayIndex=i;S.cutoff=b[i].time+TF[S.tf];S.selected=knownEvents(S.events,S.cutoff).at(-1)?.id||null;applyReplay();};
  $('step').onclick=()=>{stopPlaying();nextStep().catch(error);};$('backStep').onclick=()=>{stopPlaying();if(!replayReady())return;if(S.cutoff==null&&!beginReplay())return;const b=validBars(S.bars),i=Math.max(0,S.replayIndex-1);if(!b[i]||b[i].time+TF[S.tf]>S.cutoff)return;S.replayIndex=i;S.cutoff=b[i].time+TF[S.tf];S.selected=knownEvents(S.events,S.cutoff).at(-1)?.id||null;applyReplay();};
  $('play').onclick=()=>S.playing?stopPlaying():startPlaying();$('speed').onchange=()=>{if(S.playing){stopPlaying();startPlaying();}};
  $('notesTab').onclick=()=>{$('notesPanel').hidden=false;$('timelinePanel').hidden=true;$('notesTab').classList.add('active');$('timelineTab').classList.remove('active');};$('timelineTab').onclick=()=>{$('notesPanel').hidden=true;$('timelinePanel').hidden=false;$('timelineTab').classList.add('active');$('notesTab').classList.remove('active');};
  for(const id of ['noteText','noteTags'])$(id).oninput=()=>S.noteDirty=true;
  $('saveNote').onclick=async()=>{if(!S.episode)return;try{await post('note',{episode:S.episode.id,text:$('noteText').value,tags:$('noteTags').value});S.noteDirty=false;$('noteState').textContent='이 PC에 저장했습니다.';}catch(e){error(e);}};
  async function margin(v){if(!S.episode||S.cutoff!=null)return;const id=S.episode.id,p=await post('reference-margin',{episode:id,btc:v});if(S.episode?.id===id){S.performance=p;renderStats();}}
  $('saveMargin').onclick=()=>margin($('marginInput').value).catch(error);$('clearMargin').onclick=()=>margin(null).catch(error);
  $('export').onclick=()=>{if(S.episode&&S.cutoff==null){const a=node('a');a.href='/api/export?episode='+encodeURIComponent(S.episode.id);a.download='aoa_episode.csv';a.click();}};
  $('studyRefresh').onclick=()=>loadStudy(true).catch(error);$('studyExport').onclick=()=>{if(!S.episode)return;const p=new URLSearchParams({episode:S.episode.id});if(S.selected)p.set('event',S.selected);if(S.cutoff!=null)p.set('cutoff',S.cutoff);const a=node('a');a.href='/api/study-export?'+p;a.download='AOA-event-study.json';a.click();};
  $('files').onchange=()=>importFiles($('files').files);$('dropzone').ondragover=e=>e.preventDefault();$('dropzone').ondrop=e=>{e.preventDefault();importFiles(e.dataTransfer.files);};
  $('autoFill').onchange=()=>{savePreference('aoa.autoFill',$('autoFill').checked?'1':'0');S.autoBlocked=false;showMarketSummary();maybeAutoFill();};
  $('repairWindow').onclick=()=>repairWindow(true).catch(error);$('fetchMarket').onclick=()=>repairWindow(true).catch(error);$('repairContext').onclick=()=>repairWindow(true,true).catch(error);
  $('cancelJob').onclick=()=>post('cancel-job',{job_id:S.jobId}).then(()=>{$('marketStatus').textContent='중단 요청됨: 기존 데이터 보존';}).catch(error);window.addEventListener('beforeunload',e=>{if(S.noteDirty){e.preventDefault();e.returnValue='';}});
}
async function boot(){initChart();bind();await refreshStatus();await loadEpisodes();if(S.episodes.length)await selectEpisode(S.episodes.find(e=>e.id==='3086')||S.episodes[0]);}
boot().catch(error);
window.AOAViewer={snapshot:()=>({episode:S.episode?.id,tf:S.tf,barCount:S.bars.filter(isBar).length,visibleBarCount:S.visible.filter(isBar).length,markerCount:S.markerGroups.length,cutoff:S.cutoff,anchor:S.anchor,start:S.start,end:S.end,replayIndex:S.replayIndex,playing:S.playing,hover:S.hover,coverage:S.coverage,performance:outcomeAvailable(S.performance,S.cutoff)?S.performance:null,selected:S.selected,study:S.study,loading:S.loading,version:UI_VERSION}),pointForBar:t=>{const b=S.visible.find(x=>x.time===t);if(!isBar(b))return null;return{x:chart.timeScale().timeToCoordinate(t),y:candles.priceToCoordinate((b.open+b.close)/2)};}};
