import {FRAMES,COLORS,category,label,color,qty,px,eligible,groupMarkers,priceReturn,formatTime,desiredRange,safeCsv} from './core.mjs';
const $=id=>document.getElementById(id);
const S={token:'',episodes:[],filtered:[],ep:null,events:[],selected:null,tf:5,tz:'UTC',range:null,bars:[],groups:[],chartMeta:null,noteVersion:0,dirty:false,request:0,chartAbort:null,categories:new Set(['ENTRY','ADD','FLIP','INCREASE','TP','CUT','STOP','CLOSE','NEAR_CLOSE','REDUCE']),theme:localStorage.getItem('aoa-theme')||'light'};
let chart,candles,volume,markers,priceLine=null;
function el(tag,text='',className=''){const e=document.createElement(tag);e.textContent=text;if(className)e.className=className;return e;}
function toast(message,error=false){$('toast').textContent=message;$('toast').classList.toggle('error',error);$('toast').hidden=false;clearTimeout(toast.timer);toast.timer=setTimeout(()=>$('toast').hidden=true,9000);}
async function api(path,options={}){const response=await fetch(path,options);const body=await response.json();if(!response.ok)throw new Error(body.error||`HTTP ${response.status}`);return body;}
function post(path,body){return api(path,{method:'POST',headers:{'Content-Type':'application/json','X-AOA-Token':S.token},body:JSON.stringify(body)});}
function choose(select,values,current){select.replaceChildren();for(const [value,text]of values){const option=el('option',text);option.value=value;select.append(option);}if(values.some(v=>v[0]===current))select.value=current;}
function currentFilters(){return {minQty:Math.max(0,Number($('min-qty').value)||0)*1e6,categories:S.categories,showQty:$('show-qty').checked};}
function visibleEvents(){return S.events.filter(e=>eligible(e,currentFilters()));}
function date(us,seconds=true){return formatTime(us,S.tz,seconds);}
function themeColors(){return S.theme==='dark'?{background:'#151f2e',text:'#c8d2e1',grid:'#273345',line:'#32405a'}:{background:'#ffffff',text:'#637488',grid:'#edf1f5',line:'#dfe6ee'};}
function applyTheme(){document.body.classList.toggle('dark',S.theme==='dark');if(chart){const c=themeColors();chart.applyOptions({layout:{background:{type:'solid',color:c.background},textColor:c.text},grid:{vertLines:{color:c.grid},horzLines:{color:c.grid}},rightPriceScale:{borderColor:c.line},timeScale:{borderColor:c.line}});}localStorage.setItem('aoa-theme',S.theme);}
function initChart(){
 const L=window.LightweightCharts;
 if(!L?.createSeriesMarkers)throw new Error('차트 라이브러리를 불러오지 못했습니다. 터미널에서 python prepare_assets.py를 실행한 뒤 새로고침하세요.');
 const c=themeColors();
 chart=L.createChart($('chart'),{autoSize:true,layout:{background:{type:'solid',color:c.background},textColor:c.text,fontFamily:"'Segoe UI','Malgun Gothic',sans-serif",fontSize:11,attributionLogo:true},grid:{vertLines:{color:c.grid},horzLines:{color:c.grid}},rightPriceScale:{borderColor:c.line},timeScale:{timeVisible:true,secondsVisible:false,borderColor:c.line,rightOffset:5},crosshair:{mode:L.CrosshairMode.Normal},localization:{timeFormatter:t=>date(t*1e6)}});
 candles=chart.addSeries(L.CandlestickSeries,{upColor:COLORS.long,downColor:COLORS.short,wickUpColor:COLORS.long,wickDownColor:COLORS.short,borderVisible:false,priceFormat:{type:'price',precision:2,minMove:.01}},0);
 volume=chart.addSeries(L.HistogramSeries,{priceFormat:{type:'volume'},priceScaleId:'right',lastValueVisible:false,priceLineVisible:false},1);
 chart.panes()[1].setHeight(115);
 candles.priceScale().applyOptions({scaleMargins:{top:.16,bottom:.15}});
 markers=L.createSeriesMarkers(candles,[]);
 chart.subscribeCrosshairMove(p=>{const b=p.seriesData?.get(candles),v=p.seriesData?.get(volume);if(b?.open!==undefined){$('ohlcv-legend').textContent=`${date(p.time*1e6,false)}  O ${px(b.open)}  H ${px(b.high)}  L ${px(b.low)}  C ${px(b.close)}  ·  거래량 ${px(v?.value)} (해당 봉 최종)`;}});
 chart.subscribeClick(p=>{if(p.time==null)return;const same=S.groups.filter(g=>g.time===p.time);if(!same.length)return;const g=same.find(x=>x.marker.id===p.hoveredObjectId)||same[0];selectEvent(g.events[0],false);});
 window.addEventListener('resize',()=>{if(chart.panes()[1])chart.panes()[1].setHeight(Math.min(140,$('chart').clientHeight*.24));});
 applyTheme();
}
function clearChart(){
 S.range=null;S.bars=[];S.groups=[];S.chartMeta=null;
 markers?.setMarkers([]);
 if(priceLine){candles.removePriceLine(priceLine);priceLine=null;}
 candles?.setData([]);volume?.setData([]);
 $('coverage').textContent='캔들 데이터 대기';$('ohlcv-legend').textContent='OHLCV —';
}
function drawEvents(){
 if(!markers)return;
 const inRange=S.range?S.events.filter(e=>e.time_us/1e6>=S.range.start&&e.time_us/1e6<S.range.end):[];
 const result=groupMarkers(inRange,S.bars,S.tf,currentFilters());S.groups=result.groups;
 markers.setMarkers(result.groups.map(g=>g.marker));
 if(S.chartMeta){const m=S.chartMeta;const message=`${date(m.start*1e6,false)} — ${date(m.end*1e6,false)} · ${m.valid.toLocaleString()} / ${m.expected.toLocaleString()}봉 · 누락 ${m.missing.toLocaleString()}봉${result.missing?' · 대응 캔들 없는 주문 '+result.missing+'개':''}`;
 $('coverage').textContent=message;$('coverage').classList.toggle('warn',m.missing>0||result.missing>0);}
 renderTimeline();
}
function renderEpisodes(){
 const symbol=$('symbol-filter').value,year=$('year-filter').value,direction=$('direction-filter').value,result=$('result-filter').value,search=$('episode-search').value.trim();
 S.filtered=S.episodes.filter(e=>e.symbol===symbol&&(direction==='all'||e.direction===direction)&&(!search||e.episode_id.includes(search))&&(year==='all'||(e.start_us<Date.parse((+year+1)+'-01-01T00:00:00Z')*1000&&e.end_us>=Date.parse(year+'-01-01T00:00:00Z')*1000))&&(result==='all'||result==='unknown'&&e.net_pnl_btc==null||result==='win'&&e.net_pnl_btc>0||result==='loss'&&e.net_pnl_btc<0));
 $('episode-count').textContent=S.filtered.length.toLocaleString();const list=$('episodes');list.replaceChildren();
 for(const e of S.filtered){const button=el('button','','episode-card'+(S.ep?.episode_id===e.episode_id&&S.ep?.symbol===e.symbol?' active':''));button.dataset.episode=e.episode_id;const top=el('span','','ep-top');top.append(el('span','#'+e.episode_id),el('span',e.direction==='Long'?'LONG':'SHORT',e.direction==='Long'?'long':'short'));button.append(top,el('small',date(e.start_us,false)));const p=el('span',e.net_pnl_btc==null?'손익 미확정':`${e.net_pnl_btc>=0?'+':''}${e.net_pnl_btc.toFixed(4)} BTC`,'pnl '+(e.net_pnl_btc>0?'long':e.net_pnl_btc<0?'short':''));button.append(p);button.onclick=()=>loadEpisode(e);list.append(button);}
 if(!S.filtered.length)list.append(el('p','조건에 맞는 포지션이 없습니다.','muted'));
}
function stat(name,value,wide=false){const box=el('div','','stat'+(wide?' wide':''));box.append(el('small',name),el('strong',value));return box;}
function showEpisodeStats(){if(!S.ep)return;const e=S.ep;$('detail-title').textContent=`Episode #${e.episode_id}`;$('episode-stats').replaceChildren(stat('방향',e.direction==='Long'?'LONG':'SHORT'),stat('최대 계약 · 파일 기재',qty(e.max_qty)),stat('최종 손익 · 입력값',e.net_pnl_btc==null?'미확정':e.net_pnl_btc.toFixed(4)+' BTC'),stat('표시 주문 그룹',String(S.events.length)),stat('표시 주문 구간 ('+(S.tz==='UTC'?'UTC':'KST')+')',date(e.start_us,false)+' → '+date(e.end_us,false),true));$('chart-title').textContent=`${e.pair||'매핑 미확정'} · ${S.tf<60?S.tf+'분':S.tf===1440?'1일':S.tf/60+'시간'} · #${e.episode_id}`;$('chart-subtitle').textContent=`BitMEX ${e.symbol} / ${e.direction.toUpperCase()} · 주문 그룹 첫 체결 위치 · 사후 연구용`;
}
async function loadEpisode(e){
 if(S.dirty&&!confirm('저장하지 않은 메모가 있습니다. 이동할까요?'))return;
 const generation=++S.request;S.chartAbort?.abort();S.ep=e;S.events=[];S.selected=null;S.dirty=false;
 clearChart();showEpisodeStats();
 $('event-detail').replaceChildren(el('p','주문을 선택하세요.'));$('note-status').textContent='';$('note-body').value='';
 renderEpisodes();renderTimeline();
 try{const params=new URLSearchParams({symbol:e.symbol,episode:e.episode_id});const [events,note]=await Promise.all([api('/api/events?'+params),api('/api/note?'+new URLSearchParams({key:e.symbol+':'+e.episode_id}))]);if(generation!==S.request)return;S.events=events;$('note-body').value=note.body;S.noteVersion=note.version;showEpisodeStats();renderTimeline();await loadChart(desiredRange(e,S.tf));const query=new URLSearchParams({episode:e.episode_id,symbol:e.symbol,tf:S.tf});history.replaceState(null,'','/?'+query);}catch(err){toast(err.message,true);}
}
async function loadChart(range){
 if(!S.ep)return;
 S.chartAbort?.abort();
 if(!S.ep.pair){clearChart();$('loading').hidden=true;$('empty-state').hidden=false;$('empty-state').querySelector('h3').textContent='해당 계약의 시장 매핑이 없습니다.';$('empty-state').querySelector('p').textContent='거래는 오른쪽에서 확인할 수 있지만 다른 계약의 캔들로 대체하지 않습니다.';return;}
 const controller=new AbortController();S.chartAbort=controller;const generation=S.request,episodeKey=S.ep.symbol+':'+S.ep.episode_id;
 $('loading').hidden=false;
 try{const meta=await api('/api/chart?'+new URLSearchParams({pair:S.ep.pair,tf:S.tf,start:Math.floor(range.start),end:Math.ceil(range.end)}),{signal:controller.signal});if(generation!==S.request||controller!==S.chartAbort)return;S.range={start:meta.start,end:meta.end};S.bars=meta.bars;S.chartMeta={...meta,episodeKey};markers.setMarkers([]);candles.setData(meta.bars.map(b=>b.open===undefined?{time:b.time}:{time:b.time,open:b.open,high:b.high,low:b.low,close:b.close}));volume.setData(meta.bars.map(b=>b.open===undefined?{time:b.time}:{time:b.time,value:b.volume,color:b.close>=b.open?'rgba(8,153,129,0.48)':'rgba(242,54,69,0.48)'}));chart.timeScale().fitContent();$('empty-state').hidden=meta.valid>0;if(!meta.valid){$('empty-state').querySelector('h3').textContent='이 구간의 실제 캔들이 없습니다.';$('empty-state').querySelector('p').textContent='캔들 ZIP을 가져오거나, 위의 공개 분봉 보완 버튼을 사용하세요.';}drawEvents();showEpisodeStats();syncPriceLine();$('jump-date').value=date((S.selected?S.selected.time_us:((meta.start+meta.end)/2)*1e6),false).replace(' ','T');if(range.windowed)toast('긴 포지션입니다. 일부 구간부터 표시합니다. 주문 클릭 또는 전체 포지션 버튼으로 이동하세요.');}catch(err){if(err.name!=='AbortError'){clearChart();toast(err.message,true);}}finally{if(S.chartAbort===controller)$('loading').hidden=true;}
}
function renderTimeline(){const list=$('timeline');list.replaceChildren();const events=visibleEvents();$('event-count').textContent=`${events.length} / ${S.events.length}개 주문 그룹 · 원본 총량 기준`;
 for(const e of events){const row=el('button','','event-row'+(S.selected?.id===e.id?' selected':''));row.dataset.eventId=e.id;const dot=el('span','','dot');dot.style.background=color(e);const info=el('span','','event-info');info.append(el('b',label(e)),el('small',date(e.time_us)),el('small','첫 체결 '+px(e.first_price)));row.append(dot,info,el('span',qty(e.qty),'eqty'));row.onclick=()=>selectEvent(e,true);list.append(row);}}
