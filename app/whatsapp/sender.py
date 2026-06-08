"""
whatsapp/sender.py — Envío de mensajes via Meta Cloud API.
"""
import os
import logging
import requests

logger = logging.getLogger(__name__)


def send_whatsapp_message(to: str, message: str) -> dict:
    access_token = os.environ["WHATSAPP_ACCESS_TOKEN"]
    phone_number_id = os.environ["WHATSAPP_PHONE_NUMBER_ID"]
    api_version = os.environ.get("WHATSAPP_API_VERSION", "v22.0")

    url = f"https://graph.facebook.com/{api_version}/{phone_number_id}/messages"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": message},
    }

    resp = requests.post(url, json=payload, headers=headers, timeout=10)
    resp.raise_for_status()
    return resp.json()
