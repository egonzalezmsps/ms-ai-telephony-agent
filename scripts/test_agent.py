"""
scripts/test_agent.py

CLI interactivo para probar ReniAgent localmente.
Replica el comando /select N del proyecto original.

Uso:
    python scripts/test_agent.py

Comandos disponibles:
    /list          — lista todos los prospectos del CSV
    /select N      — carga el perfil N e inicia conversación
    /perfil        — muestra el perfil del cliente activo
    /reset         — limpia la sesión actual
    /help          — muestra esta ayuda
    /exit          — salir
"""

import sys
import os

# Añadir raíz del proyecto al path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv
load_dotenv()

from app.agent.reni_agent import run_turn
from app.tools.prospect_loader import get_prospect_list_text, select_prospect
from app.state.session import SessionState
from app.state.persistence import delete_session
from app.prompts.campaign_template import build_campaign_message


def print_help():
    print("""
Comandos:
  /list        — lista prospectos del CSV
  /select N    — carga prospecto N e inicia conversación
  /perfil      — muestra datos del cliente activo
  /reset       — limpia la sesión
  /help        — esta ayuda
  /exit        — salir
    """)


def print_session(session: SessionState):
    print(f"""
─── Perfil activo ───────────────────────────
  Nombre:    {session.first_name} ({session.full_name})
  Línea:     {session.phone_number}
  Plan:      {session.current_plan_name}
  Renta:     ${session.current_cost:.0f}/mes
  Modalidad: {session.subscription_type}
  Perfil:    {session.usage_summary or 'N/D'}
─────────────────────────────────────────────
""")


def main():
    print("\n🤖 ReniAgent — CLI de pruebas (Strands nativo)")
    print("Escribe /help para ver los comandos disponibles.\n")

    session: SessionState = None
    history: list = []

    while True:
        try:
            user_input = input("Tú: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nSaliendo...")
            break

        if not user_input:
            continue

        # ── Comandos ──────────────────────────────────────────────
        if user_input.lower() == "/exit":
            print("Hasta luego.")
            break

        elif user_input.lower() == "/help":
            print_help()

        elif user_input.lower() == "/list":
            print(get_prospect_list_text())

        elif user_input.lower() == "/reset":
            if not session:
                print("No hay sesión activa.")
            else:
                delete_session(session.phone_number)
                session = None
                history = []
                print("Sesión eliminada de PostgreSQL. Usa /select N para cargar un perfil.")

        elif user_input.lower() == "/perfil":
            if session:
                print_session(session)
            else:
                print("No hay perfil activo. Usa /select N.")

        elif user_input.lower().startswith("/select"):
            parts = user_input.split()
            if len(parts) < 2 or not parts[1].isdigit():
                print("Uso: /select N  (donde N es el número del prospecto)")
                continue

            n = int(parts[1])
            session = select_prospect(n)

            if not session:
                print(f"Prospecto {n} no encontrado. Usa /list para ver los disponibles.")
                continue

            history = []
            print_session(session)
            print("─── Iniciando conversación ──────────────────")

            # Mensaje de campaña determinístico — sin LLM
            campaign_msg = build_campaign_message(session)
            history = [{"role": "assistant", "content": campaign_msg}]
            print(f"Agente: {campaign_msg}")
            print()

        # ── Conversación normal ───────────────────────────────────
        else:
            if not session:
                print("Carga un perfil primero con /select N\n")
                continue

            print("Agente: ", end="", flush=True)
            response, history = run_turn(session, user_input, history)
            print(response)
            print()


if __name__ == "__main__":
    main()
