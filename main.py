"""
main.py — Entry point FastAPI para ReniAgent con persistencia PostgreSQL.
"""

import os
import csv
import io
import hmac
import hashlib
import json
import logging
import threading
from dotenv import load_dotenv

load_dotenv()  # Debe ejecutarse antes de importar módulos que lean os.environ al cargarse

from app.config.logging_config import setup_logging, LOGS_DIR
setup_logging()  # Debe correr antes de importar módulos que loguean al cargarse (p.ej. oci_model)

from fastapi import FastAPI, File, UploadFile, Form, Header, HTTPException, Query, BackgroundTasks, Request
from fastapi.responses import PlainTextResponse, FileResponse
from pydantic import BaseModel
from typing import Optional, Union

from app.agent.reni_agent import run_turn
from app.state.session import SessionState
from app.state.persistence import init_db, load_session, save_session, delete_session
from app.state.serializer import session_to_dict, dict_to_session
from app.prompts.campaign_template import build_campaign_message, build_template_params
from app.whatsapp.sender import send_whatsapp_message, send_whatsapp_template, send_whatsapp_interactive_buttons
from app.whatsapp.command_handler import handle_command
from app.router.semantic_router import load_reference_embeddings

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
    logger.info("[DEPLOY] Modelo OCI activo: %s", os.environ.get("OCI_MODEL_ID", "desconocido"))
    init_db()
    if _CAMPAIGN_DB_AVAILABLE:
        try:
            from campaign_app.db.models import Base as CampaignBase
            from campaign_app.db.database import get_engine
            CampaignBase.metadata.create_all(get_engine())
            logger.info("Tablas de campaña listas")
        except Exception as e:
            logger.warning(f"No se pudieron crear tablas de campaña: {e}")
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
    fila_inicio: int
    fila_fin: int


class SessionDeleteRequest(BaseModel):
    phone_number: str


@app.get("/actuator/health", include_in_schema=False)
def health():
    return {"status": "UP"}


@app.get("/health", include_in_schema=False)
def health_simple():
    return "ok"


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
    try:
        response_text, updated_history = run_turn(session, request.message, history)
    except Exception as e:
        logger.error(
            f"Error procesando /chat de {request.phone_number} "
            f"[stage={session.stage}]: {e}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Error procesando el mensaje")

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
    """
    Envía el template de campaña a los clientes de la tabla 'clientes' (Postgres)
    cuya 'fila' (mismo orden de carga que /campaign/clientes, por creado_en) esté
    entre fila_inicio y fila_fin, ambos inclusive.
    """
    expected_key = os.getenv("API_KEY", "")
    if expected_key and x_api_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

    if not _CAMPAIGN_DB_AVAILABLE:
        raise HTTPException(status_code=503, detail=f"Campaign DB not available: {_CAMPAIGN_DB_ERROR}")

    todos_clientes = campaign_crud.get_all_clientes()
    seleccionados = [
        c for i, c in enumerate(todos_clientes, start=1)
        if request.fila_inicio <= i <= request.fila_fin
    ]

    results = {"sent": [], "failed": []}

    for cliente in seleccionados:
        phone_number = cliente.linea

        try:
            session = SessionState(
                first_name=(cliente.nombre or "Cliente").split()[0].title(),
                full_name=f"{cliente.nombre or ''} {cliente.apellidos or ''}".strip(),
                phone_number=phone_number,
                current_plan_name=cliente.plan_actual_nombre or "Plan Legado",
                current_cost=cliente.renta_plan or 0.0,
                subscription_type=cliente.tipo_suscripcion or "Abierto",
                is_titular=True,
            )
            template_result = build_template_params(session)
            campaign_msg = build_campaign_message(session)

            wa_id = phone_number
            sent_template = False
            template_name = None
            delivered = False

            if template_result is None:
                # Sin plan elegible — texto plano como fallback
                try:
                    send_whatsapp_message(phone_number, campaign_msg)
                    delivered = True
                except Exception as e:
                    logger.error(f"CAMPAIGN | {phone_number} texto plano falló: {e}")
                logger.info(f"CAMPAIGN | {phone_number} — sin plan elegible, texto plano enviado")
            else:
                template_name = template_result["template_name"]
                try:
                    wa_resp = send_whatsapp_template(
                        to=phone_number,
                        template_name=template_name,
                        params=template_result["params"],
                    )
                    # wa_id es el número en formato canónico de Meta — es la clave que llega en webhooks
                    wa_id = wa_resp.get("contacts", [{}])[0].get("wa_id", phone_number)
                    logger.info(f"CAMPAIGN | {phone_number} → wa_id={wa_id} — template '{template_name}' enviado")
                    sent_template = True
                    delivered = True
                except Exception as e:
                    logger.warning(f"CAMPAIGN | {phone_number} template falló, usando texto plano: {e}")
                    try:
                        send_whatsapp_message(phone_number, campaign_msg)
                        delivered = True
                    except Exception as e2:
                        logger.error(f"CAMPAIGN | {phone_number} fallback texto también falló: {e2}")

            if not delivered:
                results["failed"].append({"phone_number": phone_number, "reason": "envío de WhatsApp falló (template y texto plano)"})
                continue

            # Guardar sesión bajo wa_id para que el webhook la encuentre al recibir la respuesta
            save_session(
                phone_number=wa_id,
                session_data=session_to_dict(session),
                history=[{"role": "assistant", "content": campaign_msg}],
            )

            results["sent"].append({
                "phone_number": phone_number,
                "wa_id": wa_id,
                "sent_template": sent_template,
                "template_name": template_name if sent_template else None,
            })
        except Exception as e:
            logger.error(f"CAMPAIGN | {phone_number} error inesperado: {e}", exc_info=True)
            results["failed"].append({"phone_number": phone_number, "reason": str(e)})

    return results


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


