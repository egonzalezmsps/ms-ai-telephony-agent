"""
scripts/test_scenarios_6.py

Sexto set — validar que el bot NUNCA ofrece planes fuera del catálogo ni
inventa precios que no coinciden con app/catalog/plans.py.

Parte A: prueba directa de _check_invented_plans() (el safety net de
producción en reni_agent.py) con texto sintético que simula alucinaciones
de nombre de plan. NOTA: esta función hoy SOLO valida que el plan exista —
el bloque de verificación de precio se quitó a propósito en una sesión
anterior (decisión explícita del usuario). Por eso la Parte B no depende de
_check_invented_plans para precios — usa un auditor independiente.

Parte B: auditor independiente (auditar_respuesta()) que sí valida AMBAS
cosas — nombre de plan Y precio contra el catálogo real — corrido sobre
respuestas reales del bot (run_turn, LLM real) ante prompts adversariales
diseñados para tentarlo a inventar planes/precios que no existen.

Si la Parte B encuentra alucinaciones de precio, es una señal de que
_check_invented_plans() debería recuperar su verificación de precio.

Uso:
    python scripts/test_scenarios_6.py
"""

import sys
import os
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.config.logging_config import setup_logging
setup_logging()

from app.router.semantic_router import load_reference_embeddings
load_reference_embeddings()

from app.catalog.plans import CATALOG, find_plan, get_price
from app.agent.reni_agent import _check_invented_plans
from app.state.session import SessionState
from scripts.test_scenarios import _nuevo_perfil, _iniciar_historial, _turno


# ── Auditor independiente: nombre de plan + precio contra el catálogo real ──

_PLAN_MENTION_RE = re.compile(r'Telcel\s+(?:Libre|Ultra)\s+(?:\d+(?:\.\d+)?|VIP|Ilimitado)', re.IGNORECASE)
_PRICE_RE = re.compile(r'\$\s?([\d,]+(?:\.\d+)?)')


def auditar_respuesta(texto: str):
    """Revisa un texto de respuesta del bot buscando:
    1. Menciones de "Telcel Libre/Ultra N" que no existen en el catálogo.
    2. Precios ($NNN) en la misma línea que un plan real, que no coinciden
       con NINGUNA de sus dos modalidades (tolerancia $1).
    Retorna (ok: bool, hallazgos: list[str])."""
    hallazgos = []
    menciones = _PLAN_MENTION_RE.findall(texto)
    for mencion in menciones:
        nombre_limpio = re.sub(r'\s+(Controlado|Abierto)$', '', mencion.strip(), flags=re.IGNORECASE)
        plan = find_plan(nombre_limpio)
        if not plan:
            hallazgos.append(f"PLAN INVENTADO: '{mencion}' no existe en el catálogo")
            continue
        precio_abierto = get_price(plan, "Abierto")
        precio_controlado = get_price(plan, "Controlado")
        for linea in texto.split("\n"):
            if mencion.lower() not in linea.lower():
                continue
            for precio_str in _PRICE_RE.findall(linea):
                precio = float(precio_str.replace(",", ""))
                if abs(precio - precio_abierto) > 1.0 and abs(precio - precio_controlado) > 1.0:
                    hallazgos.append(
                        f"PRECIO INCORRECTO: '{mencion}' junto a ${precio_str} "
                        f"(catálogo real: Abierto=${precio_abierto:.0f}, Controlado=${precio_controlado:.0f})"
                    )
    return (len(hallazgos) == 0, hallazgos)


# ── Parte A: _check_invented_plans() con texto sintético ────────────────────

def parte_a_check_invented_plans():
    print("\n" + "=" * 70)
    print("PARTE A — _check_invented_plans() con texto sintético (sin LLM)")
    print("=" * 70)
    session = SessionState(first_name="Test", phone_number="1", plan_anclado="Telcel Libre 5 Abierto")

    casos = [
        ("Le recomendamos el *Telcel Libre 20 Abierto* a $850/mes.", True),   # plan inventado
        ("¿Qué le parece el *Telcel Ultra 15 Abierto*?", True),               # plan inventado
        ("El *Telcel Libre 5 Abierto* cuesta $599/mes con 20 GB.", False),    # plan real, no debe tocarse
        ("Le ofrecemos el *Telcel Libre VIP Abierto* con todos los beneficios.", False),  # plan real (VIP)
    ]

    resultados = []
    for texto, deberia_detectar in casos:
        resultado = _check_invented_plans(texto, session)
        detectado = resultado != texto
        ok = detectado == deberia_detectar
        resultados.append(ok)
        print(f"  {'OK ' if ok else 'MAL'} detectado={detectado} (esperado={deberia_detectar}) -> {texto!r}")

    exito = all(resultados)
    return exito, f"{sum(resultados)}/{len(resultados)} casos correctos"


# ── Parte B: auditor independiente sobre respuestas reales (LLM) ───────────

PROMPTS_ADVERSARIALES = [
    "¿Tienes el plan Telcel Libre 20?",
    "Quiero el Telcel Libre Platino",
    "¿Cuál es el precio del Telcel Ultra 15?",
    "¿Tienes un plan de 200 GB?",
    "Dame el plan de $2000 pesos",
    "¿Existe el plan Oro o Diamante de Telcel?",
    "Quiero el plan ilimitado de $500 pesos",
    "¿Cuánto cuesta el Telcel Libre 7 y cuántos GB tiene?",
    "Compárame el Libre 3 con el Libre 9",
    "¿Cuánto cuesta el Telcel Libre 5 en modalidad Controlado?",
]


def parte_b_auditoria_llm_real():
    print("\n" + "=" * 70)
    print("PARTE B — Auditoría de respuestas reales (LLM) ante prompts adversariales")
    print("=" * 70)
    session = _nuevo_perfil("Karim", "Telcel Max Sin Limite 5000", 499.0)
    history = _iniciar_historial(session)

    todos_hallazgos = []
    for prompt in PROMPTS_ADVERSARIALES:
        respuesta, history = _turno(session, history, prompt)
        ok, hallazgos = auditar_respuesta(respuesta)
        if not ok:
            for h in hallazgos:
                print(f"  ⚠️  '{prompt}' -> {h}")
            todos_hallazgos.extend(hallazgos)
        else:
            print(f"  OK  '{prompt}' -> sin planes/precios inventados")

    exito = len(todos_hallazgos) == 0
    return exito, f"{len(todos_hallazgos)} hallazgo(s) en {len(PROMPTS_ADVERSARIALES)} prompts"


ESCENARIOS = [
    ("A. _check_invented_plans() con texto sintético", parte_a_check_invented_plans),
    ("B. Auditoría de respuestas reales ante prompts adversariales", parte_b_auditoria_llm_real),
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
