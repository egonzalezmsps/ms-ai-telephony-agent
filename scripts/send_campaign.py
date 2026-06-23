"""
scripts/send_campaign.py

CLI para enviar templates de campaña a clientes del CSV.
Llama directamente a la API de WhatsApp y guarda la sesión en la BD de OCI
sin depender del pod (no requiere API Gateway ni rebuild).

Prerequisito: túnel SSH activo en otro terminal:
  ssh -i <key> -N -L 5433:172.16.5.109:5432 pgsqltunnel@129.153.143.19

Uso:
    python scripts/send_campaign.py

Comandos:
    /list          — lista todos los prospectos del CSV
    /select N      — previsualiza el perfil N
    /send N        — envía template al cliente N
    /send all      — envía template a todos los clientes
    /exit          — salir
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv
load_dotenv()

from app.tools.prospect_loader import load_prospects, build_session_from_row, get_prospect_list_text
from app.whatsapp.sender import send_whatsapp_template
from app.state.persistence import save_session
from app.state.serializer import session_to_dict
from app.prompts.campaign_template import build_template_params, build_campaign_message


def _send(session) -> dict:
    """Envía el template de WhatsApp y guarda la sesión en BD OCI directamente."""
    template_result = build_template_params(session)
    campaign_msg = build_campaign_message(session)

    wa_id = session.phone_number
    sent_template = False
    template_name = None

    if template_result:
        template_name = template_result["template_name"]
        wa_resp = send_whatsapp_template(
            to=session.phone_number,
            template_name=template_name,
            params=template_result["params"],
        )
        wa_id = wa_resp.get("contacts", [{}])[0].get("wa_id", session.phone_number)
        sent_template = True
    else:
        from app.whatsapp.sender import send_whatsapp_message
        send_whatsapp_message(session.phone_number, campaign_msg)

    # Guardar sesión bajo wa_id canónico para que el webhook del pod la encuentre
    session.phone_number = wa_id
    save_session(
        phone_number=wa_id,
        session_data=session_to_dict(session),
        history=[{"role": "assistant", "content": campaign_msg}],
    )

    return {
        "wa_id": wa_id,
        "sent_template": sent_template,
        "template_name": template_name,
    }


def _print_profile(session, idx: int):
    print(f"\n  #{idx}  {session.full_name}")
    print(f"  Línea:  {session.phone_number}")
    print(f"  Plan:   {session.current_plan_name}  ${session.current_cost:.0f}/mes  ({session.subscription_type})")
    print(f"  Uso:    {session.usage_summary}")


def _send_and_report(session, idx: int):
    name = session.first_name
    phone = session.phone_number
    print(f"\n→ Enviando a {name} ({phone})...", end=" ", flush=True)
    try:
        result = _send(session)
        wa_id    = result.get("wa_id", "?")
        template = result.get("template_name") or "texto plano"
        status   = "✅ template" if result.get("sent_template") else "📄 texto plano"
        print(f"{status} | wa_id={wa_id} | plantilla={template}")
    except Exception as e:
        print(f"❌ Error — {e}")


def main():
    prospects = load_prospects()
    print(f"\nReniAgent — Envío de campaña (directo)")
    print(f"BD: {os.environ.get('DATABASE_URL', 'no configurada')[:50]}...")
    print(f"Clientes en CSV: {len(prospects)}")
    print("Escribe /help para ver los comandos.\n")

    while True:
        try:
            cmd = input(">>> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nHasta luego.")
            break

        if not cmd:
            continue

        if cmd in ("/exit", "/quit"):
            print("Hasta luego.")
            break

        elif cmd in ("/list", "/help"):
            print(get_prospect_list_text())
            if cmd == "/help":
                print("\nComandos:")
                print("  /list       — lista prospectos")
                print("  /select N   — previsualiza perfil N")
                print("  /send N     — envía template al cliente N")
                print("  /send all   — envía a todos (pide confirmación)")
                print("  /exit       — salir")

        elif cmd.startswith("/select "):
            try:
                n = int(cmd.split()[1])
                if n < 1 or n > len(prospects):
                    print(f"Índice fuera de rango (1–{len(prospects)})")
                else:
                    session = build_session_from_row(prospects[n - 1])
                    _print_profile(session, n)
            except (ValueError, IndexError):
                print("Uso: /select N")

        elif cmd.startswith("/send "):
            arg = cmd.split(maxsplit=1)[1].strip()

            if arg == "all":
                confirm = input(f"¿Enviar a los {len(prospects)} clientes? (s/N): ").strip().lower()
                if confirm != "s":
                    print("Cancelado.")
                    continue
                sent = failed = 0
                for i, row in enumerate(prospects, 1):
                    session = build_session_from_row(row)
                    try:
                        _send_and_report(session, i)
                        sent += 1
                    except Exception:
                        failed += 1
                print(f"\nResumen: {sent} enviados, {failed} fallidos.")

            else:
                try:
                    n = int(arg)
                    if n < 1 or n > len(prospects):
                        print(f"Índice fuera de rango (1–{len(prospects)})")
                    else:
                        session = build_session_from_row(prospects[n - 1])
                        _send_and_report(session, n)
                except ValueError:
                    print("Uso: /send N  o  /send all")

        else:
            print("Comando no reconocido. Escribe /help.")


if __name__ == "__main__":
    main()