class DispatchLoteRequest(BaseModel):
    campana_id: int
    limite: int = 100


@app.post("/campaign/dispatch/lote")
def campaign_dispatch_lote(
    request: DispatchLoteRequest,
    x_api_key: Optional[str] = Header(default=None),
):
    """
    Envía a los próximos N clientes pendientes (estado_envio='pendiente') de
    una campaña — evita tener que armar la lista de líneas a mano en cada
    lote. Internamente resuelve las líneas y reusa campaign_dispatch().
    """
    expected_key = os.getenv("API_KEY", "")
    if expected_key and x_api_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

    if not _CAMPAIGN_DB_AVAILABLE:
        raise HTTPException(status_code=503, detail=f"Campaign DB not available: {_CAMPAIGN_DB_ERROR}")

    from campaign_app.db.database import get_db
    from campaign_app.db.models import CampanaCliente, Cliente as ClienteModel

    with get_db() as db:
        pendientes = (
            db.query(CampanaCliente)
            .join(ClienteModel, CampanaCliente.linea == ClienteModel.linea)
            .filter(
                CampanaCliente.campana_id == request.campana_id,
                CampanaCliente.estado_envio == "pendiente",
            )
            .order_by(ClienteModel.creado_en.asc())
            .limit(request.limite)
            .all()
        )
        lineas = [cc.linea for cc in pendientes]

    if not lineas:
        return {"sent": [], "failed": [], "detail": "No hay clientes pendientes para esta campaña"}

    logger.info(f"DISPATCH_LOTE | campana_id={request.campana_id} resueltos={len(lineas)} de limite={request.limite}")
    return campaign_dispatch(DispatchRequest(campana_id=request.campana_id, lineas=lineas), x_api_key)


@app.post("/campaign/migrate-orden")
def campaign_migrate_orden(
    x_api_key: Optional[str] = Header(default=None),
):
    """
    Agrega la columna 'orden' a 'clientes' si aún no existe en esta BD, y le
    asigna un valor secuencial (por creado_en) a los clientes que no lo tengan.
    Idempotente — se puede llamar varias veces sin efectos raros.
    """
    expected_key = os.getenv("API_KEY", "")
    if expected_key and x_api_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

    if not _CAMPAIGN_DB_AVAILABLE:
        raise HTTPException(status_code=503, detail=f"Campaign DB not available: {_CAMPAIGN_DB_ERROR}")

    result = campaign_crud.ensure_orden_column()
    logger.info(
        f"MIGRATE_ORDEN | columna_agregada={result['columna_agregada']} "
        f"filas_backfilled={result['filas_backfilled']}"
    )
    return result


