// Wallet references are not margin allocations; day-close is not order-time equity.
import {pct} from './review-core.mjs';
import {completedOrder} from './study-core.mjs';
const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!=null)n.textContent=text;if(cls)n.className=cls;return n;};
const btc=x=>x==null?'미확인':Number(x).toLocaleString('en-US',{maximumFractionDigits:8})+' BTC';
export const seedBasis=s=>s?.basis==='prior_day_ledger_close'?'이전 기록일 마감 잔고 · 참고 (미실현손익 제외)':s?.kind==='equity'?'순자산 시드':'지갑잔고 시드 · 미실현손익 제외';
export function seedReturnText(p){
 if(p?.seed_return_pct!=null)return '≈ '+pct(p.seed_return_pct,3);
 if(p?.seed_initial?.btc!=null){
  if(!p.position_closed)return '미종료 / 성과 보류';
  return p.net_pnl_btc==null?'손익자료 미연결':'시드 계산 보류';
 }
 return p?.seed_initial?.has_data?'시드 계산 보류':'시드 미연결';
}
export function seedLabel(e,cutoff=null,mode='initial'){
 if(!e||cutoff!=null&&e.first_us>=cutoff*1e6||!completedOrder(e,cutoff))return '';
 const s=e.sizing;if(!s)return '';
 const n=s[mode==='current'?'order_current_seed_pct':'order_initial_seed_pct'];
 const chosen=mode==='current'?s.order_seed:s.initial_seed;
 return n==null?'':`계약/${chosen?.basis==='prior_day_ledger_close'?'전일잔고':'시드'} ≈ ${n.toFixed(2)}%`;
}
function item(root,label,value){const d=el('div',null,'detail-row');d.append(el('span',label),el('strong',value));root.append(d);}
export function renderSizing(root,e,cutoff=null,mode='initial',onImport=()=>{}){
 root.replaceChildren();root.className='seed-sizing';
 if(!e||cutoff!=null&&e.first_us>=cutoff*1e6){root.append(el('p','주문이 공개되면 시드 비중을 표시합니다.','hint'));return;}
 const s=e.sizing;if(!s){root.append(el('p','잔고 연결 중 또는 시드 자료 없음','hint'));return;}
 root.append(el('h3','이 주문의 시드 대비 규모'));
 root.append(el('p','계약 규모 비율입니다. 실제 증거금 투입 비율이 아닙니다.','warning'));
 const initial=s.initial_seed,current=s.order_seed,chosen=mode==='current'?current:initial;
 item(root,'기준',mode==='current'?'각 주문 이전 잔고 기준':'포지션 최초 진입 기준 고정');
 item(root,seedBasis(chosen),chosen?.btc==null?'미확인':'≈ '+btc(chosen.btc));
 item(root,'최초 진입 기준 잔고',initial?.btc==null?'미확인':'≈ '+btc(initial.btc));
 item(root,'이번 주문 기준 잔고',current?.btc==null?'미확인':'≈ '+btc(current.btc));
 if(chosen?.basis==='prior_day_ledger_close'||chosen?.btc==null)root.append(el('p',chosen?.reason||'사용 가능한 잔고를 연결하세요.','warning'));
 if(completedOrder(e,cutoff)){
  item(root,e.role==='Entry'?'진입·추가 계약가치':'감량 계약가치',btc(s.order_value_btc));
  item(root,'초기 기준 대비 주문','≈ '+pct(s.order_initial_seed_pct,2));
  item(root,'당시 기준 대비 주문','≈ '+pct(s.order_current_seed_pct,2));
  item(root,'주문 전 보유/기준 잔고','≈ '+pct(s[mode==='current'?'before_current_seed_pct':'before_initial_seed_pct'],2));
  item(root,'주문 후 보유/기준 잔고','≈ '+pct(s[mode==='current'?'after_current_seed_pct':'after_initial_seed_pct'],2));
  if(e.role==='Exit')item(root,'단독 감량 / 직전 수량',pct(s.reduced_position_pct,2));
  if(!s.endpoints_isolated)root.append(el('p','전후 보유량에 다른 체결이 섞이거나 끝점이 부족합니다. 이 주문만의 증감으로 합산하지 않습니다.','warning'));
 }else root.append(el('p','분할체결 중: 최종 수량·추가 비중·주문 후 보유량은 마지막 체결 뒤 공개합니다.','hint'));
 const d=el('details');d.append(el('summary','시드 시각·출처·계산 한계'));
 for(const [label,snapshot] of [['초기',initial],['당시',current]]){
  if(snapshot?.basis==='prior_day_ledger_close')d.append(el('p',`${label} 기준 원장 날짜 ${snapshot.reference_day||'미확인'} · 날짜가 끝난 뒤부터만 사용 (실제 거래시각 복원 아님)`));
  else{const stamp=snapshot?.time_us==null?'없음':new Date(snapshot.time_us/1000).toISOString();d.append(el('p',`${label} 잔고 관측 ${stamp} · 주문까지 ${snapshot?.age_seconds==null?'—':Math.round(snapshot.age_seconds)}초`));}
  d.append(el('p',snapshot?.reason||'미확인'));
  for(const source of snapshot?.sources||[])d.append(el('small','출처 '+source));
 }
 d.append(el('p','날짜만 있는 잔고는 이전 기록일 기준 참고값입니다. 당일 손익·미실현손익은 복원하지 않습니다. 100% 초과는 레버리지 포함 계약 규모이지 현금 투입 비중이 아닙니다.'));
 d.append(el('p',s.note));root.append(d);
 const b=el('button','잔고 ZIP / 시드 CSV 연결','small');b.onclick=onImport;root.append(b);
}
