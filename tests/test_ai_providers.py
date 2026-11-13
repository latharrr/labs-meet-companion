import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from labs_meet.ai import GroundedAI, GroundingError, validate_answer, validate_minutes
from labs_meet.core import normalize
from labs_meet.adapters import resend_send
from labs_meet.service import Companion
from labs_meet.store import Store
ROWS=normalize(json.loads((Path(__file__).parent.parent/'fixtures/demo.json').read_text()))
CITE={'id':'a2','quote':'We agreed to test with a private call before a deployment.'}
ANSWER={'text':'A private call comes before deployment.','citations':[CITE]}
NOTES={'summary':[ANSWER],'decisions':[ANSWER],'actions':[]}

class AITests(unittest.TestCase):
    def test_answer_valid(self):self.assertEqual(validate_answer(ANSWER,ROWS)['evidence'],['a2'])
    def test_invalid_id(self):
        with self.assertRaises(GroundingError):validate_answer({'text':'x','citations':[{'id':'fake','quote':'anything'}]},ROWS)
    def test_fabricated_quote(self):
        with self.assertRaises(GroundingError):validate_answer({'text':'x','citations':[{'id':'a2','quote':'It ships tomorrow'}]},ROWS)
    def test_uncited_answer_becomes_not_found(self):self.assertEqual(validate_answer({'text':'Invented claim','citations':[]},ROWS)['evidence'],[])
    def test_notes_owner_ignored(self):
        raw=json.loads(json.dumps(NOTES));raw['actions']=[{**ANSWER,'owner':'Invented person','deadline':'tomorrow'}]
        out=validate_minutes(raw,ROWS);self.assertIsNone(out['actions'][0]['owner']);self.assertIsNone(out['actions'][0]['deadline'])
    def test_missing_note_citations_rejected(self):
        with self.assertRaises(GroundingError):validate_minutes({'summary':[{'text':'A','citations':[]}],'decisions':[],'actions':[]},ROWS)
    def test_ai_disabled_without_authority_switch(self):
        with patch.dict(os.environ,{},clear=True),self.assertRaises(ValueError):GroundedAI('https://api.groq.com/openai/v1','no-real-key').answer('what?',ROWS)
    def test_provider_request_contract(self):
        response={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(ANSWER)}}]}
        with patch.dict(os.environ,{'LABS_AI_EFFECTS':'explicitly-approved'}),patch('labs_meet.ai.request',return_value=response) as req:
            out=GroundedAI('https://api.groq.com/openai/v1','test').answer('what was decided?',ROWS)
        args=req.call_args.args;self.assertEqual(args[1],'/chat/completions');self.assertEqual(args[2],'Bearer test')
        self.assertEqual(args[4]['model'],'openai/gpt-oss-20b');self.assertEqual(args[4]['response_format'],{'type':'json_object'})
        self.assertNotIn('c1',json.loads(args[4]['messages'][1]['content'])['segments'][0]['id'])
        self.assertEqual(out['mode'],'ai-grounded')
    def test_truncated_response_rejected(self):
        response={'choices':[{'finish_reason':'length','message':{'content':json.dumps(ANSWER)}}]}
        with patch.dict(os.environ,{'LABS_AI_EFFECTS':'explicitly-approved'}),patch('labs_meet.ai.request',return_value=response),self.assertRaises(GroundingError):GroundedAI('https://api.groq.com/openai/v1','test').answer('what?',ROWS)
    def test_resend_contract(self):
        payload={'from':'Labs <test@example.test>','to':'owner@example.test','subject':'Approved','text':'Reviewed'}
        with patch.dict(os.environ,{'LABS_RESEND_KEY':'fake'}),patch('labs_meet.adapters.request',return_value={'id':'email-1'}) as req:
            out=resend_send(payload,'labs-meet/out-1')
        args=req.call_args.args;self.assertEqual(args[0:3],('https://api.resend.com','/emails','Bearer fake'));self.assertEqual(args[4]['to'],['owner@example.test']);self.assertEqual(args[6],{'Idempotency-Key':'labs-meet/out-1'});self.assertEqual(out['status'],'accepted')
    def test_resend_requires_id(self):
        with patch.dict(os.environ,{'LABS_RESEND_KEY':'fake'}),patch('labs_meet.adapters.request',return_value={}),self.assertRaises(RuntimeError):resend_send({'from':'test@example.test','to':'owner@example.test','subject':'a','text':'b'},'one')
    def test_artifact_revision_invalidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            s=Store(Path(tmp)/'data.db');app=Companion(s);mid=app.create('T','https://meet.google.com/abc-defg-hij','Synthetic')
            s.ingest(mid,ROWS);s.save_notes(mid,validate_minutes(NOTES,ROWS));self.assertIsNotNone(s.ai_notes(mid))
            s.ingest(mid,[]);self.assertIsNone(s.ai_notes(mid));s.db.close()

class WhatsAppTests(unittest.TestCase):
    def test_verified_contract(self):
        from labs_meet.adapters import whatsapp_send
        env={'LABS_OPENWA_SESSION':'test-session','LABS_OPENWA_TEST_CHAT_ID':'test-owner-id','LABS_OPENWA_URL':'http://127.0.0.1:2785','LABS_OPENWA_KEY':'fake-key'}
        with patch.dict(os.environ,env),patch('labs_meet.adapters.request',return_value={'messageId':'msg1','timestamp':1}) as req:
            out=whatsapp_send({'chat_id':'test-owner-id','text':'Approved words'})
        args=req.call_args.args;self.assertEqual(args[1],'/api/sessions/test-session/messages/send-text');self.assertEqual(args[4],{'chatId':'test-owner-id','text':'Approved words'});self.assertEqual(out['status'],'sent');self.assertIn('not delivered',out['meaning'])
    def test_no_guessed_chat_id(self):
        from labs_meet.adapters import whatsapp_send
        with patch.dict(os.environ,{'LABS_OPENWA_SESSION':'test','LABS_OPENWA_TEST_CHAT_ID':'verified'}),self.assertRaises(ValueError):whatsapp_send({'chat_id':'guessed','text':'No'})
    def test_no_false_success_without_id(self):
        from labs_meet.adapters import whatsapp_send
        env={'LABS_OPENWA_SESSION':'test','LABS_OPENWA_TEST_CHAT_ID':'verified','LABS_OPENWA_URL':'http://127.0.0.1:2785','LABS_OPENWA_KEY':'fake'}
        with patch.dict(os.environ,env),patch('labs_meet.adapters.request',return_value={'ok':True}),self.assertRaises(RuntimeError):whatsapp_send({'chat_id':'verified','text':'Hi'})


class ConfigTests(unittest.TestCase):
    def test_config_does_not_echo_keys(self):
        from labs_meet.config import status
        with patch.dict(os.environ,{"LABS_AI_KEY":"private-example-never-echo","LABS_AI_URL":"https://api.groq.com/openai/v1"},clear=True):
            out=status()
        self.assertNotIn("private-example-never-echo",json.dumps(out))
        self.assertTrue(out["providers"]["groq_ai"]["configured"])
        self.assertEqual(out["providers"]["groq_ai"]["account_access"],"unverified")
        self.assertFalse(out["network_checked"])

    def test_config_rejects_hostless_https(self):
        from labs_meet.config import status
        with patch.dict(os.environ,{"LABS_AI_URL":"https:///missing"},clear=True):
            self.assertEqual(status()["invalid_fields"],["LABS_AI_URL"])
