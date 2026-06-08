"""
config/logging_config.py — Configuración de logs a archivo con rotación.
"""
import logging
import os
from logging.handlers import RotatingFileHandler

LOGS_DIR = "logs"


def setup_logging():
    os.makedirs(LOGS_DIR, exist_ok=True)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Handler → archivo con rotación (10 MB, máx 5 archivos)
    file_handler = RotatingFileHandler(
        filename=os.path.join(LOGS_DIR, "app.log"),
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    # Handler → consola
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
