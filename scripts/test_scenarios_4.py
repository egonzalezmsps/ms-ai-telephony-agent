"""
scripts/test_scenarios_4.py

Cuarto set — enfocado en confirmar el arreglo del falso positivo del router
semántico entre "objeción de precio" y "petición explícita de plan más
barato" (intención planes_mas_baratos).

Parte A: barrido directo sobre classify() — rápido, sin LLM. Confirma que
las frases de objeción pura ya NO se clasifican como planes_mas_baratos
(deben caer a None y resolverse vía LLM -> manejar_objecion), y que las
peticiones genuinas SÍ se siguen clasificando correctamente.

Parte B: escenarios conversacionales completos (run_turn, LLM real) para
los casos más representativos, incluyendo frases mixtas (objeción + petición
explícita en el mismo mensaje).

Uso:
    python scripts/test_scenarios_4.py
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


# ── Parte A: barrido directo sobre classify() ───────────────────────────────

FRASES_PETICION_GENUINA = [
    "¿tienes planes más baratos?",
    "¿hay algo más económico disponible?",
    "quiero pagar menos por mi plan",
    "¿tienen opciones de menor precio?",
    "¿hay algo más accesible en precio?",
    "quisiera bajar mi renta mensual",
    "¿hay algo más barato?",
    "planes con menor costo, por favor",
]

FRASES_OBJECION_PURA = [
    "está muy caro, no creo que me convenga",
    "me parece caro",
    "se me hace caro el plan",
    "no quiero pagar tanto",
    "no, está carísimo",
    "uy, qué caro está eso",
    "no me alcanza para pagar eso",
    "no me interesa, es mucho dinero",
]


def parte_a_barrido_router():
    print("\n" + "=" * 70)
    print("PARTE A — Barrido directo sobre classify() (sin LLM)")
    print("=" * 70)

    print("\n-- Peticiones genuinas de plan más barato (esperado: planes_mas_baratos) --")
    resultados_peticion = []
    for frase in FRASES_PETICION_GENUINA:
        intent = classify(frase)
        ok = intent == "planes_mas_baratos"
        resultados_peticion.append(ok)
        print(f"  {'OK ' if ok else 'MAL'} {frase!r:55} -> {intent}")

    print("\n-- Objeciones puras de precio (esperado: NADA que sea planes_mas_baratos) --")
    resultados_objecion = []
    for frase in FRASES_OBJECION_PURA:
        intent = classify(frase)
        ok = intent != "planes_mas_baratos"
        resultados_objecion.append(ok)
        print(f"  {'OK ' if ok else 'MAL'} {frase!r:55} -> {intent}")

    exito = all(resultados_peticion) and all(resultados_objecion)
    detalle = (
        f"peticiones correctas={sum(resultados_peticion)}/{len(resultados_peticion)} "
        f"objeciones correctas={sum(resultados_objecion)}/{len(resultados_objecion)}"
    )
    return exito, detalle


# ── Parte B: escenarios conversacionales completos ──────────────────────────

def escenario_1():
    print("\n" + "=" * 70)
    print("Escenario 1 — Objeción pura ('está muy caro') -> debe manejar objeción")
    print("=" * 70)
    session = _nuevo_perfil("Ana", "Telcel Max Sin Limite 5000", 499.0)
    history = _iniciar_historial(session)
    respuesta, history = _turno(session, history, "está muy caro, no creo que me convenga")
    exito = session.rejection_count >= 1 and "opciones más económicas" not in respuesta.lower()
    return exito, f"rejection_count={session.rejection_count} respuesta='{respuesta[:80]}...'"


def escenario_2():
    print("\n" + "=" * 70)
    print("Escenario 2 — Petición genuina ('tienes algo más barato?') -> debe mostrar opciones")
    print("=" * 70)
    session = _nuevo_perfil("Beto", "Telcel Max Sin Limite 6000", 699.0)
    history = _iniciar_historial(session)
    respuesta, history = _turno(session, history, "¿tienes planes más baratos?")
    exito = "$" in respuesta and session.rejection_count == 0
    return exito, f"rejection_count={session.rejection_count} contiene precio={'$' in respuesta}"


def escenario_3():
    print("\n" + "=" * 70)
    print("Escenario 3 — Mensaje mixto: objeción + petición explícita en la misma frase")
    print("=" * 70)
    session = _nuevo_perfil("Carla", "Telcel Max Sin Limite 6500", 699.0)
    history = _iniciar_historial(session)
    respuesta, history = _turno(session, history, "está caro, ¿no tienes algo más barato?")
    # Aquí no exigimos un único camino "correcto" — solo que la respuesta sea
    # coherente (no vacía) y no invente datos. Se reporta para revisión manual.
    exito = bool(respuesta.strip())
    return exito, f"respuesta no vacía={exito} (revisar manualmente cuál camino tomó) -> '{respuesta[:100]}...'"


def escenario_4():
    print("\n" + "=" * 70)
    print("Escenario 4 — Objeción informal/coloquial ('no manches qué caro')")
    print("=" * 70)
    session = _nuevo_perfil("Diego", "Telcel Plus 8", 899.0)
    history = _iniciar_historial(session)
    respuesta, history = _turno(session, history, "no manches, qué caro está eso")
    exito = session.rejection_count >= 1
    return exito, f"rejection_count={session.rejection_count} respuesta='{respuesta[:80]}...'"


def escenario_5():
    print("\n" + "=" * 70)
    print("Escenario 5 — Petición explícita tras rechazo previo (dos turnos)")
    print("=" * 70)
    session = _nuevo_perfil("Elena", "Telcel Max Sin Limite 3000", 449.0)
    history = _iniciar_historial(session)
    _, history = _turno(session, history, "no me interesa")
    respuesta, history = _turno(session, history, "¿tienes algo más económico que lo que me ofreces?")
    exito = "$" in respuesta
    return exito, f"segunda respuesta contiene precio={'$' in respuesta} respuesta='{respuesta[:100]}...'"


ESCENARIOS = [
    ("A. Barrido directo sobre classify()", parte_a_barrido_router),
    ("1. Objeción pura -> manejar objeción", escenario_1),
    ("2. Petición genuina -> mostrar opciones baratas", escenario_2),
    ("3. Mensaje mixto (objeción + petición)", escenario_3),
    ("4. Objeción informal/coloquial", escenario_4),
    ("5. Petición explícita tras rechazo previo", escenario_5),
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
