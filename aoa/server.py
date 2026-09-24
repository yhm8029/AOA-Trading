from __future__ import annotations
import csv
import hashlib
import io
import json
import mimetypes
import os
import secrets
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs, unquote
from .study import StudyStore as Store
from .review import missing_plan
from .model import TIMEFRAMES
from .importer import import_file
from .market import fetch_window
from .version import VERSION, APP_ID

ROOT=Path(__file__).resolve().parent.parent
MAX_UPLOAD=512*1024*1024

class JobCancelled(Exception):
    pass

class AppServer(ThreadingHTTPServer):
    daemon_threads=True
    # Avoid a second Windows listener silently taking over an occupied port.
    allow_reuse_address=False
    def __init__(self,address,directory):
        super().__init__(address,Handler)
        try:
            self.store=Store(directory)
            self.token=secrets.token_urlsafe(32)
            self.job={'state':'idle'}
            self.job_lock=threading.Lock()
            self.cancel_event=threading.Event()
            self.runtime={'application':APP_ID,'version':VERSION,'instance':secrets.token_hex(16),
                          'pid':os.getpid(),'app_dir':str(ROOT.resolve()),
                          'data_dir':str(self.store.directory.resolve()),
                          'port':self.server_address[1],
                          'ui_sha256':hashlib.sha256((ROOT/'web/index.html').read_bytes()).hexdigest()}
        except Exception:
            self.server_close();raise

    def start_job(self,fn,cleanup=lambda:None):
        with self.job_lock:
            if self.job.get('state')=='running':
                raise ValueError('다른 가져오기/다운로드가 진행 중입니다.')
            job_id=secrets.token_hex(10)
            cancel=threading.Event();self.cancel_event=cancel
            self.job={'id':job_id,'state':'running','message':'데이터 검증 중','counts':{},'progress':0}
        def progress(x):
            if cancel.is_set(): raise JobCancelled('사용자가 중단했습니다. 기존 데이터는 보존합니다.')
            with self.job_lock:self.job.update(x)
        def run():
            try:
                report=fn(progress)
                with self.job_lock:self.job={'id':job_id,'state':'done','report':report,'message':'완료','progress':100}
            except JobCancelled as exc:
                with self.job_lock:self.job={'id':job_id,'state':'cancelled','message':str(exc)}
            except Exception as exc:
                with self.job_lock:self.job={'id':job_id,'state':'error','message':str(exc)[:600]}
            finally:cleanup()
        threading.Thread(target=run,daemon=True).start()
        return job_id