function kv(name,value){const row=el('div','','kv');row.append(el('span',name),el('strong',String(value)));return row;}
const warningText={GROUPED_ORDER_NOT_SINGLE_FILL:'수량은 주문 그룹 총량입니다. 첫 체결 순간의 단일 체결량이 아닙니다.',GROUP_ENDPOINTS_INCLUDE_INTERLEAVED_ORDERS:'이전·이후 수량은 그룹 끝점 관측치입니다. 다른 주문이 끼어 있어 주문량과 단순 합산되지 않습니다.',IMPORTED_RETROSPECTIVE_CLASSIFICATION:'이벤트 명칭은 기존 연구에서 가져온 사후 분류입니다.',TACTICAL_INTERPRETATION_NOT_PROVEN:'추가분 철회는 해석 후보입니다. 최근 계약을 특정하여 매칭한 확정 손익이 아닙니다.',NONZERO_RESIDUAL_NOT_FULL_CLOSE:'남은 수량이 있으므로 전량 종료가 아니라 대부분 정리로 표시합니다.',TIME_ASSUMED_UTC:'원문 시각을 잠정 UTC로 해석했습니다.'};
async function selectEvent(e,move=true){
 S.selected=e;renderTimeline();const detail=$('event-detail');detail.replaceChildren(el('h3',label(e)),kv('첫 체결 시각',date(e.time_us)),kv('마지막 체결 시각',date(e.end_time_us)),kv('첫 체결가 · BitMEX',px(e.first_price)),kv('그룹 VWAP · BitMEX',px(e.group_vwap)),kv('그룹 총량',e.qty.toLocaleString()+' 계약'),kv('직전 수량 관측',e.qty_before==null?'미확정':e.qty_before.toLocaleString()),kv('마지막 직후 관측',e.qty_after==null?'미확정':e.qty_after.toLocaleString()),kv('직전 평균단가',px(e.basis_before)));
 const ret=priceReturn(e);if(ret!==null)detail.append(kv('첫 가격 / 평균단가¹',ret.toFixed(3)+'%'));
 if(e.stop_trigger)detail.append(kv('스톱 발동 가격',px(e.stop_trigger)));
 const volumeBox=el('div');volumeBox.id='event-volume-box';volumeBox.append(el('p','거래량 불러오는 중…','muted'));detail.append(volumeBox);
 const warn=el('div','','warning-box');warn.textContent=(e.warnings||[]).filter(k=>k!=='TIME_ASSUMED_UTC').map(k=>warningText[k]||k).join('\n');detail.append(warn);
 detail.append(el('p','¹ 방향 환산 가격 차이입니다. 실현 BTC 손익·계좌 수익률·수수료 차감 수익률이 아닙니다.','muted'));
 const facts=el('details');facts.append(el('summary','분류 근거 / 원본 참조 / 사전 특징'));const raw=el('pre',JSON.stringify({raw_event:e.raw_event,reason:e.classification_reason,source:e.source,row:e.source_row,order_id:e.source_orderid,pre_context:e.context},null,2),'raw-data');facts.append(raw);detail.append(facts);
 syncPriceLine();
 if(move){await loadChart(desiredRange(S.ep,S.tf,e.time_us/1e6));}
 try{const v=await api('/api/event-volume?'+new URLSearchParams({symbol:e.symbol,episode:e.episode_id,id:e.id}));if(S.selected?.id!==e.id)return;volumeBox.replaceChildren(el('h3','거래량 · '+v.volume_unit),kv('직전 완성 1분',px(v.pre_1m_volume)),kv('직전봉 / 이전 20분 평균',v.pre_1m_rvol20==null?'미확정':v.pre_1m_rvol20.toFixed(2)+'배'),kv('체결 분 최종값 · 사후',px(v.event_minute_final_volume)),kv('체결 분 / 이전 20분 · 사후',v.event_minute_final_rvol20==null?'미확정':v.event_minute_final_rvol20.toFixed(2)+'배'));}catch(err){if(S.selected?.id===e.id)volumeBox.textContent=err.message;}
}
function syncPriceLine(){if(priceLine){candles.removePriceLine(priceLine);priceLine=null;}if($('show-price-line').checked&&S.selected?.first_price&&S.chartMeta?.valid){priceLine=candles.createPriceLine({price:S.selected.first_price,color:color(S.selected),lineWidth:1,lineStyle:2,axisLabelVisible:true,title:'BitMEX 첫 체결 (대체차트 참고)'});}}
function setFrame(tf){S.tf=tf;for(const b of $('timeframes').children)b.classList.toggle('active',+b.dataset.tf===tf);}
async function refresh(){const old=S.ep;S.episodes=await api('/api/episodes');const symbols=[...new Set(S.episodes.map(e=>e.symbol))].sort();choose($('symbol-filter'),symbols.map(s=>[s,s]),old?.symbol||'XBTUSD');const years=new Set();for(const e of S.episodes){const a=new Date(e.start_us/1000).getUTCFullYear(),b=new Date(e.end_us/1000).getUTCFullYear();for(let y=a;y<=b;y++)years.add(String(y));}choose($('year-filter'),[['all','전체'],...[...years].sort().map(y=>[y,y])],$('year-filter').value==='all'&&years.has('2021')?'2021':$('year-filter').value);renderEpisodes();const url=new URLSearchParams(location.search);const wanted=old?.episode_id||url.get('episode')||'3086';const ep=S.episodes.find(e=>e.episode_id===wanted&&e.symbol===(old?.symbol||url.get('symbol')||'XBTUSD'))||S.filtered[0];if(ep)await loadEpisode(ep);}
async function waitJob(){for(;;){await new Promise(r=>setTimeout(r,650));const s=await api('/api/status');$('job-banner').hidden=false;$('job-banner').textContent=s.job.message;if(s.job.status==='error')throw new Error(s.job.message);if(s.job.status==='done'||s.job.status==='idle'){setTimeout(()=>$('job-banner').hidden=true,3500);return s.job.report;}}}
async function upload(){const files=[...$('file-input').files];if(!files.length)return toast('파일을 먼저 선택하세요.');$('upload-files').disabled=true;$('import-log').textContent='';try{for(const file of files){$('import-log').textContent+=`\n${file.name} → 로컬 업로드 중…`;
 await api('/api/upload?'+new URLSearchParams({name:file.name}),{method:'POST',headers:{'X-AOA-Token':S.token,'Content-Type':'application/octet-stream'},body:file});const report=await waitJob();$('import-log').textContent+='\n'+JSON.stringify(report,null,2);}
 await refresh();toast('데이터 가져오기가 끝났습니다.');}catch(err){$('import-log').textContent+='\n오류: '+err.message;toast(err.message,true);}finally{$('upload-files').disabled=false;}}
