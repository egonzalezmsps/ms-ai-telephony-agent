"""
integrations/telcel/otp.py

Normalización del código OTP al formato que pide createProductOrder: exactamente 6 dígitos.
"""

import re
from typing import Optional

OTP_LENGTH = 6

_OTP_PATTERN = re.compile(rf"\d{{{OTP_LENGTH}}}")
_SEPARATORS = re.compile(r"[\s\-.]")


def to_otp_code(text: str) -> Optional[str]:
    """Regresa el código de 6 dígitos o None si el texto no es un código válido.

    Se toleran separadores que el cliente suele escribir ("002 856", "002-856");
    se conserva como string para no perder ceros a la izquierda.
    """
    candidate = _SEPARATORS.sub("", text or "")
    return candidate if _OTP_PATTERN.fullmatch(candidate) else None


def is_valid_otp_code(code: str) -> bool:
    return bool(_OTP_PATTERN.fullmatch(code or ""))
