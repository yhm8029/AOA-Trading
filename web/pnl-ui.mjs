// Descriptive net performance. No assumed leverage or proxy-market PNL.
import {pct} from './review-core.mjs';
import {TF,bucket} from './core.mjs';
const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!=null)n.textContent=text;if(cls)n.className=cls;return n;};
const btc=n=>n==null?'미연결':(n>0?'+':'')+Number(n).toLocaleString('en-US',{minimumFractionDigits:6,maximumFractionDigits:8})+' BTC';
export function outcomeAvailable(p,cutoff=null){return !!p&&(cutoff==null||(p.position_closed&&p.closed_at_us!=null&&p.closed_at_us<cutoff*1e6));}
export function returnText(p){if(p?.net_return_pct!=null)return pct(p.net_return_pct,3);if(p?.net_return_estimate_pct!=null)return '≈ '+pct(p.net_return_estimate_pct,3);return '손익자료 연결 필요';}
export function renderOutcome(root,p,cutoff,onImport){
 root.replaceChildren();root.className='position-outcome';
 if(!p){root.append(el('span','포지션 손익 계산 중…'));return;}
 if(!outcomeAvailable(p,cutoff)){root.append(el('strong','복기 중 · 최종 순손익은 청산 후 공개'),el('p','이 포지션의 마지막 체결이 완료되면 수수료·펀딩을 반영한 결과가 표시됩니다.','hint'));return;}
 root.append(el('h3','포지션 최종 결과'));
 const exact=p.net_return_pct!=null,value=exact?p.net_return_pct:p.net_return_estimate_pct;
 root.append(el('small',exact?'순손익률 · 누적 진입 계약가치 기준':value!=null?'참고 순손익률 · 분모 근사/전체성 미검증':'순손익률 · 누적 진입 계약가치 기준'));
 root.append(el('div',returnText(p),'outcome-return '+(value>0?'positive':value<0?'negative':'')));
 root.append(el('div','최종 순손익 '+btc(p.net_pnl_btc),'outcome-net '+(p.net_pnl_btc>0?'positive':p.net_pnl_btc<0?'negative':'')));
 root.append(el('p',p.net_return_note||'증거금·계좌 수익률과 다릅니다.','hint'));
 if(value==null||p.gross_pnl_btc==null||p.trade_fee_btc==null||p.funding_fee_btc==null){const b=el('button','손익자료 연결 / 보완','small');b.onclick=onImport;root.append(b);}
 const d=el('details');d.append(el('summary','계산식·비용·자료 검증'));
 d.append(el('p',p.formula||''),el('p','분모 '+(p.entry_value_btc==null?'미확인':Number(p.entry_value_btc).toFixed(8)+' BTC')),
 el('p','가격손익 '+btc(p.gross_pnl_btc)),el('p','거래수수료 '+btc(p.trade_fee_btc)+' · 음수는 리베이트'),el('p','펀딩비 '+btc(p.funding_fee_btc)+' · 음수는 수취'));
 d.append(el('p','가격손익 − 거래수수료 − 펀딩비 = 최종 순손익. 세부 비용이 미연결이면 순손익 보고값을 임의로 분해하지 않습니다.'));
 d.append(el('p',`진입 분모 자료 ${p.denominator_entry_orders??0}/${p.observed_entry_orders??0} 주문 · 원장 수량 대조 ${p.ledger_verified?'일치':'미확인'}`));
 for(const reason of p.reasons||[])d.append(el('p',reason,'warning'));
 for(const source of p.sources||[])d.append(el('small','출처 '+source));
 const exportButton=el('button','성과 JSON 저장','small');exportButton.onclick=()=>{const blob=new Blob([JSON.stringify(p,null,2)],{type:'application/json'}),u=URL.createObjectURL(blob),a=el('a');a.href=u;a.download='AOA-position-performance.json';a.click();setTimeout(()=>URL.revokeObjectURL(u),1000);};
 d.append(exportButton);root.append(d);
}
export function finalResultMarker(p,bars,tf,cutoff){
 if(!outcomeAvailable(p,cutoff)||!p.position_closed||p.net_pnl_btc==null||p.closed_at_us==null)return null;
 const t=bucket(Math.floor(p.closed_at_us/1e6),tf);
 if(!bars.some(b=>b.time===t&&b.open!=null))return null;
 return {time:t,position:'belowBar',shape:'circle',color:p.net_pnl_btc>=0?'#087f72':'#c82b41',text:'최종 '+(p.net_return_pct!=null||p.net_return_estimate_pct!=null?returnText(p)+' · ':'')+btc(p.net_pnl_btc)};
}
