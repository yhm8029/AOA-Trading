import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from aoa.market import fetch_public
from aoa.store import Store
from tests.fixtures import START

class MarketTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.store=Store(self.root/'db.sqlite3')
    def tearDown(self):self.tmp.cleanup()
    def test_market_requests_do_not_include_trades(self):
        urls=[]
        def opener(request,timeout):
            urls.append(request.full_url)
            rows=[[START*1000+i*60000,'100','102','99','101','5',START*1000+i*60000+59999,'500',2,'2','200','0'] for i in range(5)]
            return io.BytesIO(json.dumps(rows).encode())
        with patch('aoa.market.time.sleep'):
            r=fetch_public(self.store,'BTCUSDT',START,START+300,self.root/'cache',opener=opener)
        self.assertEqual(r['inserted'],5)
        self.assertNotIn('order',urls[0])
        self.assertNotIn('episode',urls[0])
        self.assertTrue(urls[0].startswith('https://data-api.binance.vision/'))
        self.assertEqual(self.store.chart('BTCUSDT',5,START,START+300)['valid'],1)
    def test_region_restriction_is_not_bypassed(self):
        def opener(request,timeout):raise HTTPError(request.full_url,451,'blocked',{},None)
        with self.assertRaisesRegex(ValueError,'451'):
            fetch_public(self.store,'BTCUSDT',START,START+300,self.root/'cache',opener=opener)
        self.assertEqual(self.store.stats()['minute_bars'],0)
    def test_range_cap(self):
        with self.assertRaises(ValueError):
            fetch_public(self.store,'BTCUSDT',START,START+33*86400,self.root/'cache')
    def test_unsorted_payload_rolls_back(self):
        rows=[[START*1000,'100','102','99','101','5',START*1000+59999,'500',2,'2','200','0']]*2
        def opener(request,timeout):return io.BytesIO(json.dumps(rows).encode())
        with self.assertRaisesRegex(ValueError,'Unsorted'):
            fetch_public(self.store,'BTCUSDT',START,START+300,self.root/'cache',opener=opener)
        self.assertEqual(self.store.stats()['minute_bars'],0)

if __name__=='__main__':unittest.main()
