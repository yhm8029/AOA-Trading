import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from aoa.importer import import_file,LimitedReader
from aoa.store import Store
from tests.fixtures import package,events,event,bars,csv_bytes,START

class ImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.store=Store(self.root/'local.sqlite3')
    def tearDown(self):self.tmp.cleanup()

    def test_zip_gzip_streaming_and_idempotency(self):
        path=package(self.root/'AOA_candle_analysis(1).zip',count=360)
        report=import_file(self.store,path)
        self.assertEqual(report['candles_inserted'],360)
        self.assertEqual(self.store.stats()['events'],6)
        self.assertEqual(len(self.store.episodes()),2)
        self.assertTrue(import_file(self.store,path)['already_imported'])
        self.assertEqual(self.store.stats()['minute_bars'],360)

    def test_multiple_month_and_annual_csv_do_not_duplicate(self):
        path=self.root/'events.zip'
        with zipfile.ZipFile(path,'w') as z:
            z.writestr('annual_events.csv',csv_bytes(events()))
            z.writestr('monthly/events.csv',csv_bytes(events()))
        import_file(self.store,path)
        self.assertEqual(self.store.stats()['events'],6)

    def test_bad_bar_quarantine(self):
        rows=bars(10);rows[2]['high']=-1
        path=self.root/'candles.csv';path.write_bytes(csv_bytes(rows))
        report=import_file(self.store,path)
        self.assertEqual(report['invalid_rows'],1)
        self.assertEqual(self.store.stats()['minute_bars'],9)
        self.assertEqual(self.store.chart('BTCUSDT',5,START,START+600)['valid'],1)

    def test_bad_duplicate_poisons_known_minute(self):
        rows=bars(10);rows.append({**rows[2],'high':-1})
        path=self.root/'candles.csv';path.write_bytes(csv_bytes(rows))
        import_file(self.store,path)
        self.assertEqual(self.store.stats()['minute_bars'],9)
        self.assertEqual(self.store.chart('BTCUSDT',5,START,START+600)['valid'],1)

    def test_zip_traversal_rolls_back(self):
        path=self.root/'evil.zip'
        with zipfile.ZipFile(path,'w') as z:
            z.writestr('events.csv',csv_bytes(events()))
            z.writestr('../escape.csv',csv_bytes(events()))
        with self.assertRaises(ValueError):import_file(self.store,path)
        self.assertEqual(self.store.stats()['events'],0)
        self.assertFalse((self.root.parent/'escape.csv').exists())

    def test_no_fake_bars_from_features(self):
        row=dict(ep_id=1,symbol='XBTUSD',role='Entry',direction='Long',orderid='s',phase='first',
          event_time_assumed_utc='2021-06-04T00:00:00Z',execution_price=100,qty=10,
          pre_1m_open=1,pre_1m_high=3,pre_1m_low=.5,pre_1m_close=2,pre_1m_volume=50)
        p=self.root/'order_candle_features.csv';p.write_bytes(csv_bytes([row]))
        import_file(self.store,p)
        self.assertEqual(self.store.stats()['minute_bars'],0)
        self.assertEqual(self.store.stats()['events'],1)

    def test_unknown_table_does_not_destroy_previous_data(self):
        p=self.root/'events.csv';p.write_bytes(csv_bytes(events()));import_file(self.store,p)
        p2=self.root/'unknown.csv';p2.write_text('no,known,schema\n1,2,3\n')
        with self.assertRaises(ValueError):import_file(self.store,p2)
        self.assertEqual(self.store.stats()['events'],6)

    def test_nested_binance_archives(self):
        row=f'{START*1000},100,102,99,101,5,{START*1000+59999},500,2,2,200,0\n'
        inner=io.BytesIO()
        with zipfile.ZipFile(inner,'w') as z:z.writestr('BTCUSDT-1m-2021-06.csv',row)
        p=self.root/'AOA_market_data.zip'
        with zipfile.ZipFile(p,'w') as z:z.writestr('market/BTCUSDT-1m-2021-06.zip',inner.getvalue())
        import_file(self.store,p)
        self.assertEqual(self.store.stats()['minute_bars'],1)

    def test_expansion_cap(self):
        r=LimitedReader(io.BytesIO(b'123456'),limit=3)
        with self.assertRaises(ValueError):io.BufferedReader(r).read()

if __name__=='__main__':unittest.main()
