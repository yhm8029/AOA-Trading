import tempfile
import unittest
from pathlib import Path
from aoa.model import normalize_event,candle
from aoa.store import Store,put_event,put_candle,rebuild
from tests.fixtures import event,bars,START

class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.store=Store(Path(self.tmp.name)/'test.sqlite3')
    def tearDown(self):self.tmp.cleanup()
    def load(self,rows):
        with self.store.connect() as db:
            for r in rows:put_candle(db,candle(r),'SYNTHETIC')
            rebuild(db,{'BTCUSDT'})

    def test_complete_aggregation(self):
        rows=bars(10);self.load(rows)
        result=self.store.chart('BTCUSDT',5,START,START+600)
        self.assertEqual(result['valid'],2)
        self.assertEqual(result['bars'][0]['open'],rows[0]['open'])
        self.assertEqual(result['bars'][0]['close'],rows[4]['close'])
        self.assertAlmostEqual(result['bars'][0]['volume'],sum(x['volume'] for x in rows[:5]))

    def test_missing_minute_does_not_become_partial_candle(self):
        rows=bars(10);del rows[2];self.load(rows)
        result=self.store.chart('BTCUSDT',5,START,START+600)
        self.assertEqual(result['bars'][0],{'time':START})
        self.assertEqual(result['valid'],1)
        self.assertEqual(result['missing'],1)

    def test_conflicts_are_quarantined_not_replaced(self):
        row=bars(1)[0]
        with self.store.connect() as db:
            self.assertEqual(put_candle(db,candle(row),'A'),'inserted')
            self.assertEqual(put_candle(db,candle(row),'B'),'duplicate')
            self.assertEqual(put_candle(db,candle({**row,'volume':99}),'C'),'conflict')
            self.assertEqual(put_candle(db,candle(row),'D'),'conflict')
        self.assertEqual(self.store.stats()['minute_bars'],0)
        self.assertEqual(self.store.stats()['conflicting_minutes'],1)

    def test_first_last_and_priority_merge(self):
        e,p=normalize_event(event(),'normalized.csv',2)
        raw=dict(ep_id='900001',symbol='XBTUSD',role='Entry',direction='Short',
            orderid='SYNTHETIC-order-001',phase='first',event_time_assumed_utc=e['event_time_utc'],
            execution_price=103.2,qty=1000000,pre_return_5m_pct=-.2)
        first,fp=normalize_event(raw,'context.csv',2)
        last,lp=normalize_event({**raw,'phase':'last','event_time_assumed_utc':'2021-06-04T01:02:00Z','execution_price':103.4},'context.csv',3)
        with self.store.connect() as db:
            put_event(db,e,p);put_event(db,first,fp);put_event(db,last,lp)
        out=self.store.events('XBTUSD','900001')
        self.assertEqual(len(out),1)
        self.assertEqual(out[0]['event'],'ENTRY_SHORT')
        self.assertEqual(out[0]['first_price'],103.2)
        self.assertEqual(out[0]['last_price'],103.4)
        self.assertGreater(out[0]['end_time_us'],out[0]['time_us'])
        self.assertEqual(out[0]['context']['pre_return_5m_pct'],-.2)

    def test_volume_excludes_future(self):
        rows=bars(70)
        for row in rows:row['volume']=10
        rows[59]['volume']=20;rows[60]['volume']=999
        self.load(rows)
        e,_=normalize_event(event(),'SYNTHETIC',2)
        v=self.store.event_volume(e)
        self.assertEqual(v['pre_1m_volume'],20)
        self.assertEqual(v['pre_1m_rvol20'],2)
        self.assertEqual(v['event_minute_final_volume'],999)
        self.assertTrue(v['event_minute_is_retrospective'])

    def test_note_conflict(self):
        r=self.store.save_note('XBTUSD:900001','관측과 가설은 분리',0)
        self.assertEqual(r['version'],1)
        with self.assertRaises(ValueError):self.store.save_note('XBTUSD:900001','stale',0)
        self.assertEqual(self.store.note('XBTUSD:900001')['body'],'관측과 가설은 분리')

    def test_window_cap(self):
        with self.assertRaises(ValueError):self.store.chart('BTCUSDT',1,START,START+10001*60)
        with self.assertRaises(ValueError):self.store.chart('BTCUSDT',3,START,START+600)

if __name__=='__main__':unittest.main()
