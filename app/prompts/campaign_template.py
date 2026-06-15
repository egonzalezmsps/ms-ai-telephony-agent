"""
prompts/campaign_template.py

Mensaje inicial de campaña determinístico (sin LLM).
Replica el comportamiento del proyecto LangGraph original.
"""

from typing import Optional
from app.catalog.plans import recommend_plan, get_price, get_cashback
from app.state.session import SessionState


TEMPLATE_LIBRE = "telcel_migration_campaing_1_libre"
TEMPLATE_ULTRA = "telcel_migration_campaing__1_ultra"


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
    No llama al LLM — el texto es fijo con datos del catálogo.
    """
    target = recommend_plan(session.current_cost, session.subscription_type)

    if not target:
        return (
            f"Hola, *{session.first_name}*. En *Telcel* buscamos mejorar la experiencia "
            f"de nuestros planes.\n\n"
            f"Por el momento no tenemos una oferta disponible para su línea. "
            f"Para más información contáctenos al *800 220 9518*."
        )

    price = get_price(target, session.subscription_type)
    cashback = get_cashback(target, session.subscription_type)
    has_promo = bool(session.has_promotion)
    plan_name = f"{target.plan_id} {session.subscription_type}"

    # price_context
    if abs(price - session.current_cost) < 1:
        price_context = f"Manteniendo su renta de ${session.current_cost:.0f}/mes."
    else:
        price_context = f"A ${price:.0f}/mes, con más GB y beneficios."

    header = (
        f"Evolucione su plan con Telcel\n\n"
        f"Hola, *{session.first_name}*. En *Telcel* buscamos mejorar la experiencia "
        f"de nuestros planes.\n\n"
        f"Por eso le ofrecemos *{plan_name}* con más beneficios para su línea.\n\n"
        f"{price_context}\n\n"
    )

    # Bullet de GB
    if target.is_unlimited:
        gb_bullet = "• 📶 GB Ilimitados"
    elif has_promo and target.gb_promo > target.gb_base and price > session.current_cost + 1.0:
        extra = target.gb_promo - target.gb_base
        gb_bullet = (
            f"• 📶 {target.gb_base:g} GB + {extra:g} GB de promoción "
            f"= {target.gb_promo:g} GB de datos"
        )
    else:
        gb_bullet = f"• 📶 {target.gb_base:g} GB de datos"

    bullets = [gb_bullet]

    if cashback > 0:
        bullets.append(f"• 💰 Cashback de ${cashback:.0f} MXN/mes")

    bullets.append("• 💾 Claro Drive con 20 GB de almacenamiento")
    bullets.append("• 🎬 Amazon Prime incluido")

    footer = "\n¿Le gustaría activarlo?\n\nResponda STOP para no recibir más mensajes."

    return header + "\n".join(bullets) + footer
