"""
prompts/system_prompt.py

Construye el system prompt completo para cada turno.
Combina las reglas generales + contexto del cliente + catálogo de planes.
"""

from app.prompts.general_rules import GENERAL_RULES
from app.catalog.plans import (
    CATALOG, recommend_plan,
    get_price, get_cashback, get_legacy_gb,
)


def _gb_str(plan, has_promo: bool, price: float, current_cost: float) -> str:
    if plan.is_unlimited:
        return "Ilimitados (PUJ)"
    plan_has_promo = has_promo and price > current_cost + 1.0
    if plan_has_promo and plan.gb_promo > plan.gb_base and plan.family == "Telcel Libre":
        extra = plan.gb_promo - plan.gb_base
        return f"{plan.gb_base:g}+{extra:g} promo={plan.gb_promo:g} GB"
    return f"{plan.gb_base:g} GB"


def _table_row(plan_name: str, price: float, gb: str, cashback: float, canal: str = "") -> str:
    cashback_str = f"${cashback:.2f}/mes" if cashback > 0 else "—"
    row = f"{plan_name} | ${price:.0f}/mes | {gb} | {cashback_str}"
    if canal:
        row += f" | {canal}"
    return row


def build_catalog_block(session) -> str:
    """
    Genera el catálogo completo de planes como bloque de texto para inyectar
    en el system prompt. Una sola tabla con columna CANAL por cada plan.
    """
    modality = session.subscription_type
    has_promo = bool(session.has_promotion)
    current_cost = session.current_cost
    alt_modality = "Abierto" if modality == "Controlado" else "Controlado"

    header = (
        f"# CATÁLOGO OFICIAL TELCEL — DATOS EXACTOS Y VIGENTES\n"
        f"INSTRUCCIÓN CRÍTICA: Los únicos precios, GB y cashback válidos son\n"
        f"los que aparecen en este catálogo. Cualquier dato que no aparezca\n"
        f"aquí NO existe. NUNCA uses memoria general para datos de planes.\n"
        f"\n"
        f"MODALIDAD DEL CLIENTE: {modality}\n"
        f"TODOS los precios son en modalidad {modality} salvo que se indique\n"
        f"explícitamente lo contrario."
    )

    table_header_canal = "Plan | Precio | GB | Cashback | Canal\n-----|--------|----|---------|---------"
    table_header_plain = "Plan | Precio | GB | Cashback\n-----|--------|----|---------"

    activable = [p for p in CATALOG if get_price(p, modality) >= current_cost - 1.0]
    informative = [p for p in CATALOG if get_price(p, modality) < current_cost - 1.0]

    lines = [header, ""]

    lines.append(
        f"PLANES ACTIVABLES EN ESTE CANAL — MODALIDAD {modality} (precio >= ${current_cost:.0f}/mes):\n"
        f"Todos se activan directamente en esta conversación. NO requieren CAC.\n"
        f"CAC solo aplica para cambio de modalidad ({alt_modality}) o planes más baratos."
    )
    lines.append(table_header_canal)

    for plan in activable:
        price = get_price(plan, modality)
        cashback = get_cashback(plan, modality)
        gb = _gb_str(plan, has_promo, price, current_cost)
        lines.append(_table_row(f"{plan.plan_id} {modality}", price, gb, cashback, "✅ ESTE CANAL"))

    if informative:
        cheapest = min(informative, key=lambda p: get_price(p, modality))
        cheapest_price = get_price(cheapest, modality)
        cheapest_gb = _gb_str(cheapest, has_promo, cheapest_price, current_cost)
        cheapest_cashback = get_cashback(cheapest, modality)
        lines.append(
            f"\nPLAN INFORMATIVO MÁS ECONÓMICO "
            f"(solo mostrar si el cliente pide explícitamente algo más barato):\n"
            f"{cheapest.plan_id} {modality} | ${cheapest_price:.0f}/mes | {cheapest_gb} "
            f"| {f'${cheapest_cashback:.2f}/mes' if cheapest_cashback > 0 else '—'} | ⛔ Soporte/CAC\n"
            f"\n"
            f"TODOS los demás planes más baratos que ${current_cost:.0f}/mes existen pero "
            f"NO los menciones — si el cliente los pide, indica que puede consultar en "
            f"Soporte 800 220 9518."
        )

    if has_promo and any(
        p.family == "Telcel Libre" and get_price(p, modality) > current_cost + 1.0
        for p in activable
    ):
        lines.append(f"\nNota: GB de promoción por 24 meses desde la activación.")

    # Modalidad alternativa (todos requieren CAC — sin columna Canal)
    alt_activable = [
        (plan, get_price(plan, alt_modality))
        for plan in CATALOG
        if get_price(plan, alt_modality) >= current_cost - 1.0
    ]

    lines.append("")
    lines.append(
        f"# PRECIOS EN MODALIDAD ALTERNATIVA — {alt_modality} (solo informativo)\n"
        f"Para activar en modalidad {alt_modality} el cliente debe ir al CAC.\n"
        f"Solo se muestran planes con precio igual o superior a la renta actual "
        f"del cliente (${current_cost:.0f}/mes). Para planes más baratos en esta "
        f"modalidad, el cliente debe solicitarlos explícitamente."
    )
    lines.append(table_header_plain)
    for plan, alt_price in alt_activable:
        alt_cashback = get_cashback(plan, alt_modality)
        alt_gb = _gb_str(plan, has_promo, alt_price, current_cost)
        lines.append(_table_row(f"{plan.plan_id} {alt_modality}", alt_price, alt_gb, alt_cashback))

    return "\n".join(lines)