@app.post("/campaign/import-clientes")
def campaign_import_clientes(
    file: UploadFile = File(...),
    campana_id: Optional[int] = Form(default=None),
    x_api_key: Optional[str] = Header(default=None),
):
    """
    Importa/actualiza clientes en la tabla 'clientes' a partir de un CSV subido
    (mismo formato que docs/Masivo_backup.csv).
    Si se manda 'campana_id', además vincula las líneas importadas a esa campaña
    en 'campana_clientes' (estado_envio='pendiente'), listas para /campaign/dispatch/lote.
    """
    expected_key = os.getenv("API_KEY", "")
    if expected_key and x_api_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

    if not _CAMPAIGN_DB_AVAILABLE:
        raise HTTPException(status_code=503, detail=f"Campaign DB not available: {_CAMPAIGN_DB_ERROR}")

    content = file.file.read().decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(content))
    rows = list(reader)
    if not rows or "linea" not in rows[0]:
        raise HTTPException(status_code=400, detail="El CSV no tiene la columna 'linea'.")

    result = campaign_crud.import_clientes_csv(rows)

    if campana_id is not None and result["imported"]:
        campaign_crud.add_clientes_to_campana(campana_id, result["imported"])
        result["campana_id"] = campana_id

    logger.info(
        f"IMPORT_CLIENTES | {result['total']} filas | "
        f"{len(result['imported'])} importados | {len(result['skipped'])} omitidos"
        + (f" | vinculados a campana_id={campana_id}" if campana_id is not None else "")
    )
    return result


@app.get("/campaign/clientes")
def campaign_get_all_clientes(
    x_api_key: Optional[str] = Header(default=None),
):
    """
    Lista TODOS los clientes de la tabla 'clientes', sin filtrar por campaña
    (a diferencia de /campaign/{campana_id}/clientes, que solo trae los vinculados
    a esa campaña en 'campana_clientes').
    """
    expected_key = os.getenv("API_KEY", "")
    if expected_key and x_api_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

    if not _CAMPAIGN_DB_AVAILABLE:
        raise HTTPException(status_code=503, detail=f"Campaign DB not available: {_CAMPAIGN_DB_ERROR}")

    clientes = campaign_crud.get_all_clientes()
    result = [{
        "fila": i,
        "orden": c.orden,
        "linea": c.linea,
        "nombre": c.nombre,
        "apellidos": c.apellidos,
        "plan_actual_nombre": c.plan_actual_nombre,
        "familia_plan": c.familia_plan,
        "tipo_suscripcion": c.tipo_suscripcion,
        "renta_plan": c.renta_plan,
        "facturacion_promedio": c.facturacion_promedio,
        "creado_en": c.creado_en.isoformat() if c.creado_en else None,
    } for i, c in enumerate(clientes, start=1)]

    return {"total": len(result), "clientes": result}


@app.get("/campaign/{campana_id}/clientes")
def campaign_get_clientes(
    campana_id: int,
    x_api_key: Optional[str] = Header(default=None),
):
    """
    Lista los clientes de una campaña tal como quedaron guardados en BD
    (join de 'clientes' + 'campana_clientes'), para verificar una importación.
    """
    expected_key = os.getenv("API_KEY", "")
    if expected_key and x_api_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

    if not _CAMPAIGN_DB_AVAILABLE:
        raise HTTPException(status_code=503, detail=f"Campaign DB not available: {_CAMPAIGN_DB_ERROR}")

    campana_clientes = campaign_crud.get_campana_clientes(campana_id)
    clientes = []
    for i, cc in enumerate(campana_clientes, start=1):
        c = cc.cliente
        clientes.append({
            "fila": i,
            "orden": c.orden if c else None,
            "linea": cc.linea,
            "nombre": c.nombre if c else None,
            "apellidos": c.apellidos if c else None,
            "plan_actual_nombre": c.plan_actual_nombre if c else None,
            "familia_plan": c.familia_plan if c else None,
            "tipo_suscripcion": c.tipo_suscripcion if c else None,
            "renta_plan": c.renta_plan if c else None,
            "estado_envio": cc.estado_envio,
            "estado_interaccion": cc.estado_interaccion,
            "fecha_envio": cc.fecha_envio.isoformat() if cc.fecha_envio else None,
            "plan_seleccionado": cc.plan_seleccionado,
            "folio_contrato": cc.folio_contrato,
            "num_turnos": cc.num_turnos,
        })

    return {"campana_id": campana_id, "total": len(clientes), "clientes": clientes}


