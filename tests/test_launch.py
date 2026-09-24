"""Regression tests for the actual update failure, not just chart computation."""
import errno
import hashlib
import json
import socket
import sqlite3
import tempfile
import threading
import unittest
import urllib.request
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from aoa.launch import verify_install, bind_server, confirm_server, copy_existing_data, REQUIRED_FILES
from aoa.server import AppServer
from aoa.store import Store
from aoa.version import VERSION

ROOT=Path(__file__).resolve().parent.parent

class LaunchTests(unittest.TestCase):
    def test_current_source_has_guard_and_version(self):
        self.assertEqual(verify_install(ROOT)['version'],VERSION)

    def test_mixed_release_is_rejected_before_data_open(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            for name in REQUIRED_FILES:
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((ROOT/name).read_bytes())
            mapping={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in REQUIRED_FILES}
            (root/'release-manifest.json').write_text(json.dumps({'version':VERSION,'files_sha256':mapping}),encoding='utf-8')
            self.assertEqual(verify_install(root)['mode'],'verified-release')
            (root/'web/app.mjs').write_text('old code',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'app.mjs'):verify_install(root)
            self.assertFalse((root/'local-data').exists())

    def test_old_version_manifest_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/'release-manifest.json').write_text(json.dumps({'version':'0.0.1','files_sha256':{}}))
            with self.assertRaises(ValueError):verify_install(root)

    def test_busy_old_port_uses_a_new_verified_instance(self):
        with tempfile.TemporaryDirectory() as td, closing(socket.socket()) as old:
            old.bind(('127.0.0.1',0));old.listen();port=old.getsockname()[1]
            server,moved=bind_server(AppServer,td,port)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                self.assertTrue(moved);self.assertNotEqual(server.server_address[1],port)
                url=confirm_server(server)
                self.assertIn('launch='+server.runtime['instance'],url)
                self.assertIn('v='+VERSION,url)
                self.assertEqual(old.getsockname()[1],port)
                with urllib.request.urlopen(url.split('/?')[0]+'/api/runtime') as r:
                    self.assertIn('no-store',r.headers['Cache-Control']);body=json.load(r)
                self.assertNotIn('token',body)
                self.assertEqual(body['data_dir'],str(Path(td).resolve()))
            finally:server.shutdown();server.server_close();thread.join()

    def test_strict_port_refuses_instead_of_killing_process(self):
        with tempfile.TemporaryDirectory() as td, closing(socket.socket()) as old:
            old.bind(('127.0.0.1',0));old.listen()
            with self.assertRaises(OSError):bind_server(AppServer,td,old.getsockname()[1],strict=True)

    def test_non_bind_failure_not_silently_retried(self):
        def fail(*a):raise PermissionError(errno.EACCES,'denied')
        with self.assertRaises(PermissionError):bind_server(fail,'unused',8765)

    def test_runtime_does_not_accept_foreign_host(self):
        with tempfile.TemporaryDirectory() as td:
            server=AppServer(('127.0.0.1',0),td);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                req=urllib.request.Request('http://127.0.0.1:'+str(server.server_address[1])+'/api/runtime',headers={'Host':'example.com'})
                with self.assertRaises(urllib.error.HTTPError) as exc:urllib.request.urlopen(req)
                self.assertEqual(exc.exception.code,403)
            finally:server.shutdown();server.server_close();thread.join()

    def test_backup_copies_committed_wal_and_keeps_original(self):
        with tempfile.TemporaryDirectory() as td:
            src=Store(Path(td)/'old'/'local-data');dest=Path(td)/'new'/'local-data'
            with src.connect() as writer:
                writer.execute('PRAGMA wal_autocheckpoint=0')
                writer.execute("INSERT INTO notes(episode,text,tags) VALUES('SYNTHETIC','보존할 메모','test')")
                writer.execute("INSERT INTO orders VALUES('SYNTHETIC','SYNTHETIC','XBTUSD','Short',1,'{}')")
                writer.commit()
                self.assertTrue(Path(str(src.path)+'-wal').exists())
                report=copy_existing_data(src.directory.parent,dest,progress=lambda _:None)
                self.assertEqual(report['counts']['notes'],1)
                self.assertEqual(writer.execute('SELECT text FROM notes').fetchone()[0],'보존할 메모')
                with closing(sqlite3.connect(dest/'viewer.sqlite3')) as db:
                    self.assertEqual(db.execute('SELECT text FROM notes').fetchone()[0],'보존할 메모')
                    self.assertEqual(db.execute('PRAGMA quick_check').fetchone()[0],'ok')
                with self.assertRaises(ValueError):copy_existing_data(src.directory,dest,progress=lambda _:None)
                self.assertTrue(src.path.exists())

    def test_backup_rejects_foreign_db_without_creating_target(self):
        with tempfile.TemporaryDirectory() as td:
            src=Path(td)/'old';src.mkdir();dest=Path(td)/'new'
            with closing(sqlite3.connect(src/'viewer.sqlite3')) as db:db.execute('CREATE TABLE unknown(x)');db.commit()
            with self.assertRaises(ValueError):copy_existing_data(src,dest,progress=lambda _:None)
            self.assertFalse((dest/'viewer.sqlite3').exists())
            self.assertFalse((dest/'.migration.lock').exists())

    def test_backup_failure_cleans_stage_without_touching_source(self):
        with tempfile.TemporaryDirectory() as td:
            src=Store(Path(td)/'old');dest=Path(td)/'new'
            def fail(_):raise RuntimeError('synthetic interrupted')
            with self.assertRaises(RuntimeError):copy_existing_data(src.directory,dest,progress=fail)
            self.assertTrue(src.path.exists());self.assertFalse((dest/'viewer.sqlite3').exists())
            self.assertFalse(list(dest.glob('aoa-snapshot-*')))

if __name__=='__main__':unittest.main()
