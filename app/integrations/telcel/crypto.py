"""
integrations/telcel/crypto.py

Cifrado AES-256-CBC para las APIs intermedias Telcel.

Implementación confirmada contra el anexo de cifrado de Telcel
(AES/CBC/PKCS5Padding, llave e IV como bytes UTF-8 literales, salida en hex)
y validada end-to-end contra QA real.
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


def encrypt(plaintext: str, key: str, iv: str) -> str:
    """Cifra texto plano y regresa el ciphertext en hex mayúsculas."""
    key_bytes, iv_bytes = _key_iv_bytes(key, iv)
    cipher = AES.new(key_bytes, AES.MODE_CBC, iv_bytes)
    ciphertext = cipher.encrypt(pad(plaintext.encode("utf-8"), AES.block_size))
    return ciphertext.hex().upper()


def decrypt(hex_ciphertext: str, key: str, iv: str) -> str:
    """Descifra un ciphertext en hex y regresa el texto plano."""
    key_bytes, iv_bytes = _key_iv_bytes(key, iv)
    cipher = AES.new(key_bytes, AES.MODE_CBC, iv_bytes)
    padded = cipher.decrypt(bytes.fromhex(hex_ciphertext))
    return unpad(padded, AES.block_size).decode("utf-8")


def build_waf_token(user: str, key: str, iv: str) -> str:
    """Token del header X-amzn-waf-headertkn: "<user>@<yyyyMMddHHmmss UTC>" cifrado."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return encrypt(f"{user}@{timestamp}", key, iv)
