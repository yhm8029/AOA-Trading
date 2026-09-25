"""Synthetic integration: import -> exact net percent -> replay reveal -> persistence."""
import csv,io,json,tempfile,threading
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
from aoa.server import AppServer
from aoa.store import Store
from tests.test_performance_ledger import orders
from tests.browser_test import wait_state
OUT=Path('test-results');OUT.mkdir(exist_ok=True)

def main():
    with tempfile.TemporaryDirectory() as td:
        server=AppServer(('127.0.0.1',0),Path(td)/'data');s=server.store;ev=orders();start=ev[0]['time'];end=ev[-1]['end_time']
        with s.connect() as db:
            for e in ev:Store.order(db,e,'SYNTHETIC-ONLY')
            for t in range(start-3*86400,start+3*86400,60):Store.candle(db,('BTCUSDT',t,100,101,99,100,10),'SYNTHETIC-ONLY')
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch();ctx=browser.new_context(viewport={'width':1600,'height':1100});ctx.add_init_script("localStorage.setItem('aoa.autoFill','0')")
                page=ctx.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                try:
                    page.goto('http://127.0.0.1:'+str(server.server_port),wait_until='networkidle')
                    wait_state(page,'window.AOAViewer?.snapshot().episode==="SYNTH" && !window.AOAViewer.snapshot().loading')
                    expect(page.locator('#positionOutcome')).to_contain_text('손익자료 연결')
                    text=io.StringIO();w=csv.writer(text);w.writerow(['episode_id','symbol','direction','start','end','entry_qty','exit_qty','gross_pnl_btc','trade_fee_btc','funding_fee_btc','net_pnl_btc']);w.writerow(['SYNTH','XBTUSD','Long','2021-01-01T00:00:00Z','2021-01-01T00:05:00Z',300,300,1,.01,.02,.97])
                    page.locator('#importOpen').click();page.locator('#files').set_input_files({'name':'SYNTHETIC-episodes.csv','mimeType':'text/csv','buffer':text.getvalue().encode()})
                    wait_state(page,'window.AOAViewer.snapshot().performance?.net_return_pct===48.5')
                    page.locator('#closeImport').click()
                    expect(page.locator('#positionOutcome')).to_contain_text('+48.500%')
                    expect(page.locator('#positionOutcome')).to_contain_text('0.970000')
                    expect(page.locator('.episode-return')).to_contain_text('48.500')
                    page.locator('#result').select_option('Win');wait_state(page,'!window.AOAViewer.snapshot().loading');expect(page.locator('#episodeList .episode-item')).to_have_count(1)
                    page.locator('[data-tf="1m"]').click();wait_state(page,'window.AOAViewer.snapshot().tf==="1m" && !window.AOAViewer.snapshot().loading')
                    page.locator('#pauseOnEvent').uncheck();page.locator('#speed').select_option('10');page.locator('#replayStart').click()
                    expect(page.locator('#positionOutcome')).to_contain_text('청산 후 공개');expect(page.locator('#positionOutcome')).not_to_contain_text('48.500')
                    assert page.evaluate('window.AOAViewer.snapshot().performance') is None
                    page.locator('#play').click();wait_state(page,'window.AOAViewer.snapshot().cutoff>'+str(end))
                    page.locator('#play').click();expect(page.locator('#positionOutcome')).to_contain_text('48.500')
                    page.locator('#replayEnabled').uncheck();page.reload(wait_until='networkidle')
                    wait_state(page,'window.AOAViewer?.snapshot().performance?.net_return_pct===48.5')
                    page.evaluate("document.getElementById('chartTitle').textContent='SYNTHETIC net-return test — not actual AOA trades'")
                    page.screenshot(path=str(OUT/'synthetic-net-return-v032.png'),full_page=True)
                    for width in (1280,1024,700):
                        page.set_viewport_size({'width':width,'height':1000});page.wait_for_timeout(150)
                        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),width
                    assert not errors,errors
                    report={'synthetic_only':True,'passed':['summary_import','net_after_costs','inverse_entry_turnover','sidebar_net_return','result_filter','hide_future_PNL','reveal_at_final_close','persistence','responsive'],'errors':errors}
                    (OUT/'net-return-browser.json').write_text(json.dumps(report,indent=2));print('PNL_BROWSER_PASS',report)
                except Exception:
                    print('PNL_DIAGNOSTICS',errors,page.evaluate('window.AOAViewer?.snapshot()'))
                    page.screenshot(path=str(OUT/'pnl-failure.png'),full_page=True);raise
                finally:browser.close()
        finally:server.shutdown();server.server_close();thread.join(timeout=5)
if __name__=='__main__':main()
