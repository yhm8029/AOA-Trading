"""Synthetic ledger tests. Not a substitute for an audit of the user's CSVs."""
import csv
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from aoa.model import time_us,adapt_order
from aoa.store import Store
from aoa.seed import SeedBook,SeedStore,parse_snapshot,order_sizing,DAY_US
from aoa.seed_import import import_file

T=time_us('2021-01-03T00:00:00Z')
def snapshot(t=T,w=100,e=None,account='A',source='synthetic'):
    return dict(t=t,wallet_btc=w,equity_btc=e,account=account,source=source,quality='provided_snapshot')
def event(role='Entry',qty=100000,price=10000,**kw):
    r=dict(id='event',episode_id='1',role=role,qty=qty,symbol='XBTUSD',direction='Long',first_us=T+60_000_000,last_us=T+60_000_000,first_observed=True,last_observed=True,first_price=price,last_price=price,inverse_price=price,position_before=0,position_after=qty)
    r.update(kw);return r

class SeedTests(unittest.TestCase):
    def test_units(self):
        base={'timestamp':'2021-01-03T00:00:00Z','walletBalance':'100000000','currency':'XBt','transactStatus':'Completed'}
        self.assertEqual(parse_snapshot(base)['wallet_btc'],1)
        self.assertEqual(parse_snapshot({**base,'currency':'BTC','walletBalance':'100'})['wallet_btc'],100)
        with self.assertRaises(ValueError):parse_snapshot({**base,'currency':''})
        self.assertIsNone(parse_snapshot({**base,'transactStatus':'Canceled'}))
    def test_canonical_and_D_timestamp(self):
        r=parse_snapshot({'timestamp':'2021-01-03D00:00:00','wallet_balance_btc':100,'equity_btc':90})
        self.assertEqual(r['t'],T);self.assertEqual(r['equity_btc'],90)
    def test_past_only_and_units(self):
        book=SeedBook([snapshot(),snapshot(T+100_000_000,200)])
        self.assertIsNone(book.at(T)['btc'])
        self.assertEqual(book.at(T+1)['btc'],100)
        self.assertEqual(book.at(T+100_000_000)['btc'],100)
        self.assertEqual(book.at(T+100_000_001)['btc'],200)
    def test_date_only_blocks_until_new_snapshot(self):
        r=parse_snapshot({'date':'2021-01-03','wallet_balance_btc':200,'transactType':'Deposit'})
        book=SeedBook([snapshot(T-DAY_US),snapshot(T+DAY_US+1,200)],[dict(day=r['block'],account='A')])
        self.assertIsNone(book.at(T+60_000_000)['btc'])
        self.assertEqual(book.at(T+DAY_US+2)['btc'],200)
    def test_conflict_and_accounts(self):
        self.assertIsNone(SeedBook([snapshot(),snapshot(w=110,source='other')]).at(T+1)['btc'])
        self.assertIsNone(SeedBook([snapshot(),snapshot(account='B')]).at(T+1)['btc'])
        self.assertEqual(SeedBook([snapshot(),snapshot(source='same_value')]).at(T+1)['btc'],100)
    def test_invalid_or_stale_seed(self):
        for w in [0,-10]:self.assertIsNone(SeedBook([snapshot(w=w)]).at(T+1)['btc'])
        self.assertIsNone(SeedBook([snapshot()]).at(T+2*DAY_US)['btc'])
    def test_explicit_equity_and_fixed_current_basis(self):
        book=SeedBook([snapshot(e=100),snapshot(T+2_000_000,w=100,e=80)])
        initial=book.at(T+1)
        x=order_sizing(event(qty=200000),initial,book)
        self.assertEqual(initial['kind'],'equity')
        self.assertEqual(x['order_initial_seed_pct'],20)
        self.assertEqual(x['order_current_seed_pct'],25)
        self.assertEqual(x['after_initial_seed_pct'],20)
        self.assertEqual(x['after_current_seed_pct'],25)
    def test_reduction_and_interleaved_endpoints(self):
        book=SeedBook([snapshot()]);initial=book.at(T+1)
        x=order_sizing(event('Exit',40000,position_before=100000,position_after=60000),initial,book)
        self.assertEqual(x['reduced_position_pct'],40)
        self.assertEqual(x['after_initial_seed_pct'],6)
        x=order_sizing(event('Exit',40000,position_before=100000,position_after=90000),initial,book)
        self.assertIsNone(x['reduced_position_pct']);self.assertFalse(x['endpoints_isolated'])
    def test_non_inverse_and_over_100(self):
        book=SeedBook([snapshot(w=1)]);s=book.at(T+1)
        self.assertEqual(order_sizing(event(),s,book)['order_initial_seed_pct'],1000)
        self.assertIsNone(order_sizing(event(symbol='ETHUSD'),s,book)['order_value_btc'])
    def test_import_original_zip_shape_and_duplicate(self):
        with tempfile.TemporaryDirectory() as td:
            store=SeedStore(Path(td)/'db');store.save_note('1','KEEP','test')
            path=Path(td)/'aoa_public_2021-12-31_with_letter.zip'
            with zipfile.ZipFile(path,'w') as z:
                z.writestr('folder/aoa-wallet-2018-03-01-2021-12-31.csv','timestamp,transactid,transactstatus,transacttype,currency,walletbalance\n2021-01-03T00:00:00Z,x,Completed,RealisedPNL,XBt,10000000000\n2021-01-03T00:01:00Z,y,Canceled,Withdrawal,XBt,0\n')
                z.writestr('aoa-execution-2021-01-01-2021-06-30.csv','execid,execCost\nnot-imported,0\n')
            r=import_file(store,path);self.assertEqual(r['seed_import']['counts']['snapshot_rows'],1)
            self.assertEqual(store.seed_book().at(T+1)['btc'],100)
            self.assertTrue(import_file(store,path)['already_imported'])
            self.assertEqual(store.status()['seed_snapshots'],1)
            self.assertEqual(store.get_note('1')['text'],'KEEP')
    def test_seed_without_ledger_never_makes_pnl(self):
        with tempfile.TemporaryDirectory() as td:
            s=SeedStore(td)
            self.assertIsNone(s.performance('missing')['seed_return_pct'])
    def test_provided_partial_position_not_initial(self):
        with tempfile.TemporaryDirectory() as td:
            s=SeedStore(td)
            self.assertIsNone(s.initial_seed([event(position_before=20)])['btc'])

if __name__=='__main__':unittest.main()
