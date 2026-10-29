"""
integrations/telcel/transport.py

Llamada genérica a una API intermedia Telcel:
payload → cifrar → POST con headers de auth → validar errores → descifrar respuesta.

Todas las APIs Telcel comparten este mismo contrato, así que una API nueva solo
necesita su `TelcelApi` en config.py y una función en client.py que llame `send()`.
"""

import json
import logging
from dataclasses import dataclass
from typing import Any, Optional

import requests

from app.integrations.telcel import crypto
from app.integrations.telcel.config import TelcelApi, TelcelApiConfig, is_mock_enabled, load_config
from app.integrations.telcel.debug_log import log_exchange
from app.integrations.telcel.errors import TelcelApiError
from app.integrations.telcel.mocks import mock_response

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 30


@dataclass
class TelcelResponse:
    raw: Any             # body tal como lo regresó la API (o {"mock": True})
    data: Optional[dict]  # payload de la respuesta ya descifrado (None si no vino)


def _build_headers(config: TelcelApiConfig) -> dict:
    return {
        "Content-Type": "application/json",
        "x-api-key": config.api_key,
        "X-amzn-waf-headertkn": crypto.build_waf_token(config.user, config.enc_key, config.enc_iv),
    }


def _parse_body(response: requests.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return response.text


def _raise_for_error(response: requests.Response, body: Any) -> None:
    if not (200 <= response.status_code < 300):
        raise TelcelApiError(
            response.status_code, body, f"HTTP {response.status_code} al llamar {response.url}: {body}",
        )

    detail = body.get("detailResponse") if isinstance(body, dict) else None
    if detail and str(detail.get("code")) != "0":
        raise TelcelApiError(
            response.status_code,
            body,
            f"Error de negocio code={detail.get('code')} "
            f"({detail.get('businessMeaning')}): {detail.get('description')}",
        )


def _decrypt_payload(api: TelcelApi, config: TelcelApiConfig, body: Any) -> Optional[dict]:
    encrypted = body.get(api.response_field) if isinstance(body, dict) else None
    if not encrypted:
        return None
    return json.loads(crypto.decrypt(encrypted, config.enc_key, config.enc_iv))


def send(api: TelcelApi, payload: dict) -> TelcelResponse:
    """Envía `payload` cifrado a `api` y regresa la respuesta descifrada. Lanza TelcelApiError."""
    if is_mock_enabled(api):
        data = mock_response(api)
        logger.info("[TELCEL_%s_MOCK] request=%s response=%s", api.name, payload, data)
        log_exchange(api.name, "(mock)", payload, None, None, None, data, mock=True)
        return TelcelResponse(raw={"mock": True}, data=data)

    config = load_config(api)
    encrypted = crypto.encrypt(json.dumps(payload), config.enc_key, config.enc_iv)
    request_body = {api.request_field: encrypted}

    response = requests.post(
        config.endpoint, headers=_build_headers(config), json=request_body, timeout=_TIMEOUT_SECONDS,
    )
    body = _parse_body(response)

    data = None
    try:
        _raise_for_error(response, body)
        data = _decrypt_payload(api, config, body)
    finally:
        logger.info(
            "[TELCEL_%s] status=%s request=%s response=%s decrypted=%s",
            api.name, response.status_code, payload, str(body)[:500], data,
        )
        log_exchange(api.name, config.endpoint, payload, request_body, response.status_code, body, data)

    return TelcelResponse(raw=body, data=data)
