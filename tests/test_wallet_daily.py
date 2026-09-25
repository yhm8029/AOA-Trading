"""The user's observed CSV SHAPE, but artificial dates/IDs/amounts only."""
import csv,io,json,tempfile,unittest,zipfile
from pathlib import Path
from aoa.seed import SeedBook,SeedStore,parse_snapshot,parse_stamp,DAY_US,VERSION
from aoa.wallet_daily import DailyBook,daily_close
from aoa.seed_import import import_file
from aoa.importer import sha256
from aoa.model import time_us

HEADERS=['date','transactid','account','currency','amount','transactstatus','address','network','text','timestamp','transacttime','transacttype','tx','walletbalance']
def row(day='2020-12-31',key='x',amount='500000000',balance='10000000000',kind='RealisedPNL',**extra):
    r=dict(date=day,transactid=key,account='SYNTHETIC',currency='XBt',amount=amount,transactstatus='Completed',address='',network='',text='',timestamp='00:00.5',transacttime='00:00.0',transacttype=kind,tx='-',walletbalance=balance)
    r.update(extra);return r

def wallet_bytes():
    rows=[row('2020-12-30','a','9000000000','9000000000','Deposit',timestamp='57:26.3',transacttime='57:26.3'),
          row('2020-12-30','b','500000000','9500000000'),row(),
          row('2021-01-01','future','5000000000','15000000000'),
          row('2020-12-31','ignored','-1','1','Withdrawal',transactstatus='Canceled')]
    text=io.StringIO();w=csv.DictWriter(text,fieldnames=HEADERS);w.writeheader();w.writerows(rows)
    return text.getvalue().encode('utf-8-sig')

