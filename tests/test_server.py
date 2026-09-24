import http.client
import json
import tempfile
import threading
import unittest
from aoa.server import AppServer

class ServerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.server=AppServer(('127.0.0.1',0),self.tmp.name)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.tmp.cleanup()
    def request(self,path,method='GET',body=None,headers=None):
        c=http.client.HTTPConnection('127.0.0.1',self.server.server_address[1]);c.request(method,path,body,headers or {})
        r=c.getresponse();status=r.status;data=r.read();c.close();return status,data
    def test_status(self):
        code,body=self.request('/api/status');self.assertEqual(code,200);self.assertEqual(json.loads(body)['orders'],0)
    def test_no_token_write_rejected(self):
        code,_=self.request('/api/note','POST','{}',{'Content-Type':'application/json'});self.assertEqual(code,403)
    def test_foreign_origin_rejected(self):
        code,_=self.request('/api/status',headers={'Origin':'https://evil.example'});self.assertEqual(code,403)
    def test_dns_rebinding_host_rejected(self):
        code,_=self.request('/api/status',headers={'Host':'evil.example'});self.assertEqual(code,403)
    def test_path_traversal_rejected(self):
        code,_=self.request('/%2e%2e/aoa/server.py');self.assertEqual(code,403)
    def test_note_token_roundtrip(self):
        token=self.server.token
        code,_=self.request('/api/note','POST',json.dumps({'episode':'1','text':'note','tags':'tag'}),{'X-AOA-Token':token,'Content-Type':'application/json'})
        self.assertEqual(code,200)
        code,data=self.request('/api/note?episode=1');self.assertEqual(json.loads(data)['text'],'note')
    def test_invalid_timeframe(self):
        code,_=self.request('/api/candles?tf=abc&start=0&end=0');self.assertEqual(code,400)
    def test_static_index(self):
        code,data=self.request('/');self.assertEqual(code,200);self.assertIn(b'AOA Whale Viewer',data)
    def test_job_initial_idle(self):
        code,body=self.request('/api/job');self.assertEqual(code,200);self.assertEqual(json.loads(body)['state'],'idle')

if __name__=='__main__': unittest.main()
