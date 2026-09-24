import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from aoa.server import LocalServer
from aoa.store import Store

class ServerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.store=Store(self.root/'db.sqlite3')
        self.server=LocalServer(('127.0.0.1',0),self.store,self.root)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.port=self.server.server_address[1]
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.tmp.cleanup()
    def request(self,path,method='GET',body=None,headers=None):
        c=http.client.HTTPConnection('127.0.0.1',self.port,timeout=5)
        raw=None if body is None else json.dumps(body)
        c.request(method,path,raw,headers or {})
        r=c.getresponse();result=(r.status,dict(r.getheaders()),r.read());c.close();return result
    def test_health(self):
        status,headers,body=self.request('/api/health')
        self.assertEqual(status,200);self.assertTrue(json.loads(body)['ok'])
        self.assertIn("frame-ancestors 'none'",headers['Content-Security-Policy'])
    def test_cross_origin_read_blocked(self):
        self.assertEqual(self.request('/api/bootstrap',headers={'Origin':'https://evil.example'})[0],403)
    def test_dns_rebinding_host_blocked(self):
        self.assertEqual(self.request('/api/bootstrap',headers={'Host':'evil.example'})[0],403)
    def test_write_needs_token(self):
        self.assertEqual(self.request('/api/note','POST',{'key':'x','body':'hi','version':0})[0],403)
    def test_authenticated_note(self):
        headers={'X-AOA-Token':self.server.token,'Content-Type':'application/json'}
        result=self.request('/api/note','POST',{'key':'x','body':'사실 ≠ 추론','version':0},headers)
        self.assertEqual(result[0],200)
        self.assertEqual(json.loads(self.request('/api/note?key=x')[2])['body'],'사실 ≠ 추론')
    def test_cannot_read_arbitrary_file(self):
        status,_,_=self.request('/%2e%2e/app.py')
        self.assertEqual(status,403)
        self.assertEqual(self.request('/api/not-real')[0],404)
    def test_market_fetch_requires_confirmation(self):
        h={'X-AOA-Token':self.server.token}
        self.assertEqual(self.request('/api/fetch-market','POST',{'pair':'BTCUSDT','start':1,'end':2},h)[0],400)
    def test_index_is_served(self):
        status,h,body=self.request('/')
        self.assertEqual(status,200)
        self.assertIn('text/html',h['Content-Type'])
        self.assertIn(b'chart-wrap',body)
        self.assertIn('데이터 가져오기'.encode('utf-8'),body)

if __name__=='__main__':unittest.main()
