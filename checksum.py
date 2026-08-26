import json
import hashlib
import base64
from Crypto.Cipher import AES

def generate_groww_checksum(url_path, payload_dict, req_id, salt, secret_k="adepto007$22"):
    """
    100% Native Python reverse-engineered Groww API Checksum Generator.
    Uses AES-CBC with NoPadding on a precisely formatted 80-byte plaintext block.
    """
    # 1. Generate the inner payload hash
    if payload_dict is None:
        payload_str = "undefined"
    else:
        payload_str = json.dumps(payload_dict, separators=(',', ':'))
        
    s = url_path + payload_str
    l_hash = hashlib.sha256(s.encode('utf-8')).hexdigest()
    
    # 2. Extract first 13 characters of the Request ID hash
    r_hash = hashlib.sha256(req_id.encode('utf-8')).hexdigest()
    r_padded = r_hash[:13].ljust(13, '0')
    
    # 3. Form the exact 80-byte plaintext (13 + 3 + 64)
    payload_to_encrypt = f"{r_padded}###{l_hash}"
    
    # 4. Generate the AES Key by interleaving the padded secret key and salt
    k_padded = secret_k.ljust(16, '0')[:16]
    c_padded = salt.ljust(16, '0')[:16]
    
    interleaved = ""
    for i in range(16):
        interleaved += k_padded[i] + c_padded[i]
        
    aes_key_hex = hashlib.sha256(interleaved.encode('latin1')).hexdigest()
    aes_key_bytes = aes_key_hex[:16].encode('latin1')
    
    # 5. Encrypt with NoPadding (80-byte plaintext exactly fits 5 AES blocks)
    cipher = AES.new(aes_key_bytes, AES.MODE_CBC, iv=aes_key_bytes)
    encrypted_bytes = cipher.encrypt(payload_to_encrypt.encode('utf-8'))
    encrypted_b64 = base64.b64encode(encrypted_bytes).decode('utf-8')
    
    # 6. Prepend the salt and base64 encode the final checksum
    final_string = f"{salt}###{encrypted_b64}"
    checksum = base64.b64encode(final_string.encode('utf-8')).decode('utf-8')
    
    return checksum
