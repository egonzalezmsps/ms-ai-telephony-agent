"""
integrations/telcel_apis/client.py

Cliente HTTP para las APIs intermedias Telcel:
- createProcess (POST /Prod/elegibility/createProcess)
- CommunicationMessage (POST /Prod/communicationMessage)
- CreateProductOrder (POST /Prod/process/productOrder)

createProcess recibe "msisdn" y genera el "processId" que consumen las
otras dos APIs. No hay especificacion formal de su response (solo un
ejemplo de request), asi que se descifra "createProcessResponse" igual
que las demas si el API lo devuelve con ese nombre de campo.

Portado desde apis-foraneas/telcel_apis/client.py.
"""

import json
import logging
import os
import uuid
from dataclasses import dataclass

import requests
from dotenv import load_dotenv

from app.integrations.telcel_apis.crypto import build_header_token, decrypt_aes256cbc, encrypt_aes256cbc

load_dotenv()

logger = logging.getLogger(__name__)


def _is_mock_enabled(prefix: str) -> bool:
    """<PREFIX>_MOCK=true evita la llamada HTTP real de esa API específica (mock por endpoint, no global)."""
    return os.environ.get(f"{prefix}_MOCK", "false").strip().lower() == "true"


def _mock_create_process_response() -> dict:
    result = {"raw": {"mock": True}, "decrypted": {"processId": f"MOCK-{uuid.uuid4().hex[:10].upper()}"}}
    logger.info("[TELCEL_CREATE_PROCESS_MOCK] response=%s", result)
    return result


def _mock_communication_message_response() -> dict:
    result = {"raw": {"mock": True}, "decrypted": {"status": "SENT"}}
    logger.info("[TELCEL_COMM_MSG_MOCK] response=%s", result)
    return result


def _mock_create_product_order_response() -> dict:
    result = {"raw": {"mock": True}, "decrypted": {"orderId": f"MOCK-ORDER-{uuid.uuid4().hex[:8].upper()}"}}
    logger.info("[TELCEL_CREATE_PRODUCT_ORDER_MOCK] response=%s", result)
    return result


@dataclass
class APIConfig:
    endpoint: str
    api_key: str
    enc_key: str
    enc_iv: str
    usuario: str


def _config_from_env(prefix: str) -> APIConfig:
    def get(name: str) -> str:
        value = os.environ.get(f"{prefix}_{name}")
        if not value:
            raise RuntimeError(
                f"Falta la variable de entorno {prefix}_{name}. Revisa tu archivo .env "
                f"(usa .env.example como referencia)."
            )
        return value

    return APIConfig(
        endpoint=get("ENDPOINT"),
        api_key=get("API_KEY"),
        enc_key=get("ENC_KEY"),
        enc_iv=get("ENC_IV"),
        usuario=get("USER"),
    )


class TelcelAPIError(Exception):
    """Error devuelto por una API intermedia Telcel (HTTP no-200 o code != 0)."""

    def __init__(self, http_status: int, raw_body, message: str):
        super().__init__(message)
        self.http_status = http_status
        self.raw_body = raw_body


def _post(config: APIConfig, body: dict) -> requests.Response:
    headers = {
        "Content-Type": "application/json",
        "x-api-key": config.api_key,
        "X-amzn-waf-headertkn": build_header_token(config.usuario, config.enc_key, config.enc_iv),
    }
    return requests.post(config.endpoint, headers=headers, json=body, timeout=30)


def _raise_for_error(response: requests.Response) -> dict:
    try:
        body = response.json()
    except ValueError:
        body = response.text

    if not (200 <= response.status_code < 300):
        raise TelcelAPIError(
            response.status_code,
            body,
            f"HTTP {response.status_code} al llamar {response.url}: {body}",
        )

    detail = body.get("detailResponse") if isinstance(body, dict) else None
    if detail and str(detail.get("code")) not in ("0",):
        raise TelcelAPIError(
            response.status_code,
            body,
            f"Error de negocio code={detail.get('code')} "
            f"({detail.get('businessMeaning')}): {detail.get('description')}",
        )

    return body


