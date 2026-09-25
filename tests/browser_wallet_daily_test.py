"""Real CSV column/time SHAPE; synthetic balances/orders, no private user data."""
import json,tempfile,threading
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
from aoa.server import AppServer
from aoa.store import Store
from aoa.performance_ledger import put_summary
from tests.test_performance_ledger import orders
from tests.test_wallet_daily import wallet_bytes
from tests.browser_test import wait_state

OUT=Path('test-results');OUT.mkdir(exist_ok=True)
def main():
    with tempfile.TemporaryDirectory() as td:
        server=AppServer(('127.0.0.1',0),Path(td)/'data');s=server.store;ev=orders();start=ev[0]['time']
        with s.connect() as db:
            for e in ev:Store.order(db,e,'SYNTHETIC')
            for t in range(start-3*86400,start+3*86400,60):Store.candle(db,('BTCUSDT',t,100,101,99,100,10),'SYNTHETIC')
            put_summary(db,{'episode_id':'SYNTH','symbol':'XBTUSD','direction':'Long','start':'2021-01-01T00:00:00Z','end':'2021-01-01T00:05:00Z','entry_qty':300,'exit_qty':300,'net_pnl_btc':.97},'SYNTHETIC')
        s.save_note('SYNTH','KEEP','synthetic')
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch();ctx=browser.new_context(viewport={'width':1600,'height':1100})
                ctx.add_init_script("localStorage.setItem('aoa.autoFill','0')")
                page=ctx.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                try:
                    page.goto('http://127.0.0.1:'+str(server.server_port),wait_until='networkidle')
                    wait_state(page,'window.AOAViewer?.snapshot().episode==="SYNTH" && !window.AOAViewer.snapshot().loading')
                    expect(page.locator('#positionOutcome')).to_contain_text('시드 미연결')
                    page.locator('#importOpen').click()
                    page.locator('#files').set_input_files({'name':'SYNTHETIC-aoa-wallet.csv','mimeType':'text/csv','buffer':wallet_bytes()})
                    wait_state(page,'window.AOAViewer.snapshot().performance?.seed_initial?.btc===100')
                    page.locator('#closeImport').click()
                    expect(page.locator('#positionOutcome')).to_contain_text('+0.970%')
                    expect(page.locator('#positionOutcome')).to_contain_text('이전 기록일 마감 잔고')
                    expect(page.locator('#positionOutcome')).to_contain_text('2020-12-31')
                    expect(page.locator('#dbStatus')).to_contain_text('일별 3일')
                    expect(page.locator('#eventList')).to_contain_text('전일잔고')
                    expect(page.locator('#eventList')).to_contain_text('1.00%')
                    page.locator('#notesTab').click();expect(page.locator('#noteText')).to_have_value('KEEP');page.locator('#timelineTab').click()
                    page.locator('[data-tf="1m"]').click();wait_state(page,'window.AOAViewer.snapshot().tf==="1m" && !window.AOAViewer.snapshot().loading')
                    page.locator('#replayStart').click()
                    expect(page.locator('#positionOutcome')).to_contain_text('청산 후 공개')
                    expect(page.locator('#positionOutcome')).not_to_contain_text('+0.970%')
                    page.locator('#replayEnabled').uncheck()
                    page.reload(wait_until='networkidle')
                    wait_state(page,'window.AOAViewer?.snapshot().performance?.seed_initial?.btc===100')
                    expect(page.locator('#positionOutcome')).to_contain_text('+0.970%')
                    assert not errors,errors
                    page.evaluate("document.getElementById('chartTitle').textContent='SYNTHETIC wallet date-format regression — not AOA trades'")
                    page.screenshot(path=str(OUT/'synthetic-wallet-date-v041.png'),full_page=True)
                    report={'synthetic_only':True,'original_time_shape':'date + incomplete mm:ss fraction','passed':['CSV_import','daily_ledger_validation','past_day_seed','BTC_and_percent','seed_labels','same_database_notes','replay_future_hidden','reload_persistence'],'errors':errors,'full_original_wallet_audit':False}
                    (OUT/'wallet-daily-browser.json').write_text(json.dumps(report,indent=2));print('WALLET_DAILY_BROWSER_PASS',report)
                except Exception:
                    print('WALLET_DIAGNOSTICS',errors,page.evaluate('window.AOAViewer?.snapshot()'))
                    page.screenshot(path=str(OUT/'wallet-daily-failure.png'),full_page=True);raise
                finally:browser.close()
        finally:server.shutdown();server.server_close();thread.join(timeout=5)
if __name__=='__main__':main()
