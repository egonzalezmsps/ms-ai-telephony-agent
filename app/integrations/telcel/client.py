"""
integrations/telcel/client.py

Operaciones de negocio sobre las APIs intermedias Telcel. Flujo de cambio de plan:

    process_id = create_process(phone, otp_required)   # siempre primero
    send_otp(process_id)                               # solo si otp_required
    create_product_order(product_id, process_id, otp)  # activa el plan (valida el OTP si se envió)

Payloads (cifrados por transport.send):
- createProcess:        {"msisdn": "<10 dígitos>", "otpAuth": <bool>}
- communicationMessage: {"content": true, "messageType": "SEND_OTP", "processId": "..."}
- createProductOrder:   {"id": "<id Telcel según modalidad>", "processId": "...", "otpAuth": "<6 dígitos> | NA"}
"""

from typing import Optional

from app.integrations.telcel.config import COMMUNICATION_MESSAGE, CREATE_PROCESS, CREATE_PRODUCT_ORDER
from app.integrations.telcel.errors import TelcelApiError
from app.integrations.telcel.otp import OTP_LENGTH, is_valid_otp_code
from app.integrations.telcel.phone import to_msisdn
from app.integrations.telcel.transport import TelcelResponse, send

_MESSAGE_TYPE_SEND_OTP = "SEND_OTP"
_NO_OTP = "NA"  # valor de otpAuth en createProductOrder cuando no se pidió OTP


def create_process(phone_number: str, otp_required: bool) -> str:
    """Abre el proceso de cambio de plan para la línea y regresa el processId.

    otp_required=True cuando el precio del plan nuevo es distinto a la renta actual.
    """
    response = send(CREATE_PROCESS, {"msisdn": to_msisdn(phone_number), "otpAuth": otp_required})
    process_id = (response.data or {}).get("processId")
    if not process_id:
        raise TelcelApiError(200, response.raw, "createProcess no regresó processId")
    return process_id


def send_otp(process_id: str) -> TelcelResponse:
    """Pide a Telcel que envíe al cliente el SMS con el código OTP."""
    return send(
        COMMUNICATION_MESSAGE,
        {"content": True, "messageType": _MESSAGE_TYPE_SEND_OTP, "processId": process_id},
    )


def create_product_order(product_id: str, process_id: str, otp_code: Optional[str] = None) -> TelcelResponse:
    """Activa el plan nuevo.

    otp_code: código de 6 dígitos que el cliente recibió por SMS (normalizar con to_otp_code);
              None cuando no se pidió OTP (se manda "NA").
    Si el código es incorrecto, Telcel responde error (TelcelApiError.is_invalid_otp).
    """
    if otp_code is not None and not is_valid_otp_code(otp_code):
        raise ValueError(f"otp_code debe ser de {OTP_LENGTH} dígitos, se recibió {otp_code!r}")
    return send(
        CREATE_PRODUCT_ORDER,
        {"id": product_id, "processId": process_id, "otpAuth": otp_code or _NO_OTP},
    )
