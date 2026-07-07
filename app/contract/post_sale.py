"""
contract/post_sale.py

Mensaje de confirmación post-venta (template fijo, sin LLM).
"""

from app.state.session import SessionState


def build_post_sale_message(session: SessionState) -> str:
    message = (
        f"🔄 *Estamos procesando su cambio de plan.*\n\n"
        f"📱 *Su número:* {session.phone_number}\n\n"
        f"🔄 *Detalle del cambio:*\n"
        f"- Plan anterior: {session.current_plan_name}\n"
        f"- Plan nuevo: {session.plan_selected}\n\n"
        f"⚠️ *Aviso importante:*\n"
        f"Este cambio es definitivo y no podrá revertirse al plan anterior.\n\n"
        f"En breve nos contactaremos para dar seguimiento a su cambio.\n\n"
        f"Gracias por su preferencia, {session.first_name}. ¡Es un placer servirle!\n"
        f"_Telcel, siempre conectándote._"
    )

    # Actualizar el plan actual del cliente al plan nuevo
    if session.plan_selected:
        from app.catalog.plans import find_plan, get_price
        plan_obj = find_plan(session.plan_selected)
        if plan_obj:
            session.previous_plan_name = session.current_plan_name
            session.current_plan_name = plan_obj.plan_id
            session.current_cost = get_price(plan_obj, session.subscription_type)

    return message
