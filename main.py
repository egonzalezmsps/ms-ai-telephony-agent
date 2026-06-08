"""
main.py — Entry point FastAPI para ReniAgent con persistencia PostgreSQL.
"""

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
from typing import Optional
import os
from dotenv import load_dotenv

from app.agent.reni_agent import run_turn
from app.state.session import SessionState
from app.state.persistence import init_db, load_session, save_session, delete_session
from app.state.serializer import session_to_dict, dict_to_session
from app.prompts.campaign_template import build_campaign_message

load_dotenv()

app = FastAPI(
    title="ReniAgent — Telcel Sales Agent",
    version="2.0.0",
    description="Agente de ventas Telcel con Strands Agents + OCI + PostgreSQL",
)


@app.on_event("startup")
def startup():
    """Crea las tablas en PostgreSQL al arrancar."""
    init_db()


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
