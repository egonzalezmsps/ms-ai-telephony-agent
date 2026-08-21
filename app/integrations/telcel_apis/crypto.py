"""
integrations/telcel_apis/crypto.py

Cifrado AES-256-CBC para las APIs intermedias Telcel.

Implementacion confirmada contra el anexo de cifrado de Telcel
(AES/CBC/PKCS5Padding, llave e IV como bytes UTF-8 literales, salida en hex)
y validada end-to-end contra QA real para comm-msg y create-product-order
(header token valido, code "0" - Successful Execution, payload de respuesta
descifrado correctamente). Portado desde apis-foraneas/telcel_apis/crypto.py.
"""

from datetime import datetime, timezone

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad


def _key_iv_bytes(key: str, iv: str) -> tuple[bytes, bytes]:
    key_bytes = key.encode("utf-8")
    iv_bytes = iv.encode("utf-8")
    if len(key_bytes) != 32:
        raise ValueError(f"La llave debe representar 32 bytes UTF-8 para AES-256, tiene {len(key_bytes)}")
    if len(iv_bytes) != 16:
        raise ValueError(f"El IV debe representar 16 bytes UTF-8, tiene {len(iv_bytes)}")
    return key_bytes, iv_bytes


def encrypt_aes256cbc(plaintext: str, key: str, iv: str) -> str:
    key_bytes, iv_bytes = _key_iv_bytes(key, iv)
    cipher = AES.new(key_bytes, AES.MODE_CBC, iv_bytes)
    padded = pad(plaintext.encode("utf-8"), AES.block_size)
    ciphertext = cipher.encrypt(padded)
    return ciphertext.hex().upper()


def decrypt_aes256cbc(hex_ciphertext: str, key: str, iv: str) -> str:
    key_bytes, iv_bytes = _key_iv_bytes(key, iv)
    cipher = AES.new(key_bytes, AES.MODE_CBC, iv_bytes)
    ciphertext = bytes.fromhex(hex_ciphertext)
    padded = cipher.decrypt(ciphertext)
    return unpad(padded, AES.block_size).decode("utf-8")


def build_header_token(usuario: str, key: str, iv: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return encrypt_aes256cbc(f"{usuario}@{timestamp}", key, iv)
