"""Fail-closed Google identity verification boundary; no OAuth/client setup.

Requires the official google-auth package at runtime, provisioned separately.
Not imported by the HTTP server until approved production auth is integrated.
Never trust a browser-decoded JWT, email-to-phone guess or user-supplied audience.
"""
import hmac
import re
from .auth_core import AuthError


def verify_credential(credential, *, configured_client_id, expected_nonce, include_verified_email=False):
    if not isinstance(credential, str) or not 100 <= len(credential) <= 12000:
        raise AuthError('Google sign-in did not validate')
    if not isinstance(configured_client_id, str) or not configured_client_id.endswith('.apps.googleusercontent.com'):
        raise AuthError('Provision the intended Google web client before enabling sign-in')
    if not isinstance(expected_nonce, str) or len(expected_nonce) < 32:
        raise AuthError('Start a fresh browser login session')
    try:
        from google.oauth2 import id_token
        from google.auth.transport.requests import Request
    except ImportError:
        raise AuthError('Google verifier is not installed; sign-in remains disabled') from None
    try:
        # Official library checks signature, audience, issuer and token lifetime.
        claims = id_token.verify_oauth2_token(credential, Request(), configured_client_id)
        if not isinstance(claims, dict):
            raise ValueError()
        if claims.get('aud') != configured_client_id or claims.get('iss') not in ('accounts.google.com', 'https://accounts.google.com'):
            raise ValueError()
        if claims.get('azp', configured_client_id) != configured_client_id:
            raise ValueError()
        nonce = claims.get('nonce')
        if not isinstance(nonce, str) or not hmac.compare_digest(nonce, expected_nonce):
            raise ValueError()
        subject = claims.get('sub')
        if not isinstance(subject, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,255}', subject):
            raise ValueError()
        # No email-based account lookup or automatic phone-account linking.
        # The caller must bind this stable subject to a server-side account,
        # consume the browser nonce ONCE, and issue its own secure session.
        result = {'issuer': 'google', 'subject': subject}
        # Optional onboarding contact only. Never use email to merge identities.
        email=claims.get('email')
        if include_verified_email and claims.get('email_verified') is True and isinstance(email,str) and re.fullmatch(r'[^\s@<>;,\r\n]+@[^\s@<>;,\r\n]+\.[^\s@<>;,\r\n]+',email):
            result['verified_email']=email
        return result
    except Exception:
        raise AuthError('Google sign-in did not validate') from None
