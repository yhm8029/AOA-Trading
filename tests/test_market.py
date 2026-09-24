import io
import json
import tempfile
import unittest
from aoa.market import fetch_window
from aoa.store import Store

class MarketTests(unittest.TestCase):
    def test_public_only_url_and_validation(self):
        with tempfile.TemporaryDirectory() as d:
            store=Store(d);start=1622808000
            def opener(req,timeout):
                self.assertTrue(req.full_url.startswith('https://data-api.binance.vision/api/v3/klines?'))
                self.assertNotIn('api-key',str(req.headers).lower())
                row=[start*1000,'100','102','98','101','10',start*1000+59999,'1000',3,'5','500',0]
                return io.BytesIO(json.dumps([row]).encode())
            r=fetch_window(store,'BTCUSDT',start,start+60,opener=opener)
            self.assertEqual(r['received'],1)
            self.assertEqual(store.status()['markets'][0]['bars'],1)
    def test_nonpublic_range_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError): fetch_window(Store(d),'BTCUSDT',0,20001*60)
    def test_symbol_cannot_be_url(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError): fetch_window(Store(d),'https://evil.example',1622808000,1622808060)

if __name__=='__main__': unittest.main()
