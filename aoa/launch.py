"""Verified local startup and non-destructive migration. No process killing.

A busy old port must never open the old app. SQLite backup copies a consistent
snapshot (including committed WAL pages); it never replaces an existing DB.
"""
from __future__ import annotations
import errno
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import time
import urllib.request
from contextlib import closing
from pathlib import Path, PurePosixPath
from .version import APP_ID, VERSION

REQUIRED_UI = ('first 진입',)  # Core requirements are checked below in actual HTML IDs.
REQUIRED_FILES = ('run.py', 'aoa/server.py', 'aoa/study.py', 'aoa/version.py',
                  'web/index.html', 'web/boot.mjs', 'web/app.mjs',
                  'web/study-core.mjs', 'web/study-markers.mjs', 'web/study-ui.mjs')


def verify_install(root):
    """Reject mixed release files before importing the HTTP server or opening data."""
    root = Path(root).resolve()
    errors = [name for name in REQUIRED_FILES if not (root/name).is_file()]
    manifest_path = root/'release-manifest.json'
    release = None
    if manifest_path.exists():
        release = json.loads(manifest_path.read_text(encoding='utf-8'))
        mapping = release.get('files_sha256', {})
        if release.get('version') != VERSION or not isinstance(mapping, dict):
            errors.append('release-manifest.json version')
        for name in REQUIRED_FILES:
            if name not in mapping: errors.append('manifest missing '+name)
        for name, expected in mapping.items():
            p = PurePosixPath(name)
            if p.is_absolute() or '..' in p.parts or '\\' in name or ':' in name:
                raise ValueError('Unsafe release manifest path')
            file = (root/name).resolve()
            if not file.is_relative_to(root) or not file.is_file():
                errors.append(name)
            elif hashlib.sha256(file.read_bytes()).hexdigest() != expected:
                errors.append(name)
    if not errors:
        html = (root/'web/index.html').read_text(encoding='utf-8')
        ui = (root/'web/study-ui.mjs').read_text(encoding='utf-8')
        for name in ('version','entryFocus','studyPanel','autoFill','pauseOnEvent','runtimeInfo'):
            if 'id="'+name+'"' not in html: errors.append('UI missing '+name)
        if 'v'+VERSION not in html or "UI_VERSION='"+VERSION+"'" not in ui:
            errors.append('UI version mismatch')
        if '/boot.mjs' not in html: errors.append('UI startup guard missing')
    if errors:
        raise ValueError('설치 파일이 섞였거나 손상됐습니다: '+', '.join(errors[:12])+
                         '\n새 ZIP을 빈 폴더에 풀고 실행하세요. local-data는 삭제하지 마세요.')
    return {'version':VERSION, 'mode':'verified-release' if release else 'source-checkout',
            'commit':release.get('commit') if release else None,
            'checked_files':len(release['files_sha256']) if release else len(REQUIRED_FILES)}


def bind_server(factory, directory, preferred=8765, strict=False):
    """Bind first, then use the bound port. Never guess a free port or kill its owner."""
    if not 0 <= preferred <= 65535: raise ValueError('Port must be between 0 and 65535')
    try:
        return factory(('127.0.0.1', preferred), directory), False
    except OSError as exc:
        busy = exc.errno in (errno.EADDRINUSE, 10048) or getattr(exc, 'winerror', None)==10048
        if strict or not preferred or not busy: raise
    return factory(('127.0.0.1', 0), directory), True


def runtime_url(server):
    return f'http://127.0.0.1:{server.server_address[1]}/?v={VERSION}&launch={server.runtime["instance"]}'


def confirm_server(server, timeout=10):
    """No proxy/redirects: prove the browser URL belongs to THIS process/instance."""
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs): return None
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    url = f'http://127.0.0.1:{server.server_address[1]}/api/runtime'
    deadline = time.monotonic()+timeout
    while True:
        try:
            with opener.open(url, timeout=2) as response:
                raw = response.read(65537)
            if len(raw)>65536: raise ValueError('Unexpected runtime response')
            data = json.loads(raw)
            expected = server.runtime
            if any(data.get(k)!=expected.get(k) for k in ('application','version','instance','pid','app_dir','data_dir','ui_sha256')):
                raise ValueError('실행 서버가 방금 실행한 앱과 다릅니다. 이전 주소를 열지 않았습니다.')
            return runtime_url(server)
        except (OSError, TimeoutError):
            if time.monotonic()>=deadline: raise RuntimeError('새 앱 서버 시작 확인 시간 초과') from None
            time.sleep(.05)


