"""
config/logging_config.py — Configuración de logs a archivo con rotación.
"""
import io
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Ruta absoluta anclada al repo (no al cwd del proceso), para que siempre
# sea el mismo archivo sin importar desde dónde se lance el servicio.
LOGS_DIR = str(Path(__file__).resolve().parents[2] / "logs")


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

    # Handler → consola. En Windows, stdout/stderr suelen usar el codepage
    # legado (cp1252/cp850), que no puede codificar emojis (✅, ❌, 👋, etc.
    # usados en los mensajes al cliente). Sin esto, esas líneas se pierden
    # en silencio (UnicodeEncodeError capturado por logging.Handler.emit).
    console_stream = io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", errors="backslashreplace", newline=""
    ) if hasattr(sys.stdout, "buffer") else sys.stdout
    console_handler = logging.StreamHandler(console_stream)
    console_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    logging.getLogger("LiteLLM").setLevel(logging.WARNING)

    logging.getLogger(__name__).info("[LOGGING] Escribiendo logs en %s", log_path)
