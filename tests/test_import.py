import csv
import gzip
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from aoa.model import adapt_order,time_us,validate_bar
from aoa.store import Store
from aoa.importer import import_file,safe_members
from tests.test_model import order


def csv_bytes(rows):
    s=io.StringIO(newline=''); w=csv.DictWriter(s,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    return s.getvalue().encode('utf-8-sig')

class ImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.store=Store(self.root/'db')
    def tearDown(self): self.tmp.cleanup()
    def write(self,name,data):
        p=self.root/name;p.write_bytes(data);return p

    def test_context_deduplicates_endpoints_and_reimports(self):
        rows=[order(),order(phase='last',event_time_assumed_utc='2021-06-04T12:34:00Z')]
        p=self.write('order_context.csv',csv_bytes(rows))
        report=import_file(self.store,p)
        self.assertEqual(report['counts']['order_endpoints'],2)
        self.assertEqual(self.store.status()['orders'],1)
        self.assertTrue(import_file(self.store,p)['already_imported'])
        self.assertEqual(len(self.store.events('3086')),1)

    def test_real_extractor_shaped_zip(self):
        t=time_us('2021-06-04T12:00:00Z')//1000000
        rows=[{'reference_pair':'BTCUSDT','candle_open_utc':f'2021-06-04T12:0{i}:00Z','minute_utc':t//60+i,'open':100,'high':102,'low':98,'close':101,'volume':20} for i in range(5)]
        p=self.root/'AOA_candle_analysis.zip'
        with zipfile.ZipFile(p,'w') as z:
            z.writestr('events.csv',csv_bytes([order()]))
            z.writestr('source_metadata/output/order_context.csv',csv_bytes([order()]))
            z.writestr('candles_1m.csv.gz',gzip.compress(csv_bytes(rows)))
            z.writestr('quality_summary.json','{}')
        report=import_file(self.store,p)
        self.assertEqual(self.store.status()['orders'],1)
        self.assertEqual(self.store.status()['markets'][0]['bars'],5)
        data=self.store.candles('BTCUSDT','5m',t,t+300)
        self.assertEqual(data['complete_bars'],1)
        self.assertEqual(data['bars'][0]['volume'],100)

    def test_zip_traversal_rejected(self):
        p=self.root/'bad.zip'
        with zipfile.ZipFile(p,'w') as z:
            z.writestr('../danger.csv',csv_bytes([order()]))
        with self.assertRaises(ValueError): import_file(self.store,p)
        self.assertFalse((self.root/'danger.csv').exists())

    def test_conflicting_candles_are_removed_not_overwritten(self):
        t=time_us('2021-06-04T12:00:00Z')//1000000
        with self.store.connect() as db:
            a=validate_bar('BTCUSDT',t,100,102,98,101,10)
            self.assertEqual(Store.candle(db,a,'one'),'inserted')
            self.assertEqual(Store.candle(db,a,'two'),'duplicate')
            self.assertEqual(Store.candle(db,validate_bar('BTCUSDT',t,100,102,98,101,11),'three'),'conflict')
            self.assertEqual(Store.candle(db,a,'four'),'blocked')
        self.assertEqual(self.store.candles('BTCUSDT','1m',t,t+60)['complete_bars'],0)
        self.assertEqual(self.store.status()['conflicts'],1)

    def test_unknown_zip_rolls_back(self):
        p=self.root/'raw-executions.zip'
        with zipfile.ZipFile(p,'w') as z: z.writestr('raw.csv','execID,side\na,Buy\n')
        with self.assertRaises(ValueError): import_file(self.store,p)
        self.assertEqual(self.store.status()['orders'],0)
        self.assertEqual(self.store.status()['imports'],[])

    def test_invalid_row_is_logged_without_invented_price(self):
        rows=[order(),order(orderid='other',execution_price='-1')]
        p=self.write('context.csv',csv_bytes(rows));r=import_file(self.store,p)
        self.assertEqual(r['counts']['rejected_rows'],1)
        self.assertEqual(self.store.status()['orders'],1)

    def test_same_file_different_filename_dedup(self):
        a=self.write('one.csv',csv_bytes([order()]));b=self.write('two.csv',a.read_bytes())
        import_file(self.store,a)
        self.assertTrue(import_file(self.store,b)['already_imported'])

    def test_window_limit(self):
        with self.assertRaises(ValueError): self.store.candles('BTCUSDT','1m',1622808000,1622808000+4001*60)

    def test_notes_roundtrip(self):
        self.store.save_note('3086','관측과 가설 분리 <script>','반례')
        self.assertEqual(self.store.get_note('3086')['text'],'관측과 가설 분리 <script>')

    def test_year_overlap_includes_carryover(self):
        item=adapt_order(order(event_time_assumed_utc='2020-12-31T23:59:00Z'))
        item['last_us']=time_us('2021-01-01T00:01:00Z')
        with self.store.connect() as db: Store.order(db,item,'synthetic')
        self.assertEqual(len(self.store.episodes(year='2021')),1)
        self.assertEqual(len(self.store.episodes(year='2022')),0)

if __name__=='__main__': unittest.main()
