import base64
import hashlib
import hmac
import os
import secrets


PASSWORD_ITERATIONS = 100000


def get_password_hash(password: str) -> str:
    salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac(
        'sha256', password.encode(), salt, PASSWORD_ITERATIONS)
    return base64.b64encode(salt + key).decode()


def verify_password(password: str, password_hash: str) -> bool:
    data = base64.b64decode(password_hash.encode())
    salt, stored = data[:16], data[16:]
    key = hashlib.pbkdf2_hmac(
        'sha256', password.encode(), salt, PASSWORD_ITERATIONS)
    return hmac.compare_digest(key, stored)


def create_session_token() -> str:
    return secrets.token_urlsafe(32)
