"""Browser integration against synthetic data only. Production CSP stays enabled."""
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
from tests.seed_ci import seed
from tests.test_import import csv_bytes
from tests.test_model import order

out=Path('test-results');out.mkdir(exist_ok=True)
directory=out/'ci-local-data';seed(directory)
fixture=out/'synthetic-upload.csv'
fixture.write_bytes(csv_bytes([order(ep_id='999999',orderid='SYNTHETIC-UPLOAD',execution_price='37000')]))
server=subprocess.Popen([sys.executable,'-u','run.py','--data-dir',str(directory),'--port','8876','--no-browser','--skip-vendor'])

def wait_state(page,expression,timeout=30):
    # wait_for_function internally evals source and is blocked by a strict page CSP.
    # DevTools callFunctionOn evaluates this function without adding unsafe-eval to the app.
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        if page.evaluate('() => Boolean('+expression+')'):
            return
        time.sleep(.1)
    raise AssertionError('Browser state not reached: '+expression)

try:
    for i in range(60):
        try:urllib.request.urlopen('http://127.0.0.1:8876/api/status',timeout=1).close();break
        except Exception:time.sleep(.2)
    with sync_playwright() as p:
        browser=p.chromium.launch()
        page=browser.new_page(viewport={'width':1600,'height':1000},device_scale_factor=1)
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        try:
            page.goto('http://127.0.0.1:8876/',wait_until='networkidle')
            wait_state(page,'window.AOAViewer && window.AOAViewer.snapshot().barCount > 0')
            wait_state(page,'window.AOAViewer.snapshot().markerCount > 0')
            page.locator('#importOpen').click();page.locator('#files').set_input_files(fixture)
            wait_state(page,'document.getElementById("jobProgress").value === 100')
            expect(page.locator('[data-episode="999999"]')).to_have_count(1)
            page.locator('#closeImport').click()
            page.locator('[data-episode="3086"]').click()
            wait_state(page,'window.AOAViewer.snapshot().episode === "3086" && window.AOAViewer.snapshot().markerCount > 0')
            page.locator('[data-tf="1m"]').click()
            expect(page.locator('#loading')).to_be_hidden()
            wait_state(page,'window.AOAViewer.snapshot().tf === "1m" && window.AOAViewer.snapshot().barCount > 0')
            page.locator('.event-item').first.click()
            page.locator('#notesTab').click();page.locator('#noteText').fill('관측: 테스트 메모 <script>');page.locator('#saveNote').click()
            expect(page.locator('#noteState')).to_contain_text('저장')
            page.reload(wait_until='networkidle');wait_state(page,'window.AOAViewer.snapshot().barCount > 0')
            page.locator('#notesTab').click();expect(page.locator('#noteText')).to_have_value('관측: 테스트 메모 <script>')
            page.locator('#timelineTab').click();page.locator('#endpoint').select_option('last');page.locator('#replayEnabled').check()
            expect(page.locator('#endpoint')).to_have_value('first')
            assert '1.230' not in page.locator('#episodeStats').inner_text()
            expect(page.locator('#export')).to_be_disabled()
            page.locator('#step').click();assert page.evaluate('() => window.AOAViewer.snapshot().cutoff') is not None
            page.locator('#replayEnabled').uncheck();expect(page.locator('#export')).to_be_enabled()
            page.evaluate("() => document.getElementById('chartTitle').textContent='SYNTHETIC TEST DATA — not AOA historical trades'")
            with page.expect_download() as dl:page.locator('#screenshot').click()
            dl.value.save_as(out/'synthetic-chart-export.png')
            page.evaluate("() => document.querySelector('.brand small').textContent='AUTOMATED TEST · 합성 데이터 (고래 실거래 아님)'")
            page.screenshot(path=str(out/'synthetic-ui-desktop.png'),full_page=True)
            page.set_viewport_size({'width':700,'height':950});page.screenshot(path=str(out/'synthetic-ui-small.png'),full_page=True)
            assert not errors,errors
            print('BROWSER_PASS: import UI, chart, markers, timeframe, event focus, notes persistence, replay masking, PNG export')
        except Exception:
            print('BROWSER_DIAGNOSTICS',json.dumps({'errors':errors,'toast':page.locator('#toast').inner_text(),'job':page.locator('#jobStatus').inner_text()},ensure_ascii=False))
            page.screenshot(path=str(out/'synthetic-failure.png'),full_page=True)
            raise
        finally:
            browser.close()
finally:
    server.terminate();server.wait(timeout=10)
