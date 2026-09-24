import {TF,ACTIONS,fmtQty,bucket,displayAction,buildMarkers,completeAt,relativeVolume,parseDateInput,localDateInput} from './core.mjs';
import {isBar,validBars,candleMetrics,pct,windowRange,replayStart as initialReplay,indexAtCutoff,nextValidStep} from './review-core.mjs';
const $=id=>document.getElementById(id);
const S={token:'',episodes:[],episode:null,events:[],bars:[],visible:[],tf:'5m',loadedTf:null,zone:'UTC',start:0,end:0,anchor:null,selected:null,cutoff:null,replayIndex:-1,request:0,listRequest:0,viewRequest:0,markerGroups:[],timer:null,playing:false,playEpoch:0,loading:false,uploading:false,downloading:false,jobId:null,coverage:null,performance:null,attempts:new Set(),autoBlocked:false,noteDirty:false,hover:null};
let chart,candles,volume,markerApi,aborter=null,toastTimer,priceLines=[];
const node=(tag,text,cls)=>{const e=document.createElement(tag);if(text!=null)e.textContent=text;if(cls)e.className=cls;return e;};
function toast(text){$('toast').textContent=text;$('toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').hidden=true,6500);}
function date(t,full=false){if(t==null)return '—';return new Date((t+(S.zone==='KST'?32400:0))*1000).toISOString().slice(full?0:5,full?19:16).replace('T',' ');}
const money=n=>n==null||!Number.isFinite(+n)?'미확보':Number(n).toLocaleString('en-US',{maximumFractionDigits:2});
const dirLabel=d=>d==='Short'?'숏':d==='Long'?'롱':'방향 미확보';
function preference(k,fallback){try{return localStorage.getItem(k)??fallback;}catch{return fallback;}}
function savePreference(k,v){try{localStorage.setItem(k,v);}catch{}}
async function api(path,opts={}){const headers={...opts.headers};if(opts.method&&opts.method!=='GET')headers['X-AOA-Token']=S.token;const r=await fetch('/api/'+path,{...opts,headers});const data=await r.json();if(!r.ok)throw Error(data.error||r.statusText);return data;}
const post=(path,body)=>api(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
function error(e){if(e.name==='AbortError')return;console.error(e);toast(e.message||String(e));}
function busy(v){S.loading=v;$('loading').hidden=!v;}
function initChart(){
  if(!window.LightweightCharts)throw Error('차트 라이브러리가 없습니다. start_windows.bat를 다시 실행하세요.');
  const L=window.LightweightCharts;
  chart=L.createChart($('chart'),{autoSize:true,layout:{background:{type:L.ColorType.Solid,color:'#ffffff'},textColor:'#798599',fontSize:11,attributionLogo:true,panes:{separatorColor:'#e8edf4',separatorHoverColor:'#dbe8e5',enableResize:true}},grid:{vertLines:{color:'#f0f3f7'},horzLines:{color:'#edf1f6'}},rightPriceScale:{borderColor:'#e4eaf2'},timeScale:{timeVisible:true,secondsVisible:false,borderColor:'#e4eaf2',rightOffset:9,barSpacing:7},crosshair:{mode:L.CrosshairMode.Normal},localization:{locale:'en-US',timeFormatter:t=>date(t,true)}});
  candles=chart.addSeries(L.CandlestickSeries,{upColor:'#18a88a',downColor:'#e45260',borderVisible:false,wickUpColor:'#18a88a',wickDownColor:'#e45260',priceLineVisible:false,lastValueVisible:true});
  volume=chart.addSeries(L.HistogramSeries,{priceFormat:{type:'volume'},priceLineVisible:false,lastValueVisible:false},1);
  chart.panes()[1].setHeight(110);markerApi=L.createSeriesMarkers(candles,[],{autoScale:true});
  chart.subscribeCrosshairMove(p=>{
    const card=$('hoverCard');
    if(!p.time||!p.point||p.point.x<0||p.point.y<0){card.hidden=true;S.hover=null;return;}
    const i=S.visible.findIndex(x=>x.time===p.time),b=S.visible[i];
    if(!isBar(b)){card.hidden=true;S.hover=null;$('ohlcv').textContent=`${date(p.time)} · 실제 캔들 미확보`;return;}
    const m=candleMetrics(b,S.visible[i-1],TF[S.tf]),rv=relativeVolume(S.visible,i);S.hover={time:b.time,...m};
    $('ohlcv').textContent=`${date(b.time)} ${S.zone} · O ${money(b.open)} H ${money(b.high)} L ${money(b.low)} C ${money(b.close)} · 봉 ${pct(m.bodyPct)} · 전봉 ${pct(m.previousPct)} · 고저폭 ${pct(m.rangePct)} · 거래량 ${money(b.volume)} · RV20 ${rv==null?'—':rv.toFixed(2)+'배'}`;
    card.textContent=`${date(b.time,true)} ${S.zone}\n봉 등락률 ${pct(m.bodyPct)}\n전봉 대비 ${pct(m.previousPct)}\n고저폭/시가 ${pct(m.rangePct)}\n거래량 ${money(b.volume)} · RV20 ${rv==null?'—':rv.toFixed(2)+'배'}\n완성 봉의 최종값`;
    card.hidden=false;const rect=$('chart').getBoundingClientRect();
    card.style.left=Math.max(4,Math.min(p.point.x+16,rect.width-card.offsetWidth-8))+'px';card.style.top=Math.max(4,Math.min(p.point.y+16,rect.height-card.offsetHeight-8))+'px';
  });
  chart.subscribeClick(p=>{if(!p.time||S.loading)return;const hits=allowedEvents().filter(e=>bucket(eventTime(e),S.tf)===p.time);if(hits.length){const i=hits.findIndex(e=>e.id===S.selected);selectEvent(hits[(i+1)%hits.length],false).catch(error);}});
  updateZone();
}
function eventTime(e){return $('endpoint').value==='last'&&e.last_observed?e.end_time:e.time;}
function allowedEvents(){return S.events.filter(e=>{
  if(S.cutoff!=null&&e.first_us>=S.cutoff*1e6)return false;
  if(S.cutoff==null&&e.qty<Number($('minQty').value||0)*1e6)return false;
  return e.role==='Entry'?$('increases').checked:$('reductions').checked;
});}
function updateZone(){
  chart.applyOptions({localization:{timeFormatter:t=>date(t,true)}});
  chart.timeScale().applyOptions({tickMarkFormatter:(t,type)=>{const d=date(t,true);return S.tf==='1d'||type===0||type===1||type===2?d.slice(5,10):d.slice(11,16);}});
}
function renderReferences(){
  for(const line of priceLines)candles.removePriceLine(line);priceLines=[];
  if(S.cutoff!=null||!$('referenceLines').checked)return;
  const e=S.events.find(x=>x.id===S.selected);if(!e)return;
  for(const [value,title,color] of [[e.price,'BitMEX 선택 체결 (대체시장과 다름)','#d38a08'],[e.basis_before,'BitMEX 주문 직전 평균단가','#728299']]){
    if(Number.isFinite(value)&&value>0)priceLines.push(candles.createPriceLine({price:value,color,lineWidth:1,lineStyle:2,axisLabelVisible:true,title}));
  }
}
function renderMarkers(){
  if(!markerApi)return;
  const visible=completeAt(S.bars,S.tf,S.cutoff),out=buildMarkers(allowedEvents(),visible,S.tf,{legacy:$('legacy').checked,cutoff:S.cutoff,selected:S.selected,endpoint:$('endpoint').value});
  markerApi.setMarkers(out.markers);S.markerGroups=out.groups;
  const missing=visible.filter(b=>!isBar(b)).length;
  $('coverage').textContent=`${visible.filter(isBar).length.toLocaleString()}개 완성 ${S.tf}봉 · 누락/불완전 ${missing.toLocaleString()}봉 · 원본 보간 없음${out.missing?' · 범위 밖/누락 봉 주문 '+out.missing+'건':''}${out.truncated?' · 마커 '+out.truncated+'개 표시 생략: 수량 필터/기간을 좁히세요.':''}${S.cutoff!=null?' · 복기: 미래 봉·손익·주문 전체 수량 숨김':''}`;
  renderReferences();
}
function safeFit(){
  const actual=validBars(S.visible);if(!actual.length)return;
  if(actual.length===1){const i=S.visible.indexOf(actual[0]);chart.timeScale().setVisibleLogicalRange({from:i-10,to:i+10});}
  else chart.timeScale().setVisibleRange({from:actual[0].time,to:actual.at(-1).time});
}
function followReplay(){
  if(!S.visible.some(isBar))return;
  chart.timeScale().setVisibleLogicalRange({from:Math.max(-3,S.visible.length-100),to:S.visible.length+8});
}
function renderChart(fit=false){
  S.visible=completeAt(S.bars,S.tf,S.cutoff);$('hoverCard').hidden=true;S.hover=null;markerApi.setMarkers([]);
  candles.setData(S.visible.map(b=>!isBar(b)?{time:b.time}:{time:b.time,open:b.open,high:b.high,low:b.low,close:b.close}));
  volume.setData(S.visible.map(b=>b.volume==null?{time:b.time}:{time:b.time,value:b.volume,color:b.close>=b.open?'#18a88a66':'#e4526066'}));
  renderMarkers();if(fit)safeFit();
}
async function refreshStatus(){const s=await api('status');S.token=s.token;$('dbStatus').textContent=`v${s.version} · 주문 ${s.orders.toLocaleString()}건`;$('empty').hidden=s.orders>0;return s;}
function stopPlaying(){S.playing=false;S.playEpoch++;clearTimeout(S.timer);S.timer=null;$('play').textContent='▶ 재생';}
function resetReplay(){
  stopPlaying();S.cutoff=null;S.replayIndex=-1;$('replayEnabled').checked=false;$('replayTime').textContent='꺼짐';
  for(const id of ['result','minQty','legacy','endpoint','export','notesTab','referenceLines'])$(id).disabled=false;
  renderEvents();renderStats();renderEpisodes();drawDetail(S.events.find(e=>e.id===S.selected));
}
function clearView(){
  S.viewRequest++;S.request++;aborter?.abort();resetReplay();S.episode=null;S.events=[];S.bars=[];S.loadedTf=null;S.coverage=null;S.performance=null;S.selected=null;S.anchor=null;S.noteDirty=false;busy(false);
  renderChart();renderStats();renderEvents();drawDetail(null);$('chartTitle').textContent='조건에 맞는 포지션이 없습니다.';$('chartRange').textContent='';$('ohlcv').textContent='연도·방향·검색 조건을 확인하세요.';$('detailTitle').textContent='포지션 정보';$('marketStatus').textContent='포지션을 먼저 선택하세요.';
}
async function loadEpisodes(reselect=false){
  const serial=++S.listRequest;
  const p=new URLSearchParams({symbol:$('symbol').value,year:$('year').value,year_mode:$('carry').checked?'overlap':'entry',direction:$('direction').value,result:S.cutoff==null?$('result').value:'',search:$('search').value});
  const rows=await api('episodes?'+p);if(serial!==S.listRequest)return;
  S.episodes=rows;renderEpisodes();
  if(reselect){if(!rows.length){clearView();return;}await selectEpisode(rows[0]);}
}
function renderEpisodes(){
  $('episodeCount').textContent=S.episodes.length.toLocaleString();$('episodeList').replaceChildren();
  if(!S.episodes.length)$('episodeList').append(node('p','조건에 맞는 포지션이 없습니다.','hint'));
  for(const ep of S.episodes){const e=node('button',null,'episode-item'+(S.episode?.id===ep.id?' selected':''));e.dataset.episode=ep.id;
    const row=node('div',null,'row');row.append(node('strong','#'+ep.id),node('span',(ep.carried?'이월 · ':'')+(ep.direction||'미확보'),'badge '+(ep.direction||'').toLowerCase()));e.append(row,node('small',date(ep.start,true)+(S.cutoff==null?' · '+ep.count+'주문':'')));
    if(S.cutoff==null&&ep.pnl_btc!=null)e.append(node('small',`${ep.pnl_btc>0?'+':''}${ep.pnl_btc.toFixed(3)} BTC`,ep.pnl_btc>=0?'positive':'negative'));
    e.onclick=()=>selectEpisode(ep).catch(error);$('episodeList').append(e);
  }
}
function renderStats(){
  $('episodeStats').replaceChildren();$('performanceNote').textContent='';$('marginBox').hidden=S.cutoff!=null||!S.episode;if(!S.episode)return;
  const ep=S.episode,p=S.performance;
  const vals=S.cutoff!=null?[['방향',dirLabel(ep.direction)],['복기 모드','성과 숨김']]:[['방향',dirLabel(ep.direction)],['관측 주문',`${S.events.length}건`],['관측 최대 보유',fmtQty(ep.max_observed_qty)],['원장 순손익',p?.net_pnl_btc==null?'미확보':p.net_pnl_btc.toFixed(3)+' BTC'],['감량 가격성과*',pct(p?.price_return_pct,3)],['증거금 참고 ROI',pct(p?.reference_roi_pct,3)]];
  for(const [label,value] of vals){const b=node('div',null,'stat');b.append(node('small',label),node('strong',value));$('episodeStats').append(b);}
  if(S.cutoff==null&&p){$('performanceNote').textContent=`* 제공된 감량 중 ${p.covered_exit_orders}/${p.observed_exit_orders}주문 · 수량 ${p.coverage_pct==null?'미확보':p.coverage_pct.toFixed(1)+'%'}에 평균단가 근거가 있습니다. ${p.note}${p.pnl_conflict?' 원장 손익 값 충돌: 순손익/ROI 표시 중단.':''}`;$('marginInput').value=p.reference_margin_btc??'';}
}
async function selectEpisode(ep){
  if(S.noteDirty&&!confirm('저장하지 않은 연구 메모가 있습니다. 이동할까요?'))return;
  const serial=++S.viewRequest;S.request++;aborter?.abort();resetReplay();S.episode=ep;S.selected=null;S.events=[];S.bars=[];S.loadedTf=null;S.coverage=null;S.performance=null;S.noteDirty=false;S.anchor=ep.focus;busy(true);
  renderChart();renderEpisodes();renderEvents();renderStats();drawDetail(null);$('detailTitle').textContent='포지션 #'+ep.id;$('chartTitle').textContent=`${ep.pair||'시장 미확보'} · ${S.tf} · #${ep.id} ${ep.direction}`;
  try{
    const [events,note,p]=await Promise.all([api('events?episode='+encodeURIComponent(ep.id)),api('note?episode='+encodeURIComponent(ep.id)),api('performance?episode='+encodeURIComponent(ep.id))]);
    if(serial!==S.viewRequest)return;S.events=events;S.performance=p;$('noteText').value=note.text;$('noteTags').value=note.tags;$('noteState').textContent=note.updated?'마지막 저장 '+note.updated:'';
    S.selected=events.find(e=>e.role==='Entry'&&e.time>=ep.focus)?.id||events.find(e=>e.time>=ep.focus)?.id||null;
    renderEvents();renderStats();drawDetail(events.find(e=>e.id===S.selected));await loadWindow(ep.focus);
  }finally{if(serial===S.viewRequest&&S.loadedTf===null)busy(false);}
}
async function loadWindow(center,range=null,{preserveReplay=false,noAuto=false}={}){
  if(!S.episode?.pair){S.bars=[];S.loadedTf=null;S.coverage=null;busy(false);renderChart();toast('이 계약의 대체시장 매핑이 없습니다. XBTUSD부터 선택하세요.');return;}
  const serial=++S.request,epId=S.episode.id,pair=S.episode.pair,tf=S.tf;
  aborter?.abort();aborter=new AbortController();busy(true);S.anchor=center;S.coverage=null;
  if(S.loadedTf!==tf){S.bars=[];renderChart();}
  let [start,end]=range||windowRange(center,tf,S.episode.year_floor);
  end=Math.min(end,Math.floor(Date.now()/60000)*60);start=Math.min(start,end-TF[tf]);S.start=start;S.end=end;
  $('gotoDate').value=localDateInput(center,S.zone);
  try{
    const p=new URLSearchParams({pair,tf,start:Math.floor(start),end:Math.floor(end)});
    const data=await api('candles?'+p,{signal:aborter.signal});if(serial!==S.request||S.episode?.id!==epId)return;
    S.start=data.start;S.end=data.end;S.bars=data.bars;S.loadedTf=tf;S.coverage=data.coverage;$('empty').hidden=true;
    $('chartTitle').textContent=`${pair} · ${tf} · #${epId} ${S.episode.direction}`;$('chartRange').textContent=`${date(S.start)} → ${date(S.end)} ${S.zone}`;
    if(preserveReplay&&S.cutoff!=null){S.replayIndex=indexAtCutoff(S.bars,S.tf,S.cutoff);syncReplay();renderChart();followReplay();}
    else {S.replayIndex=-1;syncReplay();renderChart(true);}
    if(!data.complete_bars)$('ohlcv').textContent='이 구간 실제 완성 봉 없음 · 누락 시세를 보완하세요.';
    showMarketSummary();if(!noAuto)queueMicrotask(()=>maybeAutoFill());
  }catch(e){if(serial===S.request&&e.name!=='AbortError'){S.bars=[];S.loadedTf=null;S.coverage=null;renderChart();$('ohlcv').textContent='시세 요청 실패: '+e.message;throw e;}}
  finally{if(serial===S.request)busy(false);}
}
function showMarketSummary(){
  if(S.downloading)return;
  const c=S.coverage;if(!c)return;
  $('marketStatus').textContent=c.missing_minutes?`현재 요청 범위: 누락 ${c.missing_minutes.toLocaleString()}분 (충돌 ${c.conflict_minutes}분). ${S.autoBlocked?'자동 보완 중단: 버튼으로 다시 시도하세요.':$('autoFill').checked?'없는 구간만 공개 API에서 보완합니다.':'자동 보완 꺼짐 · 버튼으로 실제 시세를 받으세요.'}`:`요청 범위 ${c.valid_minutes.toLocaleString()}분 완전 확보 · 보간 없음`;
}
async function pollJob(jobId,market=false){
  while(true){const j=await api('job');if(jobId&&j.id!==jobId)throw Error('작업 식별자가 바뀌었습니다. 검증 기록을 확인하세요.');
    $('jobStatus').textContent=JSON.stringify(j,null,2);if(j.progress!=null)$('jobProgress').value=j.progress;
    if(market)$('marketStatus').textContent=j.message||'보완 중';
    if(j.state==='error'||j.state==='cancelled')throw Error(j.message);
    if(j.state==='done')return j.report;await new Promise(r=>setTimeout(r,400));
  }
}
function maybeAutoFill(){
  if(!$('autoFill').checked||S.autoBlocked||S.loading||S.uploading||S.downloading||!S.episode?.pair||!S.coverage?.fetchable_minutes)return;
  const key=`${S.episode.pair}:${S.start}:${S.end}`;if(S.attempts.has(key))return;
  repairWindow(false).catch(error);
}
async function repairWindow(manual=true){
  if(!S.episode?.pair)return toast('먼저 포지션을 선택하세요.');
  if(S.loading||S.uploading||S.downloading)return toast('현재 작업을 완료하거나 중단한 뒤 시도하세요.');
  const request=S.request,range=[S.start,S.end],pair=S.episode.pair,key=`${pair}:${range.join(':')}`,anchor=S.anchor;
  if(manual)S.autoBlocked=false;S.attempts.add(key);S.downloading=true;stopPlaying();$('cancelJob').hidden=false;$('repairWindow').disabled=true;$('fetchMarket').disabled=true;$('files').disabled=true;$('marketStatus').classList.remove('error');
  try{
    const r=await post('fetch',{pair,start:range[0],end:range[1]});S.jobId=r.job_id;
    const report=await pollJob(r.job_id,true);await refreshStatus();
    if(request===S.request&&S.episode?.pair===pair){await loadWindow(anchor,range,{preserveReplay:S.cutoff!=null,noAuto:true});}
    $('marketStatus').textContent=`실제 ${report.received.toLocaleString()}분 보완 · 남은 공백 ${report.remaining_missing_minutes}분 · 충돌 ${report.conflict_minutes}분${report.complete?' · 연속 데이터 확보':' (없는 가격을 만들지 않습니다)'}`;
  }catch(e){S.autoBlocked=true;$('marketStatus').textContent=e.message;$('marketStatus').classList.add('error');toast(e.message);}
  finally{S.downloading=false;S.jobId=null;$('cancelJob').hidden=true;$('repairWindow').disabled=false;$('fetchMarket').disabled=false;$('files').disabled=false;if(request!==S.request)queueMicrotask(()=>maybeAutoFill());}
}
function renderEvents(){
  const events=allowedEvents();$('eventCount').textContent=S.cutoff==null?`${events.length.toLocaleString()} / ${S.events.length.toLocaleString()} 주문`:`현재까지 ${events.length.toLocaleString()} 주문`;$('eventList').replaceChildren();
  for(const e of events){const action=S.cutoff!=null?(e.role==='Entry'?'INCREASE':'REDUCE'):displayAction(e,$('legacy').checked);
    const b=node('button',null,'event-item'+(e.id===S.selected?' selected':''));b.dataset.event=e.id;
    const top=node('div',null,'event-top');top.append(node('strong',`${dirLabel(e.direction)} ${ACTIONS[action]?.label||action}`),node('span',S.cutoff==null?fmtQty(e.qty):''));
    const move=S.cutoff==null&&e.role==='Exit'&&e.price_move_pct!=null?' · '+pct(e.price_move_pct)+'*':'';
    b.append(top,node('span',date(eventTime(e),true)+(S.cutoff==null?' · $'+money(e.price)+move:''),'event-sub'));b.onclick=()=>selectEvent(e,true).catch(error);$('eventList').append(b);
  }
}
function detailRow(label,value){const r=node('div',null,'detail-row');r.append(node('span',label),node('span',value));return r;}
function drawDetail(e){
  const target=$('eventDetail');target.replaceChildren();if(!e){target.append(node('p','주문을 클릭하면 해당 캔들로 이동합니다.','hint'));return;}
  target.append(node('h3',`${dirLabel(e.direction)} · ${e.role==='Entry'?'진입/추가':'감량/종료'} 주문`),detailRow('첫 체결',date(e.time,true)+' '+S.zone));
  if(S.cutoff!=null){target.append(node('p','완성 봉 복기: 주문의 최종 수량·마지막 체결시각·사후 분류·미래 손익을 숨깁니다.','warning'));return;}
  for(const [k,v] of [['마지막 체결',e.last_observed?e.end_time_utc:'미확보'],['총 체결수량',fmtQty(e.qty)+' 계약'],['첫 체결가격',money(e.first_price)],['산술평균가격',money(e.avg_price)],['역수가중가격',money(e.inverse_price)],['시작 전 보유',fmtQty(e.position_before)],['종료 뒤 보유',fmtQty(e.position_after)],['시작 전 평균단가',money(e.basis_before)],['방향환산 가격변화*',pct(e.price_move_pct,3)],['스톱 발동가격',e.stop_trigger?money(e.stop_trigger):'미기록'],['주문유형',e.order_type||'미확보']])target.append(detailRow(k,v));
  const f={...e.context,...e.features};target.append(node('h3','주문 직전 완성 봉의 시장 상태'));
  for(const [label,key] of [['5분 변화','pre_return_5m_pct'],['1시간 변화','pre_return_60m_pct'],['4시간 변화','pre_return_240m_pct'],['24시간 변화','pre_return_1440m_pct']])target.append(detailRow(label,f[key]==null?'미확보':pct(+f[key])));
  for(const [label,v] of [['1분 상대거래량',f.pre_volume_1m_vs_prior_20m],['5분 상대거래량',f.pre_volume_5m_vs_previous_20m??f.pre_volume_5m_vs_prior_20m]])target.append(detailRow(label,v==null?'미확보':(+v).toFixed(2)+'배'));
  if(e.legacy_label)target.append(node('h3','기존 연구 가설 (확정 아님)'),node('p',e.legacy_label,'warning'),node('p',e.legacy_reason||'분류 근거 미기록','hint'));
  for(const w of e.warnings||[])target.append(node('p',w,'warning'));
  target.append(node('p','* 주문 평균/첫 가격 대 직전 평균단가의 참고 변화율. 분할체결 전체 회계·수수료·펀딩·레버리지 반영 ROI가 아닙니다.','hint'));
  const refs=node('details');refs.append(node('summary','원본 연결 정보'),node('pre',JSON.stringify({order_id:e.order_id,sources:e.sources},null,2)));target.append(refs);
}
async function selectEvent(e,jump=true){
  if(!S.events.some(x=>x.id===e.id)||S.cutoff!=null&&e.first_us>=S.cutoff*1e6)return;
  const view=S.viewRequest;S.selected=e.id;S.anchor=eventTime(e);renderEvents();drawDetail(e);renderMarkers();const stamp=eventTime(e);
  if(jump){if(stamp<S.start||stamp>=S.end)await loadWindow(stamp,null,{preserveReplay:S.cutoff!=null});
    if(view!==S.viewRequest||S.selected!==e.id)return;
    const to=S.cutoff!=null?Math.min(bucket(stamp,S.tf)+65*TF[S.tf],S.cutoff-TF[S.tf]):bucket(stamp,S.tf)+65*TF[S.tf];
    const from=bucket(stamp,S.tf)-35*TF[S.tf];if(to>from&&S.visible.some(isBar))chart.timeScale().setVisibleRange({from,to});$('gotoDate').value=localDateInput(stamp,S.zone);
  }
  [...$('eventList').children].find(x=>x.dataset.event===e.id)?.scrollIntoView({block:'nearest'});
}
function syncReplay(){
  const actual=validBars(S.bars);$('replaySlider').max=Math.max(0,actual.length-1);$('replaySlider').value=Math.max(0,S.replayIndex);$('replaySlider').disabled=!actual.length;
  if(S.cutoff!=null)$('replayTime').textContent=date(S.cutoff,true)+' '+S.zone;
}
function applyReplay(follow=true){
  if(!$('replayEnabled').checked){resetReplay();renderChart();return;}
  if(S.cutoff==null)return;
  $('endpoint').value='first';
  for(const id of ['result','minQty','legacy','endpoint','export','notesTab','referenceLines'])$(id).disabled=true;
  $('notesPanel').hidden=true;$('timelinePanel').hidden=false;$('timelineTab').classList.add('active');$('notesTab').classList.remove('active');
  if(S.events.find(e=>e.id===S.selected)?.first_us>=S.cutoff*1e6)S.selected=null;
  syncReplay();$('ohlcv').textContent=`복기 시각 ${date(S.cutoff,true)} ${S.zone} · 이 시각 전에 완성된 봉만 표시`;
  renderChart();renderEvents();renderStats();renderEpisodes();drawDetail(S.events.find(e=>e.id===S.selected));if(follow)followReplay();
}
function replayReady(){
  if(S.loading||S.uploading||S.downloading){toast('현재 데이터 작업을 마친 뒤 재생하세요.');return false;}
  if(!S.episode||!S.bars.some(isBar)){toast('재생할 실제 완성 봉이 없습니다. 시세를 보완하세요.');return false;}
  return true;
}
function beginReplay(){
  stopPlaying();if(!replayReady()){$('replayEnabled').checked=S.cutoff!=null;return false;}
  const anchor=(S.selected?S.events.find(e=>e.id===S.selected)?.time:null)??S.anchor??S.episode?.focus;
  const r=initialReplay(S.bars,S.tf,anchor??S.start,3);
  if(r.index<0){resetReplay();toast(r.warning);return false;}
  S.replayIndex=r.index;S.cutoff=r.cutoff;$('replayEnabled').checked=true;
  $('replayNotice').textContent=r.warning||`기준 주문/진입 ${date(anchor,true)} ${S.zone}의 3봉 전부터 시작 · 누락 봉은 건너뛰고 안내`;
  applyReplay();return true;
}
async function nextStep(){
  if(!replayReady())return false;
  if(S.cutoff==null&&!beginReplay())return false;
  let next=nextValidStep(S.bars,S.tf,S.replayIndex);
  if(!next&&S.episode&&S.cutoff<S.episode.end+3*TF[S.tf]){
    const old=S.cutoff,view=S.viewRequest,tf=S.tf;
    const back=S.tf==='1d'?30:60,forward=S.tf==='1d'?90:240;
    await loadWindow(old,[old-back*TF[tf],Math.min(old+forward*TF[tf],S.episode.end+5*TF[tf])],{preserveReplay:true});
    if(view!==S.viewRequest||tf!==S.tf||S.cutoff==null)return false;
    next=nextValidStep(S.bars,S.tf,S.replayIndex);
  }
  if(!next){stopPlaying();$('replayNotice').textContent='현재 확보한 재생 구간 끝입니다. 누락이 있으면 실제 시세를 보완하세요.';return false;}
  S.replayIndex=next.index;S.cutoff=next.cutoff;
  if(next.skipped)$('replayNotice').textContent=`실제 데이터가 없는 ${next.skipped}개 ${S.tf} 구간을 건너뛰었습니다. 가격/거래량 보간 없음.`;
  applyReplay();return true;
}
function startPlaying(){
  if(!replayReady())return;
  if(S.cutoff==null&&!beginReplay())return;S.playing=true;const epoch=++S.playEpoch;$('play').textContent='Ⅱ 일시정지';
  const tick=async()=>{if(!S.playing||S.playEpoch!==epoch)return;try{const ok=await nextStep();if(S.playEpoch!==epoch)return;if(ok&&S.playing)S.timer=setTimeout(tick,1000/Number($('speed').value));else stopPlaying();}catch(e){if(S.playEpoch===epoch)stopPlaying();error(e);}};
  S.timer=setTimeout(tick,1000/Number($('speed').value));
}
async function importFiles(fileList){
  if(S.uploading||S.downloading){toast('현재 작업을 먼저 완료하거나 중단하세요.');return;}
  const files=Array.from(fileList);if(!files.length)return;S.uploading=true;stopPlaying();$('files').disabled=true;$('fetchMarket').disabled=true;
  try{
    for(let i=0;i<files.length;i++){const f=files[i];if(f.size>512*1024*1024)throw Error('파일당 512MB 제한');$('jobStatus').textContent=f.name+' 로컬 전송 중…';const r=await api('import?name='+encodeURIComponent(f.name),{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:f});await pollJob(r.job_id);}
    $('jobProgress').value=100;S.attempts.clear();await refreshStatus();await loadEpisodes();
    const ep=S.episodes.find(e=>e.id===S.episode?.id)||S.episodes.find(e=>e.id==='3086')||S.episodes[0];if(ep)await selectEpisode(ep);else clearView();toast('데이터 가져오기 완료. 기존 메모와 데이터는 보존됩니다.');
  }catch(e){$('jobStatus').textContent='실패: '+e.message;error(e);}finally{S.uploading=false;$('files').disabled=false;$('files').value='';$('fetchMarket').disabled=false;maybeAutoFill();}
}
async function capture(){
  if(!S.visible.some(isBar))return toast('저장할 실제 캔들이 없습니다.');
  const source=chart.takeScreenshot(true,false),canvas=document.createElement('canvas');canvas.width=source.width;canvas.height=source.height+80;const ctx=canvas.getContext('2d');ctx.fillStyle='#fff';ctx.fillRect(0,0,canvas.width,canvas.height);ctx.fillStyle='#17263a';ctx.font='bold 14px sans-serif';ctx.fillText($('chartTitle').textContent+' · '+S.zone+(S.cutoff!=null?' · REPLAY '+date(S.cutoff):''),14,25);ctx.drawImage(source,0,40);ctx.font='10px sans-serif';ctx.fillStyle='#7a8799';ctx.fillText('Binance spot proxy / BitMEX recorded orders / assumed UTC / no interpolation / research only',14,canvas.height-14);
  canvas.toBlob(blob=>{if(!blob)return toast('PNG 생성 실패');const url=URL.createObjectURL(blob),a=node('a');a.href=url;a.download=`AOA_${S.episode.id}_${S.tf}.png`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
}
async function changeFilters(){resetReplay();await loadEpisodes(true);}
function setTF(tf){S.tf=tf;for(const b of $('tfButtons').children)b.classList.toggle('active',b.dataset.tf===tf);}
function bind(){
  $('autoFill').checked=preference('aoa.autoFill','1')==='1';
  for(const id of ['importOpen','emptyImport'])$(id).onclick=()=>$('importDialog').showModal();$('closeImport').onclick=()=>$('importDialog').close();$('closeQuality').onclick=()=>$('qualityDialog').close();
  $('qualityOpen').onclick=async()=>{try{$('qualityContent').textContent=JSON.stringify({status:await api('status'),current_range:S.coverage,issues:await api('issues')},(k,v)=>k==='token'?undefined:v,2);$('qualityDialog').showModal();}catch(e){error(e);}};
  for(const id of ['symbol','year','direction','result','carry'])$(id).onchange=()=>changeFilters().catch(error);
  let debounce;$('search').oninput=()=>{clearTimeout(debounce);debounce=setTimeout(()=>changeFilters().catch(error),200);};
  for(const [id,d] of [['prevEpisode',-1],['nextEpisode',1]])$(id).onclick=()=>{const i=S.episodes.findIndex(e=>e.id===S.episode?.id),ep=S.episodes[i+d];if(ep)selectEpisode(ep).catch(error);};
  for(const [id,d] of [['prevEvent',-1],['nextEvent',1]])$(id).onclick=()=>{const rows=allowedEvents(),i=rows.findIndex(e=>e.id===S.selected),e=rows[i+d];if(e)selectEvent(e).catch(error);};
  $('tfButtons').onclick=async e=>{const b=e.target.closest('[data-tf]');if(!b||b.dataset.tf===S.tf)return;stopPlaying();const cursor=S.cutoff,center=cursor??S.anchor??S.episode?.focus;setTF(b.dataset.tf);try{if(center!=null){await loadWindow(center,null,{preserveReplay:cursor!=null});if(cursor!=null&&S.cutoff!=null)applyReplay();}}catch(err){error(err);}};
  $('timezone').onchange=()=>{S.zone=$('timezone').value;updateZone();$('chartRange').textContent=`${date(S.start)} → ${date(S.end)} ${S.zone}`;if(S.anchor!=null)$('gotoDate').value=localDateInput(S.anchor,S.zone);syncReplay();renderEvents();renderEpisodes();drawDetail(S.events.find(e=>e.id===S.selected));};
  $('jump').onclick=()=>{const t=parseDateInput($('gotoDate').value,S.zone);if(t==null)return toast('날짜를 입력하세요.');resetReplay();loadWindow(t).catch(error);};
  $('entryFocus').onclick=()=>{if(!S.episode)return;resetReplay();S.selected=S.events.find(e=>e.role==='Entry'&&e.time>=S.episode.focus)?.id||null;loadWindow(S.episode.focus).then(()=>{renderEvents();drawDetail(S.events.find(e=>e.id===S.selected));}).catch(error);};
  for(const [id,d] of [['earlier',-1],['later',1]])$(id).onclick=()=>{if(!S.episode)return;resetReplay();loadWindow((S.anchor??S.episode.focus)+d*(S.end-S.start)*.75).catch(error);};
  $('fullEpisode').onclick=async()=>{if(!S.episode)return;resetReplay();const ep=S.episode,a=Math.max(ep.start-3600,ep.year_floor||0),b=Math.min(ep.end+3600,a+179*86400);const tf=Object.keys(TF).find(k=>(b-a)/TF[k]<=3500)||'1d';setTF(tf);try{await loadWindow(ep.focus,[a,b]);if(ep.end+3600>b)toast('긴 포지션: 첫 179일 창입니다. 다음 구간으로 이어서 확인하세요.');}catch(e){error(e);}};
  $('fit').onclick=safeFit;$('screenshot').onclick=()=>capture().catch(error);
  for(const id of ['minQty','increases','reductions','legacy','endpoint','referenceLines'])$(id).onchange=()=>{renderEvents();renderMarkers();};
  $('replayEnabled').onchange=()=>{if($('replayEnabled').checked)beginReplay();else{resetReplay();renderChart(true);}};
  $('replayStart').onclick=()=>beginReplay();$('replaySlider').oninput=()=>{stopPlaying();if(!replayReady())return;const wanted=Number($('replaySlider').value);if(S.cutoff==null&&!beginReplay())return;const actual=validBars(S.bars),i=Math.min(wanted,actual.length-1);if(i<0)return;S.replayIndex=i;S.cutoff=actual[i].time+TF[S.tf];applyReplay();};
  $('step').onclick=()=>{stopPlaying();nextStep().catch(error);};$('backStep').onclick=()=>{stopPlaying();if(!replayReady())return;if(S.cutoff==null&&!beginReplay())return;const actual=validBars(S.bars);if(S.replayIndex<=0){toast('현재 구간에서 더 이전에 완성된 봉이 없습니다.');return;}S.replayIndex=Math.min(actual.length-1,S.replayIndex-1);S.cutoff=actual[S.replayIndex].time+TF[S.tf];applyReplay();};
  $('play').onclick=()=>{if(S.playing)stopPlaying();else startPlaying();};$('speed').onchange=()=>{if(S.playing){stopPlaying();startPlaying();}};
  $('notesTab').onclick=()=>{$('notesPanel').hidden=false;$('timelinePanel').hidden=true;$('notesTab').classList.add('active');$('timelineTab').classList.remove('active');};
  $('timelineTab').onclick=()=>{$('notesPanel').hidden=true;$('timelinePanel').hidden=false;$('timelineTab').classList.add('active');$('notesTab').classList.remove('active');};
  for(const id of ['noteText','noteTags'])$(id).oninput=()=>{S.noteDirty=true;};
  $('saveNote').onclick=async()=>{if(!S.episode)return;const view=S.viewRequest;try{await post('note',{episode:S.episode.id,text:$('noteText').value,tags:$('noteTags').value});if(view===S.viewRequest){S.noteDirty=false;$('noteState').textContent='이 PC에 저장했습니다.';}}catch(e){error(e);}};
  async function saveMargin(value){if(!S.episode||S.cutoff!=null)return;const id=S.episode.id;const p=await post('reference-margin',{episode:id,btc:value});if(S.episode?.id===id){S.performance=p;renderStats();}}
  $('saveMargin').onclick=()=>saveMargin($('marginInput').value).catch(error);$('clearMargin').onclick=()=>saveMargin(null).catch(error);
  $('export').onclick=()=>{if(S.episode&&S.cutoff==null){const a=node('a');a.href='/api/export?episode='+encodeURIComponent(S.episode.id);a.download='aoa_episode.csv';a.click();}};
  $('files').onchange=()=>importFiles($('files').files);$('dropzone').ondragover=e=>e.preventDefault();$('dropzone').ondrop=e=>{e.preventDefault();importFiles(e.dataTransfer.files);};
  $('autoFill').onchange=()=>{savePreference('aoa.autoFill',$('autoFill').checked?'1':'0');S.autoBlocked=false;showMarketSummary();maybeAutoFill();};
  $('repairWindow').onclick=()=>repairWindow(true).catch(error);$('fetchMarket').onclick=()=>repairWindow(true).catch(error);
  $('cancelJob').onclick=()=>post('cancel-job',{job_id:S.jobId}).then(()=>{$('marketStatus').textContent='중단 요청: 현재 응답 검증 후 멈춥니다.';}).catch(error);
  window.addEventListener('beforeunload',e=>{if(S.noteDirty){e.preventDefault();e.returnValue='';}});
}
async function boot(){initChart();bind();await refreshStatus();await loadEpisodes();if(S.episodes.length)await selectEpisode(S.episodes.find(e=>e.id==='3086')||S.episodes[0]);}
boot().catch(error);
window.AOAViewer={snapshot:()=>({episode:S.episode?.id,tf:S.tf,barCount:S.bars.filter(isBar).length,visibleBarCount:S.visible.filter(isBar).length,markerCount:S.markerGroups.length,cutoff:S.cutoff,anchor:S.anchor,start:S.start,end:S.end,replayIndex:S.replayIndex,playing:S.playing,loading:S.loading,downloading:S.downloading,hover:S.hover,coverage:S.coverage,performance:S.cutoff==null?S.performance:null}),pointForBar:t=>{const b=S.visible.find(x=>x.time===t);if(!isBar(b))return null;return {x:chart.timeScale().timeToCoordinate(t),y:candles.priceToCoordinate((b.open+b.close)/2)};}};
