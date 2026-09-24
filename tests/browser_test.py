"""Real Chromium + local API/SQLite. All trade fixtures are explicitly synthetic."""
import csv
import io
import json
import math
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs,urlsplit
from unittest.mock import patch
from playwright.sync_api import sync_playwright,expect
from aoa.server import AppServer
from aoa.market import fetch_window
from aoa.model import time_us
from tests.seed_ci import seed
from tests.test_review import order
from aoa.store import Store

OUT=Path('test-results');OUT.mkdir(exist_ok=True)

def wait_state(page,expression,timeout=30):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        if page.evaluate('() => Boolean('+expression+')'):return
        time.sleep(.1)
    raise AssertionError('Browser state not reached: '+expression)

def main():
    with tempfile.TemporaryDirectory() as td:
        store=seed(Path(td)/'local-data');base=time_us('2021-06-04T00:00:00Z')//1_000_000
        with store.connect() as db:
            db.execute('DELETE FROM candles WHERE t>=? AND t<?',(base+605*60,base+608*60))
            for event in [order('CARRY-SYNTHETIC',time_us('2020-12-31T23:30:00Z')//1_000_000,qty=5000000),order('CARRY-SYNTHETIC',time_us('2021-01-01T01:00:00Z')//1_000_000,'Exit',qty=5000000,after=0)]:
                Store.order(db,event,'SYNTHETIC-TEST-ONLY')
        # Actual browser upload through localhost, not a seeded-only UI.
        fixture=Path(td)/'SYNTHETIC-upload.csv'
        row={'ep_id':'999999','orderid':'SYNTHETIC-UPLOAD','symbol':'XBTUSD','direction':'Short','role':'Entry','qty':'5000000','event_time_assumed_utc':'2021-07-01T12:00:00Z','execution_price':'35000'}
        with fixture.open('w',encoding='utf-8',newline='') as f:w=csv.DictWriter(f,fieldnames=row);w.writeheader();w.writerow(row)
        calls=[]
        def fake_download(st,pair,start,end,progress):
            def opener(req,timeout):
                q=parse_qs(urlsplit(req.full_url).query);a=int(q['startTime'][0])//1000;b=(int(q['endTime'][0])+1)//1000;calls.append((a,b));rows=[]
                for t in range(a,b,60):
                    i=(t-base)//60;o=37000+150*math.sin(i/30)-i*.7;c=o+8*math.sin(i)
                    rows.append([t*1000,o,max(o,c)+12,min(o,c)-12,c,20+10*abs(math.sin(i/8)),t*1000+59999,0,1,0,0,0])
                return io.BytesIO(json.dumps(rows).encode())
            return fetch_window(st,pair,start,end,progress,opener=opener)
        server=AppServer(('127.0.0.1',0),store.directory);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with patch('aoa.server.fetch_window',fake_download),sync_playwright() as p:
                browser=p.chromium.launch();context=browser.new_context(viewport={'width':1440,'height':1050})
                context.add_init_script("localStorage.setItem('aoa.autoFill','0')")
                page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                try:
                    page.goto('http://127.0.0.1:'+str(server.server_address[1]),wait_until='networkidle')
                    wait_state(page,'window.AOAViewer?.snapshot().barCount>0')
                    expect(page.locator('[data-episode="CARRY-SYNTHETIC"]')).to_have_count(0)
                    assert page.evaluate('() => window.AOAViewer.snapshot().episode')=='3086'
                    assert page.evaluate('() => window.AOAViewer.snapshot().coverage.missing_minutes')==3
                    print('PASS entry-year default excludes carryover and recognizes exact missing minutes')
                    page.locator('#repairWindow').click()
                    wait_state(page,'window.AOAViewer.snapshot().coverage?.missing_minutes===0')
                    expect(page.locator('#repairWindow')).to_be_enabled()
                    assert calls==[(base+605*60,base+608*60)],calls
                    assert page.evaluate('() => window.AOAViewer.snapshot().markerCount')>0
                    print('PASS real browser -> gap-only downloader -> SQLite -> continuous chart')
                    original=page.evaluate('() => window.AOAViewer.snapshot().anchor')
                    page.locator('[data-tf="1m"]').click();expect(page.locator('#loading')).to_be_hidden()
                    wait_state(page,'window.AOAViewer.snapshot().tf==="1m" && window.AOAViewer.snapshot().barCount>0')
                    assert page.evaluate('() => window.AOAViewer.snapshot().anchor')==original
                    t=base+603*60
                    pt=page.evaluate('(t) => window.AOAViewer.pointForBar(t)',t);box=page.locator('#chart').bounding_box()
                    assert pt and pt['x'] is not None and pt['y'] is not None,pt
                    page.mouse.move(box['x']+pt['x'],box['y']+pt['y']);expect(page.locator('#hoverCard')).to_be_visible()
                    expect(page.locator('#ohlcv')).to_contain_text('%');expect(page.locator('#hoverCard')).to_contain_text('전봉 대비')
                    print('PASS actual mouse hover displays candle/previous/range percent and volume')
                    expect(page.locator('#episodeStats')).to_contain_text('감량 가격성과')
                    page.locator('#marginBox summary').click();page.locator('#marginInput').fill('2');page.locator('#saveMargin').click()
                    wait_state(page,'window.AOAViewer.snapshot().performance?.reference_roi_pct===61.5')
                    print('PASS explicit reference collateral ROI, without assumed leverage')
                    page.locator('#notesTab').click();page.locator('#noteText').fill('관측: 합성 회귀검증 <script>');page.locator('#saveNote').click();expect(page.locator('#noteState')).to_contain_text('저장')
                    page.reload(wait_until='networkidle');wait_state(page,'window.AOAViewer.snapshot().barCount>0')
                    page.locator('#notesTab').click();expect(page.locator('#noteText')).to_have_value('관측: 합성 회귀검증 <script>');page.locator('#timelineTab').click()
                    page.locator('[data-tf="1m"]').click();expect(page.locator('#loading')).to_be_hidden();wait_state(page,'window.AOAViewer.snapshot().tf==="1m"')
                    page.locator('#speed').select_option('5');page.locator('#play').click()
                    wait_state(page,'window.AOAViewer.snapshot().cutoff!=null')
                    cutoff=page.evaluate('() => window.AOAViewer.snapshot().cutoff')
                    wait_state(page,'window.AOAViewer.snapshot().cutoff>'+str(cutoff))
                    page.locator('#play').click();assert page.evaluate('() => window.AOAViewer.snapshot().visibleBarCount')>0
                    assert '1.230' not in page.locator('#episodeStats').inner_text()
                    assert page.evaluate('() => window.AOAViewer.snapshot().performance') is None
                    expect(page.locator('#export')).to_be_disabled();expect(page.locator('#marginBox')).to_be_hidden()
                    print('PASS Play advances from anchor with visible candles; future PNL/ROI hidden')
                    # The cut at 10:00 must not reveal an event at 10:00:00 (next bar opens).
                    page.evaluate("() => {let s=document.getElementById('replaySlider');s.value=59;s.dispatchEvent(new Event('input',{bubbles:true}));}")
                    assert page.evaluate('() => window.AOAViewer.snapshot().cutoff')==base+600*60
                    expect(page.locator('#eventList .event-item')).to_have_count(0)
                    page.locator('#step').click();expect(page.locator('#eventList .event-item')).to_have_count(1)
                    before=page.evaluate('() => window.AOAViewer.snapshot().cutoff')
                    page.locator('[data-tf="5m"]').click();expect(page.locator('#loading')).to_be_hidden()
                    wait_state(page,'window.AOAViewer.snapshot().tf==="5m"')
                    assert page.evaluate('() => window.AOAViewer.snapshot().cutoff')==before
                    print('PASS exact timestamp boundary and replay clock preserved across timeframes')
                    page.locator('#replayEnabled').uncheck();expect(page.locator('#export')).to_be_enabled()
                    page.locator('#year').select_option('2020');wait_state(page,'window.AOAViewer.snapshot().episode==="CARRY-SYNTHETIC"')
                    page.locator('#year').select_option('2021');wait_state(page,'window.AOAViewer.snapshot().episode==="3086"')
                    page.locator('#carry').check();wait_state(page,'window.AOAViewer.snapshot().episode==="CARRY-SYNTHETIC"')
                    expect(page.locator('#loading')).to_be_hidden()
                    assert page.evaluate('() => window.AOAViewer.snapshot().start')>=time_us('2021-01-01T00:00:00Z')//1_000_000
                    page.locator('#carry').uncheck();wait_state(page,'window.AOAViewer.snapshot().episode==="3086"')
                    page.locator('#year').select_option('2018');wait_state(page,'!window.AOAViewer.snapshot().episode');assert page.evaluate('() => window.AOAViewer.snapshot().barCount')==0
                    page.locator('#year').select_option('2021');wait_state(page,'window.AOAViewer.snapshot().barCount>0')
                    print('PASS year changes reselect, carryover is explicit, empty result clears old chart')
                    page.locator('#importOpen').click();page.locator('#files').set_input_files(fixture)
                    expect(page.locator('[data-episode="999999"]')).to_have_count(1);expect(page.locator('#files')).to_be_enabled();page.locator('#closeImport').click()
                    wait_state(page,'window.AOAViewer.snapshot().barCount>0')
                    page.evaluate("() => document.getElementById('chartTitle').textContent='SYNTHETIC REGRESSION TEST — not AOA historical trades'")
                    with page.expect_download() as dl:page.locator('#screenshot').click()
                    dl.value.save_as(OUT/'synthetic-v02-chart.png')
                    page.screenshot(path=str(OUT/'synthetic-v02-desktop.png'),full_page=True)
                    for width in (1280,1024,700):
                        page.set_viewport_size({'width':width,'height':1000});page.wait_for_timeout(150)
                        assert page.evaluate('() => document.documentElement.scrollWidth <= window.innerWidth+1'),width
                    page.screenshot(path=str(OUT/'synthetic-v02-responsive.png'),full_page=True)
                    assert not errors,errors
                    summary={'synthetic_only':True,'passed':['year_and_carryover','gap_repair_end_to_end','timeframe_anchor','mouse_hover_percent','reference_roi','notes_persistence','replay_advances','future_mask','exact_boundary','empty_filter','file_import','png_export','responsive_no_overflow'],'js_errors':errors}
                    (OUT/'browser-regressions.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
                    print('BROWSER_PASS',summary)
                except Exception:
                    print('DIAGNOSTICS',json.dumps({'errors':errors,'state':page.evaluate('() => window.AOAViewer?.snapshot()'),'toast':page.locator('#toast').inner_text()},ensure_ascii=False))
                    page.screenshot(path=str(OUT/'synthetic-v02-failure.png'),full_page=True);raise
                finally:browser.close()
        finally:server.shutdown();server.server_close();thread.join(timeout=5)

if __name__=='__main__':main()
