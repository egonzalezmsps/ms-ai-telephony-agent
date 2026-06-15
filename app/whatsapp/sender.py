"""
whatsapp/sender.py — Envío de mensajes via Meta Cloud API.
"""
import os
import logging
import requests

logger = logging.getLogger(__name__)


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
        "to": to,
        "type": "text",
        "text": {"body": message},
    }
    resp = requests.post(_build_url(), json=payload, headers=_build_headers(), timeout=10)
    resp.raise_for_status()
    return resp.json()


def send_whatsapp_template(
    to: str,
    template_name: str,
    params: list,
    language_code: str = "es_MX",
) -> dict:
    """
    Sends a WhatsApp Business template message.

    params: list of values mapping to {{1}}, {{2}}, ... in the template body.
    Static header, footer, and quick-reply buttons need no parameters.
    """
    body_parameters = [{"type": "text", "text": str(p)} for p in params]

    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language_code},
            "components": [
                {
                    "type": "body",
                    "parameters": body_parameters,
                }
            ],
        },
    }

    resp = requests.post(_build_url(), json=payload, headers=_build_headers(), timeout=10)
    if not resp.ok:
        logger.error(f"WhatsApp template error {resp.status_code}: {resp.text}")
    resp.raise_for_status()
    return resp.json()
