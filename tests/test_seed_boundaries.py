import tempfile,unittest
from aoa.seed import SeedStore,parse_snapshot
from aoa.store import Store
from tests.test_performance_ledger import orders
class BoundaryTests(unittest.TestCase):
    def test_date_D_is_not_midnight(self):
        self.assertIn('block',parse_snapshot({'transacttime':'2021-01-01D','wallet_balance_btc':100}))
    def test_partial_position_sidebar_matches_detail(self):
        with tempfile.TemporaryDirectory() as td:
            s=SeedStore(td);ev=orders();ev=ev[1:]
            with s.connect() as db:
                for e in ev:e['episode_pnl_btc']=.97;Store.order(db,e,'SYNTHETIC')
                db.execute('INSERT INTO seed_snapshots VALUES(?,?,?,?,?,?,?,?)',('synthetic','x',ev[0]['first_us']-60_000_000,100,None,'A','timestamp','provided_snapshot'))
            self.assertIsNone(s.performance('SYNTH')['seed_return_pct'])
            self.assertIsNone(s.episodes()[0]['seed_return_pct'])
if __name__=='__main__':unittest.main()