@app.delete("/campaign/clientes")
def campaign_delete_all_clientes(
    confirm: bool = Query(default=False),
    x_api_key: Optional[str] = Header(default=None),
):
    """
    Borra TODOS los registros de 'clientes' y sus vínculos en 'campana_clientes'.
    Irreversible. Requiere ?confirm=true para evitar disparos accidentales.
    """
    expected_key = os.getenv("API_KEY", "")
    if expected_key and x_api_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

    if not _CAMPAIGN_DB_AVAILABLE:
        raise HTTPException(status_code=503, detail=f"Campaign DB not available: {_CAMPAIGN_DB_ERROR}")

    if not confirm:
        raise HTTPException(status_code=400, detail="Falta ?confirm=true — esta acción borra TODOS los clientes.")

    result = campaign_crud.delete_all_clientes()
    logger.warning(
        f"DELETE_ALL_CLIENTES | {result['clientes_borrados']} clientes, "
        f"{result['campana_clientes_borrados']} vínculos de campaña borrados"
    )
    return result


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

"""Agrega logs)."""
@app.get("/logs", include_in_schema=False)
def get_logs(api_key: Optional[str] = Query(default=None)):
    """Descarga el archivo de log activo (app.log) para monitoreo remoto."""
    expected_key = os.getenv("API_KEY", "")
    if expected_key and api_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

    log_path = os.path.join(LOGS_DIR, "app.log")
    if not os.path.exists(log_path):
        raise HTTPException(status_code=404, detail="Log file not found")

    return FileResponse(
        path=log_path,
        media_type="text/plain",
        filename="app.log",
    )


class ContextLimitResult(BaseModel):
    target_tokens: int
    input_tokens: Optional[Union[int, str]] = None
    output_tokens: Optional[Union[int, str]] = None
    latency_ms: Optional[Union[int, str]] = None
    response_preview: Optional[str] = None
    status: str  # "ok" | "fallo" | "error"
    error: Optional[str] = None


