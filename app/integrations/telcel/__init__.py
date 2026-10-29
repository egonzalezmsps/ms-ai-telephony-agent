"""
integrations/telcel — cliente de las APIs intermedias Telcel.

    from app.integrations.telcel import create_process, send_otp, create_product_order, to_otp_code, TelcelApiError

Módulos:
- client.py     operaciones de negocio (lo que se usa desde fuera)
- transport.py  cifrar → POST → validar → descifrar (común a todas las APIs)
- config.py     definición de cada API y variables de entorno
- crypto.py     AES-256-CBC y token WAF
- errors.py     TelcelApiError (+ is_invalid_otp)
- phone.py      normalización de MSISDN
- otp.py        validación del código OTP (6 dígitos)
- mocks.py      respuestas simuladas para <PREFIX>_MOCK=true
- debug_log.py  TEMPORAL: logs/telcel_debug.log con payloads en claro y cifrados
"""

from app.integrations.telcel.client import create_process, create_product_order, send_otp
from app.integrations.telcel.errors import TelcelApiError
from app.integrations.telcel.otp import OTP_LENGTH, to_otp_code
from app.integrations.telcel.transport import TelcelResponse

__all__ = [
    "create_process", "send_otp", "create_product_order",
    "to_otp_code", "OTP_LENGTH", "TelcelApiError", "TelcelResponse",
]
