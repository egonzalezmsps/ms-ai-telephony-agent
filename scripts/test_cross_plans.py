import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.router.semantic_router import load_reference_embeddings
from app.agent.reni_agent import run_turn
from app.state.session import SessionState
from app.catalog.plans import recommend_plan, get_price

load_reference_embeddings()

PERFILES = [
    {"name": "Roberto",   "phone": "5511111111", "plan": "Telcel Max Sin Limite 1000",  "cost": 229.0,  "modality": "Abierto",    "gb": 3.5},
    {"name": "Luisa",     "phone": "5522222222", "plan": "Telcel Max Sin Limite 1500",  "cost": 319.0,  "modality": "Controlado", "gb": 4.5},
    {"name": "Miguel",    "phone": "5533333333", "plan": "Telcel Max Sin Limite 2000",  "cost": 299.0,  "modality": "Abierto",    "gb": 5.5},
    {"name": "Ana",       "phone": "5544444444", "plan": "Telcel Max Sin Limite 3000",  "cost": 449.0,  "modality": "Controlado", "gb": 7.5},
    {"name": "Pedro",     "phone": "5555555555", "plan": "Telcel Max Sin Limite 5000",  "cost": 499.0,  "modality": "Abierto",    "gb": 12.0},
    {"name": "Alejandro", "phone": "5513053655", "plan": "Telcel Max Sin Limite 6000",  "cost": 699.0,  "modality": "Controlado", "gb": 15.0},
    {"name": "Jesus",     "phone": "2721140994", "plan": "Telcel Max Sin Limite 6500",  "cost": 699.0,  "modality": "Abierto",    "gb": 18.0},
    {"name": "Carlos",    "phone": "5512237119", "plan": "Telcel Max Sin Limite 7000",  "cost": 899.0,  "modality": "Controlado", "gb": 24.0},
    {"name": "Armando",   "phone": "5541939914", "plan": "Telcel Max Sin Limite 8000",  "cost": 899.0,  "modality": "Abierto",    "gb": 30.0},
    {"name": "Maria",     "phone": "5580703658", "plan": "Telcel Max Sin Limite 9000",  "cost": 1099.0, "modality": "Controlado", "gb": 40.0},
    {"name": "Eduardo",   "phone": "5521295174", "plan": "Telcel Max Sin Limite 12000", "cost": 1299.0, "modality": "Abierto",    "gb": 55.0},
    {"name": "Diana",     "phone": "5510101177", "plan": "Telcel Max Sin Limite 20000", "cost": 1599.0, "modality": "Controlado", "gb": 65.0},
    {"name": "Liliana",   "phone": "5510102751", "plan": "Telcel Plus 1",               "cost": 229.0,  "modality": "Abierto",    "gb": 0},
    {"name": "Marlen",    "phone": "5518126471", "plan": "Telcel Plus 1.5",             "cost": 269.0,  "modality": "Abierto",    "gb": 0},
    {"name": "Miriam",    "phone": "5510100311", "plan": "Telcel Plus 2",               "cost": 349.0,  "modality": "Controlado", "gb": 0},
    {"name": "Norma",     "phone": "5510108952", "plan": "Telcel Plus 8",               "cost": 899.0,  "modality": "Abierto",    "gb": 0},
    {"name": "Virginia",  "phone": "5510101508", "plan": "Telcel Plus 8",               "cost": 999.0,  "modality": "Controlado", "gb": 0},
    {"name": "Horacio",   "phone": "5510109188", "plan": "Telcel Plus 14",              "cost": 1449.0, "modality": "Abierto",    "gb": 0},
    {"name": "Patricia",  "phone": "5539263657", "plan": "Telcel Max Sin Limite 8000",  "cost": 899.0,  "modality": "Abierto",    "gb": 70.0},
]

# Mensajes de prueba cruzada
MENSAJES_CROSS = [
    ("planes_ultra",   "quiero ver planes ultra"),
    ("planes_libre",   "tienes planes libres?"),
    ("sin_redes",      "me interesa pero sin redes sociales"),
    ("modalidad_alt",  "y en modalidad abierta?" if True else "y en modalidad controlada?"),
    ("mas_gb",         "tienes algo con mas datos?"),
    ("mas_barato",     "tienes algo mas barato?"),
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
print(f"PRUEBA CRUZADA DE PLANES — {len(PERFILES)} perfiles × {len(MENSAJES_CROSS)} mensajes")
print(f"{'='*80}\n")

errores = []
alertas = []

for perfil in PERFILES:
    session = make_session(perfil)
    history = []
    alt_modality = "Abierto" if perfil["modality"] == "Controlado" else "Controlado"

    print(f"\n{'─'*60}")
    print(f"Perfil: {perfil['name']} | {perfil['plan']} | ${perfil['cost']}/mes | {perfil['modality']}")
    print(f"{'─'*60}")

    for etiqueta, msg in MENSAJES_CROSS:
        # Adaptar mensaje de modalidad alternativa al perfil
        if etiqueta == "modalidad_alt":
            msg = f"y en modalidad {alt_modality.lower()}?"

        try:
            response, history = run_turn(session, msg, history)
            resp_preview = response.replace('\n', ' ')[:120]

            # Verificaciones de calidad
            alerta = ""
            if "[PLAN_INVENTADO]" in resp_preview:
                alerta = "⚠️ PLAN INVENTADO"
            elif "[PRECIO_INCORRECTO]" in resp_preview:
                alerta = "⚠️ PRECIO INCORRECTO"
            elif response.strip().endswith(":") or response.strip().endswith("son:"):
                alerta = "⚠️ RESPUESTA INCOMPLETA"
            elif "ESTE CANAL" in resp_preview or "Plan |" in resp_preview:
                alerta = "⚠️ TABLA INTERNA"

            if alerta:
                alertas.append(f"{perfil['name']} | {etiqueta} | {alerta}")

            status = alerta if alerta else "✅"
            print(f"  [{etiqueta:<12}] {status} → {resp_preview[:80]}")

        except Exception as e:
            error = f"ERROR [{perfil['name']}] msg='{msg}': {e}"
            errores.append(error)
            print(f"  [{etiqueta:<12}] ❌ ERROR: {e}")

print(f"\n{'='*80}")
print(f"RESUMEN: {len(PERFILES)} perfiles × {len(MENSAJES_CROSS)} mensajes = {len(PERFILES)*len(MENSAJES_CROSS)} turnos")
print(f"Errores: {len(errores)}")
print(f"Alertas: {len(alertas)}")
if alertas:
    print("\nDetalle de alertas:")
    for a in alertas:
        print(f"  ⚠️  {a}")
if errores:
    print("\nDetalle de errores:")
    for e in errores:
        print(f"  ❌ {e}")
print(f"{'='*80}\n")
