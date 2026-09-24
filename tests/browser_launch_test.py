"""Actual subprocess launch while an older HTTP service keeps its port.

Synthetic trades only. This suite is also run against the EXTRACTED release ZIP,
not solely against the repository worktree.
"""
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
from tests.seed_ci import seed
from tests.browser_test import wait_state
from aoa.version import VERSION

OUT=Path('test-results');OUT.mkdir(exist_ok=True)
ROOT=Path(__file__).resolve().parent.parent

class OldHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        raw=b'<html><body>OLD AOA SYNTHETIC SERVER</body></html>'
        self.send_response(200);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    def log_message(self,*args):pass


def main():
    with tempfile.TemporaryDirectory() as td:
        base=Path(td);source=seed(base/'old-data');source.save_note('3086','이전 앱 메모 보존','SYNTHETIC')
        old=ThreadingHTTPServer(('127.0.0.1',0),OldHandler)
        thread=threading.Thread(target=old.serve_forever,daemon=True);thread.start()
        data=base/'new-data';log=base/'launch.log';proc=None
        try:
            with log.open('w',encoding='utf-8') as output:
                proc=subprocess.Popen([sys.executable,str(ROOT/'run.py'),'--no-browser','--skip-vendor','--port',str(old.server_port),'--data-dir',str(data),'--copy-data-from',str(source.directory)],cwd=ROOT,stdout=output,stderr=subprocess.STDOUT,env={**os.environ,'PYTHONUTF8':'1','PYTHONUNBUFFERED':'1'})
                deadline=time.monotonic()+45
                while not (data/'last-launch.json').exists():
                    if proc.poll() is not None or time.monotonic()>deadline:raise AssertionError(log.read_text(encoding='utf-8'))
                    time.sleep(.1)
                launch=json.loads((data/'last-launch.json').read_text(encoding='utf-8'))
                assert launch['version']==VERSION
                assert launch['runtime']['port']!=old.server_port
                assert launch['runtime']['app_dir']==str(ROOT)
                with urllib.request.urlopen(f'http://127.0.0.1:{old.server_port}') as r:assert b'OLD AOA' in r.read()
                with sync_playwright() as p:
                    browser=p.chromium.launch();context=browser.new_context(viewport={'width':1500,'height':1000})
                    context.add_init_script("localStorage.setItem('aoa.autoFill','0')")
                    page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                    try:
                        page.goto(launch['url'],wait_until='networkidle')
                        wait_state(page,'window.AOALaunchState?.verified && window.AOAViewer?.snapshot().barCount>0')
                        expect(page.locator('#version')).to_have_text('v'+VERSION)
                        expect(page.locator('#runtimeInfo summary')).to_have_text('실행 확인 v'+VERSION)
                        assert page.evaluate('window.AOAViewer.snapshot().markerCount')>0
                        expect(page.locator('#studyPanel')).to_contain_text('왜 이 시점인가')
                        page.locator('#notesTab').click();expect(page.locator('#noteText')).to_have_value('이전 앱 메모 보존');page.locator('#timelineTab').click()
                        page.locator('#pauseOnEvent').uncheck();page.locator('#play').click()
                        wait_state(page,'window.AOAViewer.snapshot().cutoff!=null')
                        before=page.evaluate('window.AOAViewer.snapshot().cutoff')
                        wait_state(page,f'window.AOAViewer.snapshot().cutoff>{before}')
                        page.locator('#play').click()
                        page.locator('#replayEnabled').uncheck()
                        assert not errors,errors
                        page.evaluate("document.getElementById('chartTitle').textContent='SYNTHETIC startup regression — not AOA historical trades'")
                        page.screenshot(path=str(OUT/'synthetic-v031-launch-verified.png'),full_page=True)
                        for width in (1280,1024,700):
                            page.set_viewport_size({'width':width,'height':1000});page.wait_for_timeout(120)
                            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),width
                        # A stale launch identity must block the interface, NOT open old data.
                        page.goto(launch['url'].split('?')[0]+'?launch=stale-synthetic-instance',wait_until='networkidle')
                        expect(page.locator('#versionWarning')).to_contain_text('오래된 주소')
                        assert page.evaluate('window.AOALaunchState.verified') is False
                        assert page.evaluate("document.querySelector('.workspace').inert") is True
                        result={'synthetic_only':True,'version':VERSION,'packaged':(ROOT/'release-manifest.json').exists(),
                                'passed':['occupied_old_port_kept_alive','new_process_verified','existing_data_snapshot','notes_preserved','markers_and_study','replay_advances','old_instance_blocked','responsive_layout'],
                                'full_user_dataset_audit':False}
                        (OUT/'launch-regressions.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print('LAUNCH_BROWSER_PASS',result)
                    finally:browser.close()
        finally:
            if proc is not None:
                proc.terminate()
                try:proc.wait(timeout=10)
                except subprocess.TimeoutExpired:proc.kill();proc.wait()
            old.shutdown();old.server_close();thread.join()
            if log.exists():print(log.read_text(encoding='utf-8'))

if __name__=='__main__':main()
