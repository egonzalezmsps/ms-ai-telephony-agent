"""
app/whatsapp/command_handler.py

Maneja comandos enviados por WhatsApp. Solo /reset está disponible.

Los comandos de prueba (/lista, /seleccionar, /perfil, /ayuda) se retiraron:
no había control de quién los enviaba, y cualquier cliente podía, por ejemplo,
cargar un perfil de prueba con /seleccionar y contratar sobre su línea real con
una renta falsa, o ver nombres y rentas del CSV con /lista. Las pruebas locales
siguen disponibles en el CLI (scripts/test_agent.py).
"""

import logging
from typing import Optional

from app.state.persistence import delete_session

logger = logging.getLogger(__name__)


def handle_command(phone_number: str, text: str) -> Optional[str]:
    """
    Procesa un mensaje que empieza con '/'.

    Retorna el texto de respuesta si es /reset; None para cualquier otro
    mensaje, que pasa al flujo normal del agente.
    """
    parts = text.strip().split()
    if not parts:
        return None

    if parts[0].lower() == "/reset":
        delete_session(phone_number)
        logger.info(f"CMD | {phone_number}: /reset")
        return "Sesion eliminada."

    return None
