"""Loopback-only HTTP server. No trading endpoints, remote uploads or credentials."""
from __future__ import annotations
import json
import logging
import mimetypes
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit
from . import __version__
from .importer import MAX_FILE, import_file
from .market import fetch_public
from .model import clean_symbol

LOG=logging.getLogger('aoa')
WEB=Path(__file__).resolve().parent.parent/'web'


class Jobs:
    def __init__(self):
        self.lock=threading.Lock()
        self.state=dict(status='idle',message='',report=None)
    def start(self,fn):
        if not self.lock.acquire(blocking=False):
            raise ValueError('이미 가져오기/수집 작업이 실행 중입니다.')
        self.state=dict(status='running',message='준비 중',report=None)
        def progress(message):
            self.state={**self.state,'message':message}
        def run():
            try:
                result=fn(progress)
                self.state=dict(status='done',message='완료',report=result)
            except Exception as exc:
                LOG.exception('Local job failed')
                self.state=dict(status='error',message=str(exc),report=None)
            finally:
                self.lock.release()
        threading.Thread(target=run,name='aoa-local-import',daemon=True).start()
        return dict(self.state)


class LocalServer(ThreadingHTTPServer):
    daemon_threads=True
    allow_reuse_address=True

    def __init__(self,address,store,data_dir,web_root=WEB):
        self.store=store
        self.data_dir=Path(data_dir)
        self.inbox=self.data_dir/'inbox'
        self.inbox.mkdir(parents=True,exist_ok=True)
        self.web_root=Path(web_root).resolve()
        self.token=secrets.token_urlsafe(32)
        self.jobs=Jobs()
        super().__init__(address,Handler)

    @property
    def origins(self):
        port=self.server_address[1]
        return {f'http://127.0.0.1:{port}',f'http://localhost:{port}'}


