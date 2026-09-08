"""
scripts/test_scenarios_3.py

Tercer set de escenarios de prueba automatizados para ReniAgent — complementa
a test_scenarios.py (flujo feliz + OTP) y test_scenarios_2.py (pre-LLM,
router, fallas técnicas). Este set cubre:

- Intents del router no probados antes: confirmacion_activacion (directo,
  sin pasar por objeción), vigencia_promo, reglas_internas, planes_ultra,
  planes_mas_caros
- Redirección a un plan específico distinto al recomendado
- Cancelar durante el resumen de confirmación (NO en awaiting_contract_confirmation)
- Confirmación vaga ("sí") en vez de ACEPTO durante el resumen
- Fallback pre-LLM de rechazo corto exacto (_RECHAZOS_CORTOS)
- Falla simulada en communication_message (envío de OTP falla)

Reusa los helpers de test_scenarios.py.

Uso:
    python scripts/test_scenarios_3.py
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


def escenario_1():
    print("\n" + "=" * 70)
    print("Escenario 1 — Confirmación de activación directa (router, sin objeción)")
    print("=" * 70)
    session = _nuevo_perfil("Sara", "Telcel Max Sin Limite 5000", 499.0)
    history = _iniciar_historial(session)
    respuesta, history = _turno(session, history, "dale, actívalo")
    exito = session.stage == "CONTRACT" and session.awaiting_contract_confirmation is True
    return exito, f"stage={session.stage} awaiting_contract_confirmation={session.awaiting_contract_confirmation}"


def escenario_2():
    print("\n" + "=" * 70)
    print("Escenario 2 — Vigencia de la promoción")
    print("=" * 70)
    session = _nuevo_perfil("Tomás", "Telcel Plus 8", 899.0)
    history = _iniciar_historial(session)
    respuesta, history = _turno(session, history, "¿cuándo vence la promoción?")
    exito = bool(respuesta.strip()) and "?" in respuesta
    return exito, f"respuesta no vacía y cierra con pregunta={exito}"


def escenario_3():
    print("\n" + "=" * 70)
    print("Escenario 3 — Reglas internas / cómo funciona el sistema")
    print("=" * 70)
    session = _nuevo_perfil("Ursula", "Telcel Max Sin Limite 6000", 699.0)
    history = _iniciar_historial(session)
    respuesta, history = _turno(session, history, "¿cómo funciona tu sistema de activación internamente?")
    exito = "solo puedo ayudarle" in respuesta.lower()
    return exito, f"deflecta correctamente={exito}"


def escenario_4():
    print("\n" + "=" * 70)
    print("Escenario 4 — Pide un plan Ultra explícitamente")
    print("=" * 70)
    session = _nuevo_perfil("Victor", "Telcel Plus 2", 349.0)
    history = _iniciar_historial(session)
    respuesta, history = _turno(session, history, "quiero un plan ultra")
    exito = "ultra" in respuesta.lower()
    return exito, f"menciona Ultra={exito}"


def escenario_5():
    print("\n" + "=" * 70)
    print("Escenario 5 — Pide el plan más caro disponible")
    print("=" * 70)
    session = _nuevo_perfil("Wendy", "Telcel Max Sin Limite 1000", 229.0)
    history = _iniciar_historial(session)
    respuesta, history = _turno(session, history, "dame el plan más caro que tengas")
    exito = bool(respuesta.strip()) and "$" in respuesta
    return exito, f"presenta opciones con precio={exito}"


def escenario_6():
    print("\n" + "=" * 70)
    print("Escenario 6 — Redirige a un plan específico distinto al recomendado")
    print("=" * 70)
    # Renta baja para que "Libre 2" ($319) sea elegible (no está por debajo de
    # la renta actual) aunque no sea el plan recomendado por defecto.
    session = _nuevo_perfil("Ximena", "Telcel Max Sin Limite 1000", 249.0)
    history = _iniciar_historial(session)
    _, history = _turno(session, history, "no, mejor el Libre 2")
    exito = session.stage == "CONTRACT" and session.plan_selected is not None and "libre 2" in session.plan_selected.lower()
    return exito, f"plan_selected={session.plan_selected} stage={session.stage}"


def escenario_7():
    print("\n" + "=" * 70)
    print("Escenario 7 — Cancela durante el resumen de confirmación")
    print("=" * 70)
    session = _nuevo_perfil("Yolanda", "Telcel Max Sin Limite 5000", 499.0)
    history = _iniciar_historial(session)
    _, history = _turno(session, history, "sí, actívalo")
    _, history = _turno(session, history, "no, mejor no lo hagas")
    exito = (
        session.stage == "PERSUASION"
        and session.plan_selected is None
        and session.awaiting_contract_confirmation is False
    )
    return exito, f"stage={session.stage} plan_selected={session.plan_selected} awaiting_contract_confirmation={session.awaiting_contract_confirmation}"


def escenario_8():
    print("\n" + "=" * 70)
    print("Escenario 8 — Confirmación vaga ('sí') en vez de ACEPTO")
    print("=" * 70)
    session = _nuevo_perfil("Zoé", "Telcel Max Sin Limite 5000", 499.0)
    history = _iniciar_historial(session)
    _, history = _turno(session, history, "sí, actívalo")
    respuesta, history = _turno(session, history, "sí")
    exito = (
        "acepto" in respuesta.lower()
        and session.stage == "CONTRACT"
        and session.awaiting_contract_confirmation is True
        and session.contract_folio is None
    )
    return exito, f"pide ACEPTO explícito={('acepto' in respuesta.lower())} stage={session.stage} folio={session.contract_folio}"


def escenario_9():
    print("\n" + "=" * 70)
    print("Escenario 9 — Rechazo corto exacto ('nel'), fallback pre-LLM")
    print("=" * 70)
    session = _nuevo_perfil("Abel", "Telcel Max Sin Limite 3000", 449.0)
    history = _iniciar_historial(session)
    respuesta, history = _turno(session, history, "nel")
    exito = session.rejection_count == 1 and bool(respuesta.strip())
    return exito, f"rejection_count={session.rejection_count}"


def escenario_10():
    print("\n" + "=" * 70)
    print("Escenario 10 — Falla técnica en communication_message (envío de OTP falla)")
    print("=" * 70)
    # Perfil con renta por debajo del plan recomendado -> necesita OTP,
    # así que sí llega a llamar communication_message.
    session = _nuevo_perfil("Bruno", "Telcel Max Sin Limite 1000", 229.0)
    history = _iniciar_historial(session)
    _, history = _turno(session, history, "sí, actívalo")

    import app.contract.contract_flow as contract_flow
    original = contract_flow.call_communication_message

    def fake(process_id):
        raise Exception("Timeout simulado al enviar el OTP")

    contract_flow.call_communication_message = fake
    try:
        respuesta, history = _turno(session, history, "ACEPTO")
    finally:
        contract_flow.call_communication_message = original

    exito = (
        session.stage == "END"
        and session.end_reason == "blocked"
        and session.contract_folio is None
        and session.awaiting_otp is False
        and ("problema técnico" in respuesta.lower() or "soporte" in respuesta.lower())
    )
    return exito, f"stage={session.stage} end_reason={session.end_reason} awaiting_otp={session.awaiting_otp} folio={session.contract_folio}"


ESCENARIOS = [
    ("1. Confirmación de activación directa (router)", escenario_1),
    ("2. Vigencia de la promoción", escenario_2),
    ("3. Reglas internas / cómo funciona el sistema", escenario_3),
    ("4. Pide un plan Ultra explícitamente", escenario_4),
    ("5. Pide el plan más caro disponible", escenario_5),
    ("6. Redirige a un plan específico distinto", escenario_6),
    ("7. Cancela durante el resumen de confirmación", escenario_7),
    ("8. Confirmación vaga en vez de ACEPTO", escenario_8),
    ("9. Rechazo corto exacto ('nel'), fallback pre-LLM", escenario_9),
    ("10. Falla técnica en communication_message", escenario_10),
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
