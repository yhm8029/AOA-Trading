import gzip
import io
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from aoa.store import Store
from aoa.importer import import_file,BoundedReader
from tests.test_model import order
from tests.test_import import csv_bytes

class Regressions(unittest.TestCase):
    def test_connection_context_really_closes(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(directory)
            with store.connect() as db:db.execute('SELECT 1')
            with self.assertRaises(sqlite3.ProgrammingError):db.execute('SELECT 1')
            # Windows cannot unlink an open SQLite file.
            store.path.unlink()

    def test_features_audit_quantity_header(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'order_candle_features.csv';row=order()
            row['order_group_qty_audit_only']=row.pop('qty')
            row['pre_1m_body_pct']='20.5';row['post_proxy_15m_return_pct']='-10'
            p.write_bytes(csv_bytes([row]));store=Store(Path(directory)/'db')
            import_file(store,p);event=store.events('3086')[0]
            self.assertEqual(event['qty'],5000000)
            self.assertEqual(event['features']['pre_1m_body_pct'],20.5)
            self.assertNotIn('post_proxy_15m_return_pct',event['features'])

    def test_expanded_byte_limit(self):
        with patch('aoa.importer.MAX_ARCHIVE_BYTES',10):
            with io.BufferedReader(BoundedReader(io.BytesIO(b'x'*50),[0])) as f:
                with self.assertRaises(ValueError):f.read()

    def test_failed_archive_does_not_hold_source_file(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'unknown.csv';p.write_text('other,value\na,b\n')
            store=Store(Path(directory)/'db')
            with self.assertRaises(ValueError):import_file(store,p)
            p.unlink()

if __name__=='__main__':unittest.main()
