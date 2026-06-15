"""
main.py — Entry point FastAPI para ReniAgent con persistencia PostgreSQL.
"""

from fastapi import FastAPI, Header, HTTPException, Query, BackgroundTasks
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from typing import Optional
import os
import logging
import threading
from dotenv import load_dotenv

from app.agent.reni_agent import run_turn
from app.state.session import SessionState
from app.state.persistence import init_db, load_session, save_session, delete_session
from app.state.serializer import session_to_dict, dict_to_session
from app.prompts.campaign_template import build_campaign_message, build_template_params
from app.whatsapp.sender import send_whatsapp_message, send_whatsapp_template
from app.whatsapp.command_handler import handle_command
from app.config.logging_config import setup_logging

load_dotenv()
setup_logging()

logger = logging.getLogger(__name__)

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

app = FastAPI(
    title="ReniAgent — Telcel Sales Agent",
    version="2.0.0",
    description="Agente de ventas Telcel con Strands Agents + OCI + PostgreSQL",
)


@app.on_event("startup")
def startup():
    """Crea las tablas en PostgreSQL al arrancar."""
    init_db()
    logger.info("ReniAgent iniciado — tablas PostgreSQL listas")


class ChatRequest(BaseModel):
    message: str
    phone_number: str                          # identificador de sesión
    # Datos del cliente — solo necesarios en el primer turno
    first_name: Optional[str] = "Cliente"
    full_name: Optional[str] = ""
    current_plan_name: Optional[str] = "Telcel Plus 150"
    current_cost: Optional[float] = 150.0
    current_plan_gb: Optional[float] = None
    current_plan_cashback: Optional[float] = None
    subscription_type: Optional[str] = "Abierto"
    has_promotion: Optional[bool] = True
    usage_summary: Optional[str] = None
    is_titular: Optional[bool] = True


class ChatResponse(BaseModel):
    response: str
    stage: str
    plan_selected: Optional[str] = None
    turn: int = 1


class CampaignRequest(BaseModel):
    phone_number: str
    first_name: Optional[str] = "Cliente"
    full_name: Optional[str] = ""
    current_plan_name: Optional[str] = "Telcel Plus 150"
    current_cost: Optional[float] = 150.0
    current_plan_gb: Optional[float] = None
    current_plan_cashback: Optional[float] = None
    subscription_type: Optional[str] = "Abierto"
    has_promotion: Optional[bool] = True
    usage_summary: Optional[str] = None
    is_titular: Optional[bool] = True
    template_name: Optional[str] = None   # defaults to TEMPLATE_NAME env var
    language_code: Optional[str] = "es_MX"


class SessionDeleteRequest(BaseModel):
    phone_number: str


@app.get("/actuator/health", include_in_schema=False)
def health():
    return {"status": "UP"}


@app.post("/chat", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    x_api_key: Optional[str] = Header(default=None),
):
    # Validación API key
    expected_key = os.getenv("API_KEY", "")
    if expected_key and x_api_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

    # Intentar cargar sesión existente desde PostgreSQL
    existing = load_session(request.phone_number)

    if existing:
        # Sesión existente — restaurar estado e historial
        session = dict_to_session(existing["session_data"])
        history = existing["history"]
    else:
        # Nueva sesión — crear con datos del request
        session = SessionState(
            first_name=request.first_name,
            full_name=request.full_name,
            phone_number=request.phone_number,
            current_plan_name=request.current_plan_name,
            current_cost=request.current_cost,
            current_plan_gb=request.current_plan_gb,
            current_plan_cashback=request.current_plan_cashback,
            subscription_type=request.subscription_type,
            has_promotion=request.has_promotion,
            usage_summary=request.usage_summary,
            is_titular=request.is_titular,
        )

        # Primer turno: devolver el mensaje de campaña determinístico sin llamar al LLM
        campaign_msg = build_campaign_message(session)
        initial_history = [{"role": "assistant", "content": campaign_msg}]

        save_session(
            phone_number=request.phone_number,
            session_data=session_to_dict(session),
            history=initial_history,
        )

        return ChatResponse(
            response=campaign_msg,
            stage=session.stage,
            plan_selected=session.plan_selected,
            turn=1,
        )

    # Ejecutar turno
    response_text, updated_history = run_turn(session, request.message, history)

    # Guardar sesión actualizada en PostgreSQL
    save_session(
        phone_number=request.phone_number,
        session_data=session_to_dict(session),
        history=updated_history,
    )

    return ChatResponse(
        response=response_text,
        stage=session.stage,
        plan_selected=session.plan_selected,
        turn=len(updated_history) // 2,
    )


