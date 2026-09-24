"""End-to-end screenshots are SYNTHETIC regression evidence, not historical AOA charts."""
import io
import json
import math
import tempfile
import threading
from pathlib import Path
from urllib.parse import parse_qs,urlsplit
from unittest.mock import patch
from playwright.sync_api import sync_playwright,expect
from aoa.server import AppServer
from aoa.version import VERSION
from aoa.model import validate_bar,time_us,iso
from aoa.store import Store
from aoa.study import StudyStore
from aoa.market import fetch_window
from tests.browser_test import wait_state
from tests.test_study import event

OUT=Path('test-results');OUT.mkdir(exist_ok=True)

def main():
    with tempfile.TemporaryDirectory() as td:
        s=StudyStore(td);entry=time_us('2021-01-03T12:00:00Z')//1_000_000;start=entry-3*86400;end=entry+3*86400
        def candle(t):
            i=(t-start)//60;o=100+math.sin(i/20)*.7+i*.0001;c=o+.03*math.sin(i)
            return validate_bar('BTCUSDT',t,o,max(o,c)+.1,min(o,c)-.1,c,10+abs(math.sin(i/7))*10)
        with s.connect() as db:
            for t in range(start,end,60):Store.candle(db,candle(t),'SYNTHETIC-ONLY')
            events=[event(qty=17000,after=17000),event(before=17000,after=20000,qty=3000,minute=4,px=99.8),event('Exit',before=20000,after=0,qty=20000,minute=9,px=100.4)]
            for e in events:Store.order(db,e,'SYNTHETIC-ONLY')
            # A complete minute missing inside a 15m bucket; never interpolate it.
            db.execute('DELETE FROM candles WHERE t=?',(entry-60,))
        calls=[]
        def fake(st,pair,a,b,progress):
            def opener(req,timeout):
                q=parse_qs(urlsplit(req.full_url).query);lo=int(q['startTime'][0])//1000;hi=(int(q['endTime'][0])+1)//1000;calls.append((lo,hi));rows=[]
                for t in range(lo,hi,60):
                    p,t,o,h,l,c,v=candle(t);rows.append([t*1000,o,h,l,c,v,t*1000+59999,0,1,0,0,0])
                return io.BytesIO(json.dumps(rows).encode())
            return fetch_window(st,pair,a,b,progress,opener=opener)
        server=AppServer(('127.0.0.1',0),s.directory);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with patch('aoa.server.fetch_window',fake),sync_playwright() as p:
                browser=p.chromium.launch();ctx=browser.new_context(viewport={'width':1680,'height':1100});ctx.add_init_script("localStorage.setItem('aoa.autoFill','0')")
                page=ctx.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                try:
                    page.goto('http://127.0.0.1:'+str(server.server_address[1]),wait_until='networkidle')
                    wait_state(page,'window.AOAViewer?.snapshot().study?.event!=null && !window.AOAViewer.snapshot().loading')
                    expect(page.locator('#version')).to_have_text('v'+VERSION);expect(page.locator('#minQty')).to_have_value('0')
                    assert page.evaluate('() => window.AOAViewer.snapshot().markerCount')==3
                    first=page.evaluate('() => window.AOAViewer.snapshot().anchor');assert first==entry
                    assert page.evaluate('() => window.AOAViewer.snapshot().start')<=entry
                    assert page.evaluate('() => window.AOAViewer.snapshot().end')>entry+9*60
                    expect(page.locator('#studyPanel')).to_contain_text('관측 사실');expect(page.locator('#studyPanel')).to_contain_text('반대 근거')
                    page.locator('#minQty').fill('1');page.locator('#minQty').dispatch_event('change')
                    assert page.evaluate('() => window.AOAViewer.snapshot().markerCount')==2
                    expect(page.locator('#eventList .event-item')).to_have_count(3)
                    page.locator('#eventList .event-item').nth(1).click()
                    wait_state(page,'window.AOAViewer.snapshot().study?.event?.action==="ADD"')
                    expect(page.locator('#studyPanel')).to_contain_text('추가');expect(page.locator('#studyPanel')).to_contain_text('불리한 방향')
                    assert page.evaluate('() => window.AOAViewer.snapshot().markerCount')==3
                    page.locator('[data-tf="15m"]').click();wait_state(page,'window.AOAViewer.snapshot().tf==="15m" && !window.AOAViewer.snapshot().loading')
                    assert page.evaluate('() => window.AOAViewer.snapshot().coverage.missing_minutes')==1
                    page.locator('#repairWindow').click();wait_state(page,'window.AOAViewer.snapshot().coverage.missing_minutes===0');expect(page.locator('#repairWindow')).to_be_enabled()
                    assert calls==[(entry-60,entry)]
                    page.locator('#entryFocus').click();wait_state(page,'window.AOAViewer.snapshot().anchor==='+str(entry))
                    page.locator('[data-tf="1m"]').click();wait_state(page,'window.AOAViewer.snapshot().tf==="1m" && !window.AOAViewer.snapshot().loading')
                    page.locator('#pauseOnEvent').check();page.locator('#speed').select_option('10');page.locator('#play').click()
                    wait_state(page,'window.AOAViewer.snapshot().cutoff>'+str(entry)+' && !window.AOAViewer.snapshot().playing')
                    assert page.evaluate('() => window.AOAViewer.snapshot().cutoff')==entry+60
                    wait_state(page,'window.AOAViewer.snapshot().study?.event?.time==='+str(entry))
                    assert page.evaluate('() => window.AOAViewer.snapshot().markerCount')==1
                    expect(page.locator('#studyPanel')).to_contain_text('최초 진입');expect(page.locator('#eventList .event-item')).to_have_count(1)
                    expect(page.locator('#replayNotice')).to_contain_text('멈춤')
                    # Future order rationale is not available, even through the API.
                    token=page.evaluate('() => window.AOAViewer.snapshot().selected')
                    response=page.request.get('http://127.0.0.1:'+str(server.server_address[1])+'/api/study?episode=SYNTHETIC&event='+events[-1]['id']+'&cutoff='+str(entry+60));assert response.status==400
                    page.locator('#play').click();wait_state(page,'window.AOAViewer.snapshot().cutoff>'+str(entry+4*60)+' && !window.AOAViewer.snapshot().playing')
                    wait_state(page,'window.AOAViewer.snapshot().study?.event?.action==="ADD"')
                    expect(page.locator('#studyPanel')).to_contain_text('추가')
                    page.locator('#replayEnabled').uncheck();page.locator('#lastFocus').click();wait_state(page,'window.AOAViewer.snapshot().study?.event?.action==="CLOSE"')
                    expect(page.locator('#studyPanel')).to_contain_text('회수')
                    page.evaluate("() => document.getElementById('chartTitle').textContent='SYNTHETIC TEST — not real AOA trades / v0.3'")
                    with page.expect_download() as d:page.locator('#screenshot').click()
                    d.value.save_as(OUT/'synthetic-v03-chart.png')
                    page.screenshot(path=str(OUT/'synthetic-v03-study.png'),full_page=True)
                    with page.expect_download() as d:page.locator('#studyExport').click()
                    d.value.save_as(OUT/'synthetic-v03-explanation.json')
                    for width in (1440,1280,1024,700):
                        page.set_viewport_size({'width':width,'height':1000});page.wait_for_timeout(150)
                        assert page.evaluate('() => document.documentElement.scrollWidth<=innerWidth+1'),width
                    assert not errors,errors
                    report={'synthetic_only':True,'passed':['small_position_markers','quantity_filter_protects_boundaries','complete_timeline','episode_first_last_fit','every_event_explanation','15m_gap_repair','pause_on_event','replay_explanation','future_event_api_rejected','PNG','explanation_export','responsive'],'js_errors':errors}
                    (OUT/'study-browser-results.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print('STUDY_BROWSER_PASS',report)
                except Exception:
                    print('STUDY_DIAGNOSTICS',errors,page.evaluate('() => window.AOAViewer?.snapshot()'))
                    page.screenshot(path=str(OUT/'synthetic-v03-failure.png'),full_page=True);raise
                finally:browser.close()
        finally:server.shutdown();server.server_close();thread.join(timeout=5)

if __name__=='__main__':main()