function download(name,blob){if(!blob)return toast('파일 생성에 실패했습니다.',true);const link=document.createElement('a');const url=URL.createObjectURL(blob);link.href=url;link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(url),60000);}
function snapshot(){if(!S.chartMeta?.valid||S.chartMeta.episodeKey!==S.ep?.symbol+':'+S.ep?.episode_id||!$('loading').hidden)return toast('선택한 포지션의 캔들을 불러온 뒤 저장하세요.');const image=chart.takeScreenshot();const canvas=document.createElement('canvas');canvas.width=image.width;canvas.height=image.height+92;const ctx=canvas.getContext('2d');ctx.fillStyle=themeColors().background;ctx.fillRect(0,0,canvas.width,canvas.height);ctx.fillStyle=themeColors().text;ctx.font='bold 17px sans-serif';ctx.fillText($('chart-title').textContent,15,24);ctx.font='11px sans-serif';ctx.fillText('Binance spot candles / BitMEX event times | Retrospective trade study | '+S.tz,15,44);ctx.drawImage(image,0,56);ctx.fillText('Charts by TradingView - AOA Whale Viewer. Gaps are missing data, not interpolated prices.',15,canvas.height-12);canvas.toBlob(b=>download(`AOA_${S.ep.symbol}_${S.ep.episode_id}_${S.tf}m.png`,b));}
function exportEvents(){if(!S.ep)return;const header=['episode_id','symbol','direction','event','event_time_utc','bitmex_first_fill','bitmex_vwap','qty','qty_before','qty_after','source_orderid','classification_reason','reference_pair'];const rows=visibleEvents().map(e=>[e.episode_id,e.symbol,e.direction,e.event,e.event_time_utc,e.first_price,e.group_vwap,e.qty,e.qty_before,e.qty_after,e.source_orderid,e.classification_reason,e.reference_pair]);download(`AOA_${S.ep.symbol}_${S.ep.episode_id}_events.csv`,new Blob(['\uFEFF'+[header,...rows].map(r=>r.map(safeCsv).join(',')).join('\r\n')],{type:'text/csv;charset=utf-8'}));}
function bindings(){
 for(const id of ['import-open','empty-import'])$(id).onclick=()=>$('import-dialog').showModal();$('help-open').onclick=()=>$('help-dialog').showModal();$('upload-files').onclick=upload;
 $('import-inbox').onclick=async()=>{try{await post('/api/import-inbox',{});const r=await waitJob();$('import-log').textContent=JSON.stringify(r,null,2);await refresh();}catch(e){toast(e.message,true);}};
 for(const id of ['symbol-filter','year-filter','direction-filter','result-filter'])$(id).onchange=renderEpisodes;$('episode-search').oninput=renderEpisodes;
 for(const b of document.querySelectorAll('[data-episode]'))b.onclick=()=>{const e=S.episodes.find(x=>x.symbol==='XBTUSD'&&x.episode_id===b.dataset.episode);if(e)loadEpisode(e);else toast('해당 포지션이 없습니다. 이벤트 파일을 가져오세요.');};
 for(const [id,delta]of[['prev-episode',-1],['next-episode',1]])$(id).onclick=()=>{if(!S.filtered.length)return;const index=S.filtered.findIndex(e=>e.episode_id===S.ep?.episode_id);const n=Math.min(S.filtered.length-1,Math.max(0,index+delta));loadEpisode(S.filtered[n]);};
 for(const [id,delta]of[['prev-event',-1],['next-event',1]])$(id).onclick=()=>{const events=visibleEvents();if(!events.length)return;const index=events.findIndex(e=>e.id===S.selected?.id);selectEvent(events[Math.min(events.length-1,Math.max(0,index+delta))],true);};
 for(const b of $('timeframes').children)b.onclick=()=>{setFrame(+b.dataset.tf);if(S.ep){const focus=S.selected?S.selected.time_us/1e6:S.range?(S.range.start+S.range.end)/2:null;loadChart(desiredRange(S.ep,S.tf,focus));}};
 $('timezone').onchange=()=>{S.tz=$('timezone').value;chart.applyOptions({localization:{timeFormatter:t=>date(t*1e6)},timeScale:{tickMarkFormatter:t=>date(t*1e6,false).slice(5)}});renderEpisodes();renderTimeline();showEpisodeStats();drawEvents();if(S.selected)selectEvent(S.selected,false);};
 for(const id of ['min-qty','show-qty'])$(id).oninput=drawEvents;$('show-price-line').onchange=syncPriceLine;
 $('fit-episode').onclick=()=>{if(!S.ep)return;let tf=S.tf;while((S.ep.end_us-S.ep.start_us)/1e6/(tf*60)>9200&&tf<1440)tf=FRAMES[FRAMES.indexOf(tf)+1];setFrame(tf);loadChart({start:S.ep.start_us/1e6-tf*60*50,end:S.ep.end_us/1e6+tf*60*50});};
 for(const[id,d]of[['window-prev',-1],['window-next',1]])$(id).onclick=()=>{if(S.range){const step=(S.range.end-S.range.start)*.75*d;loadChart({start:S.range.start+step,end:S.range.end+step});}};
 $('jump').onclick=()=>{if(!S.ep)return;const ms=Date.parse($('jump-date').value+'Z')-(S.tz==='Asia/Seoul'?9*3600000:0);if(Number.isFinite(ms))loadChart(desiredRange(S.ep,S.tf,ms/1000));};
 $('fetch-market').onclick=async()=>{if(!S.range||!S.ep?.pair)return toast('포지션을 먼저 선택하세요.');if(S.range.end-S.range.start>32*86400)return toast('32일 이내 범위로 좁혀주세요.');if(!confirm('Binance 공개 API에 거래쌍과 시간 범위만 요청합니다. 거래내역·메모는 전송하지 않습니다. 1분봉을 수집해서 빈 구간을 보완할까요?'))return;try{await post('/api/fetch-market',{pair:S.ep.pair,start:S.range.start,end:S.range.end,confirmed:true});await waitJob();await loadChart(S.range);toast('공개 분봉 보완 완료. 수집되지 않은 분은 계속 누락으로 표시합니다.');}catch(e){toast(e.message,true);}};
 $('theme-toggle').onclick=()=>{S.theme=S.theme==='dark'?'light':'dark';applyTheme();};$('snapshot').onclick=snapshot;$('export-events').onclick=exportEvents;
 for(const tab of ['events','notes'])$('tab-'+tab).onclick=()=>{for(const t of ['events','notes']){$(t+'-view').hidden=t!==tab;$('tab-'+t).classList.toggle('active',t===tab);}};
 $('note-body').oninput=()=>S.dirty=true;$('save-note').onclick=async()=>{if(!S.ep)return;try{const key=S.ep.symbol+':'+S.ep.episode_id;const data=await post('/api/note',{key,body:$('note-body').value,version:S.noteVersion});S.noteVersion=data.version;S.dirty=false;$('note-status').textContent='이 PC에 저장했습니다. 버전 '+data.version;}catch(e){toast(e.message,true);}};
 window.addEventListener('beforeunload',e=>{if(S.dirty){e.preventDefault();e.returnValue='';}});
 const filterDefs=[['진입',['ENTRY','FLIP']],['추가',['ADD']],['익절',['TP']],['추가분 철회?',['CUT']],['STOP',['STOP']],['종료/대부분',['CLOSE','NEAR_CLOSE']],['미분류 증가/감량',['INCREASE','REDUCE']]];
 for(const[name,cats]of filterDefs){const lab=el('label');const input=document.createElement('input');input.type='checkbox';input.checked=true;input.onchange=()=>{for(const c of cats)input.checked?S.categories.add(c):S.categories.delete(c);drawEvents();};lab.append(input,document.createTextNode(' '+name));$('event-filters').append(lab);}
}
async function boot(){try{applyTheme();bindings();const params=new URLSearchParams(location.search);if(FRAMES.includes(+params.get('tf')))setFrame(+params.get('tf'));const b=await api('/api/bootstrap');S.token=b.token;$('version').textContent='v'+b.version;initChart();await refresh();window.__AOA={state:S,chart,candles,markers};}catch(e){toast(e.message,true);$('empty-state').querySelector('h3').textContent='시작하지 못했습니다.';$('empty-state').querySelector('p').textContent=e.message;}}
boot();
