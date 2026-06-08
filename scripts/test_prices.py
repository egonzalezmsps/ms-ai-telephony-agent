"""
scripts/test_prices.py

Verifica que el agente responde los precios, GB y cashback del catálogo
correctamente para el perfil 4 (María, $449/mes, Controlado).

Uso:
    python scripts/test_prices.py
"""

import sys
import os
import re

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv
load_dotenv()

from app.agent.reni_agent import run_turn
from app.tools.prospect_loader import select_prospect
from app.prompts.campaign_template import build_campaign_message
from app.catalog.plans import get_price, get_cashback, find_plan

# ── Casos de prueba ───────────────────────────────────────────────────────────
# expected: valor numérico exacto del catálogo
# accepted: valores alternativos válidos (ej. GB base cuando no hay promo aplicable)
# kind: "price" | "cashback" | "gb"

TEST_CASES = [
    {
        "question": "cuánto cuesta el Telcel Libre 1 Controlado?",
        "label":    "Telcel Libre 1 Controlado — precio",
        "kind":     "price",
        "expected": get_price(find_plan("Telcel Libre 1"), "Controlado"),   # 299
    },
    {
        "question": "cuánto cuesta el Telcel Libre 2 Controlado?",
        "label":    "Telcel Libre 2 Controlado — precio",
        "kind":     "price",
        "expected": get_price(find_plan("Telcel Libre 2"), "Controlado"),   # 369
    },
    {
        "question": "cuánto cuesta el Telcel Libre 3 Controlado?",
        "label":    "Telcel Libre 3 Controlado — precio",
        "kind":     "price",
        "expected": get_price(find_plan("Telcel Libre 3"), "Controlado"),   # 449
    },
    {
        "question": "cuánto cuesta el Telcel Ultra 3 Controlado?",
        "label":    "Telcel Ultra 3 Controlado — precio",
        "kind":     "price",
        "expected": get_price(find_plan("Telcel Ultra 3"), "Controlado"),   # 399
    },
    {
        "question": "cuánto cuesta el Telcel Ultra 4 Controlado?",
        "label":    "Telcel Ultra 4 Controlado — precio",
        "kind":     "price",
        "expected": get_price(find_plan("Telcel Ultra 4"), "Controlado"),   # 499
    },
    {
        "question": "cuánto es el cashback del Telcel Libre 4 Controlado?",
        "label":    "Telcel Libre 4 Controlado — cashback",
        "kind":     "cashback",
        "expected": get_cashback(find_plan("Telcel Libre 4"), "Controlado"), # 82.35
    },
    {
        "question": "cuántos GB tiene el Telcel Libre 5 Controlado?",
        "label":    "Telcel Libre 5 Controlado — GB (con promo)",
        "kind":     "gb",
        "expected": 30.0,  # GB promo (María tiene promo activa y precio 699 > 450)
        "accepted": [20.0], # GB base también aceptable si el modelo no aplica promo
    },
]

TOLERANCE = 1.0  # diferencia máxima aceptable para precios enteros


# ── Extracción de números de la respuesta ─────────────────────────────────────

def extract_prices(text: str) -> list[float]:
    """Extrae valores monetarios: $299, $82.35, 299/mes, etc."""
    hits = re.findall(r'\$\s*([\d,]+(?:\.\d+)?)', text)
    return [float(h.replace(',', '')) for h in hits]


def extract_gb(text: str) -> list[float]:
    """Extrae valores de GB: 30 GB, 30GB, 30 gb."""
    hits = re.findall(r'([\d]+(?:\.\d+)?)\s*(?:GB|gb)', text)
    return [float(h) for h in hits]


def verify(response: str, case: dict) -> tuple[str, str]:
    """
    Devuelve (status, detail) donde status es "CORRECTO", "ERROR" o "NO VERIFICABLE".
    """
    kind = case["kind"]
    expected = case["expected"]
    accepted = set(case.get("accepted", [])) | {expected}

    if kind == "gb":
        values = extract_gb(response)
    else:
        values = extract_prices(response)

    if not values:
        return "NO VERIFICABLE", "no se encontraron números en la respuesta"

    # Aceptar si cualquier valor extraído coincide con los esperados (con tolerancia)
    for v in values:
        for a in accepted:
            if abs(v - a) <= TOLERANCE:
                return "CORRECTO", f"encontrado {v} (esperado {expected})"

    # Hay números pero ninguno coincide
    return "ERROR", f"encontrados {values}, esperado {expected}"


# ── Ejecución ─────────────────────────────────────────────────────────────────

def main():
    print("\n══════════════════════════════════════════════")
    print("  test_prices.py — verificación de precios")
    print("══════════════════════════════════════════════\n")

    session = select_prospect(4)
    if not session:
        print("ERROR: No se encontró el perfil 4. Verifica el CSV en docs/Masivo_clientes.csv")
        sys.exit(1)

    print(f"Perfil cargado: {session.first_name} — ${session.current_cost:.0f}/mes {session.subscription_type}\n")

    # Iniciar historial con el mensaje de campaña (contexto inicial del agente)
    campaign = build_campaign_message(session)
    history = [{"role": "assistant", "content": campaign}]

    results = []

    for i, case in enumerate(TEST_CASES, 1):
        print(f"[{i}/{len(TEST_CASES)}] {case['label']}")
        print(f"  Pregunta: {case['question']}")

        response, history = run_turn(session, case["question"], history)
        print(f"  Respuesta: {response[:200].replace(chr(10), ' ')}")

        status, detail = verify(response, case)
        results.append(status)

        icon = "✅" if status == "CORRECTO" else ("❌" if status == "ERROR" else "⚠️")
        print(f"  {icon} {status} — {detail}\n")

    # ── Resumen ───────────────────────────────────────────────────────────────
    correct = results.count("CORRECTO")
    errors = results.count("ERROR")
    unverifiable = results.count("NO VERIFICABLE")
    total = len(results)

    print("══════════════════════════════════════════════")
    print(f"  RESUMEN: {correct}/{total} precios correctos")
    if errors:
        print(f"  ❌ Errores: {errors}")
    if unverifiable:
        print(f"  ⚠️  No verificables: {unverifiable}")
    print("══════════════════════════════════════════════\n")

    sys.exit(0 if errors == 0 else 1)


if __name__ == "__main__":
    main()
