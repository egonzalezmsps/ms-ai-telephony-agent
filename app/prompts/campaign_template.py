"""
prompts/campaign_template.py

Mensaje inicial de campaña determinístico (sin LLM).
Replica el comportamiento del proyecto LangGraph original.
"""

from typing import Optional
from app.catalog.plans import recommend_plan, get_price, get_cashback
from app.state.session import SessionState


import os as _os
TEMPLATE_LIBRE = _os.environ.get("TEMPLATE_LIBRE", "telcel_migration_campaing_1_libre")
TEMPLATE_ULTRA = _os.environ.get("TEMPLATE_ULTRA", "telcel_migration_campaing__1_ultra")

TEMPLATE_HEADER = "Evolucione su plan con Telcel ahora sin plazos forzosos"

# Cuerpos de plantilla con marcadores {{N}} — espejo exacto de las plantillas WhatsApp
_BODY_LIBRE = (
    "Hola, {{1}} 👋. En *Telcel* buscamos mejorar la experiencia de nuestros planes, "
    "por eso le ofrecemos el *{{2}}* a *${{3}} MXN/mes*.\n"
    "*{{4}}*\n"
    "• 📞 Minutos y SMS ilimitados (México, EUA, Cánada)\n"
    "• 📈 *{{5}}*\n"
    "• 📱 Apps Ilimitadas (WhatsApp, Facebook, Messenger, X, Instagram, Snapchat, Uber)\n"
    "• 💰 *Cashback de ${{6}} MXN/mes*\n"
    "• 🎬 *Claro Video*\n"
    "• 💾 *Claro Drive con 20 GB de almacenamiento*\n"
    "\n"
    "¿Le gustaría activarlo?"
)

_BODY_ULTRA = (
    "Hola, {{1}} 👋. En *Telcel* buscamos mejorar la experiencia de nuestros planes, "
    "por eso le ofrecemos el *{{2}}* a *${{3}} MXN/mes*.\n"
    "*{{4}}*\n"
    "• Minutos y SMS ilimitados (México, EUA, Cánada)\n"
    "• 📈 *{{5}}*\n"
    "• ✉ *WhatsApp Ilimitado*\n"
    "• 🎬 *Claro Video*\n"
    "• 💾 *Claro Drive con 20 GB de almacenamiento*\n"
    "¿Le gustaría activarlo?"
)


def _render_template(body: str, params: list) -> str:
    """Sustituye los marcadores {{N}} con los valores de params y antepone el header."""
    text = body
    for i, value in enumerate(params, start=1):
        text = text.replace("{{" + str(i) + "}}", value)
    return f"*{TEMPLATE_HEADER}*\n\n{text}"


def build_template_params(session: SessionState) -> Optional[dict]:
    """
    Returns {"template_name": str, "params": list} for the correct WhatsApp template.
    Returns None if no eligible plan exists for this customer.

    Telcel Libre  → TEMPLATE_LIBRE  — 6 params: nombre, plan, precio, hook, datos, cashback
    Telcel Ultra  → TEMPLATE_ULTRA  — 5 params: nombre, plan, precio, hook, GB
    """
    target = recommend_plan(session.current_cost, session.subscription_type)
    if not target:
        return None

    price = get_price(target, session.subscription_type)
    cashback = get_cashback(target, session.subscription_type)
    has_promo = bool(session.has_promotion)
    plan_name = f"{target.plan_id} {session.subscription_type}"

    hook = (
        "Mantenga su renta actual con más beneficios para su línea:"
        if abs(price - session.current_cost) < 1
        else "Disfrute de más datos y beneficios con un plan mejorado:"
    )

    if target.family == "Telcel Libre":
        if has_promo and target.gb_promo > target.gb_base and price > session.current_cost + 1.0:
            extra = target.gb_promo - target.gb_base
            datos = f"{target.gb_base:g} GB + {extra:g} GB de promoción = {target.gb_promo:g} GB de datos"
        else:
            datos = f"{target.gb_base:g} GB de datos"

        return {
            "template_name": TEMPLATE_LIBRE,
            "params": [
                session.first_name,       # {{1}} nombre
                plan_name,                # {{2}} plan
                f"{price:.0f}",           # {{3}} precio
                hook,                     # {{4}} hook
                datos,                    # {{5}} datos
                f"{cashback:.2f}",        # {{6}} cashback
            ],
        }
    else:  # Telcel Ultra
        gb = "GB Ilimitados" if target.is_unlimited else f"{target.gb_base:g} GB de datos"

        return {
            "template_name": TEMPLATE_ULTRA,
            "params": [
                session.first_name,       # {{1}} nombre
                plan_name,                # {{2}} plan
                f"{price:.0f}",           # {{3}} precio
                hook,                     # {{4}} hook
                gb,                       # {{5}} GB
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
        return (
            f"Hola, *{session.first_name}*. En *Telcel* buscamos mejorar la experiencia "
            f"de nuestros planes.\n\n"
            f"Por el momento no tenemos una oferta disponible para su línea. "
            f"Para más información contáctenos al *800 220 9518*."
        )

    body = _BODY_LIBRE if result["template_name"] == TEMPLATE_LIBRE else _BODY_ULTRA
    return _render_template(body, result["params"])
