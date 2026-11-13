"""No network calls. Transport cannot accept arbitrary browser recipients."""
import unittest
from unittest.mock import patch
from labs_meet.otp_adapter import OwnerOtpSender

class OtpAdapter(unittest.TestCase):
 def sender(self,**kw):return OwnerOtpSender(base='http://127.0.0.1:12345',key='synthetic-only',session='dedicated-test',owner_phone='+15555550199',verified_chat_id='synthetic-verified-lid',**kw)
 def test_disabled_without_effect_grant(self):
  with patch('labs_meet.otp_adapter.request') as req:
   with self.assertRaises(ValueError):self.sender()('+15555550199','123456',180)
   req.assert_not_called()
 def test_only_bound_owner_destination(self):
  with patch('labs_meet.otp_adapter.request') as req:
   with self.assertRaises(ValueError):self.sender(enabled=True)('+15555550198','123456',180)
   req.assert_not_called()
 def test_no_guessed_number_chat_id(self):
  with patch('labs_meet.otp_adapter.request',return_value={'messageId':'synthetic-result'}) as req:
   self.assertTrue(self.sender(enabled=True)('+15555550199','123456',180))
   self.assertEqual(req.call_args.args[4]['chatId'],'synthetic-verified-lid');self.assertIn('3 minutes',req.call_args.args[4]['text'])
 def test_unknown_does_not_retry(self):
  with patch('labs_meet.otp_adapter.request',side_effect=TimeoutError()) as req:
   with self.assertRaises(TimeoutError):self.sender(enabled=True)('+15555550199','123456',180)
   self.assertEqual(req.call_count,1)
 def test_empty_provider_id_is_unknown(self):
  with patch('labs_meet.otp_adapter.request',return_value={'messageId':''}):
   with self.assertRaises(RuntimeError):self.sender(enabled=True)('+15555550199','123456',180)
 def test_code_and_ttl_policy(self):
  for code,ttl in [('1234',180),('123456',600),('nondigit',180)]:
   with patch('labs_meet.otp_adapter.request') as req:
    with self.assertRaises(ValueError):self.sender(enabled=True)('+15555550199',code,ttl)
    req.assert_not_called()
