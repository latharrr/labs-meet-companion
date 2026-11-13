import base64
from http.server import HTTPServer
import json
import os
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from labs_meet.web import handler


class PrivateWebTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{'LABS_UI_USER':'owner','LABS_UI_PASSWORD':'local-test-only','LABS_UI_HOST':'meetbot.143.lat','LABS_UI_OPERATIONS':'explicitly-approved'},clear=True)
        self.env.start()
        self.server=HTTPServer(('127.0.0.1',0),handler(self.tmp.name+'/notes.db',8765))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url='http://127.0.0.1:'+str(self.server.server_port)
        self.auth='Basic '+base64.b64encode(b'owner:local-test-only').decode()

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.env.stop();self.tmp.cleanup()

    def call(self,path='/api/review',data=None,auth=True,csrf='',origin='https://meetbot.143.lat',host='meetbot.143.lat'):
        headers={'Host':host}
        if auth:headers['Authorization']=self.auth
        if data is not None:headers.update({'Content-Type':'application/json','X-Labs-CSRF':csrf,'Origin':origin})
        req=Request(self.url+path,headers=headers,data=json.dumps(data).encode() if data is not None else None)
        try:
            with urlopen(req) as r:return r.status,json.load(r)
        except HTTPError as e:return e.code,e.read().decode()

    def test_private_read_and_csrf(self):
        self.assertEqual(self.call(auth=False)[0],401)
        self.assertEqual(self.call(host='attacker.invalid')[0],403)
        status,record=self.call();self.assertEqual(status,200);self.assertTrue(record['operations'])
        self.assertNotIn('local-test-only',json.dumps(record));self.assertFalse(record['live_effects'])
        self.assertEqual(self.call('/api/operate',{'action':'create'},csrf=record['csrf'],origin='https://attacker.invalid')[0],403)
        self.assertEqual(self.call('/api/operate',{'action':'create'},csrf='wrong')[0],403)

    def test_browser_create_approve_but_live_disabled(self):
        csrf=self.call()[1]['csrf']
        data={'action':'create','title':'Private test','link':'https://meet.google.com/abc-defg-hij','consent_confirmed':False}
        self.assertEqual(self.call('/api/operate',data,csrf=csrf)[0],400)
        data['consent_confirmed']=True
        status,record=self.call('/api/operate',data,csrf=csrf);self.assertEqual(status,200)
        item=self.call()[1]['meetings'][0]['outbox'][0]
        self.assertEqual(item['status'],'draft')
        self.assertEqual(self.call('/api/operate',{'action':'approve','outbox':item['id'],'digest':'wrong'},csrf=csrf)[0],400)
        self.assertEqual(self.call('/api/operate',{'action':'approve','outbox':item['id'],'digest':item['digest']},csrf=csrf)[0],200)
        self.assertEqual(self.call('/api/operate',{'action':'execute','outbox':item['id']},csrf=csrf)[0],400)
        self.assertEqual(self.call()[1]['meetings'][0]['outbox'][0]['status'],'approved')

    def test_public_host_requires_auth(self):
        with patch.dict(os.environ,{'LABS_UI_PASSWORD':'','LABS_UI_USER':''}):
            with self.assertRaises(ValueError):handler(self.tmp.name+'/other.db',8765)

    def test_readonly_default_rejects_writes(self):
        with patch.dict(os.environ,{'LABS_UI_OPERATIONS':''}):
            h=handler(self.tmp.name+'/other.db',8765)
            self.assertIsNotNone(h)
