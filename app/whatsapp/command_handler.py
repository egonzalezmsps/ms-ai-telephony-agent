"""
app/whatsapp/command_handler.py

Maneja comandos enviados por WhatsApp (/lista, /seleccionar, /perfil, /reset).
"""

import logging
from typing import Optional

from app.tools.prospect_loader import load_prospects, select_prospect, MODALITY_MAP
from app.prompts.campaign_template import build_campaign_message
from app.state.persistence import load_session, save_session, delete_session
from app.state.serializer import session_to_dict, dict_to_session

logger = logging.getLogger(__name__)

_KNOWN_COMMANDS = {
    "/ayuda", "/help",
    "/lista", "/list",
    "/seleccionar", "/select",
    "/perfil",
    "/reset",
}

_AYUDA_TEXT = (
    "Comandos disponibles:\n\n"
    "/lista — Ver todos los prospectos del CSV\n"
    "/seleccionar N — Cargar perfil N e iniciar prueba\n"
    "/perfil — Ver datos del cliente activo\n"
    "/reset — Limpiar sesion actual\n"
    "/ayuda — Mostrar este mensaje\n\n"
    "Ejemplo: /seleccionar 3"
)


def _format_prospect_list() -> str:
    prospects = load_prospects()
    if not prospects:
        return "No se encontraron prospectos en el CSV."

    lines = ["Prospectos disponibles:\n"]
    for i, row in enumerate(prospects, 1):
        nombre = row.get("nombre", "?")
        renta = row.get("rentaplan", "?")
        tipo = MODALITY_MAP.get(row.get("tiposuscripcion", ""), "?")
        lines.append(f"{i:2}. {nombre} — ${renta}/mes ({tipo})")

    lines.append("\nUsa /seleccionar N para cargar un perfil.")
    return "\n".join(lines)


def _format_perfil(session) -> str:
    gb_info = f"{session.current_plan_gb} GB" if session.current_plan_gb else "N/D"
    plan_sel = session.plan_selected or "Ninguno"
    return (
        f"Perfil activo:\n"
        f"  Nombre: {session.full_name}\n"
        f"  Telefono: {session.phone_number}\n"
        f"  Plan actual: {session.current_plan_name}\n"
        f"  Renta: ${session.current_cost:.0f}/mes\n"
        f"  Modalidad: {session.subscription_type}\n"
        f"  GB: {gb_info}\n"
        f"  Etapa: {session.stage}\n"
        f"  Plan seleccionado: {plan_sel}\n"
        f"  Uso: {session.usage_summary or 'N/D'}"
    )


def handle_command(phone_number: str, text: str) -> Optional[str]:
    """
    Procesa un mensaje que empieza con '/'.

    Retorna el texto de respuesta si es un comando reconocido,
    None si el mensaje debe pasar al flujo normal del agente.
    """
    parts = text.strip().split()
    if not parts:
        return None

    cmd = parts[0].lower()

    if cmd not in _KNOWN_COMMANDS:
        return None  # No es un comando — dejar pasar al LLM

    # /ayuda
    if cmd in ("/ayuda", "/help"):
        return _AYUDA_TEXT

    # /lista
    if cmd in ("/lista", "/list"):
        return _format_prospect_list()

    # /seleccionar N
    if cmd in ("/seleccionar", "/select"):
        if len(parts) < 2 or not parts[1].isdigit():
            return "Uso: /seleccionar N\nEjemplo: /seleccionar 3"
        n = int(parts[1])
        session = select_prospect(n)
        if session is None:
            total = len(load_prospects())
            return f"Numero invalido. Hay {total} prospectos (1-{total})."
        # Usar el numero del admin como clave de sesion para que los
        # mensajes subsecuentes se procesen con este perfil de prueba.
        session.phone_number = phone_number
        delete_session(phone_number)
        campaign_msg = build_campaign_message(session)
        save_session(
            phone_number=phone_number,
            session_data=session_to_dict(session),
            history=[{"role": "assistant", "content": campaign_msg}],
        )
        logger.info(f"ADMIN | {phone_number}: /seleccionar {n} — {session.full_name}")
        return f"Perfil cargado: {session.full_name} ({session.current_plan_name} ${session.current_cost:.0f}/mes)\n\n{campaign_msg}"

    # /perfil
    if cmd == "/perfil":
        existing = load_session(phone_number)
        if not existing:
            return "No hay sesion activa. Usa /seleccionar N primero."
        session = dict_to_session(existing["session_data"])
        return _format_perfil(session)

    # /reset
    if cmd == "/reset":
        delete_session(phone_number)
        logger.info(f"ADMIN | {phone_number}: /reset")
        return "Sesion eliminada. Usa /seleccionar N para iniciar una nueva prueba."

    return None
