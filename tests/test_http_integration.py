"""Real HTTP against loopback contract double, NOT a real Vexa deployment."""
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from labs_meet.adapters import Vexa, request
from labs_meet.store import Store
from labs_meet.service import Companion

FIXTURE=json.loads((Path(__file__).parent.parent/'fixtures/demo.json').read_text())

class HTTPIntegration(unittest.TestCase):
    def setUp(self):
        self.calls=[]; outer=self
        class Handler(BaseHTTPRequestHandler):
            def handle_request(self):
                body=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))) or b'{}')
                outer.calls.append((self.command,self.path,body,self.headers.get('X-API-Key')))
                status=200
                if self.headers.get('X-API-Key')!='test-key':status=401;data={'detail':'no'}
                elif self.path=='/redirect':status=302;data={}
                elif self.path.startswith('/transcripts/'):data=FIXTURE
                elif self.path.endswith('/chat/result-1'):data={'status':'posted','request_id':'result-1'}
                elif self.path.endswith('/chat'):data={'status':'queued','request_id':'result-1'}
                elif self.command=='DELETE':data={'status':'stopping'}
                else:data={'status':'starting','id':42}
                self.send_response(status)
                if status==302:self.send_header('Location','https://example.test/leak')
                self.end_headers();self.wfile.write(json.dumps(data).encode())
            do_GET=handle_request;do_POST=handle_request;do_DELETE=handle_request
            def log_message(self,*args):pass
        self.server=HTTPServer(('127.0.0.1',0),Handler)
        self.thread=threading.Thread(target=self.server.serve_forever);self.thread.start()
        self.base=f'http://127.0.0.1:{self.server.server_port}'
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'test.db')
        self.app=Companion(self.store,Vexa(self.base,'test-key'))
        self.mid=self.app.create('Test','https://meet.google.com/abc-defg-hij','Synthetic HTTP test; no real call')
    def tearDown(self):self.server.shutdown();self.thread.join();self.server.server_close();self.store.db.close();self.tmp.cleanup()
    def approve(self,oid):self.store.approve(oid,self.store.out(oid)['digest'])
    def test_join_sync_chat_status_leave_flow(self):
        with patch.dict(os.environ,{'LABS_LIVE_EFFECTS':'explicitly-approved'}):
            oid=self.app.stage_join(self.mid);self.approve(oid);out=self.app.execute(oid)
            self.assertEqual(out['status'],'submitted') # never claim admitted
            drafts=self.app.sync(self.mid);self.assertEqual(len(drafts),1)
            oid=drafts[0];self.approve(oid);out=self.app.execute(oid)
            self.assertEqual(out['status'],'queued') # not delivered yet
            self.assertEqual(self.app.reconcile_chat(oid)['status'],'posted')
            leave=self.store.stage(self.mid,'leave',{'code':'abc-defg-hij'});self.approve(leave);self.app.execute(leave)
        self.assertEqual(self.calls[0][0:2],('POST','/bots'))
        self.assertEqual(self.calls[0][2]['platform'],'google_meet')
        self.assertEqual(self.calls[-1][0],'DELETE')
        self.assertTrue(all(c[3]=='test-key' for c in self.calls))
    def test_redirect_not_followed(self):
        with self.assertRaisesRegex(RuntimeError,'302'):request(self.base,'/redirect','test-key')
        self.assertEqual(len(self.calls),1)
    def test_key_error_redacted(self):
        with self.assertRaises(RuntimeError) as exc:Vexa(self.base,'secret-wrong-key').transcript('abc-defg-hij')
        self.assertNotIn('secret-wrong-key',str(exc.exception));self.assertIn('401',str(exc.exception))
    def test_write_not_retried(self):
        with patch.dict(os.environ,{'LABS_LIVE_EFFECTS':'explicitly-approved'}):
            oid=self.app.stage_join(self.mid);self.approve(oid);self.app.execute(oid)
            with self.assertRaises(ValueError):self.app.execute(oid)
        self.assertEqual(len(self.calls),1)
    def test_second_reader_does_not_recover_active_send(self):
        oid=self.app.stage_join(self.mid);self.approve(oid);self.store.claim(oid)
        other=Store(Path(self.tmp.name)/'test.db');self.assertEqual(other.out(oid)['status'],'sending');other.db.close()
