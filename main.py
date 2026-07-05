"""
main.py — Entry point FastAPI para ReniAgent con persistencia PostgreSQL.
"""

import os
import hmac
import hashlib
import json
import logging
import threading
from dotenv import load_dotenv

load_dotenv()  # Debe ejecutarse antes de importar módulos que lean os.environ al cargarse

from fastapi import FastAPI, Header, HTTPException, Query, BackgroundTasks, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from typing import Optional

from app.agent.reni_agent import run_turn
from app.state.session import SessionState
from app.state.persistence import init_db, load_session, save_session, delete_session
from app.state.serializer import session_to_dict, dict_to_session
from app.prompts.campaign_template import build_campaign_message, build_template_params
from app.whatsapp.sender import send_whatsapp_message, send_whatsapp_template, send_whatsapp_interactive_buttons
from app.whatsapp.command_handler import handle_command
from app.config.logging_config import setup_logging
from app.router.semantic_router import load_reference_embeddings
setup_logging()

logger = logging.getLogger(__name__)

# Campaign DB — optional; agent still works if campaign tables don't exist
try:
    import sys as _sys
    _sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from campaign_app.db import crud as campaign_crud
    _CAMPAIGN_DB_AVAILABLE = True
except Exception as _e:
    import traceback as _tb
    _CAMPAIGN_DB_ERROR = str(_e) + "\n" + _tb.format_exc()
    print(f"[WARN] campaign_app.db not available: {_e}")
    _tb.print_exc()
    _CAMPAIGN_DB_AVAILABLE = False
else:
    _CAMPAIGN_DB_ERROR = None

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


def _to_linea(phone_number: str) -> str:
    """Strip country/mobile prefix to get 10-digit Mexican linea as stored in DB."""
    n = phone_number.lstrip("+")
    if n.startswith("521") and len(n) == 13:   # 521XXXXXXXXXX → XXXXXXXXXX
        return n[3:]
    if n.startswith("52") and len(n) == 12:    # 52XXXXXXXXXX  → XXXXXXXXXX
        return n[2:]
    return n


def _stage_to_interaccion(session) -> str:
    if session.stage == "END":
        return "contratado" if session.contract_folio else "rechazado"
    if session.stage in ("POST_SALE",):
        return "contratado"
    return "en_conversacion"


def _maybe_update_campana_cliente(session, history: list):
    """Update CampanaCliente traceability after each turn. Silently skips on any error."""
    if not _CAMPAIGN_DB_AVAILABLE:
        return
    try:
        linea = _to_linea(session.phone_number)
        cc = campaign_crud.find_active_campana_cliente(linea)
        if not cc:
            return
        campaign_crud.update_interaction(
            campana_id=cc.campana_id,
            linea=linea,
            num_turnos=len(history) // 2,
            estado_interaccion=_stage_to_interaccion(session),
            plan_seleccionado=session.plan_selected,
            folio_contrato=getattr(session, "contract_folio", None),
        )
        if session.stage == "END":
            campaign_crud.close_session_snapshot(
                campana_id=cc.campana_id,
                linea=linea,
                history=history,
                session_data=session_to_dict(session),
            )
    except Exception as e:
        logger.warning(f"campaign traceability error: {e}")

app = FastAPI(
    title="ReniAgent — Telcel Sales Agent",
    version="2.0.0",
    description="Agente de ventas Telcel con Strands Agents + OCI + PostgreSQL",
)


@app.on_event("startup")
def startup():
    """Crea las tablas en PostgreSQL al arrancar."""
    init_db()
    load_reference_embeddings()
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

    _maybe_update_campana_cliente(session, updated_history)

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


class DispatchRequest(BaseModel):
    campana_id: int
    lineas: list[str]


@app.post("/campaign/dispatch")
def campaign_dispatch(
    request: DispatchRequest,
    x_api_key: Optional[str] = Header(default=None),
):
    """
    Batch-dispatch campaign messages from the Streamlit UI.
    For each linea, looks up the client in the DB, sends the WhatsApp template,
    and updates the CampanaCliente row accordingly.
    """
    expected_key = os.getenv("API_KEY", "")
    if expected_key and x_api_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

    if not _CAMPAIGN_DB_AVAILABLE:
        raise HTTPException(status_code=503, detail=f"Campaign DB not available: {_CAMPAIGN_DB_ERROR}")

    results = {"sent": [], "failed": []}

    for linea in request.lineas:
        try:
            from campaign_app.db.database import get_db
            from campaign_app.db.models import Cliente as ClienteModel
            with get_db() as db:
                cliente = db.query(ClienteModel).filter_by(linea=linea).first()

            if not cliente:
                results["failed"].append({"linea": linea, "reason": "cliente no encontrado"})
                continue

            session = SessionState(
                first_name=(cliente.nombre or "Cliente").split()[0].title(),
                full_name=f"{cliente.nombre or ''} {cliente.apellidos or ''}".strip(),
                phone_number=linea,
                current_plan_name=cliente.plan_actual_nombre or "Plan Legado",
                current_cost=cliente.renta_plan or 0.0,
                subscription_type=cliente.tipo_suscripcion or "Abierto",
                is_titular=True,
            )

            template_result = build_template_params(session)
            campaign_msg = build_campaign_message(session)

            logger.info(
                f"DISPATCH | {linea} | plan={session.current_plan_name} "
                f"costo=${session.current_cost:.0f} tipo={session.subscription_type}"
            )

            wa_id = linea  # fallback si Meta no devuelve wa_id
            try:
                if template_result:
                    from app.whatsapp.sender import _normalize_phone
                    numero_normalizado = _normalize_phone(linea)
                    logger.info(
                        f"DISPATCH | {linea} | enviando template='{template_result['template_name']}' "
                        f"idioma={os.environ.get('TEMPLATE_LANGUAGE', 'es_MX')} "
                        f"numero_normalizado={numero_normalizado} "
                        f"params={template_result['params']}"
                    )
                    wa_resp = send_whatsapp_template(
                        to=linea,
                        template_name=template_result["template_name"],
                        params=template_result["params"],
                    )
                    wa_id = wa_resp.get("contacts", [{}])[0].get("wa_id", linea)
                    logger.info(f"DISPATCH | {linea} → wa_id={wa_id} | respuesta Meta: {wa_resp}")
                else:
                    logger.info(f"DISPATCH | {linea} | sin plan elegible, enviando texto plano")
                    send_whatsapp_message(linea, campaign_msg)
                campaign_crud.mark_enviado(request.campana_id, linea)
                results["sent"].append(linea)
            except Exception as e:
                logger.error(f"DISPATCH | {linea} falló: {e}")
                campaign_crud.mark_fallido(request.campana_id, linea)
                results["failed"].append({"linea": linea, "reason": str(e)})

            # Guardar sesión bajo el wa_id canónico de Meta para que el webhook la encuentre
            save_session(
                phone_number=wa_id,
                session_data=session_to_dict(session),
                history=[{"role": "assistant", "content": campaign_msg}],
            )

        except Exception as e:
            logger.error(f"DISPATCH | {linea} error inesperado: {e}", exc_info=True)
            results["failed"].append({"linea": linea, "reason": str(e)})

    return results


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
            return {"status": "ok"}

        msg = messages[0]
        msg_type = msg.get("type")

        # Soportar texto, botones de template (quick_reply) y botones interactivos
        if msg_type == "text":
            message_text = msg["text"]["body"]
        elif msg_type == "button":
            # Botón de template (quick_reply)
            message_text = msg["button"]["text"]
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
