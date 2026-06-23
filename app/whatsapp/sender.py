"""
whatsapp/sender.py — Envío de mensajes via Meta Cloud API.
"""
import os
import logging
import requests

logger = logging.getLogger(__name__)

_COUNTRY_CODE = os.environ.get("WHATSAPP_COUNTRY_CODE", "52")


def _normalize_phone(number: str) -> str:
    """Agrega código de país si el número no lo tiene."""
    n = number.strip().lstrip("+")
    if not n.startswith(_COUNTRY_CODE):
        n = _COUNTRY_CODE + n
    return n


def _build_url() -> str:
    api_version = os.environ.get("WHATSAPP_API_VERSION", "v22.0")
    phone_number_id = os.environ["WHATSAPP_PHONE_NUMBER_ID"]
    return f"https://graph.facebook.com/{api_version}/{phone_number_id}/messages"


def _build_headers() -> dict:
    return {
        "Authorization": f"Bearer {os.environ['WHATSAPP_ACCESS_TOKEN']}",
        "Content-Type": "application/json",
    }


def send_whatsapp_message(to: str, message: str) -> dict:
    payload = {
        "messaging_product": "whatsapp",
        "to": _normalize_phone(to),
        "type": "text",
        "text": {"body": message},
    }
    resp = requests.post(_build_url(), json=payload, headers=_build_headers(), timeout=10)
    resp.raise_for_status()
    return resp.json()


_TEMPLATE_LANGUAGE = os.environ.get("TEMPLATE_LANGUAGE", "es_MX")

def send_whatsapp_template(
    to: str,
    template_name: str,
    params: list,
    language_code: str = _TEMPLATE_LANGUAGE,
) -> dict:
    """
    Sends a WhatsApp Business template message.

    params: list of values mapping to {{1}}, {{2}}, ... in the template body.
    """
    body_parameters = [{"type": "text", "text": str(p)} for p in params]

    components = [
        {"type": "header", "parameters": []},
        {"type": "body", "parameters": body_parameters},
    ]

    payload = {
        "messaging_product": "whatsapp",
        "to": _normalize_phone(to),
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language_code},
            "components": components,
        },
    }

    resp = requests.post(_build_url(), json=payload, headers=_build_headers(), timeout=10)
    if not resp.ok:
        logger.error(f"WhatsApp template error {resp.status_code}: {resp.text}")
        raise requests.HTTPError(f"{resp.status_code} — {resp.text}", response=resp)
    return resp.json()