def locate_database(folder):
    folder = Path(folder).expanduser().resolve()
    choices = [folder/'viewer.sqlite3', folder/'local-data'/'viewer.sqlite3']
    found = [p for p in choices if p.is_file()]
    if len(found)!=1:
        raise ValueError('기존 앱 폴더 또는 local-data 폴더를 선택하세요. viewer.sqlite3 한 개를 확인해야 합니다.')
    return found[0]


def copy_existing_data(source_folder, destination, progress=print, timeout=600):
    """Copy into an EMPTY data directory only. Source DB stays in place, unchanged."""
    src = locate_database(source_folder)
    destination = Path(destination).resolve()
    target = destination/'viewer.sqlite3'
    if src == target: return {'same_directory':True,'data_dir':str(destination)}
    destination.mkdir(parents=True, exist_ok=True)
    if any(p.exists() for p in (target, Path(str(target)+'-wal'), Path(str(target)+'-shm'))):
        raise ValueError('새 폴더에 이미 DB가 있습니다. 덮어쓰지 않았습니다. 기존 local-data를 유지하거나 새 빈 폴더를 선택하세요.')
    lock = destination/'.migration.lock'
    fd = os.open(lock, os.O_CREAT|os.O_EXCL|os.O_WRONLY, 0o600)
    os.close(fd)
    stage = None
    started = time.monotonic()
    last_message = [-1.0]
    def tick(status, remaining, total):
        now = time.monotonic()
        if now-started>timeout: raise TimeoutError('기존 DB 복사 시간이 초과됐습니다. 원본은 유지했습니다.')
        if now-last_message[0]>=.5 or remaining==0:
            progress(f'기존 데이터 안전 복사: {total-remaining:,}/{total:,} pages')
            last_message[0] = now
    try:
        with closing(sqlite3.connect(src.as_uri()+'?mode=ro', uri=True, timeout=5)) as source:
            tables = {r[0] for r in source.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {'orders','candles','notes','imports'} <= tables:
                raise ValueError('이 DB는 지원되는 AOA viewer.sqlite3 형식이 아닙니다. 원본은 변경하지 않았습니다.')
            size = source.execute('PRAGMA page_count').fetchone()[0]*source.execute('PRAGMA page_size').fetchone()[0]
            if shutil.disk_usage(destination).free < size+64*1024**2:
                raise ValueError('안전한 데이터 사본을 만들 디스크 공간이 부족합니다.')
            handle, name = tempfile.mkstemp(prefix='aoa-snapshot-',suffix='.sqlite3',dir=destination)
            os.close(handle);stage=Path(name)
            with closing(sqlite3.connect(stage)) as dest:
                source.backup(dest, pages=2048, progress=tick, sleep=.05)
                if dest.execute('PRAGMA quick_check').fetchall() != [('ok',)]:
                    raise ValueError('복사한 DB 무결성 검사 실패. 원본은 변경하지 않았습니다.')
                counts={table:dest.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]
                        for table in ('orders','candles','notes','imports')}
                dest.commit()
        # Atomic no-clobber publication on NTFS and ordinary POSIX filesystems.
        # If hard links are unsupported, fail safely rather than risk overwriting.
        os.link(stage, target)
        report={'copied':True,'source_database':str(src),'data_dir':str(destination),
                'counts':counts,'version':VERSION,'source_modified':False,
                'note':'SQLite backup API snapshot; original database retained; later edits in the old app are NOT synchronized.'}
        (destination/'migration-receipt.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        progress('기존 주문·시세·메모 사본 복사 완료. 원본 폴더는 그대로 남았습니다.')
        return report
    finally:
        if stage:
            for p in (stage,Path(str(stage)+'-wal'),Path(str(stage)+'-shm')):
                p.unlink(missing_ok=True)
        lock.unlink(missing_ok=True)


def choose_source():
    try:
        import tkinter as tk
        from tkinter import filedialog
        root=tk.Tk();root.withdraw();root.attributes('-topmost', True)
        try:
            return filedialog.askdirectory(title='기존 AOA 앱 또는 local-data 폴더 선택 (취소: 새 데이터로 시작)') or None
        finally: root.destroy()
    except (ImportError, RuntimeError) as exc:
        raise ValueError('폴더 선택 창을 열 수 없습니다. python run.py --copy-data-from "기존 앱 폴더"를 사용하세요.') from exc
