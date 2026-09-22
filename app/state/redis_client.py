"""
state/redis_client.py

Locks distribuidos y deduplicación de mensajes en Redis — reemplazan los mecanismos
en memoria (threading.Lock / set) que no funcionan entre pods distintos al escalar
horizontalmente.
"""

import os
import uuid
from typing import Optional

import redis

_client: Optional[redis.Redis] = None


def get_redis_client() -> redis.Redis:
    global _client
    if _client is None:
        host = os.environ.get("REDIS_HOST", "")
        if not host:
            raise ValueError("REDIS_HOST no está configurada en el entorno")
        port = int(os.environ.get("REDIS_PORT", "6379"))
        password = os.environ.get("REDIS_PASSWORD") or None
        _client = redis.Redis(
            host=host,
            port=port,
            password=password,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
    return _client


def acquire_phone_lock(phone_number: str, ttl_seconds: int = 120) -> Optional[str]:
    """
    Intenta tomar el lock distribuido para un teléfono.
    Retorna un token si lo consigue (necesario para liberarlo de forma segura),
    o None si ya está tomado por otro turno en curso.
    """
    client = get_redis_client()
    token = uuid.uuid4().hex
    got = client.set(f"phone_lock:{phone_number}", token, nx=True, ex=ttl_seconds)
    return token if got else None


def release_phone_lock(phone_number: str, token: str) -> None:
    """
    Libera el lock solo si el token coincide — evita liberar un lock ajeno si el
    propio ya expiró y otro pod lo tomó mientras tanto.
    """
    client = get_redis_client()
    key = f"phone_lock:{phone_number}"
    if client.get(key) == token:
        client.delete(key)


def is_duplicate_message(msg_id: str, ttl_seconds: int = 600) -> bool:
    """True si el msg_id ya fue procesado recientemente (reintento de Meta)."""
    client = get_redis_client()
    got = client.set(f"wa_msg:{msg_id}", "1", nx=True, ex=ttl_seconds)
    return not got
