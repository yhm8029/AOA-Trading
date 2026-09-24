"""End-to-end Chromium test against a real local server and the official chart JS.

Every chart in this test is SYNTHETIC. Screenshots must not be advertised as
actual AOA records or as proof of complete private-dataset reconciliation.
"""
from __future__ import annotations
import json
import sys
import tempfile
import threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright,expect
from aoa.server import LocalServer
from aoa.store import Store
from tests.fixtures import package
from prepare_assets import ensure_assets

ROOT=Path(__file__).resolve().parents[1]
ART=ROOT/'artifacts'


def main():
    ART.mkdir(exist_ok=True)
    ensure_assets()
    checks=[]
    def done(name):
        checks.append(name);print('PASS '+name,flush=True)
    with tempfile.TemporaryDirectory() as temp:
        path=Path(temp)
        fixture=package(path/'SYNTHETIC-not-AOA.zip')
        store=Store(path/'local'/'aoa.sqlite3')
        server=LocalServer(('127.0.0.1',0),store,path/'local')
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch()
                context=browser.new_context(viewport={'width':1600,'height':1050},device_scale_factor=1)
                page=context.new_page();errors=[];external=[]
                page.on('pageerror',lambda error:errors.append(str(error)))
                page.on('request',lambda request:external.append(request.url) if request.url.startswith('http') and not request.url.startswith(('http://127.0.0.1:','http://localhost:')) else None)
                page.goto(f'http://127.0.0.1:{server.server_address[1]}',wait_until='networkidle')
                page.wait_for_function('window.__AOA !== undefined')
                expect(page.locator('#empty-state')).to_be_visible()
                done('empty app has no fabricated trades')
                page.locator('#empty-import').click()
                page.locator('#file-input').set_input_files(str(fixture))
                page.locator('#upload-files').click()
                page.wait_for_function('window.__AOA.state.episodes.length === 2 && window.__AOA.state.chartMeta?.valid > 0',timeout=90000)
                page.wait_for_function("document.querySelector('#upload-files').disabled === false")
                page.locator('#import-dialog .dialog-close').click()
                expect(page.locator('#chart-title')).to_contain_text('900001')
                assert page.locator('#chart canvas').count()>=4
                assert page.evaluate('window.__AOA.chart.panes().length')==2
                done('ZIP upload -> SQLite import -> candles and volume render')
                assert page.evaluate('window.__AOA.state.groups.length')>0
                assert page.evaluate('window.__AOA.state.groups.some(g=>g.marker.position === "aboveBar")')
                assert page.evaluate('window.__AOA.state.groups.some(g=>g.marker.position === "belowBar")')
                done('trade arrows above/below actual timeframe candles')
                page.locator('.event-row').nth(1).click()
                page.wait_for_function('window.__AOA.state.selected?.source_orderid === "SYNTHETIC-order-002"')
                page.wait_for_function("document.querySelector('#event-volume-box')?.textContent.includes('직전 완성 1분')")
                expect(page.locator('#event-detail')).to_contain_text('그룹 VWAP')
                expect(page.locator('#event-detail')).to_contain_text('사후')
                done('timeline click zooms + separate first/VWAP and volume timing')
                page.locator('[data-tf="1"]').click()
                page.wait_for_function('window.__AOA.state.chartMeta.timeframe === 1')
                page.locator('[data-tf="60"]').click()
                page.wait_for_function('window.__AOA.state.chartMeta.timeframe === 60')
                page.locator('[data-tf="5"]').click()
                page.wait_for_function('window.__AOA.state.chartMeta.timeframe === 5')
                done('1m / 5m / 1h changes preserve trade times')
                page.locator('#timezone').select_option('Asia/Seoul')
                expect(page.locator('#event-detail')).to_contain_text('10:02:30')
                page.locator('#timezone').select_option('UTC')
                done('UTC/KST display conversion')
                page.locator('#min-qty').fill('999')
                expect(page.locator('.event-row')).to_have_count(0)
                page.locator('#min-qty').fill('0')
                expect(page.locator('.event-row')).to_have_count(4)
                done('minimum size filter')
                page.locator('#tab-notes').click()
                note='<img src=x onerror="window.bad=true"> 관측/가설 분리'
                page.locator('#note-body').fill(note)
                page.locator('#save-note').click()
                expect(page.locator('#note-status')).to_contain_text('버전 1')
                page.reload(wait_until='networkidle')
                page.wait_for_function('window.__AOA?.state.chartMeta?.valid > 0')
                page.locator('#tab-notes').click()
                expect(page.locator('#note-body')).to_have_value(note)
                assert not page.evaluate('Boolean(window.bad)')
                page.locator('#tab-events').click()
                done('research notes persist, imported HTML is not executed')
                page.locator('#theme-toggle').click()
                expect(page.locator('body')).to_have_class('dark')
                page.locator('#theme-toggle').click()
                done('light and dark themes')
                page.locator('#fit-episode').click()
                page.wait_for_function('window.__AOA.state.chartMeta?.valid > 0')
                page.locator('.mode-badge').evaluate("e=>{e.textContent='SYNTHETIC TEST DATA — NOT AOA';e.style.color='#c62828';}")
                with page.expect_download() as d:
                    page.locator('#snapshot').click()
                download=d.value;download.save_as(str(ART/'synthetic-chart-export.png'))
                assert (ART/'synthetic-chart-export.png').stat().st_size>10000
                done('PNG chart screenshot export')
                with page.expect_download() as d:
                    page.locator('#export-events').click()
                d.value.save_as(str(path/'export.csv'))
                assert 'SYNTHETIC-order-001' in (path/'export.csv').read_text(encoding='utf-8-sig')
                done('selected episode CSV export')
                page.screenshot(path=str(ART/'ui-synthetic-desktop.png'),full_page=True)
                page.locator('#next-episode').click()
                page.wait_for_function('window.__AOA.state.ep?.episode_id === "900002" && window.__AOA.state.events.length === 2')
                expect(page.locator('#event-count')).to_contain_text('2 / 2')
                done('previous/next episode navigation')
                page.set_viewport_size({'width':430,'height':932})
                page.wait_for_timeout(300)
                page.screenshot(path=str(ART/'ui-synthetic-mobile.png'),full_page=True)
                assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 2')
                done('responsive mobile layout without horizontal overflow')
                assert not errors,errors
                assert not external,external
                done('no JavaScript runtime errors or external app-data requests')
                context.close();browser.close()
        finally:
            server.shutdown();server.server_close();thread.join()
    report={'status':'passed','data':'SYNTHETIC TESTS ONLY - NOT PRIVATE AOA DATA',
            'browser':'Chromium','checks':checks,'count':len(checks)}
    (ART/'browser-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
