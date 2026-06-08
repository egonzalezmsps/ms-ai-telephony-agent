"""
state/session.py

Estado de sesión de ReniAgent — simplificado para arquitectura Strands nativa.

En Strands no necesitamos los flags del router (awaiting_*, active_scenario, etc.)
porque el modelo razona directamente. Solo necesitamos:
1. Datos del cliente (quién es, qué plan tiene)
2. Plan recomendado (calculado una vez al inicio)
3. Estado de la contratación (si ya aceptó y qué plan)
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SessionState:
    """Estado de sesión minimalista para ReniAgent Strands."""

    # ── Identidad ─────────────────────────────────────────────────
    first_name: str = ""
    full_name: str = ""
    phone_number: str = ""

    # ── Plan actual ───────────────────────────────────────────────
    current_plan_name: str = ""
    current_cost: float = 0.0
    current_plan_gb: Optional[float] = None
    current_plan_cashback: Optional[float] = None
    subscription_type: str = "Abierto"      # "Abierto" | "Controlado"

    # ── Promoción ─────────────────────────────────────────────────
    has_promotion: bool = True
    fecha_vigencia: str = "30/05/2026"

    # ── Perfil de uso ─────────────────────────────────────────────
    usage_summary: Optional[str] = None

    # ── Contratación ─────────────────────────────────────────────
    plan_selected: Optional[str] = None     # plan que el cliente aceptó activar
    stage: str = "PERSUASION"               # PERSUASION | CONTRACT | POST_SALE | END

    # ── Titular ───────────────────────────────────────────────────
    is_titular: bool = True

    # ── Flujo de contratación ─────────────────────────────────────
    awaiting_contract_confirmation: bool = False
    awaiting_otp: bool = False
    otp_sent: bool = False
    otp_attempt_count: int = 0
    otp_resend_count: int = 0
    is_authenticated: bool = False
    authentication_locked: bool = False
    contract_folio: Optional[str] = None

