"""
agent/reni_agent.py

ReniAgent con persistencia de historial de conversación.
El agente recuerda todos los turnos anteriores de la sesión.
"""

import logging
import re
import warnings
from typing import List, Dict, Tuple

from strands import Agent

from app.config.oci_model import oci_model
from app.prompts.system_prompt import build_system_prompt
from app.tools.telcel_tools import make_tools
from app.state.session import SessionState
from app.contract.contract_flow import handle_contract_turn
from app.contract.post_sale import build_post_sale_message

# Silencia los WARNING internos de Strands (ej. "overriding stop reason due to toolUse").
# El mensaje viene de strands.event_loop.streaming como logger.warning() y no debe
# llegar al cliente. Mantenemos ERROR y CRITICAL para fallos reales.
logging.getLogger("strands").setLevel(logging.ERROR)


def clean_response(text: str) -> str:
    """
    Safety net: si la respuesta tiene más de una pregunta, elimina todas
    excepto la última (que siempre debe ser la de activación).

    Ejemplo:
      ANTES: "¿Le gustaría comparar?\\n¿Le gustaría activar el Telcel Libre 3?"
      DESPUÉS: "¿Le gustaría activar el Telcel Libre 3?"
    """
    if text.count("?") <= 1:
        return text

    # Buscar el inicio de la última pregunta (último "¿")
    last_q_open = text.rfind("¿")
    if last_q_open == -1:
        return text

    before = text[:last_q_open].rstrip()
    last_q = text[last_q_open:].strip()

    # Si el texto anterior también contiene preguntas, filtrar esas líneas
    if "?" in before:
        lines = re.split(r"\n+", before)
        before = "\n".join(l for l in lines if "?" not in l).rstrip()

    return (before + "\n\n" + last_q).strip() if before else last_q


def create_agent(session: SessionState, messages: List[Dict] = None) -> Agent:
    """Crea el agente con system prompt, herramientas e historial inicial."""
    return Agent(
        model=oci_model,
        system_prompt=build_system_prompt(session),
        tools=make_tools(session),
        callback_handler=None,
        messages=messages or [],
    )


def run_turn(
    session: SessionState,
    user_message: str,
    history: List[Dict] = None,
) -> Tuple[str, List[Dict]]:
    """
    Ejecuta un turno de conversación con historial persistente.

    Args:
        session:      Estado actual de la sesión.
        user_message: Mensaje del cliente en este turno.
        history:      Historial simple [{role, content}] de turnos anteriores.

    Returns:
        Tupla (respuesta_texto, historial_actualizado)
    """
    history = history or []

    # ── Flujo de contratación determinístico (sin LLM) ────────────────────────
    if session.stage == "CONTRACT":
        contract_msg = handle_contract_turn(session, user_message)

        if contract_msg is not None:
            # Respuesta determinística — enviar directamente
            updated_history = history + [
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": contract_msg},
            ]
            return contract_msg, updated_history

        if session.stage == "POST_SALE":
            # OTP validado — generar mensaje de confirmación
            post_sale_text = build_post_sale_message(session)
            session.stage = "END"
            updated_history = history + [
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": post_sale_text},
            ]
            return post_sale_text, updated_history

        if session.stage == "PERSUASION":
            # Cliente canceló — caer al flujo LLM normal abajo
            pass
        # else: pregunta durante espera → continúa al LLM con contexto de contrato

    # ── Flujo conversacional con LLM ─────────────────────────────────────────

    # Convertir historial simple al formato Strands / Bedrock Converse API.
    # El formato correcto de un content block de texto es {"text": "..."} —
    # NO {"type": "text", "text": "..."}.
    prior_messages = [
        {"role": msg["role"], "content": [{"text": msg["content"]}]}
        for msg in history
    ]

    # El historial va en el constructor, no como kwarg de agent().
    # Pasar messages= a agent() lo mete en **kwargs (deprecado) y no
    # tiene efecto en la memoria de la conversación.
    agent = create_agent(session, messages=prior_messages)

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=UserWarning, module="strands")
        response = agent(user_message)

    response_text = ""
    if hasattr(response, "message") and response.message:
        for block in response.message.get("content", []):
            if isinstance(block, dict) and "text" in block:
                response_text += block.get("text", "")
    response_text = response_text.strip()

    # ── Fallback: respuesta vacía o solo caracteres especiales ("()") ─────────
    if not response_text or response_text.strip("() \n") == "":
        if "iniciar_contratacion" in str(agent.messages):
            if session.plan_selected and session.stage == "CONTRACT":
                contract_msg = handle_contract_turn(session, user_message)
                if contract_msg:
                    response_text = contract_msg
        if not response_text or response_text.strip("() \n") == "":
            response_text = "Disculpe, ¿podría repetir su mensaje?"

    # ── Interceptar iniciar_contratacion — Opción A ───────────────────────────
    # Si el LLM invocó iniciar_contratacion, ignorar su respuesta y devolver
    # el template determinístico de contratación directamente.
    _tools_invoked = [
        block["toolUse"]["name"]
        for msg in agent.messages
        for block in msg.get("content", [])
        if isinstance(block, dict) and "toolUse" in block
    ]
    if "iniciar_contratacion" in _tools_invoked and session.stage == "CONTRACT":
        contract_msg = handle_contract_turn(session, user_message)
        if contract_msg:
            response_text = contract_msg

    # Llama 4 Maverick a veces escribe herramientas como texto literal:
    # "[tool_name]" o "tool_name(param='valor')" en lugar de invocarlas.
    # Si se detecta ese patrón, se reintenta una vez con un agente fresco.
    _TOOL_PATTERN = re.compile(r'(\[[a-z_]+\]|[a-z_]+\([^)]*\))', re.IGNORECASE)
    if _TOOL_PATTERN.search(response_text):
        agent_retry = create_agent(session, messages=prior_messages)
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=UserWarning, module="strands")
            response2 = agent_retry(user_message)
        retry_text = ""
        if hasattr(response2, "message") and response2.message:
            for block in response2.message.get("content", []):
                if isinstance(block, dict) and "text" in block:
                    retry_text += block.get("text", "")
        retry_text = _TOOL_PATTERN.sub('', retry_text).strip()
        if retry_text:
            response_text = retry_text
        else:
            response_text = "Por favor, ¿podría repetir su pregunta?"

    response_text = clean_response(response_text)

    updated_history = history + [
        {"role": "user", "content": user_message},
        {"role": "assistant", "content": response_text},
    ]

    # Limitar a los últimos 20 mensajes (10 intercambios)
    if len(updated_history) > 20:
        updated_history = updated_history[-20:]

    return response_text, updated_history
