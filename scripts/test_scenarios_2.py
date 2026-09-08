"""
scripts/test_scenarios_2.py

Segundo set de escenarios de prueba automatizados para ReniAgent — complementa
a scripts/test_scenarios.py (flujo feliz + OTP). Este set cubre:

- Detecciones pre-LLM deterministas (titular, nombre incorrecto)
- Intents del router semántico no cubiertos en el primer set (facturación,
  por qué CAC, modalidad distinta)
- Rechazo hasta el cierre definitivo (3 objeciones, sin conversión)
- info_plan_actual, otra_recomendacion
- Fallas técnicas simuladas en las APIs de Telcel (create_process caída)
- Comparación aislada: mismo precio (sin OTP) vs. precio distinto (con OTP)

Reusa los helpers de test_scenarios.py para no duplicar código.

Uso:
    python scripts/test_scenarios_2.py
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

from scripts.test_scenarios import _nuevo_perfil, _iniciar_historial, _turno


# ── 1-2: Detecciones pre-LLM deterministas ──────────────────────────────────

def escenario_1():
    print("\n" + "=" * 70)
    print("Escenario 1 — Cliente no es el titular")
    print("=" * 70)
    # is_titular/nombre_incorrecto no son flags persistentes: la detección la
    # dispara _detect_titular_issues() analizando el TEXTO del mensaje en ese
    # turno (regex + keywords) — no basta con pre-construir la sesión con el
    # campo ya en False, hay que mandar el mensaje que lo detona de verdad.
    session = _nuevo_perfil("Karla", "Telcel Max Sin Limite 3000", 449.0)
    history = _iniciar_historial(session)
    respuesta, history = _turno(session, history, "no soy el titular, soy su esposa")
    exito = "titular" in respuesta.lower() and session.is_titular is False
    return exito, f"is_titular={session.is_titular} contiene 'titular'={'titular' in respuesta.lower()}"


def escenario_2():
    print("\n" + "=" * 70)
    print("Escenario 2 — Nombre incorrecto en la cuenta")
    print("=" * 70)
    session = _nuevo_perfil("Karla", "Telcel Max Sin Limite 3000", 449.0)
    history = _iniciar_historial(session)
    respuesta, history = _turno(session, history, "mi nombre es Roberto, no Karla")
    exito = (
        ("cac" in respuesta.lower() or "centro de atención" in respuesta.lower())
        and session.nombre_incorrecto is True
    )
    return exito, f"nombre_incorrecto={session.nombre_incorrecto} deriva a CAC={exito}"


# ── 3: Rechazo hasta el cierre definitivo ───────────────────────────────────

def escenario_3():
    print("\n" + "=" * 70)
    print("Escenario 3 — Rechazo definitivo tras 3 objeciones (sin conversión)")
    print("=" * 70)
    session = _nuevo_perfil("Lorena", "Telcel Max Sin Limite 5000", 499.0)
    history = _iniciar_historial(session)
    respuesta = ""
    for msg in ["no me interesa", "no gracias, de verdad no quiero", "ya dije que no, gracias, no insistas"]:
        respuesta, history = _turno(session, history, msg)
    exito = session.rejection_count >= 2 and "cac" in respuesta.lower()
    return exito, f"rejection_count={session.rejection_count} folio={session.contract_folio}"


# ── 4-7: Intents del router / tools no cubiertos antes ──────────────────────

def escenario_4():
    print("\n" + "=" * 70)
    print("Escenario 4 — Pregunta de facturación/cobros")
    print("=" * 70)
    session = _nuevo_perfil("Miguel", "Telcel Plus 8", 899.0)
    history = _iniciar_historial(session)
    respuesta, history = _turno(session, history, "¿cuándo empieza el cobro del nuevo plan?")
    exito = bool(respuesta.strip()) and ("soporte" in respuesta.lower() or "mi telcel" in respuesta.lower())
    return exito, f"deriva a Soporte/Mi Telcel={exito}"


def escenario_5():
    print("\n" + "=" * 70)
    print("Escenario 5 — Por qué debe ir al CAC")
    print("=" * 70)
    session = _nuevo_perfil("Nadia", "Telcel Max Sin Limite 6000", 699.0)
    history = _iniciar_historial(session)
    respuesta, history = _turno(session, history, "¿por qué no puedes activarlo tú mismo? ¿por qué tengo que ir al CAC?")
    exito = bool(respuesta.strip())
    return exito, f"respuesta no vacía={exito}"


def escenario_6():
    print("\n" + "=" * 70)
    print("Escenario 6 — Solicita modalidad distinta (Controlado siendo Abierto)")
    print("=" * 70)
    session = _nuevo_perfil("Oscar", "Telcel Max Sin Limite 5000", 499.0, modalidad="Abierto")
    history = _iniciar_historial(session)
    respuesta, history = _turno(session, history, "¿tienes planes en modalidad controlada?")
    exito = "cac" in respuesta.lower() or "centro de atención" in respuesta.lower()
    return exito, f"deriva a CAC por modalidad={exito}"


def escenario_7():
    print("\n" + "=" * 70)
    print("Escenario 7 — Pregunta cuál es su plan actual")
    print("=" * 70)
    session = _nuevo_perfil("Paty", "Telcel Max Sin Limite 6500", 699.0)
    history = _iniciar_historial(session)
    respuesta, history = _turno(session, history, "¿cuál es mi plan actual y cuánto pago?")
    exito = "699" in respuesta or session.current_plan_name.split()[0].lower() in respuesta.lower()
    return exito, f"menciona plan/renta actual={exito}"


def escenario_8():
    print("\n" + "=" * 70)
    print("Escenario 8 — Otra recomendación con criterio (más GB)")
    print("=" * 70)
    session = _nuevo_perfil("Quique", "Telcel Max Sin Limite 3000", 449.0)
    history = _iniciar_historial(session)
    r1, history = _turno(session, history, "muéstrame otra opción")
    r2, history = _turno(session, history, "quiero uno con más GB")
    exito = bool(r1.strip()) and bool(r2.strip())
    return exito, f"ambas respuestas no vacías={exito}"


# ── 9: Falla técnica simulada en las APIs de Telcel ─────────────────────────

def escenario_9():
    print("\n" + "=" * 70)
    print("Escenario 9 — Falla técnica en create_process (API Telcel caída)")
    print("=" * 70)
    session = _nuevo_perfil("Rosa", "Telcel Max Sin Limite 5000", 499.0)
    history = _iniciar_historial(session)
    _, history = _turno(session, history, "sí, actívalo")

    import app.contract.contract_flow as contract_flow
    original = contract_flow.call_create_process

    def fake(msisdn):
        raise Exception("Timeout simulado de la API Telcel")

    contract_flow.call_create_process = fake
    try:
        respuesta, history = _turno(session, history, "ACEPTO")
    finally:
        contract_flow.call_create_process = original

    exito = (
        session.stage == "END"
        and session.end_reason == "blocked"
        and session.contract_folio is None
        and ("problema técnico" in respuesta.lower() or "soporte" in respuesta.lower())
    )
    return exito, f"stage={session.stage} end_reason={session.end_reason} folio={session.contract_folio}"


# ── 10: Mismo precio (sin OTP) vs. precio distinto (con OTP), aislado ───────

def escenario_10():
    print("\n" + "=" * 70)
    print("Escenario 10 — Mismo precio (sin OTP) vs. precio distinto (con OTP)")
    print("=" * 70)

    print("\n-- Cliente A: renta ya al precio del plan recomendado --")
    session_a = _nuevo_perfil("Omar", "Telcel Libre 5", 599.0)
    history_a = _iniciar_historial(session_a)
    _, history_a = _turno(session_a, history_a, "sí, actívalo")
    _, history_a = _turno(session_a, history_a, "ACEPTO")
    sin_otp_ok = bool(session_a.contract_folio) and session_a.awaiting_otp is False and session_a.stage == "END"

    print("\n-- Cliente B: renta por debajo del plan recomendado --")
    session_b = _nuevo_perfil("Paola", "Telcel Max Sin Limite 1000", 229.0)
    history_b = _iniciar_historial(session_b)
    _, history_b = _turno(session_b, history_b, "sí, actívalo")
    _, history_b = _turno(session_b, history_b, "ACEPTO")
    pidio_otp = session_b.awaiting_otp is True and session_b.contract_folio is None
    con_otp_ok = pidio_otp
    if pidio_otp:
        _, history_b = _turno(session_b, history_b, "T12345")
        con_otp_ok = bool(session_b.contract_folio) and session_b.stage == "END"

    exito = sin_otp_ok and con_otp_ok
    return exito, f"sin_otp_ok={sin_otp_ok} (folio A={session_a.contract_folio}) con_otp_ok={con_otp_ok} (folio B={session_b.contract_folio})"


ESCENARIOS = [
    ("1. Cliente no es el titular", escenario_1),
    ("2. Nombre incorrecto en la cuenta", escenario_2),
    ("3. Rechazo definitivo tras 3 objeciones", escenario_3),
    ("4. Pregunta de facturación/cobros", escenario_4),
    ("5. Por qué debe ir al CAC", escenario_5),
    ("6. Solicita modalidad distinta", escenario_6),
    ("7. Pregunta cuál es su plan actual", escenario_7),
    ("8. Otra recomendación con criterio", escenario_8),
    ("9. Falla técnica en create_process", escenario_9),
    ("10. Mismo precio vs. precio distinto (aislado)", escenario_10),
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
