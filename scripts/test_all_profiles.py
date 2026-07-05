import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.router.semantic_router import load_reference_embeddings
from app.agent.reni_agent import run_turn
from app.state.session import SessionState

load_reference_embeddings()

# Casos de prueba por perfil — mismos mensajes para todos
MENSAJES = [
    "porque me conviene este plan?",
    "tienes planes mas baratos?",
    "tienes planes con mas datos?",
    "que gano con el cambio?",
    "hasta cuando dura esta promocion?",
    "como es el proceso para activar?",
    "me parece caro",
    "no me interesa",
    "si quiero activarlo",
]

# 18 perfiles del CSV
PERFILES = [
    {"name": "Luisa",    "phone": "5522222222", "plan": "Telcel Max Sin Limite 1500", "cost": 319,  "modality": "Controlado", "gb": 1.5},
    {"name": "Pedro",    "phone": "5533333333", "plan": "Telcel Max Sin Limite 5000", "cost": 499,  "modality": "Abierto",    "gb": 5},
    {"name": "Ana",      "phone": "5544444444", "plan": "Telcel Max Sin Limite 2000", "cost": 449,  "modality": "Controlado", "gb": 3},
    {"name": "Roberto",  "phone": "5511111111", "plan": "Telcel Max Sin Limite 1000", "cost": 229,  "modality": "Abierto",    "gb": 1},
    {"name": "Maria",    "phone": "5566666666", "plan": "Telcel Max Sin Limite 3000", "cost": 549,  "modality": "Controlado", "gb": 8},
    {"name": "Carlos",   "phone": "5577777777", "plan": "Telcel Max Sin Limite 6000", "cost": 699,  "modality": "Controlado", "gb": 12},
    {"name": "Diana",    "phone": "5588888888", "plan": "Telcel Max Sin Limite 8000", "cost": 899,  "modality": "Abierto",    "gb": 26},
    {"name": "Jorge",    "phone": "5599999999", "plan": "Telcel Max Sin Limite 10000","cost": 999,  "modality": "Controlado", "gb": 30},
    {"name": "Sofia",    "phone": "5510101010", "plan": "Telcel Max Sin Limite 12000","cost": 1099, "modality": "Abierto",    "gb": 40},
    {"name": "Miguel",   "phone": "5521212121", "plan": "Telcel Max Sin Limite 15000","cost": 1199, "modality": "Controlado", "gb": 50},
    {"name": "Laura",    "phone": "5532323232", "plan": "Telcel Max Sin Limite 20000","cost": 1299, "modality": "Abierto",    "gb": 60},
    {"name": "Antonio",  "phone": "5543434343", "plan": "Telcel Plus 1",              "cost": 199,  "modality": "Controlado", "gb": 0},
    {"name": "Carmen",   "phone": "5554545454", "plan": "Telcel Plus 2",              "cost": 249,  "modality": "Abierto",    "gb": 0},
    {"name": "Ricardo",  "phone": "5565656565", "plan": "Telcel Max Sin Limite 4000", "cost": 599,  "modality": "Controlado", "gb": 10},
    {"name": "Norma",    "phone": "5576767676", "plan": "Telcel Max Sin Limite 7000", "cost": 799,  "modality": "Abierto",    "gb": 20},
    {"name": "Armando",  "phone": "5587878787", "plan": "Telcel Max Sin Limite 8000", "cost": 899,  "modality": "Abierto",    "gb": 26},
    {"name": "Horacio",  "phone": "5598989898", "plan": "Telcel Plus 14",             "cost": 1449, "modality": "Abierto",    "gb": 0},
    {"name": "Jesus",    "phone": "5509090909", "plan": "Telcel Max Sin Limite 6500", "cost": 699,  "modality": "Abierto",    "gb": 12},
]

def make_session(perfil):
    session = SessionState()
    session.first_name = perfil["name"]
    session.phone_number = perfil["phone"]
    session.current_plan_name = perfil["plan"]
    session.current_cost = perfil["cost"]
    session.subscription_type = perfil["modality"]
    session.current_plan_gb = perfil["gb"]
    session.has_promotion = True
    session.is_titular = True
    session.stage = "PERSUASION"
    return session

print(f"\n{'='*80}")
print(f"PRUEBA DE 18 PERFILES — {len(MENSAJES)} mensajes cada uno")
print(f"{'='*80}\n")

errores = []

for perfil in PERFILES:
    session = make_session(perfil)
    history = []
    print(f"\n{'─'*60}")
    print(f"Perfil: {perfil['name']} | {perfil['plan']} | ${perfil['cost']}/mes | {perfil['modality']}")
    print(f"{'─'*60}")

    for msg in MENSAJES:
        try:
            response, history = run_turn(session, msg, history)
            # Mostrar solo primeras 100 chars de la respuesta
            resp_preview = response.replace('\n', ' ')[:100]
            print(f"  > {msg[:40]:<40} → {resp_preview}")
        except Exception as e:
            error = f"ERROR [{perfil['name']}] msg='{msg}': {e}"
            errores.append(error)
            print(f"  > {msg[:40]:<40} → ❌ ERROR: {e}")

print(f"\n{'='*80}")
print(f"RESUMEN: {len(PERFILES)} perfiles × {len(MENSAJES)} mensajes = {len(PERFILES)*len(MENSAJES)} turnos")
print(f"Errores: {len(errores)}")
if errores:
    print("\nDetalle de errores:")
    for e in errores:
        print(f"  {e}")
print(f"{'='*80}\n")
