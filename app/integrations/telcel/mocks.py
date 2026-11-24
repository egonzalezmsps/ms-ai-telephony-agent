"""
integrations/telcel/mocks.py

Respuestas simuladas (ya descifradas) para cuando <PREFIX>_MOCK=true.
"""

import uuid

from app.integrations.telcel.config import (
    COMMUNICATION_MESSAGE,
    CREATE_PROCESS,
    CREATE_PRODUCT_ORDER,
    MOCK_OTP_CODE,
    TelcelApi,
)
from app.integrations.telcel.errors import INVALID_OTP_CODE, TelcelApiError

_NO_OTP = "NA"


def _invalid_otp_error() -> TelcelApiError:
    """Misma forma que el error real de Telcel (errorList en el payload descifrado)."""
    body = {
        "errorList": [{
            "code": INVALID_OTP_CODE,
            "severityLevel": 1,
            "description": "Business Error",
            "actor": "System",
            "businessMeaning": "OTP INVALID ",
        }]
    }
    return TelcelApiError(200, body, f"Error de negocio code={INVALID_OTP_CODE} (OTP invalido) [mock]")


def mock_response(api: TelcelApi, payload: dict) -> dict:
    """Respuesta simulada. Para createProductOrder valida el OTP contra TELCEL_MOCK_OTP_CODE."""
    if api == CREATE_PROCESS:
        # Misma forma que la respuesta real de Telcel (processId en process.id)
        return {
            "subscription": {"msisdn": "0000000000", "subscriberName": "MOCK"},
            "process": {"id": f"MOCK-{uuid.uuid4().hex[:10].upper()}"},
        }
    if api == COMMUNICATION_MESSAGE:
        return {"status": "SENT"}
    if api == CREATE_PRODUCT_ORDER:
        otp = str(payload.get("otpAuth", _NO_OTP))
        if otp != _NO_OTP and otp != MOCK_OTP_CODE:
            raise _invalid_otp_error()
        return {"orderId": f"MOCK-ORDER-{uuid.uuid4().hex[:8].upper()}"}
    raise ValueError(f"Sin mock definido para {api.name}")
