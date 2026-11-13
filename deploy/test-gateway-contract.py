"""Run with pinned gateway production venv/PYTHONPATH and synthetic env/key.
Requires generated gateway/manifests copied/symlinked to gateway/core like Docker COPY.
No server, Redis, HTTP provider, real meeting, or real owner credential used.
"""
import importlib.util
from pathlib import Path
from fastapi.testclient import TestClient

spec=importlib.util.spec_from_file_location('meeting_wrapper',Path(__file__).with_name('meeting-gateway.py'))
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
app=module.make_app();client=TestClient(app)
assert len(app.routes)==len(module.ALLOWED)==7
omitted=('/mcp','/mcp/test','/agent','/agent/test','/api/chat','/api/sessions','/invocations','/docs','/openapi.json','/user/models','/meetings/a/share','/bot-accounts')
for path in omitted:
    for method in ('GET','POST'):
        result=client.request(method,path)
        assert result.status_code==404,(method,path,result.status_code)
for method,path in [('GET','/transcripts/google_meet/abc-defg-hij'),('POST','/bots'),('POST','/bots/google_meet/abc-defg-hij/chat')]:
    result=client.request(method,path,json={})
    assert result.status_code==401,(method,path,result.status_code)
assert client.get('/bots').status_code==405
assert client.post('/transcripts/google_meet/abc-defg-hij',json={}).status_code==405
print('PASS:7minimal routes;24omitted requests404;3unauthenticated requests401;2wrong-method requests405')
