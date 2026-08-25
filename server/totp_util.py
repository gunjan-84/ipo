import pyotp


def generate_totp(secret: str) -> str:
    # Standard RFC 6238 TOTP — SHA-1, 30s step, 6 digits — same algorithm Kite's web app uses.
    return pyotp.TOTP(secret).now()
