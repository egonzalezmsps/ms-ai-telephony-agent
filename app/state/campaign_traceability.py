"""
state/campaign_traceability.py

Estado y helpers de trazabilidad de campaña compartidos entre el router de
chat, el de webhook de WhatsApp y el de campañas. El import de campaign_app.db
es opcional — el agente conversacional sigue funcionando aunque no esté
disponible (ver CAMPAIGN_DB_AVAILABLE).
"""

import os
import logging

from app.state.serializer import session_to_dict

logger = logging.getLogger(__name__)

# Campaign DB — optional; agent still works if campaign tables don't exist
try:
    import sys as _sys
    _sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from campaign_app.db import crud as campaign_crud
    CAMPAIGN_DB_AVAILABLE = True
except Exception as _e:
    import traceback as _tb
    CAMPAIGN_DB_ERROR = str(_e) + "\n" + _tb.format_exc()
    print(f"[WARN] campaign_app.db not available: {_e}")
    _tb.print_exc()
    CAMPAIGN_DB_AVAILABLE = False
else:
    CAMPAIGN_DB_ERROR = None


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


def _maybe_persist_plan_change(session):
    """Tras un cambio de plan exitoso, guarda el plan nuevo en la tabla 'clientes'. Silencioso ante cualquier error."""
    if not CAMPAIGN_DB_AVAILABLE:
        return
    if session.end_reason != "success":
        return
    try:
        linea = _to_linea(session.phone_number)
        campaign_crud.actualizar_plan_cliente(
            linea=linea,
            plan_nuevo=session.current_plan_name,
        )
    except Exception as e:
        logger.warning(f"actualizar_plan_cliente error: {e}")


def _maybe_update_campana_cliente(session, history: list):
    """Update CampanaCliente traceability after each turn. Silently skips on any error."""
    if not CAMPAIGN_DB_AVAILABLE:
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