class Handler(BaseHTTPRequestHandler):
    server_version='AOA-Local/0.1'
    protocol_version='HTTP/1.0'

    def log_message(self,fmt,*args):
        LOG.info('%s - %s',self.client_address[0],fmt%args)

    def allowed(self,write=False):
        host=self.headers.get('Host','')
        if 'http://'+host not in self.server.origins:
            self.send_json({'error':'Loopback host required'},403)
            return False
        origin=self.headers.get('Origin')
        if origin and origin not in self.server.origins:
            self.send_json({'error':'Cross-origin requests are not allowed'},403)
            return False
        if write and not secrets.compare_digest(self.headers.get('X-AOA-Token',''),self.server.token):
            self.send_json({'error':'Invalid local session token'},403)
            return False
        return True

    def headers_common(self):
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Cache-Control','no-store')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")

    def send_json(self,data,status=200):
        body=json.dumps(data,ensure_ascii=False,allow_nan=False).encode('utf-8')
        self.send_response(status)
        self.headers_common()
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def body_json(self):
        size=int(self.headers.get('Content-Length','0'))
        if size<1 or size>100000:
            raise ValueError('Invalid JSON request size')
        return json.loads(self.rfile.read(size))

    def do_GET(self):
        if not self.allowed():
            return
        url=urlsplit(self.path)
        p=unquote(url.path)
        query=parse_qs(url.query)
        def q(k,default=''):
            return query.get(k,[default])[0]
        try:
            if p=='/api/bootstrap':
                self.send_json(dict(version=__version__,token=self.server.token,stats=self.server.store.stats()))
            elif p=='/api/status':
                self.send_json(dict(job=self.server.jobs.state,stats=self.server.store.stats() if self.server.jobs.state['status']!='running' else None))
            elif p=='/api/episodes':
                self.send_json(self.server.store.episodes())
            elif p=='/api/events':
                self.send_json(self.server.store.events(clean_symbol(q('symbol','XBTUSD')),q('episode')))
            elif p=='/api/chart':
                self.send_json(self.server.store.chart(clean_symbol(q('pair','BTCUSDT')),int(q('tf','5')),int(q('start')),int(q('end'))))
            elif p=='/api/event-volume':
                events=self.server.store.events(clean_symbol(q('symbol','XBTUSD')),q('episode'))
                event=next((e for e in events if e['id']==q('id')),None)
                if event is None:
                    raise ValueError('Event not found')
                self.send_json(self.server.store.event_volume(event))
            elif p=='/api/note':
                self.send_json(self.server.store.note(q('key')))
            elif p=='/api/inbox':
                self.send_json([dict(name=f.name,size=f.stat().st_size) for f in self.server.inbox.iterdir() if f.is_file() and f.name.lower().endswith(('.csv','.zip','.csv.gz'))])
            elif p=='/api/health':
                self.send_json({'ok':True,'version':__version__})
            elif p.startswith('/api/'):
                self.send_json({'error':'Unknown endpoint'},404)
            else:
                self.static(p)
        except (ValueError,TypeError,KeyError) as exc:
            self.send_json({'error':str(exc)},400)
        except (BrokenPipeError,ConnectionResetError):
            pass
        except Exception:
            LOG.exception('GET failed')
            self.send_json({'error':'처리 중 오류가 발생했습니다. 터미널 로그를 확인하세요.'},500)

    def static(self,p):
        relative='index.html' if p=='/' else p.lstrip('/')
        path=(self.server.web_root/relative).resolve()
        try:
            path.relative_to(self.server.web_root)
        except ValueError:
            self.send_json({'error':'Forbidden'},403)
            return
        allowed={'.html','.css','.js','.mjs','.svg','.png','.json'}
        if not path.is_file() or (path.suffix not in allowed and path.name not in ('LICENSE','NOTICE')):
            self.send_json({'error':'Not found'},404)
            return
        body=path.read_bytes()
        ctype='text/javascript' if path.suffix in ('.js','.mjs') else mimetypes.guess_type(path.name)[0] or 'text/plain'
        self.send_response(200)
        self.headers_common()
        self.send_header('Content-Type',ctype+'; charset=utf-8' if ctype.startswith('text/') else ctype)
        self.send_header('Content-Length',str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if not self.allowed(write=True):
            return
        u=urlsplit(self.path)
        try:
            if u.path=='/api/upload':
                if self.server.jobs.state['status']=='running':
                    raise ValueError('현재 작업이 끝난 뒤 파일을 추가하세요.')
                raw=parse_qs(u.query).get('name',[''])[0]
                if not raw or raw!=Path(raw).name or '/' in raw or '\\' in raw or len(raw)>180:
                    raise ValueError('Invalid filename')
                if not raw.lower().endswith(('.zip','.csv','.csv.gz')):
                    raise ValueError('CSV / CSV.GZ / ZIP만 선택하세요.')
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=MAX_FILE:
                    raise ValueError('파일당 최대 512 MiB')
                target=self.server.inbox/(secrets.token_hex(4)+'_'+raw)
                temp=target.with_name(target.name+'.partial')
                try:
                    self.connection.settimeout(90)
                    with temp.open('xb') as f:
                        remaining=size
                        while remaining:
                            chunk=self.rfile.read(min(1024*1024,remaining))
                            if not chunk:
                                raise ValueError('Upload interrupted')
                            f.write(chunk);remaining-=len(chunk)
                    temp.replace(target)
                finally:
                    temp.unlink(missing_ok=True)
                self.send_json(self.server.jobs.start(lambda progress:import_file(self.server.store,target,progress)),202)
            elif u.path=='/api/import-inbox':
                self.body_json()
                paths=[p for p in sorted(self.server.inbox.iterdir()) if p.is_file() and p.name.lower().endswith(('.csv','.csv.gz','.zip'))]
                def run(progress):
                    result=[]
                    for path in paths:
                        try:
                            result.append(import_file(self.server.store,path,progress))
                        except Exception as exc:
                            result.append({'filename':path.name,'error':str(exc)})
                    return result
                self.send_json(self.server.jobs.start(run),202)
            elif u.path=='/api/fetch-market':
                body=self.body_json()
                if body.get('confirmed') is not True:
                    raise ValueError('외부 공개 시장 데이터 요청 동의가 필요합니다.')
                pair=clean_symbol(body['pair']);start=int(body['start']);end=int(body['end'])
                self.send_json(self.server.jobs.start(lambda progress:fetch_public(self.server.store,pair,start,end,self.server.data_dir/'market-downloads',progress)),202)
            elif u.path=='/api/note':
                body=self.body_json()
                self.send_json(self.server.store.save_note(str(body['key']),str(body['body']),int(body['version'])))
            else:
                self.send_json({'error':'Unknown endpoint'},404)
        except (ValueError,TypeError,KeyError,json.JSONDecodeError) as exc:
            self.send_json({'error':str(exc)},400)
        except (BrokenPipeError,ConnectionResetError):
            pass
        except Exception:
            LOG.exception('POST failed')
            self.send_json({'error':'로컬 처리 실패. 터미널 로그를 확인하세요.'},500)
