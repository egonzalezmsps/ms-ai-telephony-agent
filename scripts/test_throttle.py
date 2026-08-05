import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.config.logging_config import setup_logging
setup_logging()

from app.router.semantic_router import load_reference_embeddings
from app.agent.reni_agent import run_turn
from app.state.session import SessionState

load_reference_embeddings()

# Sesión de Pedro
session = SessionState()
session.first_name = "Pedro"
session.phone_number = "5555555555"
session.current_plan_name = "Telcel Max Sin Limite 5000"
session.current_cost = 499.0
session.subscription_type = "Abierto"
session.current_plan_gb = 5.0
session.has_promotion = True
session.is_titular = True
session.stage = "PERSUASION"
session.plan_anclado = "Telcel Libre 4 Abierto"

# Mensajes que caen al LLM (no interceptados por router)
mensajes = [
    "que beneficios tiene el plan?",
    "cuanto cuesta el cashback?",
    "tiene claro video?",
    "y claro drive?",
    "cuanto tiempo dura la promocion?",
    "puedo decidir despues?",
    "que pasa si se me acaban los datos?",
    "puedo regresar a mi plan actual?",
    "es un proceso seguro?",
    "debo firmar contrato?",
    "me van a dar un celular nuevo?",
    "incluye amazon prime?",
    "que es claro drive?",
    "tiene planes con mas gigas?",
    "cuanto mas pagaria por mas gigas?",
    "y si quiero sin redes sociales?",
    "que diferencia hay entre libre y ultra?",
    "puedo ver mi saldo en la app?",
    "como redimo el cashback?",
    "cuando comienza mi nuevo plan?",
]

history = []
print("\nEnviando mensajes rápido para provocar throttling...\n")

for i, msg in enumerate(mensajes):
    # Resetear sesión si entró en CONTRACT
    if session.stage == "CONTRACT":
        session.stage = "PERSUASION"
        session.awaiting_contract_confirmation = False
        session.awaiting_otp = False
        history = []
        print(f"  [RESET] sesión reseteada\n")

    print(f"[{i+1}] '{msg}'")
    try:
        response, history = run_turn(session, msg, history)
        print(f"  → {response[:80]}")
    except Exception as e:
        print(f"  ❌ ERROR: {e}")
    # Sin sleep
