"""
routes/webhook.py

Webhook de WhatsApp (Meta Cloud API): verificación (GET) y recepción de
mensajes (POST), procesados en segundo plano.
"""

import hmac
import hashlib
import json
import logging
import os
import threading
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from app.agent.reni_agent import run_turn
from app.state.session import SessionState
from app.state.persistence import load_session, save_session
from app.state.serializer import session_to_dict, dict_to_session
from app.prompts.campaign_template import build_campaign_message, build_template_params
from app.whatsapp.sender import send_whatsapp_message, send_whatsapp_interactive_buttons
from app.whatsapp.command_handler import handle_command
from app.state.campaign_traceability import _maybe_update_campana_cliente, _maybe_persist_plan_change
from app.routes.deps import require_api_key

logger = logging.getLogger(__name__)

router = APIRouter()


class ProvisioningStatusRequest(BaseModel):
    processId: str
    msisdn: str = Field(pattern=r"^\d{10}$")
    statusProvisioning: str

# IDs de mensajes ya procesados — evita duplicados por reintentos de Meta
_processed_msg_ids: set = set()
_processed_lock = threading.Lock()

# Un lock por número de teléfono — evita turnos simultáneos del mismo cliente
_phone_locks: dict = {}
_phone_locks_mutex = threading.Lock()


def _get_phone_lock(phone_number: str) -> threading.Lock:
    with _phone_locks_mutex:
        if phone_number not in _phone_locks:
            _phone_locks[phone_number] = threading.Lock()
        return _phone_locks[phone_number]


@router.get("/webhook")
def verify_webhook(
    hub_mode: str = Query(default=None, alias="hub.mode"),
    hub_verify_token: str = Query(default=None, alias="hub.verify_token"),
    hub_challenge: str = Query(default=None, alias="hub.challenge"),
):
    """Verificación del webhook por Meta."""
    verify_token = os.getenv("VERIFY_TOKEN", "")
    if hub_mode == "subscribe" and hub_verify_token == verify_token:
        return PlainTextResponse(hub_challenge)
    raise HTTPException(status_code=403, detail="Verification failed")


def _process_whatsapp_message(phone_number: str, message_text: str, sender_name: str):
    """Procesa el mensaje en segundo plano para no bloquear el webhook."""
    lock = _get_phone_lock(phone_number)
    if not lock.acquire(blocking=False):
        logger.warning(f"WA SKIP | {phone_number} — turno en proceso, mensaje descartado")
        return
    try:
        first_name = sender_name.split()[0] if sender_name else "Cliente"

        # Detectar comandos antes del flujo normal
        if message_text.startswith("/"):
            cmd_response = handle_command(phone_number, message_text)
            if cmd_response is not None:
                cmd_name = message_text.strip().lower().split()[0]
                sent_with_buttons = False
                if cmd_name in ("/seleccionar", "/select"):
                    cmd_session_data = load_session(phone_number)
                    cmd_session = dict_to_session(cmd_session_data["session_data"]) if cmd_session_data else None
                    if cmd_session is not None and build_template_params(cmd_session) is not None:
                        send_whatsapp_interactive_buttons(
                            to=phone_number,
                            body_text=cmd_response,
                            buttons=[
                                {"id": "COMPARAR", "title": "Sí, compáralo"},
                                {"id": "DESPUES", "title": "En otro momento"},
                            ]
                        )
                        sent_with_buttons = True
                if not sent_with_buttons:
                    send_whatsapp_message(phone_number, cmd_response)
                return

        existing = load_session(phone_number)

        if existing:
            session = dict_to_session(existing["session_data"])
            history = existing["history"]
            response_text, updated_history = run_turn(session, message_text, history)
            save_session(
                phone_number=phone_number,
                session_data=session_to_dict(session),
                history=updated_history,
            )
            _maybe_update_campana_cliente(session, updated_history)
            if session.awaiting_contract_confirmation:
                send_whatsapp_interactive_buttons(
                    to=phone_number,
                    body_text=response_text,
                    buttons=[
                        {"id": "ACEPTO", "title": "✅ Sí, activar"},
                        {"id": "NO", "title": "❌ No, cancelar"},
                    ]
                )
            else:
                send_whatsapp_message(phone_number, response_text)
                _maybe_persist_plan_change(session)
            logger.info(f"WA OUT | {phone_number} [stage={session.stage}]: {response_text[:80]}")
        else:
            session = SessionState(
                first_name=first_name,
                full_name=sender_name,
                phone_number=phone_number,
            )
            campaign_msg = build_campaign_message(session)
            initial_history = [{"role": "assistant", "content": campaign_msg}]
            save_session(
                phone_number=phone_number,
                session_data=session_to_dict(session),
                history=initial_history,
            )
            if build_template_params(session) is not None:
                send_whatsapp_interactive_buttons(
                    to=phone_number,
                    body_text=campaign_msg,
                    buttons=[
                        {"id": "COMPARAR", "title": "Sí, compáralo"},
                        {"id": "DESPUES", "title": "En otro momento"},
                    ]
                )
            else:
                send_whatsapp_message(phone_number, campaign_msg)
            logger.info(f"WA NEW | {phone_number} — sesión creada, campaña enviada")

    except Exception as e:
        logger.error(f"Error procesando mensaje de {phone_number}: {e}", exc_info=True)
    finally:
        lock.release()