@app.post("/campaign")
def campaign(
    request: CampaignRequest,
    x_api_key: Optional[str] = Header(default=None),
):
    """Inicia una campaña enviando el template de WhatsApp al cliente y creando la sesión."""
    expected_key = os.getenv("API_KEY", "")
    if expected_key and x_api_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

    session = SessionState(
        first_name=request.first_name,
        full_name=request.full_name,
        phone_number=request.phone_number,
        current_plan_name=request.current_plan_name,
        current_cost=request.current_cost,
        current_plan_gb=request.current_plan_gb,
        current_plan_cashback=request.current_plan_cashback,
        subscription_type=request.subscription_type,
        has_promotion=request.has_promotion,
        usage_summary=request.usage_summary,
        is_titular=request.is_titular,
    )

    template_result = build_template_params(session)
    campaign_msg = build_campaign_message(session)

    if template_result is None:
        # Sin plan elegible — texto plano como fallback
        try:
            send_whatsapp_message(request.phone_number, campaign_msg)
        except Exception as e:
            logger.error(f"CAMPAIGN | texto plano falló: {e}")
        logger.info(f"CAMPAIGN | {request.phone_number} — sin plan elegible, texto plano enviado")
        sent_template = False
        template_name = None
    else:
        template_name = request.template_name or template_result["template_name"]
        params_list = template_result["params"]
        wa_id = request.phone_number
        try:
            wa_resp = send_whatsapp_template(
                to=request.phone_number,
                template_name=template_name,
                params=params_list,
                language_code=request.language_code,
            )
            # wa_id es el número en formato canónico de Meta — es la clave que llega en webhooks
            wa_id = wa_resp.get("contacts", [{}])[0].get("wa_id", request.phone_number)
            logger.info(f"CAMPAIGN | {request.phone_number} → wa_id={wa_id} — template '{template_name}' enviado")
            sent_template = True
        except Exception as e:
            logger.warning(f"CAMPAIGN | template falló, usando texto plano: {e}")
            try:
                send_whatsapp_message(request.phone_number, campaign_msg)
            except Exception as e2:
                logger.error(f"CAMPAIGN | fallback texto también falló: {e2}")
            sent_template = False

    # Guardar sesión bajo wa_id para que el webhook la encuentre al recibir la respuesta
    save_session(
        phone_number=wa_id,
        session_data=session_to_dict(session),
        history=[{"role": "assistant", "content": campaign_msg}],
    )

    return {
        "status": "sent",
        "phone_number": request.phone_number,
        "wa_id": wa_id,
        "sent_template": sent_template,
        "template_name": template_name if sent_template else None,
        "params": template_result["params"] if template_result else None,
    }


@app.get("/webhook")
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
            send_whatsapp_message(phone_number, response_text)
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
            send_whatsapp_message(phone_number, campaign_msg)
            logger.info(f"WA NEW | {phone_number} — sesión creada, campaña enviada")

    except Exception as e:
        logger.error(f"Error procesando mensaje de {phone_number}: {e}", exc_info=True)
    finally:
        lock.release()


@app.post("/webhook")
def whatsapp_webhook(payload: dict, background_tasks: BackgroundTasks):
    """Recibe mensajes de WhatsApp — responde 200 inmediatamente y procesa en segundo plano."""
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
            return {"status": "ok"}

        msg = messages[0]
        msg_type = msg.get("type")

        # Soportar texto y pulsaciones de botones de template (quick_reply)
        if msg_type == "text":
            message_text = msg["text"]["body"]
        elif msg_type == "button":
            # El usuario pulsó un botón de template — tratar el texto del botón como mensaje
            message_text = msg["button"]["text"]
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


@app.delete("/session")
def delete(
    request: SessionDeleteRequest,
    x_api_key: Optional[str] = Header(default=None),
):
    """Elimina la sesión de un cliente (para pruebas o reset)."""
    expected_key = os.getenv("API_KEY", "")
    if expected_key and x_api_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

    delete_session(request.phone_number)
    return {"deleted": request.phone_number}