@app.get("/test/limits", include_in_schema=False)
def test_context_limits(x_api_key: Optional[str] = Header(default=None)):
    """
    Prueba el límite de contexto del modelo OCI con inputs de tamaño creciente.
    Réplica de scripts/test_context_limit.py expuesta como endpoint.
    """
    expected_key = os.getenv("API_KEY", "")
    if expected_key and x_api_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

    from strands import Agent
    from app.config.oci_model import oci_model

    WORD = "navegación "
    sizes = [1000, 2000, 4000, 6000, 8000, 10000, 12000, 14000, 16000]
    results = []

    for target_tokens in sizes:
        chars = target_tokens * 4
        filler = WORD * (chars // len(WORD))

        try:
            agent = Agent(
                model=oci_model,
                system_prompt=f"Eres un asistente. Contexto: {filler}",
                tools=[],
                callback_handler=None,
            )
            response = agent("Responde solo: OK")

            text = ""
            if hasattr(response, "message") and response.message:
                for block in response.message.get("content", []):
                    if isinstance(block, dict) and "text" in block:
                        text += block.get("text", "")

            # Leer tokens del message directamente
            input_tokens = "?"
            output_tokens = "?"
            latency = "?"
            if hasattr(response, "message") and response.message:
                metadata = response.message.get("metadata", {})
                usage = metadata.get("usage", {})
                input_tokens = usage.get("inputTokens", "?")
                output_tokens = usage.get("outputTokens", "?")
                latency = metadata.get("metrics", {}).get("latencyMs", "?")

            try:
                out_int = int(output_tokens)
            except (ValueError, TypeError):
                out_int = 1  # si no podemos leer, asumimos que funcionó

            results.append(ContextLimitResult(
                target_tokens=target_tokens,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=latency,
                response_preview=text[:30],
                status="fallo" if out_int == 0 else "ok",
            ))
            if out_int == 0:
                break

        except Exception as e:
            results.append(ContextLimitResult(
                target_tokens=target_tokens,
                status="error",
                error=str(e),
            ))
            break

    return {"results": results}


_PEDRO_CONVERSATION = [
    {"role": "assistant", "content": [{"text": "Hola Pedro, le ofrecemos el Telcel Libre 4 Abierto a $499/mes. ¿Le gustaría activarlo?"}]},
    {"role": "user", "content": [{"text": "que beneficios tiene?"}]},
    {"role": "assistant", "content": [{"text": "Lo que gana con el cambio: 10 GB, cashback $74.85/mes, apps ilimitadas. ¿Le gustaría activarlo?"}]},
    {"role": "user", "content": [{"text": "cuanto cuesta el cashback?"}]},
    {"role": "assistant", "content": [{"text": "El cashback es de $74.85/mes y puede usarlo en servicios Telcel. ¿Le gustaría activar el Telcel Libre 4 Abierto?"}]},
    {"role": "user", "content": [{"text": "tiene claro video?"}]},
    {"role": "assistant", "content": [{"text": "Sí, incluye Claro Video. ¿Le gustaría activar el Telcel Libre 4 Abierto?"}]},
    {"role": "user", "content": [{"text": "y claro drive?"}]},
    {"role": "assistant", "content": [{"text": "Sí, incluye Claro Drive con 20 GB. ¿Le gustaría activar el Telcel Libre 4 Abierto?"}]},
    {"role": "user", "content": [{"text": "cuanto tiempo dura la promocion?"}]},
    {"role": "assistant", "content": [{"text": "Esta promoción tiene vigencia el día de hoy. ¿Le gustaría activar el Telcel Libre 4 Abierto?"}]},
    {"role": "user", "content": [{"text": "puedo decidir despues?"}]},
    {"role": "assistant", "content": [{"text": "Esta promoción tiene vigencia el día de hoy. ¿Le gustaría activar el Telcel Libre 4 Abierto?"}]},
    {"role": "user", "content": [{"text": "que pasa si se me acaban los datos?"}]},
    {"role": "assistant", "content": [{"text": "Al agotar los GB el servicio se suspende hasta el siguiente ciclo. ¿Le gustaría activar el Telcel Libre 4 Abierto?"}]},
    {"role": "user", "content": [{"text": "ok me interesa"}]},
    {"role": "assistant", "content": [{"text": "¿Le gustaría activar el Telcel Libre 4 Abierto?"}]},
    {"role": "user", "content": [{"text": "si"}]},
    {"role": "assistant", "content": [{"text": "¿Le gustaría activar el Telcel Libre 4 Abierto?"}]},
    {"role": "user", "content": [{"text": "adelante"}]},
]


class ConversationLimitResult(BaseModel):
    n_msgs: int
    input_tokens: Optional[Union[int, str]] = None
    output_tokens: Optional[Union[int, str]] = None
    latency_ms: Optional[Union[int, str]] = None
    response_preview: Optional[str] = None
    status: str  # "ok" | "fallo" | "error"
    error: Optional[str] = None


@app.get("/test/limits/conversation", include_in_schema=False)
def test_context_limits_conversation(x_api_key: Optional[str] = Header(default=None)):
    """
    Prueba el límite de contexto con una conversación de ventas realista de tamaño
    creciente (system prompt real + herramientas reales), a diferencia de /test/limits
    que usa texto de relleno sintético.
    """
    expected_key = os.getenv("API_KEY", "")
    if expected_key and x_api_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

    from app.agent.reni_agent import create_agent

    session = SessionState(
        first_name="Pedro",
        phone_number="5555555555",
        current_plan_name="Telcel Max Sin Limite 5000",
        current_cost=499.0,
        subscription_type="Abierto",
        current_plan_gb=5.0,
        has_promotion=True,
        is_titular=True,
        stage="PERSUASION",
        plan_anclado="Telcel Libre 4 Abierto",
    )

    sizes = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 14, 16, 18, 20]
    results = []

    for n_msgs in sizes:
        history = _PEDRO_CONVERSATION[:n_msgs]

        try:
            agent = create_agent(session, messages=history)
            response = agent("si, adelante")

            text = ""
            if hasattr(response, "message") and response.message:
                for block in response.message.get("content", []):
                    if isinstance(block, dict) and "text" in block:
                        text += block.get("text", "")

            # Leer tokens del message directamente
            input_tokens = "?"
            output_tokens = "?"
            latency = "?"
            if hasattr(response, "message") and response.message:
                metadata = response.message.get("metadata", {})
                usage = metadata.get("usage", {})
                input_tokens = usage.get("inputTokens", "?")
                output_tokens = usage.get("outputTokens", "?")
                latency = metadata.get("metrics", {}).get("latencyMs", "?")

            try:
                out_int = int(output_tokens)
            except (ValueError, TypeError):
                out_int = 1  # si no podemos leer, asumimos que funcionó

            results.append(ConversationLimitResult(
                n_msgs=n_msgs,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=latency,
                response_preview=text[:50],
                status="fallo" if out_int == 0 else "ok",
            ))
            if out_int == 0:
                break

        except Exception as e:
            results.append(ConversationLimitResult(
                n_msgs=n_msgs,
                status="error",
                error=str(e),
            ))
            break

    return {"results": results}
