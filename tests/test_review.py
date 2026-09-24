"""Offline regressions for the user's reported symptoms. Fixtures are synthetic."""
import io
import json
import math
import tempfile
import unittest
import urllib.error
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch
from aoa.review import ReviewStore, missing_plan, performance
from aoa.market import fetch_window
from aoa.model import adapt_order, validate_bar, time_us, iso
from aoa.store import Store

T=time_us('2021-01-03T10:00:00Z')//1_000_000

def order(ep,t,role='Entry',qty=100,px=100,basis=100,after=100,pnl=None):
    return adapt_order({'ep_id':str(ep),'orderid':f'SYNTHETIC-{ep}-{t}-{role}','symbol':'XBTUSD','direction':'Short','role':role,'qty':qty,'event_time_assumed_utc':iso(t*1_000_000),'last_time':iso((t+1)*1_000_000),'execution_price':px,'avg_basis_before':basis,'qty_before':0 if role=='Entry' else qty,'qty_after':after,'episode_net_pnl_btc':pnl})

def response_row(t):
    return [t*1000,'100','102','99','101','10',t*1000+59999,'1000',3,'5','500',0]

class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.store=ReviewStore(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def add(self,item):
        with self.store.connect() as db:Store.order(db,item,'SYNTHETIC-TEST')
    def bar(self,t):
        with self.store.connect() as db:Store.candle(db,validate_bar('BTCUSDT',t,100,102,99,101,10),'SYNTHETIC-TEST')
    def test_entry_year_excludes_carryover(self):
        old=time_us('2020-12-28T20:54:00Z')//1_000_000
        self.add(order('old',old));self.add(order('old',T,'Exit',after=0))
        self.add(order('new',T));self.add(order('new',T+60,'Exit',after=0))
        self.assertEqual([e['id'] for e in self.store.episodes(year='2021')],['new'])
        both=self.store.episodes(year='2021',year_mode='overlap')
        self.assertEqual([e['id'] for e in both],['old','new'])
        self.assertTrue(both[0]['carried'])
        self.assertGreaterEqual(both[0]['focus'],time_us('2021-01-01T00:00:00Z')//1_000_000)
    def test_invalid_year(self):
        with self.assertRaises(ValueError):self.store.episodes(year='1')
        with self.assertRaises(ValueError):self.store.episodes(year='2021',year_mode='unknown')
    def test_gap_plan_and_strict_aggregate(self):
        for i in (0,1,4):self.bar(T+i*60)
        p=missing_plan(self.store,'BTCUSDT',T,T+300)
        self.assertEqual(p['ranges'],[(T+120,T+240)])
        r=self.store.candles('BTCUSDT','5m',T,T+300)
        self.assertEqual(r['complete_bars'],0);self.assertEqual(r['coverage']['missing_minutes'],2)
    def test_conflicts_are_never_overwritten(self):
        self.bar(T)
        with self.store.connect() as db:Store.candle(db,validate_bar('BTCUSDT',T,100,103,99,101,10),'CONFLICT')
        p=missing_plan(self.store,'BTCUSDT',T,T+120)
        self.assertEqual(p['conflict_minutes'],1);self.assertEqual(p['ranges'],[(T+60,T+120)])
    def test_gap_download_only_requests_missing_and_is_cached(self):
        self.bar(T);self.bar(T+180);calls=[]
        def opener(req,timeout):
            q=parse_qs(urlsplit(req.full_url).query);a=int(q['startTime'][0])//1000;b=(int(q['endTime'][0])+1)//1000
            calls.append((a,b));return io.BytesIO(json.dumps([response_row(t) for t in range(a,b,60)]).encode())
        r=fetch_window(self.store,'BTCUSDT',T,T+300,opener=opener)
        self.assertEqual(calls,[(T+60,T+180),(T+240,T+300)])
        self.assertTrue(r['complete']);self.assertEqual(r['received'],3)
        self.assertEqual(self.store.candles('BTCUSDT','5m',T,T+300)['complete_bars'],1)
        r=fetch_window(self.store,'BTCUSDT',T,T+300,opener=opener)
        self.assertEqual(r['requests'],0);self.assertEqual(len(calls),2)
    def test_no_sqlite_write_lock_during_network(self):
        def opener(req,timeout):
            # This second writer would time out with the old BEGIN spanning network waits.
            with self.store.connect() as db:
                db.execute('PRAGMA busy_timeout=100')
                db.execute("INSERT INTO notes(episode,text,tags) VALUES('test','can write','')")
            return io.BytesIO(json.dumps([response_row(T)]).encode())
        fetch_window(self.store,'BTCUSDT',T,T+60,opener=opener)
        self.assertEqual(self.store.get_note('test')['text'],'can write')
    def test_empty_upstream_is_reported_not_filled(self):
        r=fetch_window(self.store,'BTCUSDT',T,T+60,opener=lambda req,timeout:io.BytesIO(b'[]'))
        self.assertEqual(r['received'],0);self.assertEqual(r['remaining_missing_minutes'],1);self.assertFalse(r['complete'])
    def test_malformed_bar_rejected_before_write(self):
        r=response_row(T);r[3]='200'
        with self.assertRaises(ValueError):fetch_window(self.store,'BTCUSDT',T,T+60,opener=lambda req,timeout:io.BytesIO(json.dumps([r]).encode()))
        self.assertFalse(self.store.status()['markets'])
    def test_access_restriction_not_bypassed(self):
        def opener(req,timeout):raise urllib.error.HTTPError(req.full_url,451,'Restricted',{},None)
        with self.assertRaisesRegex(ValueError,'접근 제한'):fetch_window(self.store,'BTCUSDT',T,T+60,opener=opener)
    def test_large_retry_after_does_not_retry_early(self):
        def opener(req,timeout):raise urllib.error.HTTPError(req.full_url,429,'Rate',{'Retry-After':'120'},None)
        with self.assertRaisesRegex(ValueError,'120초'):fetch_window(self.store,'BTCUSDT',T,T+60,opener=opener)
    def test_pages_commit_and_resume_after_later_failure(self):
        n=[0]
        def opener(req,timeout):
            n[0]+=1
            if n[0]>1:raise urllib.error.HTTPError(req.full_url,451,'Restricted',{},None)
            return io.BytesIO(json.dumps([response_row(T+i*60) for i in range(1000)]).encode())
        with patch('aoa.market.time.sleep'):
            with self.assertRaises(ValueError):fetch_window(self.store,'BTCUSDT',T,T+1001*60,opener=opener)
        self.assertEqual(self.store.status()['markets'][0]['bars'],1000)
    def test_performance_is_qty_weighted_not_first_to_last(self):
        events=[{'role':'Exit','direction':'Long','qty':100,'basis_before':100,'avg_price':110,'episode_pnl_btc':2},
                {'role':'Exit','direction':'Long','qty':300,'basis_before':200,'avg_price':180,'episode_pnl_btc':2}]
        p=performance(events)
        self.assertAlmostEqual(p['price_return_pct'],-5)
        self.assertEqual(p['net_pnl_btc'],2);self.assertIsNone(p['reference_roi_pct'])
        self.assertAlmostEqual(performance(events,4)['reference_roi_pct'],50)
    def test_missing_basis_is_not_zero(self):
        p=performance([{'role':'Exit','direction':'Short','qty':100,'first_price':90}])
        self.assertIsNone(p['price_return_pct']);self.assertEqual(p['coverage_pct'],0)
    def test_profit_conflict_blocks_roi(self):
        p=performance([{'episode_pnl_btc':1},{'episode_pnl_btc':2}],2)
        self.assertTrue(p['pnl_conflict']);self.assertIsNone(p['net_pnl_btc']);self.assertIsNone(p['reference_roi_pct'])
    def test_margin_reference_persists_without_erasing_old_notes(self):
        self.add(order('one',T,pnl=2));self.store.save_note('one','existing note','tag')
        self.store.set_reference_margin('one',4)
        reopened=ReviewStore(self.temp.name)
        self.assertEqual(reopened.get_note('one')['text'],'existing note')
        self.assertEqual(reopened.performance('one')['reference_roi_pct'],50)
        for v in (-1,0,math.inf,math.nan):
            with self.assertRaises(ValueError):self.store.set_reference_margin('one',v)
        self.store.set_reference_margin('one',None);self.assertIsNone(self.store.performance('one')['reference_roi_pct'])

if __name__=='__main__':unittest.main()
