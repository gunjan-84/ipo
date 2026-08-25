import base64
import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# Same layout as the previous Node implementation: iv(12) + tag(16) + ciphertext, base64-encoded.
# Kept byte-compatible so the existing encrypted accounts.json stays readable.
_KEY = hashlib.sha256(
    (os.environ.get("ACCOUNTS_ENC_KEY") or os.environ.get("SESSION_SECRET") or "ipo-dashboard-dev-secret").encode(
        "utf-8"
    )
).digest()


def encrypt(text: str) -> str:
    aesgcm = AESGCM(_KEY)
    iv = os.urandom(12)
    ct_and_tag = aesgcm.encrypt(iv, text.encode("utf-8"), None)
    ciphertext, tag = ct_and_tag[:-16], ct_and_tag[-16:]
    return base64.b64encode(iv + tag + ciphertext).decode("ascii")


def decrypt(payload: str) -> str:
    raw = base64.b64decode(payload)
    iv, tag, ciphertext = raw[:12], raw[12:28], raw[28:]
    aesgcm = AESGCM(_KEY)
    return aesgcm.decrypt(iv, ciphertext + tag, None).decode("utf-8")
