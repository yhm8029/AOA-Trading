"""Browser integration test against synthetic fixtures only; chart PNG stored as CI artifact."""
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright
from tests.seed_ci import seed

out=Path('test-results');out.mkdir(exist_ok=True)
directory=out/'ci-local-data';seed(directory)
server=subprocess.Popen([sys.executable,'run.py','--data-dir',str(directory),'--port','8876','--no-browser','--skip-vendor'])
try:
    for i in range(60):
        try:
            urllib.request.urlopen('http://127.0.0.1:8876/api/status',timeout=1).close();break
        except Exception: time.sleep(.2)
    with sync_playwright() as p:
        browser=p.chromium.launch()
        page=browser.new_page(viewport={'width':1600,'height':1000},device_scale_factor=1)
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto('http://127.0.0.1:8876/',wait_until='networkidle')
        page.wait_for_function('window.AOAViewer && window.AOAViewer.snapshot().barCount > 0')
        page.wait_for_function('window.AOAViewer.snapshot().markerCount > 0')
        page.locator('[data-tf="1m"]').click()
        page.wait_for_function('window.AOAViewer.snapshot().tf === "1m" && window.AOAViewer.snapshot().barCount > 0')
        page.locator('.event-item').first.click()
        page.locator('#notesTab').click();page.locator('#noteText').fill('관측: 테스트 메모 <script>');page.locator('#saveNote').click()
        page.wait_for_function('document.getElementById("noteState").textContent.includes("저장")')
        page.reload(wait_until='networkidle');page.wait_for_function('window.AOAViewer.snapshot().barCount > 0')
        page.locator('#notesTab').click();assert page.locator('#noteText').input_value()=='관측: 테스트 메모 <script>'
        page.locator('#timelineTab').click();page.locator('#replayEnabled').check()
        assert page.locator('#episodeStats').inner_text().find('1.230')<0
        page.locator('#step').click();assert page.evaluate('window.AOAViewer.snapshot().cutoff') is not None
        page.locator('#replayEnabled').uncheck()
        with page.expect_download() as dl:
            page.locator('#screenshot').click()
        dl.value.save_as(out/'synthetic-chart-export.png')
        page.evaluate("document.querySelector('.brand small').textContent='AUTOMATED TEST · 합성 데이터 (고래 실거래 아님)'")
        page.screenshot(path=str(out/'synthetic-ui-desktop.png'),full_page=True)
        page.set_viewport_size({'width':700,'height':950});page.screenshot(path=str(out/'synthetic-ui-small.png'),full_page=True)
        assert not errors,errors
        print('BROWSER_PASS: chart, markers, timeframe, event focus, note persistence, replay masking, PNG export')
        browser.close()
finally:
    server.terminate();server.wait(timeout=10)
