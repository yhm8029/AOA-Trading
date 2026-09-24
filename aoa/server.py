from __future__ import annotations
import csv
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
from .store import Store
from .model import TIMEFRAMES
from .importer import import_file
from .market import fetch_window

ROOT=Path(__file__).resolve().parent.parent
MAX_UPLOAD=512*1024*1024

class AppServer(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,address,directory):
        super().__init__(address,Handler)
        self.store=Store(directory)
        self.token=secrets.token_urlsafe(32)
        self.job={'state':'idle'}
        self.job_lock=threading.Lock()

    def start_job(self,fn,cleanup=lambda:None):
        with self.job_lock:
            if self.job.get('state')=='running':
                raise ValueError('다른 가져오기/다운로드가 진행 중입니다.')
            self.job={'state':'running','message':'데이터 검증 중','counts':{}}
        def progress(x):
            with self.job_lock:
                self.job.update(x)
        def run():
            try:
                report=fn(progress)
                with self.job_lock:
                    self.job={'state':'done','report':report,'message':'완료'}
            except Exception as exc:
                with self.job_lock:
                    self.job={'state':'error','message':str(exc)[:600]}
            finally:
                cleanup()
        threading.Thread(target=run,daemon=True).start()

class Handler(BaseHTTPRequestHandler):
    server_version='AOAViewer/0.1'
    def setup(self):
        super().setup()
        self.connection.settimeout(180)

    def log_message(self,format,*args):
        # Avoid logging query bodies or local filenames.
        print('[AOA]',format%args)

    def allowed(self,write=False):
        host=self.headers.get('Host','')
        port=self.server.server_address[1]
        allowed={f'127.0.0.1:{port}',f'localhost:{port}'}
        if host not in allowed:
            self.send_json(403,{'error':'Loopback Host required'}); return False
        origin=self.headers.get('Origin')
        if origin and origin not in {'http://'+x for x in allowed}:
            self.send_json(403,{'error':'Cross-origin request rejected'}); return False
        if write and not secrets.compare_digest(self.headers.get('X-AOA-Token',''),self.server.token):
            self.send_json(403,{'error':'Local session token required'}); return False
        return True

    def send_bytes(self,status,body,content_type='application/json; charset=utf-8',extra=None):
        self.send_response(status)
        self.send_header('Content-Type',content_type)
        self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('X-Frame-Options','DENY')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'none'")
        for key,value in (extra or {}).items():
            self.send_header(key,value)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError,ConnectionResetError):
            pass

    def send_json(self,status,data):
        self.send_bytes(status,json.dumps(data,ensure_ascii=False,allow_nan=False).encode('utf-8'))

    def query(self):
        parsed=urlsplit(self.path)
        return unquote(parsed.path),{k:v[-1] for k,v in parse_qs(parsed.query).items()}

    def do_GET(self):
        if not self.allowed(): return
        path,q=self.query()
        try:
            if path=='/api/status':
                return self.send_json(200,{'token':self.server.token,**self.server.store.status(),'version':'0.1.0'})
            if path=='/api/job':
                with self.server.job_lock:
                    snapshot=dict(self.server.job)
                return self.send_json(200,snapshot)
            if path=='/api/episodes':
                return self.send_json(200,self.server.store.episodes(q.get('symbol','XBTUSD'),q.get('year',''),q.get('direction',''),q.get('result',''),q.get('search','')))
            if path=='/api/events':
                return self.send_json(200,self.server.store.events(q.get('episode','')))
            if path=='/api/candles':
                if q.get('tf') not in TIMEFRAMES: raise ValueError('Invalid timeframe')
                return self.send_json(200,self.server.store.candles(q.get('pair','BTCUSDT'),q['tf'],int(q['start']),int(q['end'])))
            if path=='/api/note':
                return self.send_json(200,self.server.store.get_note(q.get('episode','')))
            if path=='/api/issues':
                return self.send_json(200,self.server.store.issues())
            if path=='/api/export':
                rows=self.server.store.events(q.get('episode',''))
                output=io.StringIO(newline=''); fields=['id','episode_id','time_utc','end_time_utc','role','direction','action','qty','first_price','avg_price','position_before','position_after','basis_before','price_move_pct','legacy_label','legacy_reason']
                writer=csv.DictWriter(output,fieldnames=fields,extrasaction='ignore'); writer.writeheader()
                for row in rows:
                    safe={k:("'"+str(v) if isinstance(v,str) and v.startswith(('=','+','-','@')) else v) for k,v in row.items()}
                    writer.writerow(safe)
                return self.send_bytes(200,('\ufeff'+output.getvalue()).encode(),'text/csv; charset=utf-8',{'Content-Disposition':'attachment; filename="aoa_episode.csv"'})
            if path.startswith('/api/'):
                return self.send_json(404,{'error':'Not found'})
            if path=='/vendor/lightweight-charts.js':
                p=ROOT/'vendor'/'lightweight-charts.js'
            else:
                base=(ROOT/'web').resolve()
                p=(base/('index.html' if path=='/' else path.lstrip('/'))).resolve()
                if not p.is_relative_to(base):
                    return self.send_json(403,{'error':'Invalid static path'})
            if not p.is_file():
                return self.send_json(404,{'error':'File not found'})
            mime=mimetypes.guess_type(str(p))[0] or 'application/octet-stream'
            if p.suffix in {'.js','.mjs'}: mime='text/javascript'
            self.send_bytes(200,p.read_bytes(),mime)
        except (ValueError,KeyError,TypeError) as exc:
            self.send_json(400,{'error':str(exc)})
        except Exception:
            self.send_json(500,{'error':'서버 오류. 콘솔 로그와 데이터 형식을 확인하세요.'})
            import traceback; traceback.print_exc()

    def body(self,limit):
        length=int(self.headers.get('Content-Length','0'))
        if length<1 or length>limit:
            raise ValueError('Request size limit exceeded')
        data=self.rfile.read(length)
        if len(data)!=length: raise ValueError('Incomplete request body')
        return data

    def do_POST(self):
        if not self.allowed(write=True): return
        path,q=self.query()
        temp=None
        try:
            if path=='/api/import':
                name=Path(q.get('name','')).name
                if not name.lower().endswith(('.zip','.csv','.gz')): raise ValueError('ZIP, CSV, CSV.GZ만 지원합니다.')
                length=int(self.headers.get('Content-Length','0'))
                if length<=0 or length>MAX_UPLOAD: raise ValueError('파일당 512MB 이내만 지원합니다.')
                with self.server.job_lock:
                    if self.server.job.get('state')=='running': raise ValueError('현재 작업 완료 후 가져오세요.')
                fd,temp=tempfile.mkstemp(prefix='upload-',dir=self.server.store.directory)
                with os.fdopen(fd,'wb') as f:
                    left=length
                    while left:
                        chunk=self.rfile.read(min(left,1024*1024))
                        if not chunk: raise ValueError('파일 업로드가 중단되었습니다.')
                        f.write(chunk); left-=len(chunk)
                saved=temp
                self.server.start_job(lambda cb:import_file(self.server.store,saved,name,cb),lambda:Path(saved).unlink(missing_ok=True))
                temp=None
                return self.send_json(202,{'ok':True})
            body=json.loads(self.body(128*1024))
            if path=='/api/note':
                self.server.store.save_note(str(body['episode']),str(body.get('text','')),str(body.get('tags','')))
                return self.send_json(200,{'ok':True})
            if path=='/api/fetch':
                pair=str(body.get('pair','BTCUSDT')); start=int(body['start']); end=int(body['end'])
                self.server.start_job(lambda cb:fetch_window(self.server.store,pair,start,end,cb))
                return self.send_json(202,{'ok':True})
            self.send_json(404,{'error':'Not found'})
        except (ValueError,KeyError,TypeError,json.JSONDecodeError) as exc:
            self.send_json(400,{'error':str(exc)})
        except Exception:
            self.send_json(500,{'error':'로컬 작업 오류. 콘솔을 확인하세요.'})
            import traceback; traceback.print_exc()
        finally:
            if temp: Path(temp).unlink(missing_ok=True)