@router.post("/webhook")
async def whatsapp_webhook(request: Request, background_tasks: BackgroundTasks):
    """Recibe mensajes de WhatsApp — responde 200 inmediatamente y procesa en segundo plano."""
    body_bytes = await request.body()

    app_secret = os.getenv("WHATSAPP_APP_SECRET", "")
    if app_secret:
        sig_header = request.headers.get("X-Hub-Signature-256", "")
        expected = "sha256=" + hmac.new(app_secret.encode(), body_bytes, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig_header, expected):
            raise HTTPException(status_code=403, detail="Invalid signature")

    try:
        payload = json.loads(body_bytes)
    except Exception:
        return {"status": "ok"}

    try:
        entry = payload.get("entry", [])
        if not entry:
            return {"status": "ok"}

        changes = entry[0].get("changes", [])
        if not changes:
            return {"status": "ok"}

        value = changes[0].get("value", {})
        messages = value.get("messages", [])

        if not messages:
            # Callback de estatus de entrega (sent/delivered/read/failed) —
            # aquí llega la razón real cuando un template no le llega al cliente.
            for status in value.get("statuses", []):
                errors = status.get("errors", [])
                error_detail = f" | errors={errors}" if errors else ""
                logger.info(
                    f"WA STATUS | {status.get('recipient_id')} | "
                    f"status={status.get('status')}{error_detail}"
                )
            return {"status": "ok"}

        msg = messages[0]
        msg_type = msg.get("type")

        # Soportar texto, botones de template (quick_reply) y botones interactivos
        if msg_type == "text":
            message_text = msg["text"]["body"]
        elif msg_type == "button":
            # Botón de template (quick_reply) — usar el payload configurado en el
            # template si existe; si no, cae al texto visible del botón
            btn = msg.get("button", {})
            message_text = btn.get("payload") or btn.get("text", "")
        elif msg_type == "interactive":
            # Botón interactivo — usar el id del botón (ACEPTO o NO)
            interactive = msg.get("interactive", {})
            btn_reply = interactive.get("button_reply", {})
            message_text = btn_reply.get("id", btn_reply.get("title", ""))
        else:
            return {"status": "ok"}

        # Deduplicación: ignorar reintentos de Meta con el mismo ID de mensaje
        msg_id = msg.get("id", "")
        if msg_id:
            with _processed_lock:
                if msg_id in _processed_msg_ids:
                    return {"status": "ok"}
                _processed_msg_ids.add(msg_id)
                # Limitar el tamaño del cache en memoria
                if len(_processed_msg_ids) > 500:
                    _processed_msg_ids.clear()

        phone_number = msg["from"]

        contacts = value.get("contacts", [])
        sender_name = contacts[0]["profile"]["name"] if contacts else "Cliente"

        logger.info(f"WA IN  | {phone_number} ({sender_name}): {message_text}")

        # Procesar en segundo plano — Meta recibe 200 de inmediato
        background_tasks.add_task(_process_whatsapp_message, phone_number, message_text, sender_name)

    except Exception as e:
        logger.error(f"WhatsApp webhook error: {e}", exc_info=True)

    return {"status": "ok"}


@router.post("/webhook/provisioning-status", dependencies=[Depends(require_api_key)])
def provisioning_status_webhook(payload: ProvisioningStatusRequest):
    """Recibe la notificación de Telcel del estatus de provisioning de un cambio de plan."""
    logger.info(
        "PROVISIONING | processId=%s msisdn=%s statusProvisioning=%s",
        payload.processId, payload.msisdn, payload.statusProvisioning,
    )

    now = datetime.now()
    token_operation = f"ORCL-{now.strftime('%Y%m%d%H%M%S')}.{now.microsecond // 1000:03d}"

    return {
        "detailResponse": {
            "code": 200,
            "severityLevel": "0",
            "description": "Petición exitosa",
            "actor": "BOTWHSAP-ORACLE",
            "businessMeaning": "Success",
        },
        "found": True,
        "success": True,
        "tokenOperation": token_operation,
    }
