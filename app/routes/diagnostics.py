"""
routes/diagnostics.py

Endpoints de diagnóstico/debug (no aparecen en el schema público): descarga
de logs y pruebas de límites de contexto del modelo OCI.
"""

import os
from typing import Optional, Union

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.config.logging_config import LOGS_DIR
from app.state.session import SessionState
from app.routes.deps import require_api_key

router = APIRouter()


@router.get("/logs", include_in_schema=False)
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


@router.get("/test/limits", include_in_schema=False, dependencies=[Depends(require_api_key)])
def test_context_limits():
    """
    Prueba el límite de contexto del modelo OCI con inputs de tamaño creciente.
    Réplica de scripts/test_context_limit.py expuesta como endpoint.
    """
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


@router.get("/test/limits/conversation", include_in_schema=False, dependencies=[Depends(require_api_key)])
def test_context_limits_conversation():
    """
    Prueba el límite de contexto con una conversación de ventas realista de tamaño
    creciente (system prompt real + herramientas reales), a diferencia de /test/limits
    que usa texto de relleno sintético.
    """
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
