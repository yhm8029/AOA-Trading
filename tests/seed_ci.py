"""AUTOMATED TEST DATA ONLY. Not AOA's real trades. Never loaded by run.py."""
import math
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from aoa.store import Store
from aoa.model import adapt_order,validate_bar,time_us,iso


def seed(directory):
    store=Store(directory);start=time_us('2021-06-04T00:00:00Z')//1000000
    with store.connect() as db:
        # Two days cover the viewer's context window beyond midnight. Deliberate
        # internal gaps are created by each test, not by a truncated fixture.
        for i in range(48*60):
            o=37000+150*math.sin(i/30)-i*.7;c=o+8*math.sin(i)
            Store.candle(db,validate_bar('BTCUSDT',start+i*60,o,max(o,c)+12,min(o,c)-12,c,20+10*abs(math.sin(i/8))),'SYNTHETIC-TEST-ONLY')
        for idx,(minute,role,before,after,px) in enumerate([(600,'Entry',0,5000000,36700),(620,'Entry',5000000,10000000,36650),(640,'Exit',10000000,5000000,36400),(680,'Exit',5000000,0,36300)]):
            row={'ep_id':'3086','symbol':'XBTUSD','direction':'Short','role':role,'orderid':'SYNTHETIC-'+str(idx),'qty':'5000000','phase':'first',
                 'event_time_assumed_utc':iso((start+minute*60)*1000000),'execution_price':str(px),'qty_before':str(before),'qty_after':str(after),
                 'last_time':iso((start+minute*60+20)*1000000),'avg_basis_before':'36700','episode_net_pnl_btc':'1.23'}
            Store.order(db,adapt_order(row),'SYNTHETIC-TEST-ONLY')
    return store

if __name__=='__main__':seed(sys.argv[1])
