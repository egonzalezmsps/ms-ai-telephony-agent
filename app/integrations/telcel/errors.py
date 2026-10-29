"""
integrations/telcel/errors.py

Errores devueltos por las APIs intermedias Telcel.
"""

from typing import Any, Optional

INVALID_OTP_CODE = "BE_MP_BPS_0040"


class TelcelApiError(Exception):
    """HTTP no-2xx o detailResponse.code != "0"."""

    def __init__(self, http_status: int, raw_body: Any, message: str):
        super().__init__(message)
        self.http_status = http_status
        self.raw_body = raw_body

    @property
    def detail(self) -> dict:
        body = self.raw_body if isinstance(self.raw_body, dict) else {}
        return body.get("detailResponse") or {}

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
