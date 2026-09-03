"""
routes/chat.py

Endpoint principal de conversación (/chat) y borrado de sesión (/session).
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.agent.reni_agent import run_turn
from app.state.session import SessionState
from app.state.persistence import load_session, save_session, delete_session
from app.state.serializer import session_to_dict, dict_to_session
from app.prompts.campaign_template import build_campaign_message
from app.state.campaign_traceability import _maybe_update_campana_cliente
from app.routes.deps import require_api_key

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_api_key)])


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


class SessionDeleteRequest(BaseModel):
    phone_number: str


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
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


@router.delete("/session")
def delete(request: SessionDeleteRequest):
    """Elimina la sesión de un cliente (para pruebas o reset)."""
    delete_session(request.phone_number)
    return {"deleted": request.phone_number}
