"""Windows/macOS/Linux launcher; Python 3.10+; no pip dependencies."""
from __future__ import annotations
import argparse
import socket
import sys
import threading
import webbrowser
from pathlib import Path


def main():
    if sys.version_info<(3,10):
        raise SystemExit('Python 3.10 or newer is required.')
    parser=argparse.ArgumentParser(description='AOA Whale Viewer (local research only)')
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--data-dir',default=str(Path(__file__).parent/'local-data'))
    parser.add_argument('--no-browser',action='store_true')
    parser.add_argument('--skip-vendor',action='store_true')
    args=parser.parse_args()
    if not args.skip_vendor:
        from scripts.prepare_vendor import install
        try: install()
        except Exception as exc:
            print('Chart library setup failed:',exc)
            print('First launch needs network access to registry.npmjs.org; existing trading data is untouched.')
            return 1
    from aoa.server import AppServer
    try:
        server=AppServer(('127.0.0.1',args.port),args.data_dir)
    except OSError:
        print('Port unavailable. Try: python run.py --port 8766')
        return 1
    url=f'http://127.0.0.1:{server.server_address[1]}'
    print('\nAOA Whale Viewer:',url,'\nStop: Ctrl+C\nData stays in:',Path(args.data_dir).resolve())
    if not args.no_browser:
        threading.Timer(0.5,lambda:webbrowser.open(url)).start()
    try: server.serve_forever()
    except KeyboardInterrupt: print('\nStopping.')
    finally: server.server_close()
    return 0

if __name__=='__main__':
    raise SystemExit(main())
