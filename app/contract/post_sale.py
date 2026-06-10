"""
contract/post_sale.py

Mensaje de confirmación post-venta (template fijo, sin LLM).
"""

from app.state.session import SessionState


def build_post_sale_message(session: SessionState) -> str:
    return (
        f"✅ *Su cambio de plan ha sido confirmado.*\n\n"
        f"📋 *Folio de contratación:* {session.contract_folio}\n"
        f"📱 *Su número:* {session.phone_number}\n\n"
        f"🔄 *Detalle del cambio:*\n"
        f"- Plan anterior: {session.current_plan_name}\n"
        f"- Plan nuevo: {session.plan_selected}\n\n"
        f"⚠️ *Aviso importante:*\n"
        f"Este cambio es definitivo y no podrá revertirse al plan anterior.\n\n"
        f"Gracias por su preferencia, {session.first_name}. ¡Es un placer servirle!\n"
        f"_Telcel, siempre conectándote._"
    )
