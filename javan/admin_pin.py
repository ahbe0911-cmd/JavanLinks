"""Local manager PIN, independent of the HTML and exported accounting data."""
import hashlib
import hmac
import json
import secrets
from .storage import atomic_write


class PinStore:
    def __init__(self, folder):
        self.path = folder / 'manager-pin.json'

    def exists(self):
        return self.path.exists()

    @staticmethod
    def valid(pin):
        return isinstance(pin, str) and pin.isascii() and pin.isdigit() and 6 <= len(pin) <= 12

    @staticmethod
    def digest(pin, salt):
        return hashlib.scrypt(pin.encode('ascii'), salt=salt, n=16384, r=8, p=1, dklen=32)

    def configure(self, pin):
        if self.exists() or not self.valid(pin):
            raise ValueError('رمز مدیر قبلاً تعریف شده یا نامعتبر است.')
        salt = secrets.token_bytes(16)
        payload = {'salt': salt.hex(), 'digest': self.digest(pin, salt).hex()}
        atomic_write(self.path, json.dumps(payload).encode('ascii'))

    def verify(self, pin):
        if not self.valid(pin):
            return False
        try:
            record = json.loads(self.path.read_text(encoding='ascii'))
            salt, expected = bytes.fromhex(record['salt']), bytes.fromhex(record['digest'])
            if len(salt) != 16 or len(expected) != 32:
                return False
            return hmac.compare_digest(self.digest(pin, salt), expected)
        except (OSError, ValueError, KeyError, TypeError):
            return False
