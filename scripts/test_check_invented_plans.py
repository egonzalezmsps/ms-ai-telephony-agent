import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.state.session import SessionState
from app.agent.reni_agent import _check_invented_plans

def make_session(modality="Controlado", cost=699.0):
    session = SessionState()
    session.phone_number = "5500000000"
    session.subscription_type = modality
    session.current_cost = cost
    session.plan_anclado = f"Telcel Libre 5 {modality}"
    return session

# ── Casos de prueba ───────────────────────────────────────────────────────────
casos = []

# CASO 1: Plan que no existe → debe interceptar
casos.append({
    "desc": "Plan inventado (no existe en catálogo)",
    "session": make_session("Controlado", 699.0),
    "text": "Le recomendamos el *Telcel Ultra 20 Controlado* a $1599/mes con 50 GB.",
    "debe_interceptar": True,
})

# CASO 2: Plan existe, precio correcto en Controlado → NO debe interceptar
casos.append({
    "desc": "Plan real, precio correcto en Controlado",
    "session": make_session("Controlado", 699.0),
    "text": "El *Telcel Libre 5 Controlado* a $699/mes incluye 20 GB y cashback.",
    "debe_interceptar": False,
})

# CASO 3: Plan existe, precio correcto en Abierto → NO debe interceptar
casos.append({
    "desc": "Plan real, precio correcto en Abierto",
    "session": make_session("Abierto", 699.0),
    "text": "El *Telcel Libre 5 Abierto* a $599/mes incluye 20 GB y cashback.",
    "debe_interceptar": False,
})

# CASO 4: Plan existe pero precio incorrecto → debe interceptar
casos.append({
    "desc": "Plan real pero precio inventado",
    "session": make_session("Controlado", 699.0),
    "text": "El *Telcel Ultra 9 Controlado* a $1599/mes tiene 30 GB.",
    "debe_interceptar": True,
})

# CASO 5: Cliente Controlado, LLM menciona precio en Abierto → NO debe interceptar
casos.append({
    "desc": "Cliente Controlado, LLM menciona precio Abierto correctamente",
    "session": make_session("Controlado", 699.0),
    "text": "El *Telcel Libre 6 Abierto* tiene un precio de $699/mes en modalidad Abierto.",
    "debe_interceptar": False,
})

# CASO 6: Texto sin planes Telcel → NO debe interceptar
casos.append({
    "desc": "Texto sin mencionar planes",
    "session": make_session("Controlado", 699.0),
    "text": "Para más información puede comunicarse con Soporte al 800 220 9518.",
    "debe_interceptar": False,
})

# CASO 7: Plan inventado con número alto
casos.append({
    "desc": "Plan con número inventado (Telcel Libre 25)",
    "session": make_session("Abierto", 499.0),
    "text": "El *Telcel Libre 25 Abierto* a $499/mes tiene 100 GB.",
    "debe_interceptar": True,
})

# CASO 8: Plan Ultra Ilimitado con precio correcto → NO debe interceptar
casos.append({
    "desc": "Telcel Ultra Ilimitado precio correcto Controlado",
    "session": make_session("Controlado", 1099.0),
    "text": "El *Telcel Ultra Ilimitado Controlado* a $1399/mes tiene datos ilimitados.",
    "debe_interceptar": False,
})

# CASO 9: Plan Ultra Ilimitado con precio incorrecto → debe interceptar
casos.append({
    "desc": "Telcel Ultra Ilimitado precio inventado",
    "session": make_session("Controlado", 1099.0),
    "text": "El *Telcel Ultra Ilimitado Controlado* a $999/mes tiene datos ilimitados.",
    "debe_interceptar": True,
})

# CASO 10: Telcel Libre VIP precio correcto Abierto → NO debe interceptar
casos.append({
    "desc": "Telcel Libre VIP precio correcto Abierto",
    "session": make_session("Abierto", 1449.0),
    "text": "El *Telcel Libre VIP Abierto* a $1499/mes incluye 60 GB y cashback.",
    "debe_interceptar": False,
})

# CASO 11: Múltiples planes en texto — uno inventado → debe interceptar
casos.append({
    "desc": "Múltiples planes, uno inventado",
    "session": make_session("Controlado", 699.0),
    "text": (
        "• *Telcel Libre 5 Controlado*: $699/mes · 20 GB\n"
        "• *Telcel Ultra 15 Controlado*: $999/mes · 200 GB\n"
    ),
    "debe_interceptar": True,
})

# CASO 12: Mención de "Telcel Ultra sin redes" → NO debe interceptar (no es plan)
casos.append({
    "desc": "Frase 'Telcel Ultra sin redes' no es nombre de plan",
    "session": make_session("Controlado", 699.0),
    "text": "Los planes Telcel Ultra sin redes ilimitadas son ideales para usted.",
    "debe_interceptar": False,
})

# ── Ejecutar pruebas ──────────────────────────────────────────────────────────
print(f"\n{'='*70}")
print("PRUEBAS DE _check_invented_plans")
print(f"{'='*70}\n")

passed = 0
failed = 0

for i, caso in enumerate(casos, 1):
    session = caso["session"]
    result = _check_invented_plans(caso["text"], session)
    interceptado = result != caso["text"]
    ok = interceptado == caso["debe_interceptar"]

    status = "✅ PASS" if ok else "❌ FAIL"
    if ok:
        passed += 1
    else:
        failed += 1

    print(f"{status} [{i:02d}] {caso['desc']}")
    if not ok:
        print(f"       Esperado: {'interceptar' if caso['debe_interceptar'] else 'no interceptar'}")
        print(f"       Resultado: {'interceptado' if interceptado else 'no interceptado'}")
        print(f"       Texto: {caso['text'][:80]}")
        print(f"       Respuesta: {result[:80]}")
    print()

print(f"{'='*70}")
print(f"RESUMEN: {passed} passed, {failed} failed de {len(casos)} casos")
print(f"{'='*70}\n")
