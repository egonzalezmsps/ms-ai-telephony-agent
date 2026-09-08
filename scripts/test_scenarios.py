"""
scripts/test_scenarios.py

Escenarios de prueba automatizados para ReniAgent — usa run_turn() y
SessionState directamente (sin CLI interactiva, sin WhatsApp, sin BD).

Los escenarios 1-8 recorren el flujo normal (router semántico + LLM), así
que requieren que OCI esté funcionando. Los escenarios 9-10 (OTP) se
construyen ya en stage="CONTRACT", que se evalúa ANTES del router/LLM —
son 100% deterministas y no requieren red.

Uso:
    python scripts/test_scenarios.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.config.logging_config import setup_logging
setup_logging()

from app.router.semantic_router import load_reference_embeddings
load_reference_embeddings()

from app.agent.reni_agent import run_turn
from app.state.session import SessionState
from app.prompts.campaign_template import build_campaign_message

_CONTADOR_TELEFONO = [5000000000]


def _nuevo_perfil(nombre: str, plan: str, costo: float, modalidad: str = "Abierto", **extra) -> SessionState:
    _CONTADOR_TELEFONO[0] += 1
    kwargs = dict(
        first_name=nombre,
        full_name=f"{nombre} Prueba",
        phone_number=str(_CONTADOR_TELEFONO[0]),
        current_plan_name=plan,
        current_cost=costo,
        subscription_type=modalidad,
        has_promotion=True,
    )
    kwargs.update(extra)
    return SessionState(**kwargs)


def _iniciar_historial(session: SessionState) -> list:
    msg = build_campaign_message(session)
    print(f"  Agente:  {msg[:200]}")
    return [{"role": "assistant", "content": msg}]


def _turno(session: SessionState, history: list, mensaje: str):
    print(f"  Cliente: {mensaje}")
    respuesta, history = run_turn(session, mensaje, history)
    print(f"  Agente:  {respuesta[:200]}")
    print()
    return respuesta, history


def _aceptar_y_completar(session: SessionState, history: list):
    """Envía ACEPTO y, si el flujo pide OTP, responde T12345. Retorna history actualizado."""
    _, history = _turno(session, history, "ACEPTO")
    if session.awaiting_otp:
        _, history = _turno(session, history, "T12345")
    return history


# ── Escenarios 1-8: flujo normal (router + LLM) ─────────────────────────────

def escenario_1():
    print("\n" + "=" * 70)
    print("Escenario 1 — Flujo feliz: acepta en el primer mensaje")
    print("=" * 70)
    session = _nuevo_perfil("Ana", "Telcel Max Sin Limite 3000", 449.0)
    history = _iniciar_historial(session)
    _, history = _turno(session, history, "Sí, me interesa, actívenmelo")
    history = _aceptar_y_completar(session, history)
    exito = bool(session.contract_folio) and session.stage == "END"
    return exito, f"folio={session.contract_folio} stage={session.stage}"


def escenario_2():
    print("\n" + "=" * 70)
    print("Escenario 2 — Flujo feliz: compara y luego activa")
    print("=" * 70)
    session = _nuevo_perfil("Beto", "Telcel Plus 8", 899.0)
    history = _iniciar_historial(session)
    _, history = _turno(session, history, "¿Qué gano si cambio comparado con mi plan actual?")
    _, history = _turno(session, history, "Sí, actívalo")
    history = _aceptar_y_completar(session, history)
    exito = bool(session.contract_folio) and session.stage == "END"
    return exito, f"folio={session.contract_folio} stage={session.stage}"


def escenario_3():
    print("\n" + "=" * 70)
    print("Escenario 3 — Objeción de precio → manejo → activa")
    print("=" * 70)
    session = _nuevo_perfil("Carla", "Telcel Max Sin Limite 6000", 699.0)
    history = _iniciar_historial(session)
    _, history = _turno(session, history, "No, está muy caro, no creo que me convenga")
    _, history = _turno(session, history, "Bueno, va, sí acepto, actívalo")
    history = _aceptar_y_completar(session, history)
    exito = bool(session.contract_folio) and session.stage == "END"
    return exito, f"folio={session.contract_folio} stage={session.stage} rejection_count={session.rejection_count}"


def escenario_4():
    print("\n" + "=" * 70)
    print("Escenario 4 — Múltiples preguntas informativas")
    print("=" * 70)
    session = _nuevo_perfil("Diego", "Telcel Max Sin Limite 5000", 499.0)
    history = _iniciar_historial(session)
    preguntas = [
        "¿cuánto es el cashback?",
        "¿qué apps incluye?",
        "¿qué es Claro Drive?",
        "¿cuánto dura la promoción?",
    ]
    respuestas = []
    for p in preguntas:
        r, history = _turno(session, history, p)
        respuestas.append(r)
    exito = all(r.strip() for r in respuestas)
    return exito, f"{len(respuestas)} respuestas, todas no vacías={exito}"


def escenario_5():
    print("\n" + "=" * 70)
    print("Escenario 5 — Mensajes cortos ambiguos")
    print("=" * 70)
    session = _nuevo_perfil("Elena", "Telcel Max Sin Limite 6500", 599.0)
    history = _iniciar_historial(session)
    respuestas = []
    for m in ["si", "no", "ok", "2", "4"]:
        r, history = _turno(session, history, m)
        respuestas.append(r)
    exito = all(r.strip() for r in respuestas)
    return exito, f"{len(respuestas)} respuestas, todas no vacías={exito}"


def escenario_6():
    print("\n" + "=" * 70)
    print("Escenario 6 — Errores ortográficos")
    print("=" * 70)
    session = _nuevo_perfil("Fernando", "Telcel Plus 2", 349.0)
    history = _iniciar_historial(session)
    respuestas = []
    for m in ["kiero el plan", "cuanto cuesat"]:
        r, history = _turno(session, history, m)
        respuestas.append(r)
    exito = all(r.strip() for r in respuestas)
    return exito, f"{len(respuestas)} respuestas, todas no vacías={exito}"


def escenario_7():
    print("\n" + "=" * 70)
    print("Escenario 7 — Preguntas fuera de tema")
    print("=" * 70)
    session = _nuevo_perfil("Gaby", "Telcel Max Sin Limite 7000", 799.0)
    history = _iniciar_historial(session)
    respuestas = []
    for m in ["¿incluye Amazon Prime?", "¿me dan un celular nuevo?", "¿cuál es mi correo registrado?"]:
        r, history = _turno(session, history, m)
        respuestas.append(r)
    exito = all(r.strip() for r in respuestas)
    return exito, f"{len(respuestas)} respuestas, todas no vacías={exito} (revisar manualmente que no ofrezca lo que no aplica)"


def escenario_8():
    print("\n" + "=" * 70)
    print("Escenario 8 — Cliente cambia de opinión varias veces")
    print("=" * 70)
    session = _nuevo_perfil("Hugo", "Telcel Max Sin Limite 9000", 999.0)
    history = _iniciar_historial(session)
    _, history = _turno(session, history, "no me interesa")
    _, history = _turno(session, history, "espera, mejor sí, cuéntame más")
    _, history = _turno(session, history, "no, mejor no")
    _, history = _turno(session, history, "bueno ya, sí acepto, actívalo")
    history = _aceptar_y_completar(session, history)
    exito = bool(session.contract_folio) and session.stage == "END"
    return exito, f"folio={session.contract_folio} stage={session.stage} rejection_count={session.rejection_count}"


# ── Escenarios 9-10: OTP determinista (sin LLM) ─────────────────────────────

def _falla_otp_simulada():
    """TelcelAPIError con el código de negocio que _is_otp_invalid() reconoce como OTP incorrecto."""
    import app.contract.contract_flow as contract_flow
    return contract_flow.TelcelAPIError(
        400, {"detailResponse": {"code": "BE_MP_BPS_0040"}}, "OTP inválido (simulado)"
    )


def escenario_9():
    print("\n" + "=" * 70)
    print("Escenario 9 — OTP fallido 2 veces, luego correcto")
    print("=" * 70)
    print("(TELCEL_CREATE_PRODUCT_ORDER_MOCK=true siempre simula éxito, así que")
    print(" se monkeypatchea call_create_product_order para forzar 2 fallas primero)")
    session = _nuevo_perfil(
        "Irene", "Telcel Max Sin Limite 3000", 449.0,
        stage="CONTRACT", awaiting_otp=True, otp_sent=True,
        plan_selected="Telcel Libre 5", process_id_api="MOCK-PROC-9",
    )
    history = [{"role": "assistant", "content": "Le hemos enviado un código de verificación."}]

    import app.contract.contract_flow as contract_flow
    original = contract_flow.call_create_product_order
    intentos = {"n": 0}

    def fake(id_plan, process_id):
        intentos["n"] += 1
        if intentos["n"] <= 2:
            raise _falla_otp_simulada()
        return original(id_plan, process_id)

    contract_flow.call_create_product_order = fake
    try:
        _, history = _turno(session, history, "111111")
        _, history = _turno(session, history, "222222")
        _, history = _turno(session, history, "T12345")
    finally:
        contract_flow.call_create_product_order = original

    exito = bool(session.contract_folio) and session.stage == "END" and session.otp_attempt_count == 2
    return exito, f"folio={session.contract_folio} stage={session.stage} intentos={session.otp_attempt_count}"


def escenario_10():
    print("\n" + "=" * 70)
    print("Escenario 10 — OTP fallido 3 veces → bloqueo")
    print("=" * 70)
    session = _nuevo_perfil(
        "Javier", "Telcel Max Sin Limite 3000", 449.0,
        stage="CONTRACT", awaiting_otp=True, otp_sent=True,
        plan_selected="Telcel Libre 5", process_id_api="MOCK-PROC-10",
    )
    history = [{"role": "assistant", "content": "Le hemos enviado un código de verificación."}]

    import app.contract.contract_flow as contract_flow
    original = contract_flow.call_create_product_order

    def fake(id_plan, process_id):
        raise _falla_otp_simulada()

    contract_flow.call_create_product_order = fake
    try:
        _, history = _turno(session, history, "111111")
        _, history = _turno(session, history, "222222")
        respuesta, history = _turno(session, history, "333333")
    finally:
        contract_flow.call_create_product_order = original

    exito = (
        session.authentication_locked is True
        and session.contract_folio is None
        and ("superado" in respuesta.lower() or "soporte" in respuesta.lower())
    )
    return exito, f"bloqueado={session.authentication_locked} folio={session.contract_folio}"


ESCENARIOS = [
    ("1. Flujo feliz — acepta en el primer mensaje", escenario_1),
    ("2. Flujo feliz — compara y luego activa", escenario_2),
    ("3. Objeción de precio → manejo → activa", escenario_3),
    ("4. Múltiples preguntas informativas", escenario_4),
    ("5. Mensajes cortos ambiguos", escenario_5),
    ("6. Errores ortográficos", escenario_6),
    ("7. Preguntas fuera de tema", escenario_7),
    ("8. Cliente cambia de opinión varias veces", escenario_8),
    ("9. OTP fallido 2 veces luego correcto", escenario_9),
    ("10. OTP fallido 3 veces → bloqueo", escenario_10),
]


def main():
    resultados = []
    for nombre, fn in ESCENARIOS:
        try:
            exito, detalle = fn()
        except Exception as e:
            exito, detalle = False, f"EXCEPCIÓN: {e}"
        resultados.append((nombre, exito, detalle))

    print("\n" + "=" * 70)
    print("RESUMEN")
    print("=" * 70)
    for nombre, exito, detalle in resultados:
        icono = "✅" if exito else "❌"
        print(f"{icono} {nombre}")
        print(f"    {detalle}")

    total = len(resultados)
    exitosos = sum(1 for _, exito, _ in resultados if exito)
    print(f"\n{exitosos}/{total} escenarios exitosos")


if __name__ == "__main__":
    main()
