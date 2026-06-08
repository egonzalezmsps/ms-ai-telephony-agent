"""
tools/telcel_tools.py

Herramienta de acción de ReniAgent.

El catálogo de planes y la lógica de objeciones/derivaciones están en el
system prompt. El agente solo necesita una herramienta para registrar
el momento en que el cliente confirma que quiere activar un plan.
"""

from strands import tool
from app.catalog.plans import find_plan, get_price, get_cashback


def make_tools(state):
    """Fabrica las herramientas de acción para una sesión específica."""

    @tool
    def iniciar_contratacion(plan_id: str) -> str:
        """
        Inicia el proceso de contratación cuando el cliente confirma que quiere
        activar un plan. Úsala SOLO cuando el cliente haya dado una confirmación
        clara de querer activar (acepto, sí quiero, actívalo, confirmo).

        Args:
            plan_id: ID exacto del plan a contratar. Ej: "Telcel Libre 5"
        """
        plan = find_plan(plan_id)
        if not plan:
            return (
                f"No encontré el plan '{plan_id}' en el catálogo. "
                f"Verifica el nombre con el cliente antes de iniciar la contratación."
            )

        modality = state.subscription_type
        price = get_price(plan, modality)
        cashback = get_cashback(plan, modality)
        has_promo = bool(state.has_promotion)

        if price < state.current_cost - 1.0:
            return (
                f"⚠️ El plan {plan.plan_id} (${price:.0f}/mes) está por debajo de la renta "
                f"actual del cliente (${state.current_cost:.0f}/mes). "
                f"No se puede contratar en este canal. "
                f"Informa al cliente con amabilidad y deriva al Soporte 800 220 9518 "
                f"para gestionar excepciones."
            )

        gb = plan.gb_promo if (has_promo and plan.gb_promo > plan.gb_base) else plan.gb_base
        gb_label = "Ilimitados" if plan.is_unlimited else f"{gb:g} GB"
        if has_promo and plan.gb_promo > plan.gb_base and not plan.is_unlimited:
            extra = plan.gb_promo - plan.gb_base
            gb_label = f"{plan.gb_base:g} GB base + {extra:g} GB promo = {gb:g} GB totales"

        state.plan_selected = plan.plan_id
        state.stage = "CONTRACT"

        return (
            f"CONTRATACIÓN INICIADA — presenta este resumen al cliente y solicita confirmación explícita:\n\n"
            f"┌─────────────────────────────────────┐\n"
            f"  Resumen de activación\n\n"
            f"  📋 Plan: *{plan.plan_id} {modality}*\n"
            f"  💰 Costo mensual: *${price:.0f} MXN/mes*\n"
            f"  📶 Datos: *{gb_label}*\n"
            f"  {'💰 Cashback: *$' + f'{cashback:.2f}' + '/mes*' + chr(10) if cashback > 0 else ''}"
            f"  📱 Beneficios: incluidos según familia {plan.family}\n\n"
            f"  Plan anterior: {state.current_plan_name} (${state.current_cost:.0f}/mes)\n"
            f"└─────────────────────────────────────┘\n\n"
            f"Pide al cliente que confirme con ACEPTO o CONFIRMO para proceder con la activación. "
            f"El cambio es definitivo y no se puede revertir al plan anterior."
        )

    return [iniciar_contratacion]
