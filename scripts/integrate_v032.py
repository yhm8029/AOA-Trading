"""One-time exact-anchor source integration; CI definition is committed via connector."""
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent

def edit(path,old,new,count=1):
    p=ROOT/path;s=p.read_text(encoding='utf-8')
    actual=s.count(old)
    if actual!=count:raise RuntimeError(f'{path}: expected {count} exact anchors, found {actual}: {old[:90]}')
    p.write_text(s.replace(old,new),encoding='utf-8')

def main():
    edit('aoa/server.py','from .study import StudyStore as Store','from .performance_ledger import PnlStore as Store')
    edit('aoa/server.py','from .importer import import_file','from .performance_import import import_file')
    edit('aoa/server.py',"('.zip','.csv','.gz')","('.zip','.csv','.gz','.xlsx')")
    edit('web/app.mjs',"import {renderStudy,UI_VERSION} from './study-ui.mjs';", "import {renderStudy,UI_VERSION} from './study-ui.mjs';\nimport {renderOutcome,outcomeAvailable,returnText,finalResultMarker} from './pnl-ui.mjs';")
    edit('web/app.mjs','function renderStats(){',"function renderStats(){\n  $('positionOutcome').hidden=!S.episode;if(S.episode)renderOutcome($('positionOutcome'),S.performance,S.cutoff,()=>{$('importDialog').showModal();});")
    edit('web/app.mjs','markerApi.setMarkers(out.markers);S.markerGroups=out.groups;',"const resultMark=finalResultMarker(S.performance,S.visible,S.tf,S.cutoff);if(resultMark)out.markers.push(resultMark);out.markers.sort((a,b)=>a.time-b.time);markerApi.setMarkers(out.markers);S.markerGroups=out.groups;")
    edit('web/app.mjs',"b.onclick=()=>selectEpisode(ep).catch(error);$('episodeList').append(b);", "if(S.cutoff==null&&(ep.net_return_pct!=null||ep.net_return_estimate_pct!=null))b.append(node('small',returnText(ep)+(ep.net_return_pct==null?' · 참고':' · 순손익률'),'episode-return'));b.onclick=()=>selectEpisode(ep).catch(error);$('episodeList').append(b);")
    edit('web/app.mjs','performance:S.cutoff==null?S.performance:null','performance:outcomeAvailable(S.performance,S.cutoff)?S.performance:null')
    edit('web/index.html','</head>','<link rel="stylesheet" href="/pnl.css?v=032"></head>')
    edit('web/index.html','<div id="episodeStats" class="stats"></div>','<section id="positionOutcome" aria-live="polite" hidden></section><div id="episodeStats" class="stats"></div>')
    edit('web/index.html','accept=".csv,.gz,.zip"','accept=".csv,.gz,.zip,.xlsx"')
    edit('web/index.html','<div id="dropzone"', '<p id="performanceHelp"><b>최종 순손익률 연결</b><br>기존 <b>AOA_candle_analysis.zip</b>을 다시 선택하면 이전에 건너뛴 포지션 손익표와 주문 평균가격을 새 방식으로 연결합니다. 기존 봉/메모는 유지됩니다.<br><b>AOA_거래분석_2018-2021.xlsx</b>의 포지션 시트, 명시적 BTC 손익 episodes.csv, <b>AOA_XBTUSD_2021_events.csv</b>도 지원합니다. XLSX만으로는 진입 계약가치 분모가 부족할 수 있어 주문 자료도 함께 필요합니다. 이미 가져온 파일도 새 손익 파서로 재처리합니다. 새 파일을 수집할 필요는 없습니다.</p><div id="dropzone"')
    for path in ['aoa/version.py','web/index.html','web/boot.mjs','web/study-ui.mjs']:
        p=ROOT/path;s=p.read_text(encoding='utf-8');s=s.replace('0.3.1','0.3.2').replace('v031','v032').replace('v=031','v=032')
        p.write_text(s,encoding='utf-8')
    p=ROOT/'README.md';s=p.read_text(encoding='utf-8');p.write_text('# v0.3.2 — 포지션 순손익률\n\n[이번 업데이트 실행/자료 연결](docs/RELEASE_v0.3.2.md)\n\n'+s.replace('0.3.1','0.3.2'),encoding='utf-8')

if __name__=='__main__':main()