def build_system_prompt(session) -> str:
    """
    Construye el system prompt inyectando el contexto del cliente y el catálogo completo.
    El catálogo va en el prompt — el agente ya no necesita herramientas para consultar planes.
    """

    # Plan recomendado como contexto de apertura
    target = recommend_plan(session.current_cost, session.subscription_type)
    target_block = ""
    if target:
        price = get_price(target, session.subscription_type)
        cashback = get_cashback(target, session.subscription_type)
        has_promo = session.has_promotion

        if has_promo and target.gb_promo > target.gb_base and price > session.current_cost + 1.0:
            gb_label = f"{target.gb_promo:g} GB totales"
        else:
            gb_label = f"{target.gb_base:g} GB"

        target_block = f"""
# PLAN RECOMENDADO PARA ESTE CLIENTE
Plan: {target.plan_id} {session.subscription_type}
Precio: ${price:.0f}/mes
GB: {gb_label}
Cashback: ${cashback:.2f}/mes
{"[INSTRUCCIÓN INTERNA: Este plan NO tiene promoción de GB adicionales. NO menciones promoción, GB extra ni +50%. Solo menciona los GB base del plan.]"
 if abs(price - session.current_cost) <= 1.0 or target.family != "Telcel Libre"
 else "Promoción activa: +50% GB durante 24 meses desde la activación."}

Este es el plan base de tu recomendación.
"""

    titular_note = ""
    if not session.is_titular:
        titular_note = """
# RESTRICCIÓN ACTIVA — USUARIO NO ES EL TITULAR
La persona que escribe no es el titular de la línea.
- Responde preguntas informativas normalmente.
- NO incluyas invitación a activar ni CTA de contratación.
- NO uses el nombre del cliente en las respuestas.
"""

    current_gb = session.current_plan_gb or get_legacy_gb(session.current_plan_name)
    gb_line = (
        f"GB actuales: {current_gb:g} GB"
        if current_gb
        else "GB actuales: no disponibles — no estimes ni inventes este dato"
    )

    client_context = f"""
# CONTEXTO DEL CLIENTE EN ESTA SESIÓN
Nombre: {session.first_name}
Plan actual: {session.current_plan_name} {session.subscription_type} — ${session.current_cost:.0f}/mes
{gb_line}
{f"Cashback actual: ${session.current_plan_cashback:.2f}/mes" if session.current_plan_cashback and session.current_plan_cashback > 0 else ""}
Modalidad: {session.subscription_type}
{f"Perfil de uso: {session.usage_summary}" if session.usage_summary else ""}
"""

    reasons_block = f"""
# RAZONES DE LA RECOMENDACIÓN
Estas son las razones exactas por las que se le ofrece este plan a este cliente.
Úsalas cuando el cliente pregunte por qué.

1. MODALIDAD {session.subscription_type}:
   Se le ofrece modalidad {session.subscription_type} porque es la misma
   que tiene en su plan actual. La modalidad no puede cambiar en este canal —
   para cambiarla debe acudir a un CAC.

2. FAMILIA TELCEL LIBRE:
   Se le recomienda Telcel Libre (y no Telcel Ultra) porque la campaña está
   orientada a planes con cashback y apps ilimitadas, que son beneficios
   exclusivos de la familia Telcel Libre. Telcel Ultra no incluye cashback
   ni apps ilimitadas.

3. PROMOCIÓN DE GB:
   {("El plan recomendado tiene GB de promoción porque su precio es mayor a su renta actual ($"
     + f"{session.current_cost:.0f}"
     + "/mes). La promoción aplica en planes de migración hacia arriba. Si el plan tuviera "
     + "el mismo precio que su renta actual, no tendría GB adicionales de promoción.")
    if target and get_price(target, session.subscription_type) > session.current_cost + 1.0
    else "El plan recomendado no tiene promoción de GB porque su precio es igual a su renta actual."}
"""

    catalog_block = build_catalog_block(session)

    return (
        f"{GENERAL_RULES}\n"
        f"{client_context}\n"
        f"{reasons_block}\n"
        f"{target_block}\n"
        f"{titular_note}\n"
        f"{catalog_block}"
    )