class WalletDailyTests(unittest.TestCase):
    def test_truncated_time_falls_back_to_date_not_invented_midnight(self):
        r=parse_snapshot(row(timestamp='57:26.3',transacttime='25:46.0'))
        self.assertIn('daily',r);self.assertNotIn('t',r)
        self.assertEqual(r['wallet_btc'],100);self.assertEqual(r['amount_btc'],5)
        with self.assertRaises(ValueError):parse_stamp('57:26.3')
    def test_full_alternative_timestamp_is_usable(self):
        r=parse_snapshot(row(timestamp='57:26.3',transacttime='2020-12-31T23:10:11Z'))
        self.assertEqual(r['t'],time_us('2020-12-31T23:10:11Z'))
        self.assertNotIn('daily',r)
    def test_no_guess_with_malformed_only_or_missing_units(self):
        with self.assertRaises(ValueError):parse_snapshot(row(date='unknown'))
        with self.assertRaises(ValueError):parse_snapshot(row(currency=''))
    def test_timestamp_remains_preferred_over_date(self):
        r=parse_snapshot(row(timestamp='2020-12-31T21:00:00Z'))
        self.assertEqual(r['t'],time_us('2020-12-31T21:00:00Z'))
    def test_canceled_rows_not_cashflow_blocks(self):
        self.assertIsNone(parse_snapshot(row(transactstatus='Canceled',kind='Withdrawal')))
    def test_import_past_day_and_same_hash_reprocessing(self):
        with tempfile.TemporaryDirectory() as td:
            s=SeedStore(Path(td)/'db');s.save_note('SYNTH','KEEP','synthetic')
            p=Path(td)/'wallet.csv';p.write_bytes(wallet_bytes());digest=sha256(p)
            with s.connect() as db:
                db.execute('INSERT INTO seed_imports VALUES(?,?,?)',(digest,'seed-1',json.dumps({'counts':{'seed_files':1,'rejected_rows':4}})))
                db.execute('INSERT INTO issues(source,line,reason) VALUES(?,?,?)',(digest[:12]+'/wallet.csv',2,'시드 연결: old error'))
            report=import_file(s,p)
            counts=report['seed_import']['counts']
            self.assertEqual(counts['daily_rows'],4);self.assertEqual(counts['daily_verified_days'],3)
            self.assertEqual(counts.get('rejected_rows',0),0)
            self.assertEqual(s.status()['seed_daily_verified_days'],3)
            t=time_us('2021-01-01T00:00:00Z');v=s.seed_book().at(t)
            self.assertEqual(v['btc'],100);self.assertEqual(v['reference_day'],'2020-12-31');self.assertIsNone(v['time_us'])
            self.assertEqual(s.seed_book().at(t+12*3_600_000_000)['btc'],100)
            self.assertEqual(s.seed_book().at(t+DAY_US)['btc'],150)
            self.assertTrue(import_file(s,p)['already_imported'])
            self.assertEqual(s.get_note('SYNTH')['text'],'KEEP')
            with s.connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM seed_daily_rows').fetchone()[0],4)
    def test_cashflow_day_is_blocked_until_next_day(self):
        with tempfile.TemporaryDirectory() as td:
            s=SeedStore(Path(td)/'db');p=Path(td)/'wallet.csv';p.write_bytes(wallet_bytes().replace(b'RealisedPNL,-,15000000000',b'Deposit,-,15000000000'))
            import_file(s,p);book=s.seed_book();t=time_us('2021-01-01T12:00:00Z')
            self.assertIsNone(book.at(t)['btc']);self.assertTrue(book.at(t)['has_data'])
            self.assertEqual(book.at(time_us('2021-01-02T00:00:00Z'))['btc'],150)
    def test_daily_chain_and_conflicting_source(self):
        def r(q,v,n,source='A'):return dict(source=source,row_key=str(n),day=1,wallet_btc=v,amount_btc=q,account='S',kind='realisedpnl',ordinal=n,quality='date_only_ledger')
        self.assertEqual(daily_close([r(5,95,1),r(5,100,2)])['btc'],100)
        self.assertEqual(daily_close([r(5,100,1),r(5,95,2)])['btc'],100)
        self.assertFalse(daily_close([r(5,95,1),r(5,103,2)])['valid'])
        self.assertFalse(daily_close([r(10,110,1),r(-10,100,2)])['valid'])
        book=SeedBook(daily=[r(5,100,1),r(5,101,1,'B')])
        self.assertIsNone(book.at(2*DAY_US)['btc'])
    def test_newer_exact_snapshot_and_stale_daily(self):
        d=dict(source='A',row_key='x',day=1,wallet_btc=100,amount_btc=1,account='S',kind='realisedpnl',ordinal=1,quality='date_only_ledger')
        exact=dict(source='A',t=2*DAY_US+1,wallet_btc=120,equity_btc=None,account='S',quality='provided_snapshot')
        book=SeedBook([exact],daily=[d])
        self.assertEqual(book.at(2*DAY_US)['btc'],100)
        self.assertEqual(book.at(2*DAY_US+2)['btc'],120)
        self.assertIsNone(SeedBook(daily=[d]).at(4*DAY_US)['btc'])
    def test_zip_and_csv_agree_without_double_count(self):
        with tempfile.TemporaryDirectory() as td:
            s=SeedStore(Path(td)/'db');p=Path(td)/'wallet.csv';p.write_bytes(wallet_bytes());import_file(s,p)
            z=Path(td)/'original.zip'
            with zipfile.ZipFile(z,'w') as a:a.writestr('source/aoa-wallet.csv',wallet_bytes())
            import_file(s,z)
            self.assertEqual(s.seed_book().at(time_us('2021-01-01T12:00:00Z'))['btc'],100)
    def test_not_using_current_day_when_no_history(self):
        d=dict(source='A',row_key='x',day=1,wallet_btc=100,amount_btc=1,account='S',kind='realisedpnl',ordinal=1,quality='date_only_ledger')
        self.assertIsNone(SeedBook(daily=[d]).at(DAY_US+3600_000_000)['btc'])

if __name__=='__main__':unittest.main()
