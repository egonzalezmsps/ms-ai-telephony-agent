"""
integrations/telcel/errors.py

Errores devueltos por las APIs intermedias Telcel.
"""

from typing import Any, Optional

INVALID_OTP_CODE = "BE_MP_BPS_0040"


class TelcelApiError(Exception):
    """HTTP no-2xx, detailResponse.code != "0" o errorList no vacío en el payload descifrado."""

    def __init__(self, http_status: int, raw_body: Any, message: str):
        super().__init__(message)
        self.http_status = http_status
        self.raw_body = raw_body

    @property
    def detail(self) -> dict:
        """Error de negocio: detailResponse del body crudo, o el primer elemento de
        errorList del payload descifrado (Telcel responde HTTP 200 con el error ahí)."""
        body = self.raw_body if isinstance(self.raw_body, dict) else {}
        if body.get("detailResponse"):
            return body["detailResponse"]
        error_list = body.get("errorList")
        if isinstance(error_list, list) and error_list and isinstance(error_list[0], dict):
            return error_list[0]
        return {}

    @property
    def business_code(self) -> Optional[str]:
        code = self.detail.get("code")
        return str(code) if code is not None else None

    @property
    def is_invalid_otp(self) -> bool:
        """True si Telcel rechazó el código OTP que ingresó el cliente."""
        if self.business_code == INVALID_OTP_CODE:
            return True
        meaning = f"{self.detail.get('businessMeaning', '')} {self.detail.get('description', '')}".upper()
        return "OTP" in meaning
