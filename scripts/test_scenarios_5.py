"""
scripts/test_scenarios_5.py

Quinto set — cobertura amplia de variantes de "se me hace caro el plan" y
frases similares, confirmando el arreglo del router (semantic_router.py) y
el nuevo comportamiento de manejar_objecion (resaltar beneficios concretos
cuando hay incremento de renta).

Parte A: barrido directo sobre classify() con ~15 variantes de objeción de
precio (formales, coloquiales, con doble negación, etc.) contra TODAS las
intenciones — no solo planes_mas_baratos/facturacion/info_plan_actual que
ya sabíamos que colisionaban.

Parte B: escenarios conversacionales completos (run_turn, LLM real) para
variantes representativas, más una prueba directa de manejar_objecion() en
la segunda objeción (rejection_count==1), que no se había probado antes.

Uso:
    python scripts/test_scenarios_5.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.config.logging_config import setup_logging
setup_logging()

from app.router.semantic_router import load_reference_embeddings, classify
load_reference_embeddings()

from scripts.test_scenarios import _nuevo_perfil, _iniciar_historial, _turno
from app.state.session import SessionState
from app.tools.telcel_tools import make_tools


# ── Parte A: barrido amplio de variantes de objeción de precio ─────────────

FRASES_OBJECION_PRECIO = [
    "se me hace caro el plan",
    "no me alcanza para pagar eso",
    "cuesta mucho ese plan",
    "está bien caro para lo que ofrece",
    "es demasiado dinero para mí",
    "no tengo ese dinero disponible",
    "se me complica pagar esa renta",
    "está fuera de mi presupuesto",
    "no puedo pagar tanto cada mes",
    "qué caro, no lo creo",
    "mmm está caro",
    "ese precio no me late",
    "no manches qué caro",
    "uf, sale muy caro",
    "no, la neta está caro",
]


def parte_a_barrido_amplio():
    print("\n" + "=" * 70)
    print("PARTE A — Barrido amplio de variantes de objeción de precio")
    print("=" * 70)
    resultados = []
    for frase in FRASES_OBJECION_PRECIO:
        intent = classify(frase)
        ok = intent is None
        resultados.append(ok)
        print(f"  {'OK ' if ok else 'MAL'} {frase!r:45} -> {intent}")

    exito = all(resultados)
    return exito, f"{sum(resultados)}/{len(resultados)} correctas (todas deben ser None)"


# ── Parte B: escenarios conversacionales + prueba directa de la tool ────────

def escenario_1():
    print("\n" + "=" * 70)
    print("Escenario 1 — 'no me alcanza para pagar eso' (con incremento de renta)")
    print("=" * 70)
    session = _nuevo_perfil("Gina", "Telcel Max Sin Limite 1000", 229.0)
    history = _iniciar_historial(session)
    respuesta, history = _turno(session, history, "no me alcanza para pagar eso")
    exito = (
        session.rejection_count >= 1
        and "opciones más económicas" not in respuesta.lower()
        and "?" in respuesta
    )
    return exito, f"rejection_count={session.rejection_count} respuesta='{respuesta[:100]}...'"


def escenario_2():
    print("\n" + "=" * 70)
    print("Escenario 2 — 'está fuera de mi presupuesto'")
    print("=" * 70)
    session = _nuevo_perfil("Hector", "Telcel Plus 2", 349.0)
    history = _iniciar_historial(session)
    respuesta, history = _turno(session, history, "está fuera de mi presupuesto")
    exito = session.rejection_count >= 1 and bool(respuesta.strip())
    return exito, f"rejection_count={session.rejection_count} respuesta='{respuesta[:100]}...'"


def escenario_3():
    print("\n" + "=" * 70)
    print("Escenario 3 — Objeción coloquial ('ese precio no me late')")
    print("=" * 70)
    session = _nuevo_perfil("Irma", "Telcel Max Sin Limite 6000", 699.0)
    history = _iniciar_historial(session)
    respuesta, history = _turno(session, history, "ese precio no me late")
    exito = session.rejection_count >= 1 and bool(respuesta.strip())
    return exito, f"rejection_count={session.rejection_count} respuesta='{respuesta[:100]}...'"


def escenario_4():
    print("\n" + "=" * 70)
    print("Escenario 4 — Verificación directa de manejar_objecion(motivo='precio')")
    print("Plan Ultra (sin cashback) -> solo debe resaltar GB, sin mencionar cashback")
    print("=" * 70)
    # current_cost por debajo del precio del plan Ultra 3 ($349) para forzar
    # la rama "con incremento" (Ultra no tiene cashback -> solo debe salir GB).
    session = SessionState(
        first_name="Julio", phone_number="999", current_plan_name="Telcel Plus 1",
        current_cost=249.0, subscription_type="Abierto", plan_anclado="Telcel Ultra 3 Abierto",
    )
    tools = make_tools(session)
    manejar = next(t for t in tools if t.tool_name == "manejar_objecion")
    respuesta = manejar(motivo="precio")
    exito = "gb" in respuesta.lower() and "cashback" not in respuesta.lower() and "?" in respuesta
    return exito, f"respuesta='{respuesta[len('RESPONDE EXACTAMENTE CON ESTE TEXTO SIN MODIFICAR NADA:'):].strip()[:150]}...'"


def escenario_5():
    print("\n" + "=" * 70)
    print("Escenario 5 — Verificación directa en la SEGUNDA objeción (rejection_count==1)")
    print("=" * 70)
    session = SessionState(
        first_name="Karen", phone_number="998", current_plan_name="Telcel Max Sin Limite 1000",
        current_cost=229.0, subscription_type="Abierto", plan_anclado="Telcel Libre 1 Abierto",
        rejection_count=1,
    )
    tools = make_tools(session)
    manejar = next(t for t in tools if t.tool_name == "manejar_objecion")
    respuesta = manejar(motivo="precio")
    exito = (
        session.rejection_count == 2
        and "opciones más económicas" not in respuesta.lower()
        and ("gb" in respuesta.lower() or "cashback" in respuesta.lower() or "incremento" in respuesta.lower())
    )
    return exito, f"rejection_count={session.rejection_count} respuesta='{respuesta[len('RESPONDE EXACTAMENTE CON ESTE TEXTO SIN MODIFICAR NADA:'):].strip()[:150]}...'"


ESCENARIOS = [
    ("A. Barrido amplio de variantes de objeción de precio", parte_a_barrido_amplio),
    ("1. 'no me alcanza para pagar eso'", escenario_1),
    ("2. 'está fuera de mi presupuesto'", escenario_2),
    ("3. Objeción coloquial ('no me late')", escenario_3),
    ("4. manejar_objecion directo, plan Ultra (solo GB)", escenario_4),
    ("5. manejar_objecion directo, segunda objeción", escenario_5),
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
    print(f"\n{exitosos}/{total} exitosos")


if __name__ == "__main__":
    main()
