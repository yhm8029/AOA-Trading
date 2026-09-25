"""One-shot exact integration on an isolated development branch."""
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent

def edit(path,old,new):
    p=ROOT/path;s=p.read_text(encoding='utf-8')
    if old not in s:raise SystemExit('Expected source not found: '+path+' '+old[:80])
    p.write_text(s.replace(old,new),encoding='utf-8')

edit('aoa/server.py','from .performance_ledger import PnlStore as Store','from .seed import SeedStore as Store')
edit('aoa/server.py','from .performance_import import import_file','from .seed_import import import_file')
for path in ['aoa/version.py','web/index.html','web/study-ui.mjs']:
    edit(path,'0.3.2','0.4.0')
for path in ['web/boot.mjs','web/index.html']:
    p=ROOT/path;s=p.read_text(encoding='utf-8');p.write_text(s.replace('?v=032','?v=040'),encoding='utf-8')
edit('web/app.mjs',"const $=id=>document.getElementById(id);", "import {renderSizing,seedLabel,seedReturnText} from './seed-ui.mjs';\nconst $=id=>document.getElementById(id);")
edit('web/app.mjs',"function bind(){", """function initSeedControls(){
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
 initSeedControls();""")
edit('web/app.mjs',"function drawDetail(e){\n  const root=", "function drawDetail(e){\n  if($('seedPanel'))renderSizing($('seedPanel'),e,S.cutoff,$('seedMode')?.value||'initial',()=>$('importDialog').showModal());\n  const root=")
edit('web/app.mjs',"b.onclick=()=>selectEvent(e).catch(error);$('eventList').append(b);", "const sl=seedLabel(e,S.cutoff,$('seedMode')?.value||'initial');if(sl)b.append(node('small',sl,'seed-note'));b.onclick=()=>selectEvent(e).catch(error);$('eventList').append(b);")
edit('web/app.mjs',"b.onclick=()=>selectEpisode(ep).catch(error);$('episodeList').append(b);", "if(S.cutoff==null&&ep.seed_return_pct!=null)b.append(node('small','초기 시드 '+seedReturnText(ep),'seed-return'));b.onclick=()=>selectEpisode(ep).catch(error);$('episodeList').append(b);")
edit('web/app.mjs',"const resultMark=finalResultMarker(S.performance,S.visible,S.tf,S.cutoff);", """const selectedEvent=S.events.find(e=>e.id===S.selected);
  const sl=seedLabel(selectedEvent,S.cutoff,$('seedMode')?.value||'initial');
  if(sl){const gi=out.groups.findIndex(g=>g.items.some(e=>e.id===S.selected));const mark=out.markers.find(m=>m.id==='g'+gi);if(mark)mark.text+=' · '+(out.groups[gi].items.length>1?'선택 주문 ':'')+sl;}
  const resultMark=finalResultMarker(S.performance,S.visible,S.tf,S.cutoff);""")
edit('web/pnl-ui.mjs',"import {TF,bucket} from './core.mjs';", "import {TF,bucket} from './core.mjs';\nimport {seedReturnText,seedBasis} from './seed-ui.mjs';")
edit('web/pnl-ui.mjs',"root.append(el('h3','포지션 최종 결과'));", """root.append(el('h3','포지션 최종 결과'));
 const seedBox=el('div',null,'seed-outcome');
 seedBox.append(el('small','초기 시드 대비 손익 기여도'),el('strong',seedReturnText(p),p.seed_return_pct>0?'positive':p.seed_return_pct<0?'negative':''));
 seedBox.append(el('small',seedBasis(p.seed_initial)),el('small',p.seed_initial?.btc==null?(p.seed_initial?.reason||'잔고 원본 연결 필요'):'초기 시드 ≈ '+Number(p.seed_initial.btc).toFixed(8)+' BTC'));
 seedBox.append(el('small',p.seed_return_note||'계좌 전체 수익률·실제 투입 증거금 ROI가 아닙니다.'));
 if(p.seed_return_pct==null){const b=el('button','잔고자료 연결','small');b.onclick=onImport;seedBox.append(b);}
 if(p.seed_first_order_pct!=null)seedBox.append(el('small','최초 주문 규모/시드 ≈ '+pct(p.seed_first_order_pct,2)));
 if(p.seed_peak_observed_pct!=null)seedBox.append(el('small','관측 끝점 최대 보유/초기 시드 ≈ '+pct(p.seed_peak_observed_pct,2)));
 root.append(seedBox);""")
edit('web/pnl-ui.mjs',"+btc(p.net_pnl_btc)};", "+btc(p.net_pnl_btc)+(p.seed_return_pct!=null?' · 초기 시드 '+seedReturnText(p):'')};")
p=ROOT/'web/index.html';s=p.read_text(encoding='utf-8');needle='</body>'
assert needle in s
s=s.replace(needle,'<template id="seedHelp">잔고: aoa_public_2021-12-31_with_letter.zip 또는 aoa-wallet CSV / timestamp,wallet_balance_btc,equity_btc 형식. 지갑잔고는 미실현손익 제외.</template>'+needle)
p.write_text(s,encoding='utf-8')
p=ROOT/'README.md';s=p.read_text(encoding='utf-8');p.write_text('# v0.4.0 · 시드 비중 추가\n\n[업데이트·잔고 연결·계산 한계](docs/RELEASE_v0.4.0.md)\n\n'+s,encoding='utf-8')
print('SEED_INTEGRATION_APPLIED')
