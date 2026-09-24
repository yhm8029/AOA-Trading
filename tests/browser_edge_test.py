"""Synthetic regression: empty higher-timeframe replay and fast navigation."""
import json
import tempfile
import threading
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
from aoa.server import AppServer
from aoa.model import time_us
from tests.seed_ci import seed
from tests.browser_test import wait_state

OUT=Path('test-results');OUT.mkdir(exist_ok=True)

def main():
    with tempfile.TemporaryDirectory() as td:
        store=seed(td);entry=time_us('2021-06-04T10:00:00Z')//1_000_000
        # One real-in-format synthetic minute cannot form any complete 5m/1h candle.
        with store.connect() as db:db.execute('DELETE FROM candles WHERE t<>?',(entry,))
        server=AppServer(('127.0.0.1',0),store.directory);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch();context=browser.new_context(viewport={'width':1280,'height':1000})
                context.add_init_script("localStorage.setItem('aoa.autoFill','0')")
                page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                try:
                    page.goto('http://127.0.0.1:'+str(server.server_address[1]),wait_until='networkidle')
                    wait_state(page,'window.AOAViewer?.snapshot().episode==="3086" && !window.AOAViewer.snapshot().loading')
                    assert page.evaluate('() => window.AOAViewer.snapshot().barCount')==0
                    page.locator('#play').click();page.locator('#backStep').click()
                    assert page.evaluate('() => window.AOAViewer.snapshot().cutoff') is None
                    page.locator('[data-tf="1m"]').click()
                    wait_state(page,'window.AOAViewer.snapshot().barCount===1 && !window.AOAViewer.snapshot().loading')
                    page.locator('#replayStart').click();cutoff=page.evaluate('() => window.AOAViewer.snapshot().cutoff')
                    assert cutoff==entry+60
                    page.locator('#backStep').click();assert page.evaluate('() => window.AOAViewer.snapshot().cutoff')==cutoff
                    page.locator('[data-tf="1h"]').click()
                    wait_state(page,'window.AOAViewer.snapshot().tf==="1h" && !window.AOAViewer.snapshot().loading')
                    assert page.evaluate('() => window.AOAViewer.snapshot().barCount')==0
                    page.locator('#backStep').click();page.locator('#step').click();page.locator('#play').click()
                    assert page.evaluate('() => window.AOAViewer.snapshot().cutoff')==cutoff
                    assert page.evaluate('() => window.AOAViewer.snapshot().performance') is None
                    expect(page.locator('#replaySlider')).to_be_disabled()
                    print('PASS empty higher timeframe never crashes back/next/play or changes the replay clock')
                    # Trigger rapid timeframe requests, then make the selected year empty.
                    page.evaluate("() => {document.querySelector('[data-tf=\"4h\"]').click();document.querySelector('[data-tf=\"5m\"]').click();document.querySelector('[data-tf=\"1m\"]').click();let y=document.getElementById('year');y.value='2018';y.dispatchEvent(new Event('change',{bubbles:true}));}")
                    wait_state(page,'!window.AOAViewer.snapshot().episode && !window.AOAViewer.snapshot().loading')
                    page.wait_for_timeout(200)
                    assert page.evaluate('() => window.AOAViewer.snapshot().barCount')==0
                    assert not errors,errors
                    summary={'synthetic_only':True,'passed':['empty_play','first_bar_back_guard','empty_higher_timeframe','retained_cutoff','fast_navigation_stale_response_guard'],'js_errors':errors}
                    (OUT/'browser-edge-regressions.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
                    print('BROWSER_EDGE_PASS',summary)
                except Exception:
                    print('EDGE_DIAGNOSTICS',errors,page.evaluate('() => window.AOAViewer?.snapshot()'))
                    page.screenshot(path=str(OUT/'synthetic-edge-failure.png'),full_page=True);raise
                finally:browser.close()
        finally:server.shutdown();server.server_close();thread.join(timeout=5)

if __name__=='__main__':main()
