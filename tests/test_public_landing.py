"""Public synthetic marketing assets cannot bypass private app authentication."""
import base64, os, tempfile, threading, unittest, urllib.request, urllib.error
from http.server import HTTPServer
from pathlib import Path
from unittest.mock import patch
from labs_meet.web import handler

class LandingBoundary(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory()
  self.env=patch.dict(os.environ,{'LABS_UI_USER':'owner','LABS_UI_PASSWORD':'synthetic-only','LABS_UI_HOST':'bot.143.lat','LABS_PUBLIC_LANDING':'explicitly-approved'},clear=True);self.env.start()
  self.server=HTTPServer(('127.0.0.1',0),handler(Path(self.t.name)/'not-created.db',0));self.port=self.server.server_port
  # Use the allowed public host to avoid the ephemeral local-port test mismatch.
  self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
 def tearDown(self):self.server.shutdown();self.server.server_close();self.thread.join();self.env.stop();self.t.cleanup()
 def get(self,path,host='bot.143.lat'):
  req=urllib.request.Request(f'http://127.0.0.1:{self.port}'+path,headers={'Host':host})
  try:
   with urllib.request.urlopen(req,timeout=3) as r:return r.status,r.read(),r.headers
  except urllib.error.HTTPError as r:return r.code,r.read(),r.headers
 def test_preview_is_static_without_reading_database(self):
  for path in ['/welcome/','/welcome/landing.css','/welcome/landing.js']:
   code,body,headers=self.get(path);self.assertEqual(code,200);self.assertTrue(body);self.assertEqual(headers['Cache-Control'],'no-store');self.assertIn("frame-ancestors 'none'",headers['Content-Security-Policy'])
  self.assertFalse((Path(self.t.name)/'not-created.db').exists())
 def test_private_api_and_app_still_require_auth(self):
  for path in ['/','/api/review','/app.js','/style.css']:
   self.assertEqual(self.get(path)[0],401)
 def test_public_assets_require_allowlisted_host(self):
  self.assertEqual(self.get('/welcome/',host='attacker.invalid')[0],403)
 def test_path_traversal_never_serves_private_files(self):
  for path in ['/welcome/../api/review','/welcome/../../auth_core.py','/welcome/%2e%2e/web.py','/welcome/state.db']:
   self.assertNotEqual(self.get(path)[0],200)
 def test_public_preview_requires_explicit_switch(self):
  with patch.dict(os.environ,{'LABS_PUBLIC_LANDING':'off'}):self.assertEqual(self.get('/welcome/')[0],401)
