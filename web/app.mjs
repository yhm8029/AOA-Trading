import {TF,ACTIONS,fmtQty,bucket,displayAction,buildMarkers,completeAt,relativeVolume,parseDateInput,localDateInput} from './core.mjs';
const $=id=>document.getElementById(id);
const S={token:'',episodes:[],episode:null,events:[],bars:[],tf:'5m',zone:'UTC',start:0,end:0,selected:null,cutoff:null,replayIndex:0,request:0,markerGroups:[],timer:null,uploading:false};
let chart,candles,volume,markerApi,aborter=null,toastTimer;
function toast(text){$('toast').textContent=text;$('toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').hidden=true,6000);}
function date(t,full=false){if(t==null)return '—';return new Date((t+(S.zone==='KST'?32400:0))*1000).toISOString().slice(full?0:5,full?19:16).replace('T',' ');}
function money(n){return n==null?'—':Number(n).toLocaleString('en-US',{maximumFractionDigits:2});}
function dirLabel(d){return d==='Short'?'숏':d==='Long'?'롱':'방향 미확보';}
function node(tag,text,cls){const el=document.createElement(tag);if(text!=null)el.textContent=text;if(cls)el.className=cls;return el;}
async function api(path,opts={}){const headers={...opts.headers};if(opts.method&&opts.method!=='GET')headers['X-AOA-Token']=S.token;const r=await fetch('/api/'+path,{...opts,headers});const data=await r.json();if(!r.ok)throw Error(data.error||r.statusText);return data;}
function post(path,body){return api(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});}
function error(e){console.error(e);toast(e.message||String(e));}
function busy(v){$('loading').hidden=!v;}
function initChart(){
  if(!window.LightweightCharts)throw Error('차트 라이브러리가 없습니다. run.py를 다시 실행하세요.');
  const L=window.LightweightCharts;
  chart=L.createChart($('chart'),{autoSize:true,layout:{background:{type:L.ColorType.Solid,color:'#ffffff'},textColor:'#798599',fontSize:11,attributionLogo:true,panes:{separatorColor:'#e8edf4',separatorHoverColor:'#dbe8e5',enableResize:true}},grid:{vertLines:{color:'#f0f3f7'},horzLines:{color:'#edf1f6'}},rightPriceScale:{borderColor:'#e4eaf2'},timeScale:{timeVisible:true,secondsVisible:false,borderColor:'#e4eaf2',rightOffset:9,barSpacing:7},crosshair:{mode:L.CrosshairMode.Normal},localization:{locale:'en-US',timeFormatter:t=>date(t,true)}});
  candles=chart.addSeries(L.CandlestickSeries,{upColor:'#18a88a',downColor:'#e45260',borderVisible:false,wickUpColor:'#18a88a',wickDownColor:'#e45260',priceLineVisible:false,lastValueVisible:true});
  volume=chart.addSeries(L.HistogramSeries,{priceFormat:{type:'volume'},priceLineVisible:false,lastValueVisible:false},1);
  chart.panes()[1].setHeight(115);
  markerApi=L.createSeriesMarkers(candles,[],{autoScale:true});
  chart.subscribeCrosshairMove(p=>{
    if(!p.time)return;
    const visible=completeAt(S.bars,S.tf,S.cutoff);const i=visible.findIndex(x=>x.time===p.time),b=visible[i];if(!b||b.open==null)return;
    const rv=relativeVolume(visible,i);
    $('ohlcv').textContent=`${date(b.time)}  O ${money(b.open)}  H ${money(b.high)}  L ${money(b.low)}  C ${money(b.close)}  거래량 ${money(b.volume)}  RV20 ${rv==null?'—':rv.toFixed(2)+'배'}`;
  });
  chart.subscribeClick(p=>{
    if(!p.time)return;
    const hits=allowedEvents().filter(e=>bucket($('endpoint').value==='last'&&e.last_observed?e.end_time:e.time,S.tf)===p.time);
    if(hits.length){const index=hits.findIndex(e=>e.id===S.selected);selectEvent(hits[(index+1)%hits.length],false).catch(error);}
  });
  chart.timeScale().applyOptions({tickMarkFormatter:t=>date(t).slice(-5)});
}
function allowedEvents(){return S.events.filter(e=>{
  if(S.cutoff!=null)return e.first_us<=S.cutoff*1e6;
  if(e.qty<Number($('minQty').value||0)*1e6)return false;
  return e.role==='Entry'?$('increases').checked:$('reductions').checked;
});}
function renderMarkers(){
  if(!markerApi)return;
  const visible=completeAt(S.bars,S.tf,S.cutoff);
  const out=buildMarkers(allowedEvents(),visible,S.tf,{legacy:$('legacy').checked,cutoff:S.cutoff,selected:S.selected,endpoint:$('endpoint').value});
  markerApi.setMarkers(out.markers);S.markerGroups=out.groups;
  const missing=visible.filter(b=>b.open==null).length;
  $('coverage').textContent=`${visible.filter(b=>b.open!=null).length.toLocaleString()}개 완성 ${S.tf}봉 · 누락/불완전 ${missing.toLocaleString()}봉 · 원본 보간 없음${out.missing?' · 현재 화면 밖 또는 누락 봉의 주문 '+out.missing+'건':''}${out.truncated?' · 마커 '+out.truncated+'개 생략: 수량 필터를 높이세요.':''}${S.cutoff!=null?' · 복기: 미래 봉·성과·집계 수량·사후 분류 숨김':''}`;
}
function renderChart(fit=false){
  const bars=completeAt(S.bars,S.tf,S.cutoff);markerApi.setMarkers([]);
  candles.setData(bars.map(b=>b.open==null?{time:b.time}:{time:b.time,open:b.open,high:b.high,low:b.low,close:b.close}));
  volume.setData(bars.map(b=>b.volume==null?{time:b.time}:{time:b.time,value:b.volume,color:b.close>=b.open?'#18a88a66':'#e4526066'}));
  renderMarkers();if(fit)chart.timeScale().fitContent();
}
async function refreshStatus(){const status=await api('status');S.token=status.token;$('dbStatus').textContent=`로컬 · 주문 ${status.orders.toLocaleString()}건`;$('empty').hidden=status.orders>0;return status;}
async function loadEpisodes(){
  const params=new URLSearchParams({symbol:$('symbol').value,year:$('year').value,direction:$('direction').value,result:S.cutoff==null?$('result').value:'',search:$('search').value});
  S.episodes=await api('episodes?'+params);renderEpisodes();
}
function renderEpisodes(){
  $('episodeCount').textContent=S.episodes.length.toLocaleString();$('episodeList').replaceChildren();
  for(const ep of S.episodes){const el=node('button',null,'episode-item'+(S.episode?.id===ep.id?' selected':''));el.dataset.episode=ep.id;
    const row=node('div',null,'row');row.append(node('strong','#'+ep.id),node('span',ep.direction||'미확보','badge '+ep.direction.toLowerCase()));el.append(row,node('small',date(ep.start)+(S.cutoff==null?' · '+ep.count+'주문':'')));
    if(S.cutoff==null&&ep.pnl_btc!=null)el.append(node('small',`${ep.pnl_btc>0?'+':''}${ep.pnl_btc.toFixed(3)} BTC`,ep.pnl_btc>=0?'positive':'negative'));
    el.onclick=()=>selectEpisode(ep).catch(error);$('episodeList').append(el);
  }
}
function renderStats(){
  $('episodeStats').replaceChildren();if(!S.episode)return;
  const ep=S.episode;const vals=S.cutoff!=null?[['방향',dirLabel(ep.direction)],['복기 모드','성과 숨김']]:[['방향',dirLabel(ep.direction)],['표시 주문',String(S.events.length)+'건'],['관측 최대 보유',fmtQty(ep.max_observed_qty)],['원장 순손익',ep.pnl_btc==null?'미확보':ep.pnl_btc.toFixed(3)+' BTC']];
  for(const [label,value] of vals){const b=node('div',null,'stat');b.append(node('small',label),node('strong',value));$('episodeStats').append(b);}
}
function resetReplay(){
  clearInterval(S.timer);S.timer=null;S.cutoff=null;$('replayEnabled').checked=false;$('play').textContent='▶ 재생';$('replayTime').textContent='꺼짐';
  for(const id of ['result','minQty','legacy','endpoint','export','notesTab'])$(id).disabled=false;
  renderEvents();renderStats();renderEpisodes();drawDetail(S.events.find(e=>e.id===S.selected));
}
async function selectEpisode(ep){
  resetReplay();S.episode=ep;S.selected=null;S.events=[];S.bars=[];renderChart();renderEpisodes();renderEvents();renderStats();drawDetail(null);
  $('detailTitle').textContent='포지션 #'+ep.id;$('chartTitle').textContent=`${ep.pair||'시장 미확보'} · ${S.tf} · #${ep.id} ${ep.direction}`;
  const targetId=ep.id;const events=await api('events?episode='+encodeURIComponent(ep.id));if(S.episode.id!==targetId)return;S.events=events;renderEvents();renderStats();
  const note=await api('note?episode='+encodeURIComponent(ep.id));if(S.episode.id!==targetId)return;$('noteText').value=note.text;$('noteTags').value=note.tags;$('noteState').textContent=note.updated?'마지막 저장 '+note.updated:'';
  await loadWindow(ep.focus);if(S.episode.id!==targetId)return;
  const initial=events.find(e=>e.time>=ep.focus);if(initial)await selectEvent(initial,false);
}
async function loadWindow(center,range=null){
  if(!S.episode?.pair){toast('이 계약의 대체 시장 매핑이 없습니다. XBTUSD부터 선택하세요.');return;}
  const serial=++S.request;aborter?.abort();aborter=new AbortController();busy(true);
  const step=TF[S.tf];S.start=range?range[0]:bucket(center,S.tf)-180*step;S.end=range?range[1]:bucket(center,S.tf)+360*step;$('gotoDate').value=localDateInput(center,S.zone);
  try{
    const p=new URLSearchParams({pair:S.episode.pair,tf:S.tf,start:Math.floor(S.start),end:Math.floor(S.end)});
    const data=await api('candles?'+p,{signal:aborter.signal});if(serial!==S.request)return;
    S.start=data.start;S.end=data.end;S.bars=data.bars;$('empty').hidden=true;
    $('chartTitle').textContent=`${S.episode.pair} · ${S.tf} · #${S.episode.id} ${S.episode.direction}`;
    $('chartRange').textContent=`${date(S.start)} → ${date(S.end)} ${S.zone}`;
    $('replaySlider').max=Math.max(0,S.bars.length-1);$('replaySlider').value=0;
    renderChart(true);
    if(data.complete_bars===0)toast('이 구간의 실제 캔들이 없습니다. 데이터 가져오기 → 누락 시세 보완을 사용하세요.');
  }catch(e){if(e.name!=='AbortError')throw e;}finally{if(serial===S.request)busy(false);}
}
function renderEvents(){
  const events=allowedEvents();$('eventCount').textContent=S.cutoff==null?`${events.length.toLocaleString()} / ${S.events.length.toLocaleString()} 주문`:`현재까지 ${events.length.toLocaleString()} 주문`;
  $('eventList').replaceChildren();
  for(const e of events){const action=S.cutoff!=null?(e.role==='Entry'?'INCREASE':'REDUCE'):displayAction(e,$('legacy').checked);
    const button=node('button',null,'event-item'+(e.id===S.selected?' selected':''));button.dataset.event=e.id;
    const top=node('div',null,'event-top');top.append(node('strong',`${dirLabel(e.direction)} ${ACTIONS[action]?.label||action}`),node('span',S.cutoff==null?fmtQty(e.qty):''));
    button.append(top,node('span',date($('endpoint').value==='last'&&e.last_observed?e.end_time:e.time,true)+(S.cutoff==null?' · $'+money(e.price):''),'event-sub'));
    button.onclick=()=>selectEvent(e,true).catch(error);$('eventList').append(button);
  }
}
function detailRow(label,value){const row=node('div',null,'detail-row');row.append(node('span',label),node('span',value));return row;}
function drawDetail(e){
  const target=$('eventDetail');target.replaceChildren();if(!e)return;
  target.append(node('h3',`${dirLabel(e.direction)} · ${e.role==='Entry'?'진입/추가':'감량/종료'} 주문`),detailRow('첫 체결',date(e.time,true)+' '+S.zone));
  if(S.cutoff!=null){target.append(node('p','복기 중에는 분할체결의 최종 수량·종료시각·사후 분류를 숨깁니다. 완성 봉 단위 복기이며 개별 틱 재생은 아닙니다.','warning'));return;}
  for(const [label,value] of [['원본 시각',e.time_utc],['마지막 체결',e.last_observed?e.end_time_utc:'미확보'],['총 체결수량',Number(e.qty).toLocaleString()+' 계약'],['첫 체결가격',money(e.first_price)],['산술평균가격',money(e.avg_price)],['역수가중가격',money(e.inverse_price)],['시작 전 보유',fmtQty(e.position_before)],['종료 뒤 보유',fmtQty(e.position_after)],['시작 전 평균단가',money(e.basis_before)],['가격 변화율*',e.price_move_pct==null?'미확보':e.price_move_pct.toFixed(3)+'%'],['스톱 발동가격',e.stop_trigger?money(e.stop_trigger):'미기록'],['주문유형',e.order_type||'미확보']])target.append(detailRow(label,value));
  const fields={...e.context,...e.features},volume1=fields.pre_volume_1m_vs_prior_20m,volume5=fields.pre_volume_5m_vs_previous_20m??fields.pre_volume_5m_vs_prior_20m;
  target.append(node('h3','직전에 완성된 봉의 시장 상태'));
  for(const [label,key] of [['5분 변화','pre_return_5m_pct'],['1시간 변화','pre_return_60m_pct'],['4시간 변화','pre_return_240m_pct'],['24시간 변화','pre_return_1440m_pct']]){const v=fields[key];target.append(detailRow(label,v==null?'미확보':(+v).toFixed(2)+'%'));}
  target.append(detailRow('1분 상대거래량',volume1==null?'미확보':(+volume1).toFixed(2)+'배'),detailRow('5분 상대거래량',volume5==null?'미확보':(+volume5).toFixed(2)+'배'));
  if(e.legacy_label)target.append(node('h3','기존 연구 가설 (확정 아님)'),node('p',e.legacy_label,'warning'),node('p',e.legacy_reason||'분류 근거 미기록','hint'));
  for(const w of e.warnings)target.append(node('p',w,'warning'));
  target.append(node('p','* 주문 평균/첫 가격 대 당시 평균단가의 방향환산 변화입니다. 수수료·펀딩·레버리지를 반영한 순손익이나 계좌 수익률이 아닙니다.','hint'));
  const refs=document.createElement('details');refs.append(node('summary','원본 연결 정보'),node('pre',JSON.stringify({order_id:e.order_id,sources:e.sources},null,2)));target.append(refs);
}
async function selectEvent(e,jump=true){
  if(S.cutoff!=null&&e.first_us>S.cutoff*1e6)return;
  S.selected=e.id;renderEvents();drawDetail(e);renderMarkers();const stamp=$('endpoint').value==='last'&&e.last_observed?e.end_time:e.time;
  if(jump){
    if(stamp<S.start||stamp>=S.end){resetReplay();await loadWindow(stamp);}
    chart.timeScale().setVisibleRange({from:bucket(stamp,S.tf)-35*TF[S.tf],to:bucket(stamp,S.tf)+65*TF[S.tf]});$('gotoDate').value=localDateInput(stamp,S.zone);
  }
  $('eventList').querySelector(`[data-event="${e.id}"]`)?.scrollIntoView({block:'nearest'});
}
function applyReplay(){
  if(!$('replayEnabled').checked){resetReplay();renderChart();return;}
  if(!S.bars.length){resetReplay();return;}
  $('endpoint').value='first';
  const i=Math.min(+$('replaySlider').value,S.bars.length-1);S.replayIndex=i;S.cutoff=S.bars[i].time+TF[S.tf];$('replayTime').textContent=date(S.cutoff);
  for(const id of ['result','minQty','legacy','endpoint','export','notesTab'])$(id).disabled=true;
  $('notesPanel').hidden=true;$('timelinePanel').hidden=false;$('timelineTab').classList.add('active');$('notesTab').classList.remove('active');
  if(S.events.find(e=>e.id===S.selected)?.first_us>S.cutoff*1e6)S.selected=null;
  $('ohlcv').textContent='완성 봉 단위 복기 · 미래 봉은 숨겨집니다.';
  renderChart();renderEvents();renderStats();renderEpisodes();drawDetail(S.events.find(e=>e.id===S.selected));chart.timeScale().scrollToRealTime();
}
function nextStep(){if(+$('replaySlider').value>=+$('replaySlider').max){clearInterval(S.timer);S.timer=null;$('play').textContent='▶ 재생';return;}$('replaySlider').value=+$('replaySlider').value+1;applyReplay();}
async function pollJob(){while(true){const job=await api('job');$('jobStatus').textContent=JSON.stringify(job,null,2);if(job.state==='error')throw Error(job.message);if(job.state==='done')return job;await new Promise(r=>setTimeout(r,700));}}
async function importFiles(fileList){
  if(S.uploading)return;const selected=Array.from(fileList);if(!selected.length)return;S.uploading=true;$('files').disabled=true;$('fetchMarket').disabled=true;
  try{
    for(let i=0;i<selected.length;i++){const file=selected[i];if(file.size>512*1024*1024)throw Error('파일당 512MB 제한');$('jobStatus').textContent=file.name+' 로컬 전송 중…';$('jobProgress').value=i/selected.length*100;await api('import?name='+encodeURIComponent(file.name),{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:file});await pollJob();}
    $('jobProgress').value=100;await refreshStatus();await loadEpisodes();
    if(!S.episode&&S.episodes.length)await selectEpisode(S.episodes.find(e=>e.id==='3086')||S.episodes[0]);
    else if(S.episode){const ep=S.episodes.find(e=>e.id===S.episode.id);if(ep)await selectEpisode(ep);}
    toast('데이터 가져오기 완료. 닫기를 눌러 차트를 확인하세요.');
  }catch(e){$('jobStatus').textContent='실패: '+e.message;error(e);}finally{S.uploading=false;$('files').disabled=false;$('fetchMarket').disabled=false;}
}
async function capture(){
  if(!S.bars.some(b=>b.open!=null))return toast('저장할 실제 캔들이 없습니다.');
  const source=chart.takeScreenshot(true,false),canvas=document.createElement('canvas');canvas.width=source.width;canvas.height=source.height+80;const ctx=canvas.getContext('2d');ctx.fillStyle='#fff';ctx.fillRect(0,0,canvas.width,canvas.height);ctx.fillStyle='#17263a';ctx.font='bold 15px sans-serif';ctx.fillText($('chartTitle').textContent+' · '+S.zone,18,26);ctx.drawImage(source,0,40);ctx.font='10px sans-serif';ctx.fillStyle='#7a8799';ctx.fillText('Binance spot proxy / BitMEX recorded orders / source time assumed UTC / research, not a trading signal',18,canvas.height-15);
  canvas.toBlob(blob=>{if(!blob)return toast('PNG 생성에 실패했습니다.');const url=URL.createObjectURL(blob);const a=node('a');a.href=url;a.download=`AOA_${S.episode.id}_${S.tf}.png`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
}
function bind(){
  for(const id of ['importOpen','emptyImport'])$(id).onclick=()=>$('importDialog').showModal();$('closeImport').onclick=()=>$('importDialog').close();$('closeQuality').onclick=()=>$('qualityDialog').close();
  $('qualityOpen').onclick=async()=>{try{$('qualityContent').textContent=JSON.stringify({status:await api('status'),issues:await api('issues')},(k,v)=>k==='token'?undefined:v,2);$('qualityDialog').showModal();}catch(e){error(e);}};
  for(const id of ['symbol','year','direction','result'])$(id).onchange=()=>loadEpisodes().catch(error);
  let debounce;$('search').oninput=()=>{clearTimeout(debounce);debounce=setTimeout(()=>loadEpisodes().catch(error),200);};
  for(const [id,delta] of [['prevEpisode',-1],['nextEpisode',1]])$(id).onclick=()=>{const i=S.episodes.findIndex(e=>e.id===S.episode?.id);const ep=S.episodes[i+delta];if(ep)selectEpisode(ep).catch(error);};
  $('tfButtons').onclick=async e=>{const b=e.target.closest('[data-tf]');if(!b)return;const range=chart.timeScale().getVisibleRange();const center=range?(range.from+range.to)/2:S.episode?.focus;resetReplay();S.tf=b.dataset.tf;for(const x of $('tfButtons').children)x.classList.toggle('active',x===b);try{if(center)await loadWindow(center);}catch(err){error(err);}};
  $('timezone').onchange=()=>{S.zone=$('timezone').value;chart.applyOptions({localization:{timeFormatter:t=>date(t,true)}});chart.timeScale().applyOptions({tickMarkFormatter:t=>date(t).slice(-5)});$('chartRange').textContent=`${date(S.start)} → ${date(S.end)} ${S.zone}`;$('gotoDate').value=localDateInput((S.start+S.end)/2,S.zone);renderEvents();renderEpisodes();drawDetail(S.events.find(e=>e.id===S.selected));};
  $('jump').onclick=()=>{const t=parseDateInput($('gotoDate').value,S.zone);if(t==null)return toast('날짜를 입력하세요.');resetReplay();loadWindow(t).catch(error);};
  for(const [id,delta] of [['earlier',-1],['later',1]])$(id).onclick=()=>{if(!S.episode)return;const w=S.end-S.start;resetReplay();loadWindow((S.start+S.end)/2+delta*w*.7).catch(error);};
  $('fit').onclick=()=>chart.timeScale().fitContent();$('screenshot').onclick=()=>capture().catch(error);
  for(const id of ['minQty','increases','reductions','legacy','endpoint'])$(id).onchange=()=>{renderEvents();renderMarkers();};
  $('replayEnabled').onchange=()=>{if($('replayEnabled').checked){const idx=S.bars.findIndex(b=>b.time>=bucket(S.episode?.focus||S.start,S.tf));$('replaySlider').value=Math.max(0,idx-3);}applyReplay();};
  $('replaySlider').oninput=applyReplay;
  $('step').onclick=()=>{if(!$('replayEnabled').checked){$('replayEnabled').checked=true;applyReplay();}nextStep();};
  $('play').onclick=()=>{if(S.timer){clearInterval(S.timer);S.timer=null;$('play').textContent='▶ 재생';return;}if(!S.bars.length)return;if(!$('replayEnabled').checked){$('replayEnabled').checked=true;applyReplay();}S.timer=setInterval(nextStep,500);$('play').textContent='Ⅱ 일시정지';};
  $('notesTab').onclick=()=>{$('notesPanel').hidden=false;$('timelinePanel').hidden=true;$('notesTab').classList.add('active');$('timelineTab').classList.remove('active');};
  $('timelineTab').onclick=()=>{$('notesPanel').hidden=true;$('timelinePanel').hidden=false;$('timelineTab').classList.add('active');$('notesTab').classList.remove('active');};
  $('saveNote').onclick=async()=>{if(!S.episode)return;try{await post('note',{episode:S.episode.id,text:$('noteText').value,tags:$('noteTags').value});$('noteState').textContent='이 PC에 저장했습니다.';}catch(e){error(e);}};
  $('export').onclick=()=>{if(S.episode&&S.cutoff==null){const a=node('a');a.href='/api/export?episode='+encodeURIComponent(S.episode.id);a.download='aoa_episode.csv';a.click();}};
  $('files').onchange=()=>importFiles($('files').files);$('dropzone').ondragover=e=>e.preventDefault();$('dropzone').ondrop=e=>{e.preventDefault();importFiles(e.dataTransfer.files);};
  $('fetchMarket').onclick=async()=>{if(!S.episode)return toast('먼저 주문 데이터를 가져오고 포지션을 선택하세요.');if(!confirm('현재 구간의 공개 Binance 1분봉을 다운로드할까요? 거래 원본은 외부로 보내지 않습니다.'))return;try{$('fetchMarket').disabled=true;await post('fetch',{pair:S.episode.pair,start:S.start,end:S.end});await pollJob();await refreshStatus();await loadWindow((S.start+S.end)/2,[S.start,S.end]);toast('실제 시세 다운로드 완료');}catch(e){$('jobStatus').textContent=e.message;error(e);}finally{$('fetchMarket').disabled=false;}};
}
async function boot(){initChart();bind();await refreshStatus();await loadEpisodes();if(S.episodes.length)await selectEpisode(S.episodes.find(e=>e.id==='3086')||S.episodes[0]);}
boot().catch(error);
window.AOAViewer={snapshot:()=>({episode:S.episode?.id,tf:S.tf,barCount:S.bars.filter(b=>b.open!=null).length,markerCount:S.markerGroups.length,cutoff:S.cutoff})};