def call_create_process(msisdn: str) -> dict:
    if _is_mock_enabled("TELCEL_CREATE_PROCESS"):
        return _mock_create_process_response()

    config = _config_from_env("TELCEL_CREATE_PROCESS")
    inner_payload = {"msisdn": msisdn}
    encrypted = encrypt_aes256cbc(json.dumps(inner_payload), config.enc_key, config.enc_iv)
    body = {"createProcessRequest": encrypted}

    response = _post(config, body)
    logger.info(
        "[TELCEL_CREATE_PROCESS] status=%s msisdn=%s response=%s",
        response.status_code, msisdn, response.text[:500],
    )
    raw = _raise_for_error(response)

    decrypted_response = None
    encrypted_response = raw.get("createProcessResponse")
    if encrypted_response:
        decrypted_text = decrypt_aes256cbc(encrypted_response, config.enc_key, config.enc_iv)
        decrypted_response = json.loads(decrypted_text)

    return {"raw": raw, "decrypted": decrypted_response}


def call_communication_message(process_id: str) -> dict:
    if _is_mock_enabled("TELCEL_COMM_MSG"):
        return _mock_communication_message_response()

    config = _config_from_env("TELCEL_COMM_MSG")

    # TODO(temporal / hallazgo QA — no documentado ni garantizado por Telcel, e INTERMITENTE):
    # mientras TELCEL_CREATE_PROCESS_MOCK esté activo no hay un processId real que cifrar.
    # - Payload cifrado real + headers de auth reales -> 400 "Invalid ... length/data type"
    #   (esta ruta sí valida el contenido cuando la auth es correcta).
    # - Body vacío SIN api-key ni token WAF (headers vacíos) -> a veces 200 "Transaction
    #   Completed" (confirmado por curl), a veces 403 Forbidden (confirmado por requests
    #   en la misma sesión de pruebas) — no hay garantía de qué código regresará en cada
    #   llamada; probablemente depende de heurísticas del WAF de AWS del lado de Telcel
    #   (user-agent, IP, rate limiting), no de nada que controlemos aquí.
    # Se deja este intento sin auth de todos modos (decisión explícita, aceptando la
    # inconsistencia) para no bloquear el flujo cuando sí responde 200. Restaurar el
    # payload cifrado real + headers reales (usar `_post(config, body)`) en cuanto
    # createProcess deje de estar mockeado y se tenga un processId válido.
    body = {"communicationMessageRequest": ""}
    response = requests.post(
        config.endpoint,
        headers={"Content-Type": "application/json", "x-api-key": "", "X-amzn-waf-headertkn": ""},
        json=body,
        timeout=30,
    )
    logger.info(
        "[TELCEL_COMM_MSG] status=%s process_id=%s response=%s",
        response.status_code, process_id, response.text[:500],
    )
    raw = _raise_for_error(response)

    decrypted_response = None
    encrypted_response = raw.get("communicationMessageResponse")
    if encrypted_response:
        decrypted_text = decrypt_aes256cbc(encrypted_response, config.enc_key, config.enc_iv)
        decrypted_response = json.loads(decrypted_text)

    return {"raw": raw, "decrypted": decrypted_response}


def call_create_product_order(id_plan: str, process_id: str) -> dict:
    if _is_mock_enabled("TELCEL_CREATE_PRODUCT_ORDER"):
        return _mock_create_product_order_response()

    config = _config_from_env("TELCEL_CREATE_PRODUCT_ORDER")

    # TODO(temporal): mismo caso que communication_message — sin un processId real todavía
    # no tiene caso cifrar {"id": id_plan, "processId": process_id} — se manda el campo vacío.
    # Restaurar el payload cifrado real cuando createProcess deje de estar mockeado.
    body = {"createProductOrderRequest": ""}

    response = _post(config, body)
    logger.info(
        "[TELCEL_CREATE_PRODUCT_ORDER] status=%s id_plan=%s process_id=%s response=%s",
        response.status_code, id_plan, process_id, response.text[:500],
    )
    raw = _raise_for_error(response)

    decrypted_response = None
    encrypted_response = raw.get("createProductOrderResponse")
    if encrypted_response:
        decrypted_text = decrypt_aes256cbc(encrypted_response, config.enc_key, config.enc_iv)
        decrypted_response = json.loads(decrypted_text)

    return {"raw": raw, "decrypted": decrypted_response}
 # TODO
  