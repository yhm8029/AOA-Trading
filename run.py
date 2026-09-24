"""Verified local launcher, Python 3.10+. Busy old servers are never killed."""
from __future__ import annotations
import argparse
import json
import os
import sys
import threading
import time
import webbrowser
from pathlib import Path


def main(argv=None):
    if sys.version_info < (3,10):
        raise SystemExit('Python 3.10 or newer is required.')
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'): stream.reconfigure(errors='backslashreplace')
    from aoa.version import VERSION
    from aoa.launch import verify_install, bind_server, confirm_server, copy_existing_data, choose_source
    root=Path(__file__).resolve().parent
    parser=argparse.ArgumentParser(description='AOA Whale Viewer verified launcher')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--strict-port', action='store_true', help='Fail instead of selecting a free port')
    parser.add_argument('--data-dir', default=None)
    parser.add_argument('--copy-data-from', default=None, help='Copy old database into a new EMPTY local-data folder')
    parser.add_argument('--choose-data', action='store_true')
    parser.add_argument('--fresh', action='store_true', help='Skip the Windows first-run folder picker; never erases data')
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--skip-vendor', action='store_true')
    parser.add_argument('--self-check', action='store_true')
    args=parser.parse_args(argv)
    try:
        check=verify_install(root)
        if args.self_check:
            print(json.dumps(check,ensure_ascii=False,indent=2),flush=True);return 0
        data=Path(args.data_dir).expanduser().resolve() if args.data_dir else root/'local-data'
        source=args.copy_data_from
        first_windows_run=(os.name=='nt' and not args.data_dir and not (data/'viewer.sqlite3').exists()
                           and not args.fresh and not args.no_browser and not source)
        if args.choose_data or first_windows_run:
            print('기존 데이터 폴더 선택: 원본을 지우지 않고 새 폴더에 안전한 사본을 만듭니다.',flush=True)
            source=choose_source()
        if source: copy_existing_data(source,data,progress=lambda text:print(text,flush=True))
        if not args.skip_vendor:
            from scripts.prepare_vendor import install
            install()
        from aoa.server import AppServer
        server,moved=bind_server(AppServer,data,args.port,args.strict_port)
    except (ValueError,OSError,RuntimeError) as exc:
        print('\nSTART FAILED:',exc,'\n기존 데이터는 삭제하지 않았습니다.',file=sys.stderr,flush=True)
        return 1
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        url=confirm_server(server)
        record={'version':VERSION,'url':url,'runtime':server.runtime,'verification':check}
        (data/'last-launch.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
        print(f'\nAOA Whale Viewer v{VERSION} — 실행 검증 완료',flush=True)
        if moved: print(f'이전 {args.port} 포트가 사용 중입니다. 기존 프로세스는 그대로 두고 새 포트로 열었습니다.',flush=True)
        print('App folder:',root,'\nData folder:',data,'\nOPEN THIS URL:',url,'\nStop: Ctrl+C',flush=True)
        if not args.no_browser:
            try: webbrowser.open(url,new=2)
            except Exception as exc: print('브라우저를 직접 열어 위 URL로 접속하세요:',exc,flush=True)
        while thread.is_alive(): thread.join(.5)
        return 0
    except KeyboardInterrupt:
        print('\nStopping.',flush=True);return 0
    except (ValueError,OSError,RuntimeError) as exc:
        print('서버 확인 실패. 브라우저는 열지 않았습니다:',exc,file=sys.stderr,flush=True);return 1
    finally:
        server.shutdown();server.server_close();thread.join(timeout=5)

if __name__=='__main__':
    raise SystemExit(main())
