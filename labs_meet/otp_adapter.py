"""Disabled-by-default unofficial OTP adapter for an approved OWNER test only.

No public-recipient resolution is guessed. No session or recipient may come from
an HTTP request. An operator must bind the approved number to a LIVE-VERIFIED chat
ID, dedicated/approved session and scoped credential before the gate is enabled.
Unofficial transport may be restricted/banned and is not a reliable public auth SLA.
"""
import re
from urllib.parse import quote
from .adapters import endpoint, request


class OwnerOtpSender:
    def __init__(self, *, base, key, session, owner_phone, verified_chat_id, enabled=False, digits=6):
        if digits not in (4,6):raise ValueError('Unexpected code length')
        self.digits=digits
        self.base = endpoint(base)
        if not all(isinstance(v, str) and v for v in (key, session, owner_phone, verified_chat_id)):
            raise ValueError('Approved session, credential and verified owner destination required')
        if not re.fullmatch(r'\+[1-9][0-9]{7,14}', owner_phone):
            raise ValueError('Valid owner number required')
        self.key, self.session = key, session
        self.owner_phone, self.chat_id, self.enabled = owner_phone, verified_chat_id, enabled

    def __call__(self, phone, code, ttl):
        if self.enabled is not True:
            raise ValueError('OTP sends disabled until sender and message scope are approved')
        if phone != self.owner_phone:
            raise ValueError('Only the approved owner test number is allowed')
        if not isinstance(code, str) or not re.fullmatch(r'[0-9]{%d}' % self.digits, code) or ttl != 180:
            raise ValueError('Unexpected OTP policy')
        text = code + ' is your Lathar Labs sign-in code. Expires in 3 minutes. Do not share it. If you did not request it, ignore this message.'
        # One attempt only. SENT means engine acceptance, never delivery/read.
        result = request(self.base, '/api/sessions/' + quote(self.session, safe='') + '/messages/send-text',
                         self.key, 'POST', {'chatId': self.chat_id, 'text': text})
        if not isinstance(result, dict) or not isinstance(result.get('messageId'), str) or not result['messageId'].strip():
            raise RuntimeError('OTP provider outcome unknown; no automatic retry')
        return True
