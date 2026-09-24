import sqlite3
import tempfile
import unittest
from pathlib import Path
from aoa.store import Store

class ResourceTests(unittest.TestCase):
    def test_connection_is_explicitly_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'db.sqlite3')
            with store.connect() as db:
                self.assertEqual(db.execute('SELECT 1').fetchone()[0],1)
            with self.assertRaises(sqlite3.ProgrammingError):
                db.execute('SELECT 1')
            # Keep db variable alive: the file must still be movable on Windows.
            store.path.rename(Path(tmp)/'moved.sqlite3')

    def test_exception_rolls_back_and_closes(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'db.sqlite3')
            with self.assertRaises(RuntimeError):
                with store.connect() as db:
                    db.execute("INSERT INTO metadata VALUES('rollback-test','x')")
                    raise RuntimeError('synthetic failure')
            with store.connect() as db:
                self.assertIsNone(db.execute("SELECT value FROM metadata WHERE key='rollback-test'").fetchone())

if __name__=='__main__':unittest.main()
