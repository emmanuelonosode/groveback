"""
Symmetric encryption helpers for sensitive PII fields (SSN, etc.).
Uses Fernet (AES-128-CBC + HMAC-SHA256) with a key derived from Django's SECRET_KEY.
No extra configuration needed — the key rotates only if SECRET_KEY changes.
"""
import base64
import hashlib

from django.conf import settings


def _fernet():
    from cryptography.fernet import Fernet
    # SHA-256 of SECRET_KEY → 32 bytes → base64url → valid Fernet key
    raw = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(raw))


def encrypt_value(plaintext: str) -> str:
    """Encrypt a plaintext string. Returns a base64 token string."""
    if not plaintext:
        return ""
    cleaned = plaintext.strip()
    return _fernet().encrypt(cleaned.encode()).decode()


def decrypt_value(token: str) -> str:
    """Decrypt a Fernet token. Returns the original plaintext string."""
    if not token:
        return ""
    return _fernet().decrypt(token.encode()).decode()


def encrypt_ssn(ssn: str) -> str:
    """Encrypt a full SSN. Strips dashes/spaces before encrypting."""
    cleaned = ssn.replace("-", "").replace(" ", "").strip()
    return encrypt_value(cleaned)


def decrypt_ssn(token: str) -> str:
    """Decrypt an SSN token. Returns formatted XXX-XX-XXXX if 9 digits."""
    raw = decrypt_value(token)
    if len(raw) == 9 and raw.isdigit():
        return f"{raw[:3]}-{raw[3:5]}-{raw[5:]}"
    return raw
