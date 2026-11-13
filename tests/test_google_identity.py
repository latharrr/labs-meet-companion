"""Verifier integration contract mocks only. No Google login/network call."""
import sys, types, unittest
from unittest.mock import patch
from labs_meet.google_identity import verify_credential
from labs_meet.auth_core import AuthError

class GoogleBoundary(unittest.TestCase):
 def verify(self,claims=None,error=None):
  mod=types.ModuleType('google.oauth2');token=types.SimpleNamespace()
  def check(credential,request,aud):
   self.assertEqual(aud,'synthetic.apps.googleusercontent.com')
   if error:raise error
   return claims
  token.verify_oauth2_token=check;mod.id_token=token
  transport=types.ModuleType('google.auth.transport.requests');transport.Request=lambda:object()
  with patch.dict(sys.modules,{'google.oauth2':mod,'google.auth.transport.requests':transport}):
   return verify_credential('synthetic-token-'*10,configured_client_id='synthetic.apps.googleusercontent.com',expected_nonce='a'*32)
 def good(self):return {'aud':'synthetic.apps.googleusercontent.com','iss':'https://accounts.google.com','nonce':'a'*32,'sub':'synthetic-stable-sub','email':'not-used@example.test','email_verified':True}
 def test_only_stable_subject_returned_not_email(self):
  result=self.verify(self.good());self.assertEqual(result,{'issuer':'google','subject':'synthetic-stable-sub'})
 def test_unverified_signature_or_expired_token_refused(self):
  with self.assertRaises(AuthError):self.verify(error=ValueError('untrusted upstream details'))
 def test_wrong_audience_issuer_nonce_authorized_party_refused(self):
  for field,value in [('aud','other.apps.googleusercontent.com'),('iss','attacker.invalid'),('nonce','b'*32),('azp','other.apps.googleusercontent.com'),('sub','')]:
   with self.subTest(field=field),self.assertRaises(AuthError):self.verify({**self.good(),field:value})
 def test_no_missing_nonce_or_subject(self):
  for field in ('nonce','sub'):
   claims=self.good();claims.pop(field)
   with self.assertRaises(AuthError):self.verify(claims)
 def test_invalid_configuration_does_not_attempt_google_call(self):
  for client,nonce in [('', 'a'*32),('x.apps.googleusercontent.com','short')]:
   with self.assertRaises(AuthError):verify_credential('synthetic-token-'*10,configured_client_id=client,expected_nonce=nonce)
 def test_verified_email_only_when_requested_and_verified(self):
  mod=types.ModuleType('google.oauth2');mod.id_token=types.SimpleNamespace(verify_oauth2_token=lambda *args:self.good())
  transport=types.ModuleType('google.auth.transport.requests');transport.Request=lambda:object()
  with patch.dict(sys.modules,{'google.oauth2':mod,'google.auth.transport.requests':transport}):
   result=verify_credential('synthetic-token-'*10,configured_client_id='synthetic.apps.googleusercontent.com',expected_nonce='a'*32,include_verified_email=True)
   self.assertEqual(result['verified_email'],'not-used@example.test')
   mod.id_token.verify_oauth2_token=lambda *args:{**self.good(),'email_verified':False}
   self.assertNotIn('verified_email',verify_credential('synthetic-token-'*10,configured_client_id='synthetic.apps.googleusercontent.com',expected_nonce='a'*32,include_verified_email=True))
