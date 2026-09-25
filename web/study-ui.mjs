// Render structured explanations with textContent only: imported text is never HTML.
import {pct} from './review-core.mjs';
export const UI_VERSION='0.3.2';
const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!=null)n.textContent=text;if(cls)n.className=cls;return n;};
export function renderStudy(root,data,onEvidence){
  root.replaceChildren();delete root.dataset.eventId;
  if(!data){root.append(el('p','주문을 선택하면 당시까지의 캔들·거래량과 보유량 근거를 연결해 설명합니다.','hint'));return;}
  const o=data.overview,e=data.event;
  root.append(el('div',`포지션 #${o.episode} · 현재 관측 ${o.observed_orders}주문: 증가 ${o.increases} / 감량 ${o.reductions}`,'study-overview'));
  if(!e){root.append(el('p','아직 공개된 주문이 없습니다. 재생이 진입 봉에 도달하면 마커와 해설이 함께 나타납니다.','hint'));return;}
  root.dataset.eventId=e.event_id;root.append(el('h3',e.title+' — 왜 이 시점인가?'),el('span','사실과 구분된 연구 가설 · 매매 신호 아님','study-badge'),el('p',e.summary,'study-summary'));
  root.append(el('h4','관측 사실'));
  for(const f of e.facts){const row=el('div',null,'study-fact');row.append(el('p',f.text));
    if(f.start!=null){const b=el('button','근거 봉 보기','small');b.onclick=()=>onEvidence(f);row.append(b);}
    row.append(el('small',f.source==='order_record'?'원장 기록':f.source==='local_closed_1m'?'로컬 실제 완성 1분봉 재계산':'제공된 첫 체결 사전 특징 · 미재계산'));root.append(row);}
  root.append(el('h4','유력한 해석과 다른 가능성'));
  if(!e.hypotheses.length)root.append(el('p','조건을 충족하는 근거가 부족하여 특정 매매법을 붙이지 않았습니다. 시세 보완 후 다시 분석할 수 있습니다.','warning'));
  for(const h of e.hypotheses){const d=el('details',null,'hypothesis');d.open=e.hypotheses.length===1;d.append(el('summary',h.title+' (가설)'),el('p',h.interpretation),el('small','근거: '+h.evidence.join(' / ')),el('p','반대 근거·대안: '+h.counter_evidence,'counter'));root.append(d);}
  root.append(el('h4','반대 근거·단정하면 안 되는 이유'));
  if(e.counter_evidence.length){for(const t of e.counter_evidence)root.append(el('p',t,'counter'));}
  else root.append(el('p',e.hypotheses.length?'추가 반대 근거가 검출되지 않았다는 것이 가설의 확정을 뜻하지 않습니다. 각 가설의 대안 설명도 함께 확인하세요.':'비교할 가설을 우선하지 않았습니다. 특히 사전 캔들이 부족하면 반대 근거도 확인하지 못한 상태이지, 반대 근거가 없다는 뜻은 아닙니다.','counter'));
  root.append(el('h4','체결 직전 여러 시간대'));
  const wrap=el('div',null,'study-table-wrap'),table=el('table',null,'study-table'),head=el('tr');
  for(const t of ['구간','변화율','범위 위치','거래량 비','구조'])head.append(el('th',t));table.append(head);
  for(const f of e.market.frames){const r=el('tr');
    for(const text of [f.minutes>=60?f.minutes/60+'시간':f.minutes+'분',pct(f.return_pct),f.range_location_pct==null?'—':f.range_location_pct.toFixed(1)+'%',f.volume_ratio==null?'—':f.volume_ratio.toFixed(2)+'배',f.structure])r.append(el('td',text));
    r.title=f.source==='local_closed_1m'?'해당 시각 이전 완성 분봉 재계산':'제공된 사전 특징. 원시 분봉 재검산 아님';table.append(r);}
  wrap.append(table);root.append(wrap,el('small',`직전 24시간 로컬 분봉 ${e.market.valid_1m}/${e.market.expected_1m}분 · 거래량 비=해당 구간/바로 앞 같은 길이 구간. RV20은 직전 1분/그 이전 20분 평균. 구조=세 연속 구간의 고점·저점 비교.`));
  const limits=el('details');limits.append(el('summary','자료 한계·판단 시각·검사 규칙'));
  for(const t of e.limitations)limits.append(el('p',t));
  limits.append(el('pre',JSON.stringify({engine:e.engine_version,thresholds:e.thresholds,methods:e.methods,evidence_hash:e.evidence_hash},null,2)));root.append(limits);
}
