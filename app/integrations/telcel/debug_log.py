"""
integrations/telcel/debug_log.py

TEMPORAL — solo para pruebas. Escribe en logs/telcel_debug.log cada llamada a las
APIs Telcel con el payload en claro, el body cifrado que se envía, la respuesta
cruda y la respuesta descifrada.

⚠️ Este archivo incluye datos sensibles (teléfonos, processId) en texto plano.
Para eliminarlo: borrar este archivo y la llamada a `log_exchange()` en transport.py.
"""

import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Optional

_LOG_PATH = Path(__file__).resolve().parents[3] / "logs" / "telcel_debug.log"

_logger = logging.getLogger("telcel.debug")
_logger.setLevel(logging.INFO)
_logger.propagate = False  # no ensuciar app.log con los payloads en claro

if not _logger.handlers:
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _handler = RotatingFileHandler(_LOG_PATH, maxBytes=5 * 1024 * 1024, backupCount=2, encoding="utf-8")
    _handler.setFormatter(logging.Formatter("%(asctime)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
    _logger.addHandler(_handler)


def _pretty(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, indent=2)
    return str(value)


def log_exchange(
    api_name: str,
    endpoint: str,
    request_payload: dict,
    request_body: Optional[dict],
    http_status: Optional[int],
    response_body: Any,
    response_payload: Any,
    mock: bool = False,
) -> None:
    _logger.info(
        "\n========== %s%s ==========\n"
        "endpoint: %s\n"
        "--- request (descifrado) ---\n%s\n"
        "--- request (cifrado, enviado) ---\n%s\n"
        "--- response HTTP %s (crudo) ---\n%s\n"
        "--- response (descifrado) ---\n%s\n",
        api_name, " [MOCK]" if mock else "",
        endpoint,
        _pretty(request_payload),
        _pretty(request_body),
        http_status, _pretty(response_body),
        _pretty(response_payload),
    )
