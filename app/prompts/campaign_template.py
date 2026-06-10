"""
prompts/campaign_template.py

Mensaje inicial de campaña determinístico (sin LLM).
Replica el comportamiento del proyecto LangGraph original.
"""

from app.catalog.plans import recommend_plan, get_price, get_cashback
from app.state.session import SessionState


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
    bullets.append("• 🎬 Claro Video incluido")

    footer = "\n¿Le gustaría activarlo?\n\nResponda STOP para no recibir más mensajes."

    return header + "\n".join(bullets) + footer
