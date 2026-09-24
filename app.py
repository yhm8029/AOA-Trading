"""Run: python app.py --open. Python 3.10+; no pip packages required."""
from __future__ import annotations
import argparse
import logging
import sys
import threading
import webbrowser
from pathlib import Path


def main():
    if sys.version_info<(3,10):
        raise SystemExit('Python 3.10 or newer is required.')
    from aoa.store import Store
    from aoa.server import LocalServer
    from aoa.importer import import_file
    parser=argparse.ArgumentParser(description='AOA Whale Viewer - localhost only')
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--data-dir',type=Path,default=Path(__file__).resolve().parent/'data')
    parser.add_argument('--open',action='store_true')
    parser.add_argument('--import-file',type=Path,action='append',default=[])
    parser.add_argument('--skip-assets',action='store_true',help='Tests/development only')
    args=parser.parse_args()
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    if not args.skip_assets:
        from prepare_assets import ensure_assets
        try:
            ensure_assets()
        except Exception as exc:
            raise SystemExit(f'Chart library setup failed: {exc}\nInternet is only required for initial library setup, or use the CI-built package.')
    store=Store(args.data_dir/'aoa.sqlite3')
    for file in args.import_file:
        print(import_file(store,file,print))
    server=None
    ports=[0] if args.port==0 else range(args.port,min(args.port+10,65536))
    for port in ports:
        try:
            server=LocalServer(('127.0.0.1',port),store,args.data_dir)
            break
        except OSError:
            continue
    if server is None:
        raise SystemExit('No free port. Try: python app.py --port 8870 --open')
    url=f'http://127.0.0.1:{server.server_address[1]}'
    print('\nAOA Whale Viewer: '+url+'\nLocal data stays on this computer. Ctrl+C stops the app.\n',flush=True)
    if args.open:
        threading.Timer(.7,lambda:webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nStopped.')
    finally:
        server.server_close()

if __name__=='__main__':
    main()
