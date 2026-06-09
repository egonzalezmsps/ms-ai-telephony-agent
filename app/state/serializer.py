"""
state/serializer.py

Convierte SessionState a dict (para guardar en DB) y viceversa.
"""

from app.state.session import SessionState


def session_to_dict(session: SessionState) -> dict:
    """Serializa SessionState a dict para guardar en PostgreSQL."""
    return {
        "first_name": session.first_name,
        "full_name": session.full_name,
        "phone_number": session.phone_number,
        "current_plan_name": session.current_plan_name,
        "current_cost": session.current_cost,
        "current_plan_gb": session.current_plan_gb,
        "current_plan_cashback": session.current_plan_cashback,
        "subscription_type": session.subscription_type,
        "has_promotion": session.has_promotion,
        "fecha_vigencia": session.fecha_vigencia,
        "usage_summary": session.usage_summary,
        "plan_selected": session.plan_selected,
        "stage": session.stage,
        "is_titular": session.is_titular,
        "nombre_incorrecto": session.nombre_incorrecto,
        "cac_nombre_incorrecto_shown": session.cac_nombre_incorrecto_shown,
        "post_not_titular": session.post_not_titular,
        "awaiting_contract_confirmation": session.awaiting_contract_confirmation,
        "awaiting_otp": session.awaiting_otp,
        "otp_sent": session.otp_sent,
        "otp_attempt_count": session.otp_attempt_count,
        "otp_resend_count": session.otp_resend_count,
        "is_authenticated": session.is_authenticated,
        "authentication_locked": session.authentication_locked,
        "contract_folio": session.contract_folio,
    }


def dict_to_session(data: dict) -> SessionState:
    """Deserializa un dict de PostgreSQL a SessionState."""
    return SessionState(
        first_name=data.get("first_name", ""),
        full_name=data.get("full_name", ""),
        phone_number=data.get("phone_number", ""),
        current_plan_name=data.get("current_plan_name", ""),
        current_cost=float(data.get("current_cost", 0)),
        current_plan_gb=data.get("current_plan_gb"),
        current_plan_cashback=data.get("current_plan_cashback"),
        subscription_type=data.get("subscription_type", "Abierto"),
        has_promotion=data.get("has_promotion", True),
        fecha_vigencia=data.get("fecha_vigencia", "30/05/2026"),
        usage_summary=data.get("usage_summary"),
        plan_selected=data.get("plan_selected"),
        stage=data.get("stage", "PERSUASION"),
        is_titular=data.get("is_titular", True),
        nombre_incorrecto=bool(data.get("nombre_incorrecto", False)),
        cac_nombre_incorrecto_shown=bool(data.get("cac_nombre_incorrecto_shown", False)),
        post_not_titular=bool(data.get("post_not_titular", False)),
        awaiting_contract_confirmation=bool(data.get("awaiting_contract_confirmation", False)),
        awaiting_otp=bool(data.get("awaiting_otp", False)),
        otp_sent=bool(data.get("otp_sent", False)),
        otp_attempt_count=int(data.get("otp_attempt_count", 0)),
        otp_resend_count=int(data.get("otp_resend_count", 0)),
        is_authenticated=bool(data.get("is_authenticated", False)),
        authentication_locked=bool(data.get("authentication_locked", False)),
        contract_folio=data.get("contract_folio"),
    )
