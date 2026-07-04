from cryptography.fernet import Fernet
from app.config import settings
import base64


def get_fernet():
    key = settings.ENCRYPTION_KEY
    # Ensure key is 32 bytes, then base64 encode for Fernet
    key_bytes = key.encode()[:32].ljust(32, b'0')
    fernet_key = base64.urlsafe_b64encode(key_bytes)
    return Fernet(fernet_key)


def encrypt(value: str) -> str:
    f = get_fernet()
    return f.encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    f = get_fernet()
    return f.decrypt(value.encode()).decode()
