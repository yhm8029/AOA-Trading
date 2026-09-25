"""Synthetic account/contract integration, including ZIP upload and replay."""
import io,json,tempfile,threading,zipfile
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
            for e in ev:
                e['episode_pnl_btc']=.97;Store.order(db,e,'SYNTHETIC-ONLY')
            for t in range(start-3*86400,start+3*86400,60):Store.candle(db,('BTCUSDT',t,100,101,99,100,10),'SYNTHETIC-ONLY')
        s.save_note('SYNTH','DO NOT DELETE','synthetic')
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch();ctx=browser.new_context(viewport={'width':1650,'height':1200})
                ctx.add_init_script("localStorage.setItem('aoa.autoFill','0')")
                page=ctx.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                try:
                    page.goto('http://127.0.0.1:'+str(server.server_port),wait_until='networkidle')
                    wait_state(page,'window.AOAViewer?.snapshot().episode==="SYNTH" && !window.AOAViewer.snapshot().loading')
                    expect(page.locator('#positionOutcome')).to_contain_text('시드 미연결')
                    buf=io.BytesIO()
                    with zipfile.ZipFile(buf,'w') as z:
                        z.writestr('aoa-wallet-2018-03-01-2021-12-31.csv','timestamp,transactid,transactstatus,transacttype,currency,walletbalance\n2020-12-31T23:59:00Z,a,Completed,RealisedPNL,XBt,10000000000\n2021-01-01T00:00:30Z,b,Completed,RealisedPNL,XBt,8000000000\n2021-01-01T00:00:40Z,c,Canceled,Withdrawal,XBt,0\n')
                    page.locator('#seedImport').click();page.locator('#files').set_input_files({'name':'SYNTHETIC-original-wallet.zip','mimeType':'application/zip','buffer':buf.getvalue()})
                    wait_state(page,'window.AOAViewer.snapshot().performance?.seed_return_pct===0.97')
                    page.locator('#closeImport').click()
                    expect(page.locator('#positionOutcome .seed-outcome')).to_contain_text('+0.970%')
                    expect(page.locator('#positionOutcome .seed-outcome')).to_contain_text('미실현손익 제외')
                    expect(page.locator('#positionOutcome')).to_contain_text('0.970000')
                    expect(page.locator('#episodeList .seed-return')).to_contain_text('0.970%')
                    page.locator('#eventList .event-item').nth(1).click()
                    expect(page.locator('#seedPanel')).to_contain_text('1.25%')
                    expect(page.locator('#seedPanel')).to_contain_text('실제 증거금')
                    page.locator('#seedMode').select_option('current')
                    expect(page.locator('#eventList .event-item').nth(1)).to_contain_text('1.25%')
                    page.locator('#eventList .event-item').nth(2).click()
                    expect(page.locator('#seedPanel')).to_contain_text('100.00%')
                    page.locator('#notesTab').click();expect(page.locator('#noteText')).to_have_value('DO NOT DELETE');page.locator('#timelineTab').click()
                    page.locator('#entryFocus').click()
                    page.locator('[data-tf="1m"]').click();wait_state(page,'window.AOAViewer.snapshot().tf==="1m" && !window.AOAViewer.snapshot().loading')
                    page.locator('#pauseOnEvent').uncheck();page.locator('#speed').select_option('10');page.locator('#replayStart').click()
                    expect(page.locator('#positionOutcome')).to_contain_text('청산 후 공개')
                    expect(page.locator('#positionOutcome')).not_to_contain_text('0.970%')
                    expect(page.locator('#episodeList')).not_to_contain_text('0.970%')
                    page.locator('#play').click();wait_state(page,'window.AOAViewer.snapshot().cutoff>'+str(end))
                    page.locator('#play').click();expect(page.locator('#positionOutcome')).to_contain_text('0.970%')
                    page.locator('#replayEnabled').uncheck();page.reload(wait_until='networkidle')
                    wait_state(page,'window.AOAViewer?.snapshot().performance?.seed_return_pct===0.97')
                    expect(page.locator('#seedMode')).to_have_value('current')
                    for width in (1280,1024,700):
                        page.set_viewport_size({'width':width,'height':1100});page.wait_for_timeout(150)
                        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),width
                    page.set_viewport_size({'width':1650,'height':1200})
                    page.evaluate("document.getElementById('chartTitle').textContent='SYNTHETIC seed-sizing test — not AOA historical data'")
                    page.screenshot(path=str(OUT/'synthetic-seed-v040.png'),full_page=True)
                    assert not errors,errors
                    report={'synthetic_only':True,'full_user_data_audit':False,'checks':['wallet_zip_import','XBt_units','cancelled_withdrawal_ignored','BTC_and_seed_pct','sidebar_seed_pct','initial_vs_order_seed','reduced_fraction','notes_preserved','replay_hides_future_result','reveal_at_close','persistence','responsive'],'errors':errors}
                    (OUT/'seed-browser.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print('SEED_BROWSER_PASS',report)
                except Exception:
                    print('SEED_DIAGNOSTICS',errors,page.evaluate('window.AOAViewer?.snapshot()'))
                    page.screenshot(path=str(OUT/'seed-failure.png'),full_page=True);raise
                finally:browser.close()
        finally:server.shutdown();server.server_close();thread.join(timeout=5)
if __name__=='__main__':main()
