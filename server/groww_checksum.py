import base64
import hashlib
import json

from Crypto.Cipher import AES

_SECRET_K = "adepto007$22"


def generate_checksum(url_path: str, payload_dict, req_id: str, salt: str) -> str:
    """Reverse-engineered Groww web-app request checksum: AES-CBC (no padding) over an
    80-byte block built from the request-id hash and a hash of the URL+payload.

    payload_dict is None for GET/unauthenticated-body calls (hashed as the literal string
    "undefined", matching Groww's JS `JSON.stringify(undefined)`); it's "" specifically for
    PUT calls with a truly empty body like cancel, where Groww hashes the empty string
    instead — passing None there produces "undefined" and gets rejected with a 500.
    """
    if payload_dict is None:
        payload_str = "undefined"
    elif payload_dict == "":
        payload_str = ""
    else:
        payload_str = json.dumps(payload_dict, separators=(",", ":"))

    l_hash = hashlib.sha256((url_path + payload_str).encode("utf-8")).hexdigest()

    r_hash = hashlib.sha256(req_id.encode("utf-8")).hexdigest()
    r_padded = r_hash[:13].ljust(13, "0")

    payload_to_encrypt = f"{r_padded}###{l_hash}"

    k_padded = _SECRET_K.ljust(16, "0")[:16]
    c_padded = salt.ljust(16, "0")[:16]
    interleaved = "".join(k_padded[i] + c_padded[i] for i in range(16))

    aes_key_hex = hashlib.sha256(interleaved.encode("latin1")).hexdigest()
    aes_key_bytes = aes_key_hex[:16].encode("latin1")

    cipher = AES.new(aes_key_bytes, AES.MODE_CBC, iv=aes_key_bytes)
    encrypted_bytes = cipher.encrypt(payload_to_encrypt.encode("utf-8"))
    encrypted_b64 = base64.b64encode(encrypted_bytes).decode("utf-8")

    final_string = f"{salt}###{encrypted_b64}"
    return base64.b64encode(final_string.encode("utf-8")).decode("utf-8")
