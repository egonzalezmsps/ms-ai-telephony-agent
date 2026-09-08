"""
config/logging_config.py — Configuración de logs a archivo con rotación.
"""
import io
import logging
import os
import re
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Ruta absoluta anclada al repo (no al cwd del proceso), para que siempre
# sea el mismo archivo sin importar desde dónde se lance el servicio.
LOGS_DIR = str(Path(__file__).resolve().parents[2] / "logs")

_SECRET_MARKERS = ("PRIVATE KEY", "BEGIN CERTIFICATE")


class _RedactSecretsFilter(logging.Filter):
    """
    Evita que credenciales sensibles (llaves privadas PEM, certificados)
    lleguen a cualquier handler — sin esto, dependencias como strands/litellm
    en modo DEBUG pueden volcar su config interna completa (incluida la
    llave privada de OCI) al inicializar el modelo.

    Se aplica a nivel de Handler (no de Logger) para que atrape la fuga sin
    importar de qué logger/módulo venga — un filtro en un Logger padre NO
    se vuelve a evaluar cuando el record llega por propagación.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:
            return True
        if any(marker in message for marker in _SECRET_MARKERS):
            record.msg = (
                "[REDACTADO] El mensaje original de '%s' contenía una llave/certificado "
                "y fue suprimido por seguridad."
            )
            record.args = (record.name,)
        return True


def setup_logging():
    os.makedirs(LOGS_DIR, exist_ok=True)
    log_path = os.path.join(LOGS_DIR, "app.log")

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Handler → archivo con rotación (10 MB, máx 5 archivos)
    file_handler = RotatingFileHandler(
        filename=log_path,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(_RedactSecretsFilter())

    # Handler → consola. En Windows, stdout/stderr suelen usar el codepage
    # legado (cp1252/cp850), que no puede codificar emojis (✅, ❌, 👋, etc.
    # usados en los mensajes al cliente). Sin esto, esas líneas se pierden
    # en silencio (UnicodeEncodeError capturado por logging.Handler.emit).
    console_stream = io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", errors="backslashreplace", newline=""
    ) if hasattr(sys.stdout, "buffer") else sys.stdout
    console_handler = logging.StreamHandler(console_stream)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(_RedactSecretsFilter())

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    logging.getLogger("LiteLLM").setLevel(logging.WARNING)

    # Propagar logs de strands al logger principal (para que terminen en app.log)
    strands_logger = logging.getLogger("strands")
    strands_logger.setLevel(logging.DEBUG)
    strands_logger.propagate = True

    strands_event_logger = logging.getLogger("strands.event_loop.event_loop")
    strands_event_logger.setLevel(logging.DEBUG)
    strands_event_logger.propagate = True

    # También capturar litellm que es el cliente HTTP
    litellm_logger = logging.getLogger("litellm")
    litellm_logger.setLevel(logging.WARNING)
    litellm_logger.propagate = True

    logging.getLogger(__name__).info("[LOGGING] Escribiendo logs en %s", log_path)