class Handler(BaseHTTPRequestHandler):
    server_version='AOAViewer/'+VERSION
    def setup(self):
        super().setup();self.connection.settimeout(180)
    def log_message(self,format,*args):print('[AOA]',format%args)
    def allowed(self,write=False):
        port=self.server.server_address[1];allowed={f'127.0.0.1:{port}',f'localhost:{port}'}
        if self.headers.get('Host','') not in allowed:
            self.send_json(403,{'error':'Loopback Host required'});return False
        origin=self.headers.get('Origin')
        if origin and origin not in {'http://'+x for x in allowed}:
            self.send_json(403,{'error':'Cross-origin request rejected'});return False
        if write and not secrets.compare_digest(self.headers.get('X-AOA-Token',''),self.server.token):
            self.send_json(403,{'error':'Local session token required'});return False
        return True
    def send_bytes(self,status,body,content_type='application/json; charset=utf-8',extra=None):
        self.send_response(status)
        for k,v in {'Content-Type':content_type,'Content-Length':str(len(body)),
                    'Cache-Control':'no-store, max-age=0','X-Content-Type-Options':'nosniff','X-Frame-Options':'DENY',
                    'Referrer-Policy':'no-referrer','Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'none'",**(extra or {})}.items():self.send_header(k,v)
        self.end_headers()
        try:self.wfile.write(body)
        except (BrokenPipeError,ConnectionResetError):pass
    def send_json(self,status,data):self.send_bytes(status,json.dumps(data,ensure_ascii=False,allow_nan=False).encode('utf-8'))
    def query(self):
        parsed=urlsplit(self.path)
        return unquote(parsed.path),{k:v[-1] for k,v in parse_qs(parsed.query).items()}
    def do_GET(self):
        if not self.allowed():return
        path,q=self.query()
        try:
            if path=='/api/runtime':return self.send_json(200,self.server.runtime)
            if path=='/api/status':return self.send_json(200,{'token':self.server.token,**self.server.store.status(),'version':VERSION,'runtime':self.server.runtime})
            if path=='/api/job':
                with self.server.job_lock:snapshot=dict(self.server.job)
                return self.send_json(200,snapshot)
            if path=='/api/episodes':return self.send_json(200,self.server.store.episodes(q.get('symbol','XBTUSD'),q.get('year',''),q.get('direction',''),q.get('result',''),q.get('search',''),q.get('year_mode','entry')))
            if path=='/api/events':return self.send_json(200,self.server.store.events(q.get('episode','')))
            if path=='/api/study':return self.send_json(200,self.server.store.study(q.get('episode',''),q.get('event',''),q.get('cutoff')))
            if path=='/api/performance':return self.send_json(200,self.server.store.performance(q.get('episode','')))
            if path=='/api/coverage':return self.send_json(200,missing_plan(self.server.store,q.get('pair','BTCUSDT'),int(q['start']),int(q['end'])))
            if path=='/api/candles':
                if q.get('tf') not in TIMEFRAMES:raise ValueError('Invalid timeframe')
                return self.send_json(200,self.server.store.candles(q.get('pair','BTCUSDT'),q['tf'],int(q['start']),int(q['end'])))
            if path=='/api/note':return self.send_json(200,self.server.store.get_note(q.get('episode','')))
            if path=='/api/issues':return self.send_json(200,self.server.store.issues())
            if path=='/api/study-export':
                data=self.server.store.study(q.get('episode',''),q.get('event',''),q.get('cutoff'))
                return self.send_bytes(200,json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False).encode(),'application/json; charset=utf-8',{'Content-Disposition':'attachment; filename="AOA-event-study.json"'})
            if path=='/api/export':
                rows=self.server.store.events(q.get('episode',''))
                output=io.StringIO(newline='');fields=['id','episode_id','time_utc','end_time_utc','role','direction','action','qty','first_price','avg_price','position_before','position_after','basis_before','price_move_pct','legacy_label','legacy_reason']
                writer=csv.DictWriter(output,fieldnames=fields,extrasaction='ignore');writer.writeheader()
                for row in rows:writer.writerow({k:("'"+str(v) if isinstance(v,str) and v.startswith(('=','+','-','@')) else v) for k,v in row.items()})
                return self.send_bytes(200,('\ufeff'+output.getvalue()).encode(),'text/csv; charset=utf-8',{'Content-Disposition':'attachment; filename="aoa_episode.csv"'})
            if path.startswith('/api/'):return self.send_json(404,{'error':'Not found'})
            if path=='/vendor/lightweight-charts.js':p=ROOT/'vendor'/'lightweight-charts.js'
            else:
                base=(ROOT/'web').resolve();p=(base/('index.html' if path=='/' else path.lstrip('/'))).resolve()
                if not p.is_relative_to(base):return self.send_json(403,{'error':'Invalid static path'})
            if not p.is_file():return self.send_json(404,{'error':'File not found'})
            mime=mimetypes.guess_type(str(p))[0] or 'application/octet-stream'
            if p.suffix in {'.js','.mjs'}:mime='text/javascript'
            self.send_bytes(200,p.read_bytes(),mime)
        except (ValueError,KeyError,TypeError) as exc:self.send_json(400,{'error':str(exc)})
        except Exception:
            self.send_json(500,{'error':'서버 오류. 콘솔 로그와 데이터 형식을 확인하세요.'})
            import traceback;traceback.print_exc()
    def body(self,limit):
        length=int(self.headers.get('Content-Length','0'))
        if length<1 or length>limit:raise ValueError('Request size limit exceeded')
        data=self.rfile.read(length)
        if len(data)!=length:raise ValueError('Incomplete request body')
        return data
    def do_POST(self):
        if not self.allowed(write=True):return
        path,q=self.query();temp=None
        try:
            if path=='/api/import':
                name=Path(q.get('name','')).name
                if not name.lower().endswith(('.zip','.csv','.gz')):raise ValueError('ZIP, CSV, CSV.GZ만 지원합니다.')
                length=int(self.headers.get('Content-Length','0'))
                if length<=0 or length>MAX_UPLOAD:raise ValueError('파일당 512MB 이내만 지원합니다.')
                with self.server.job_lock:
                    if self.server.job.get('state')=='running':raise ValueError('현재 작업 완료 후 가져오세요.')
                fd,temp=tempfile.mkstemp(prefix='upload-',dir=self.server.store.directory)
                with os.fdopen(fd,'wb') as f:
                    left=length
                    while left:
                        chunk=self.rfile.read(min(left,1024*1024))
                        if not chunk:raise ValueError('파일 업로드가 중단되었습니다.')
                        f.write(chunk);left-=len(chunk)
                saved=temp
                job_id=self.server.start_job(lambda cb:import_file(self.server.store,saved,name,cb),lambda:Path(saved).unlink(missing_ok=True))
                temp=None
                return self.send_json(202,{'ok':True,'job_id':job_id})
            body=json.loads(self.body(128*1024))
            if not isinstance(body,dict):raise ValueError('JSON object required')
            if path=='/api/note':
                self.server.store.save_note(str(body['episode']),str(body.get('text','')),str(body.get('tags','')))
                return self.send_json(200,{'ok':True})
            if path=='/api/reference-margin':
                self.server.store.set_reference_margin(str(body['episode']),body.get('btc'))
                return self.send_json(200,self.server.store.performance(str(body['episode'])))
            if path=='/api/cancel-job':
                with self.server.job_lock:
                    if body.get('job_id') and body['job_id']!=self.server.job.get('id'):raise ValueError('작업이 이미 변경됐습니다.')
                    self.server.cancel_event.set()
                return self.send_json(200,{'ok':True})
            if path=='/api/fetch':
                pair=str(body.get('pair','BTCUSDT'));start=int(body['start']);end=int(body['end'])
                job_id=self.server.start_job(lambda cb:fetch_window(self.server.store,pair,start,end,cb))
                return self.send_json(202,{'ok':True,'job_id':job_id})
            self.send_json(404,{'error':'Not found'})
        except (ValueError,KeyError,TypeError,json.JSONDecodeError) as exc:self.send_json(400,{'error':str(exc)})
        except Exception:
            self.send_json(500,{'error':'로컬 작업 오류. 콘솔을 확인하세요.'})
            import traceback;traceback.print_exc()
        finally:
            if temp:Path(temp).unlink(missing_ok=True)
