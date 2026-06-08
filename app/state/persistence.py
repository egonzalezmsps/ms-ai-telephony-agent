"""
state/persistence.py

Persistencia de sesiones y historial de conversación en PostgreSQL.

Guarda:
- SessionState (datos del cliente y estado de la conversación)
- Historial de mensajes (para que el agente recuerde el contexto)
"""

import json
import os
from datetime import datetime, timedelta
from typing import Optional, List

from sqlalchemy import create_engine, Column, String, Text, DateTime, JSON
from sqlalchemy.orm import declarative_base, sessionmaker, Session

Base = declarative_base()


class ConversationSession(Base):
    """Sesión activa de un cliente."""
    __tablename__ = "conversation_sessions"

    phone_number = Column(String(20), primary_key=True)
    session_data = Column(JSON, nullable=False)       # SessionState serializado
    history = Column(JSON, nullable=False, default=list)  # historial de mensajes
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)


# ── Engine ────────────────────────────────────────────────────────────────────

def _get_engine():
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise ValueError("DATABASE_URL no está configurada en el .env")
    return create_engine(url, pool_pre_ping=True)


def init_db():
    """Crea las tablas si no existen."""
    engine = _get_engine()
    Base.metadata.create_all(engine)
    return engine


def _get_session_factory():
    engine = init_db()
    return sessionmaker(bind=engine)


# ── Session TTL ───────────────────────────────────────────────────────────────

SESSION_TTL_HOURS = int(os.environ.get("SESSION_TTL_HOURS", "24"))


def _expiry() -> datetime:
    return datetime.utcnow() + timedelta(hours=SESSION_TTL_HOURS)


# ── CRUD ──────────────────────────────────────────────────────────────────────

def load_session(phone_number: str) -> Optional[dict]:
    """
    Carga la sesión de un cliente desde PostgreSQL.
    Retorna None si no existe o expiró.
    """
    factory = _get_session_factory()
    with factory() as db:
        record = db.query(ConversationSession).filter_by(
            phone_number=phone_number
        ).first()

        if not record:
            return None

        # Verificar expiración
        if record.expires_at < datetime.utcnow():
            db.delete(record)
            db.commit()
            return None

        return {
            "session_data": record.session_data,
            "history": record.history or [],
        }


def save_session(phone_number: str, session_data: dict, history: List[dict]):
    """
    Guarda o actualiza la sesión de un cliente en PostgreSQL.
    """
    factory = _get_session_factory()
    with factory() as db:
        record = db.query(ConversationSession).filter_by(
            phone_number=phone_number
        ).first()

        if record:
            record.session_data = session_data
            record.history = history
            record.updated_at = datetime.utcnow()
            record.expires_at = _expiry()
        else:
            record = ConversationSession(
                phone_number=phone_number,
                session_data=session_data,
                history=history,
                expires_at=_expiry(),
            )
            db.add(record)

        db.commit()


def delete_session(phone_number: str):
    """Elimina la sesión de un cliente."""
    factory = _get_session_factory()
    with factory() as db:
        record = db.query(ConversationSession).filter_by(
            phone_number=phone_number
        ).first()
        if record:
            db.delete(record)
            db.commit()
