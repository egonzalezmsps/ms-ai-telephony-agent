"""
prompts/campaign_template.py

Mensaje inicial de campaña determinístico (sin LLM).
Replica el comportamiento del proyecto LangGraph original.
"""

from typing import Optional
from app.catalog.plans import recommend_plan, get_price, get_cashback
from app.state.session import SessionState


import os as _os
TEMPLATE_LIBRE = _os.environ.get("TEMPLATE_LIBRE", "template_telcel_libre")
TEMPLATE_ULTRA = _os.environ.get("TEMPLATE_ULTRA", "template_telcel_ultra")

import datetime as _dt
from zoneinfo import ZoneInfo as _ZoneInfo
DEPLOY_TIMESTAMP = _os.environ.get("DEPLOY_TIMESTAMP") or _dt.datetime.now(_ZoneInfo("America/Mexico_City")).strftime("%Y-%m-%d %H:%M:%S")
OCI_MODEL_NAME = _os.environ.get("OCI_MODEL_ID", "desconocido")

# Cuerpos de plantilla con marcadores {{N}} — espejo exacto de las plantillas WhatsApp
# aprobadas en Meta (template_telcel_libre / template_telcel_ultra). La palabra
# "Abierto" y la frase "Con este plan obtendrá..." ya vienen fijas en el cuerpo
# aprobado — no son variables.
_BODY_LIBRE = (
    "Hola, *{{1}}* 👋\n"
    "En *Telcel* queremos que disfrute de una mejor experiencia. Por ello, tenemos una "
    "oferta especial para usted: cambie a *{{2}} Abierto* por solo *${{3}} MXN* al mes.\n\n"
    "Con este plan obtendrá más conectividad y mejores beneficios para aprovechar al "
    "máximo su servicio:\n\n"
    "• 📞 *Minutos y SMS ilimitados* en México, Estados Unidos y Canadá\n"
    "• 📈 *{{4}} GB* de datos\n"
    "• 📱 *Apps Ilimitadas* (WhatsApp, Facebook, Messenger, X, Instagram, Snapchat, Uber)\n"
    "• 💰 *Cashback de ${{5}} MXN/mes*\n"
    "• 🎬 *Claro Video y Claro Drive (20 GB)*\n\n"
    "¿Le gustaría comparar su plan actual con esta nueva opción para conocer exactamente "
    "qué beneficios adicionales obtendría?"
)

_BODY_ULTRA = (
    "Hola, *{{1}}* 👋\n"
    "En *Telcel* queremos que disfrute de una mejor experiencia. Por ello, tenemos una "
    "oferta especial para usted: cambie a *{{2}} Abierto* por solo *${{3}} MXN* al mes.\n\n"
    "Con este plan obtendrá más conectividad y mejores beneficios para aprovechar al "
    "máximo su servicio:\n\n"
    "• 📞 *Minutos y SMS ilimitados* en México, Estados Unidos y Canadá\n"
    "• 📈 *{{4}} GB* de datos\n"
    "• ✉️ *WhatsApp Ilimitado*\n"
    "• 🎬 *Claro Video y Claro Drive (20 GB)*\n\n"
    "¿Le gustaría comparar su plan actual con esta nueva opción para conocer exactamente "
    "qué beneficios adicionales obtendría?"
)


def _render_template(body: str, params: list) -> str:
    """Sustituye los marcadores {{N}} con los valores de params."""
    text = body
    for i, value in enumerate(params, start=1):
        text = text.replace("{{" + str(i) + "}}", value)
    return text


def build_template_params(session: SessionState) -> Optional[dict]:
    """
    Returns {"template_name": str, "params": list} for the correct WhatsApp template.
    Returns None if no eligible plan exists for this customer.

    Telcel Libre  → TEMPLATE_LIBRE  — 5 params: nombre, plan, precio, GB, cashback
    Telcel Ultra  → TEMPLATE_ULTRA  — 4 params: nombre, plan, precio, GB

    "Abierto" y la frase de introducción ya vienen fijas en el cuerpo aprobado
    en Meta — no se envían como variables.
    """
    target = recommend_plan(session.current_cost, session.subscription_type)
    if not target:
        return None

    price = get_price(target, session.subscription_type)
    cashback = get_cashback(target, session.subscription_type)
    has_promo = bool(session.has_promotion)

    if has_promo and target.gb_promo > target.gb_base and price > session.current_cost + 1.0:
        gb_value = target.gb_promo
    else:
        gb_value = target.gb_base
    gb_str = "Ilimitados" if target.is_unlimited else f"{gb_value:g}"

    if target.family == "Telcel Libre":
        return {
            "template_name": TEMPLATE_LIBRE,
            "params": [
                session.first_name,       # {{1}} nombre
                target.plan_id,           # {{2}} plan (sin modalidad — "Abierto" es texto fijo)
                f"{price:.0f}",           # {{3}} precio
                gb_str,                   # {{4}} GB
                f"{cashback:.2f}",        # {{5}} cashback
            ],
        }
    else:  # Telcel Ultra
        return {
            "template_name": TEMPLATE_ULTRA,
            "params": [
                session.first_name,       # {{1}} nombre
                target.plan_id,           # {{2}} plan (sin modalidad — "Abierto" es texto fijo)
                f"{price:.0f}",           # {{3}} precio
                gb_str,                   # {{4}} GB
            ],
        }


def build_campaign_message(session: SessionState) -> str:
    """
    Genera el mensaje inicial de campaña de forma determinística.
    Simula el renderizado de la plantilla WhatsApp sustituyendo los marcadores {{N}}.
    No llama al LLM — el texto es fijo con datos del catálogo.
    """
    result = build_template_params(session)

    if not result:
        msg = (
            f"Hola, *{session.first_name}*. En *Telcel* buscamos mejorar la experiencia "
            f"de nuestros planes.\n\n"
            f"Por el momento no tenemos una oferta disponible para su línea. "
            f"Para más información contáctenos al *800 220 9518*."
        )
        if DEPLOY_TIMESTAMP:
            msg += f"\n\n_(deploy: {DEPLOY_TIMESTAMP})_"
            msg += f"\n_(modelo: {OCI_MODEL_NAME})_"
        return msg

    body = _BODY_LIBRE if result["template_name"] == TEMPLATE_LIBRE else _BODY_ULTRA
    msg = _render_template(body, result["params"])
    if DEPLOY_TIMESTAMP:
        msg += f"\n\n_(deploy: {DEPLOY_TIMESTAMP})_"
        msg += f"\n_(modelo: {OCI_MODEL_NAME})_"
    return msg
