"""
tools/telcel_tools.py

Herramienta de acción de ReniAgent.

El catálogo de planes y la lógica de objeciones/derivaciones están en el
system prompt. El agente solo necesita una herramienta para registrar
el momento en que el cliente confirma que quiere activar un plan.
"""

import json
import re
import unicodedata

from strands import tool
from app.catalog.plans import (
    CATALOG, find_plan, get_price, get_cashback, recommend_plan, eligible_plans,
)


def quitar_tildes(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )


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

    @tool
    def responder_por_que(tema: str) -> str:
        """
        Responde preguntas del cliente sobre el motivo de la recomendación,
        promociones o modalidad. Úsala cuando el cliente pregunte:
        - "¿por qué me recomiendas este plan?"
        - "¿por qué tiene o no tiene promoción?"
        - "¿por qué esa modalidad?"
        - "¿cuál es el criterio de las promociones?"
        - "¿por qué me ofrecen esto?"
        - "si pago un plan menor, ¿tendría promoción?"
        - "¿los planes más baratos tienen promoción?"
        - "¿cuándo aplican las promociones?"
        - "¿qué planes tienen promoción?"

        Args:
            tema: "plan" | "promocion" | "modalidad" | "criterio"
        """
        target = recommend_plan(state.current_cost, state.subscription_type)
        plan_name = (
            f"{target.plan_id} {state.subscription_type}"
            if target else "el plan recomendado"
        )

        RESPUESTAS = {
            "plan": (
                f"Le recomendamos el {plan_name} porque ofrece más beneficios "
                f"para su perfil: más GB, cashback mensual y apps ilimitadas incluidas."
            ),
            "promocion": (
                f"Las promociones son beneficios que Telcel activa en planes "
                f"seleccionados para darles más valor. "
                f"El {plan_name} sí incluye esta promoción."
            ),
            "modalidad": (
                f"Le ofrecemos planes en modalidad {state.subscription_type} "
                f"porque es la misma que tiene en su plan actual. "
                f"Para cambiar de modalidad puede acudir a un CAC "
                f"o llamar al 800 220 9518."
            ),
            "criterio": (
                f"Las promociones son beneficios que Telcel activa en planes "
                f"seleccionados para darles más valor. "
                f"El {plan_name} sí incluye esta promoción."
            ),
        }

        return RESPUESTAS.get(tema, RESPUESTAS["plan"])

    @tool
    def presentar_planes(criterio: str, tipo: str = "general") -> str:
        """
        Busca y presenta planes o información de apps según la intención del cliente.

        ÚSALA SOLO para preguntas sobre:
        - Planes Telcel (precios, GB, cashback, características)
        - Apps o servicios digitales incluidos en los planes

        NO la uses para preguntas sobre:
        - Garantías, devoluciones, contratos
        - Equipos o dispositivos
        - Facturación o pagos
        - Cualquier tema que no sea planes o apps digitales

        Args:
            criterio: descripción o nombre específico de lo que busca el cliente
            tipo: intención del cliente — elige UNO de:
                "mas_barato"  — quiere un plan más económico que el actual
                "mas_caro"    — quiere el plan más premium/caro disponible
                "ultra"       — pregunta por planes de la familia Telcel Ultra
                "libre"       — pregunta por planes de la familia Telcel Libre
                "especifico"  — pregunta por un plan concreto (por nombre o precio)
                "apps"        — pregunta qué apps están incluidas (criterio = nombre de la app
                                o "general" si no menciona una app específica)
                "general"     — cualquier otra consulta de planes o catálogo
        """
        modality = state.subscription_type
        current_cost = state.current_cost
        has_promo = bool(state.has_promotion)
        eligible = eligible_plans(current_cost, modality)

        def gb_label(plan) -> str:
            price = get_price(plan, modality)
            if plan.is_unlimited:
                return "Datos ilimitados (PUJ)"
            if (has_promo and price > current_cost + 1.0
                    and plan.gb_promo > plan.gb_base
                    and plan.family == "Telcel Libre"):
                extra = plan.gb_promo - plan.gb_base
                return f"{plan.gb_base:g} GB + {extra:g} GB promo = {plan.gb_promo:g} GB"
            return f"{plan.gb_base:g} GB"

        def format_one(plan) -> str:
            price = get_price(plan, modality)
            cashback = get_cashback(plan, modality)
            apps = (
                ["Facebook", "WhatsApp", "Messenger", "X", "Instagram", "Snapchat", "Uber"]
                if plan.family == "Telcel Libre"
                else ["WhatsApp"]
            )
            data = {
                "plan": f"{plan.plan_id} {modality}",
                "precio": price,
                "gb": gb_label(plan),
                "cashback": cashback if cashback > 0 else None,
                "apps_ilimitadas": apps,
                "beneficios": ["Claro Video", "Claro Drive 20 GB"],
                "instruccion": (
                    "USA ÚNICAMENTE estos datos para presentar el plan. "
                    "No agregues GB, cashback ni apps que no estén aquí. "
                    "Redacta de forma natural y persuasiva."
                ),
            }
            return json.dumps(data, ensure_ascii=False)

        def format_many(planes) -> str:
            lista = []
            for p in planes:
                price = get_price(p, modality)
                cashback = get_cashback(p, modality)
                lista.append({
                    "plan": f"{p.plan_id} {modality}",
                    "precio": price,
                    "gb": gb_label(p),
                    "cashback": cashback if cashback > 0 else None,
                })
            data = {
                "planes_disponibles": lista,
                "instruccion": (
                    "USA ÚNICAMENTE estos datos para listar los planes. "
                    "No agregues datos que no estén aquí. "
                    "Presenta cada plan de forma clara y concisa."
                ),
            }
            return json.dumps(data, ensure_ascii=False)

        def no_plans_found() -> str:
            target = recommend_plan(current_cost, modality)
            plan_name = f"{target.plan_id} {modality}" if target else "el plan recomendado"
            return (
                "RESPONDE EXACTAMENTE CON ESTE TEXTO SIN MODIFICAR NADA:\n\n"
                f"No encontré planes que cumplan ese criterio en modalidad {modality}.\n"
                f"Le recomiendo el *{plan_name}* que ya le presentamos."
            )

        if tipo == "apps":
            _LISTA_APPS = ["Facebook", "WhatsApp", "Messenger", "X", "Instagram", "Snapchat", "Uber"]
            APPS_INCLUIDAS = {quitar_tildes(w) for w in {
                "facebook", "whatsapp", "messenger", "x", "twitter",
                "instagram", "snapchat", "uber",
            }}
            app_norm = quitar_tildes(criterio.lower().strip("?¿ "))

            if not app_norm or app_norm in {"general", "apps", "aplicaciones", "redes", "sociales"}:
                return (
                    "RESPONDE EXACTAMENTE CON ESTE TEXTO SIN MODIFICAR NADA:\n\n"
                    "Apps ilimitadas incluidas (no consumen GB de su paquete):\n"
                    "📱 Facebook · WhatsApp · Messenger · X · Instagram · Snapchat · Uber\n\n"
                    "Cualquier otra app (YouTube, TikTok, Netflix, etc.) sí consume GB del plan.\n\n"
                    "Después de este texto agrega la pregunta de activación del plan recomendado."
                )
            if app_norm in APPS_INCLUIDAS:
                return json.dumps({
                    "app_consultada": criterio,
                    "incluida": True,
                    "consume_gb": False,
                    "lista_apps_incluidas": _LISTA_APPS,
                    "instruccion": "USA ÚNICAMENTE estos datos para responder. No agregues apps adicionales ni información de tu conocimiento general.",
                }, ensure_ascii=False)
            if "amazon" in app_norm or "prime" in app_norm:
                return (
                    "RESPONDE EXACTAMENTE CON ESTE TEXTO SIN MODIFICAR NADA:\n\n"
                    "Amazon Prime no forma parte de ningún plan Telcel. Los planes incluyen Claro Video como servicio de streaming."
                )
            if "claro" in app_norm:
                return (
                    "RESPONDE EXACTAMENTE CON ESTE TEXTO SIN MODIFICAR NADA:\n\n"
                    "Claro Video está incluido en todos los planes. Sí consume GB del plan — no es ilimitado."
                )
            return json.dumps({
                "app_consultada": criterio,
                "incluida": False,
                "consume_gb": True,
                "lista_apps_incluidas": _LISTA_APPS,
                "instruccion": "USA ÚNICAMENTE estos datos para responder. No agregues apps adicionales ni información de tu conocimiento general.",
            }, ensure_ascii=False)

        elif tipo == "mas_barato":
            cheaper = [p for p in CATALOG if get_price(p, modality) < current_cost - 1.0]
            if not cheaper:
                return no_plans_found()
            # más cercanos a la renta actual primero (descendente por precio)
            planes_mostrar = sorted(cheaper, key=lambda p: get_price(p, modality), reverse=True)[:3]
            target = recommend_plan(current_cost, modality)
            plan_rec = f"{target.plan_id} {modality}" if target else ""
            if len(planes_mostrar) == 1:
                plan = planes_mostrar[0]
                price = get_price(plan, modality)
                cashback = get_cashback(plan, modality)
                cashback_str = f" y ${cashback:.2f}/mes de cashback" if cashback > 0 else ""
                return (
                    f"RESPONDE EXACTAMENTE CON ESTE TEXTO SIN MODIFICAR NADA:\n\n"
                    f"La opción más económica es el *{plan.plan_id} {modality}* "
                    f"a ${price:.0f}/mes con {plan.gb_base:g} GB{cashback_str}.\n\n"
                    f"Para activarlo, comuníquese con Soporte al 800 220 9518 "
                    f"o acuda a un Centro de Atención a Clientes.\n\n"
                    f"Después agrega únicamente la pregunta de activación del *{plan_rec}*."
                )
            lista_planes = ""
            for p in planes_mostrar:
                price = get_price(p, modality)
                cashback = get_cashback(p, modality)
                cb_str = f" · Cashback ${cashback:.2f}/mes" if cashback > 0 else ""
                lista_planes += f"• *{p.plan_id} {modality}*: ${price:.0f}/mes · {p.gb_base:g} GB{cb_str}\n"
            return (
                f"RESPONDE EXACTAMENTE CON ESTE TEXTO SIN MODIFICAR NADA:\n\n"
                f"Opciones más económicas en modalidad {modality}:\n\n"
                f"{lista_planes}\n"
                f"Para activarlas, comuníquese con Soporte al 800 220 9518 "
                f"o acuda a un Centro de Atención a Clientes.\n\n"
                f"Después agrega la pregunta de activación del *{plan_rec}*."
            )

        elif tipo == "mas_caro":
            plan = max(CATALOG, key=lambda p: get_price(p, modality))
            return format_one(plan)

        elif tipo == "ultra":
            planes = [p for p in eligible if p.family == "Telcel Ultra"]
            if not planes:
                return no_plans_found()
            return format_one(planes[0]) if len(planes) == 1 else (
                "RESPONDE EXACTAMENTE CON ESTE TEXTO SIN MODIFICAR NADA:\n\n"
                f"Opciones *Telcel Ultra {modality}*:\n\n" + format_many(planes)
            )

        elif tipo == "libre":
            planes = [p for p in eligible if p.family == "Telcel Libre"]
            if not planes:
                return no_plans_found()
            return format_one(planes[0]) if len(planes) == 1 else (
                "RESPONDE EXACTAMENTE CON ESTE TEXTO SIN MODIFICAR NADA:\n\n"
                f"Opciones *Telcel Libre {modality}*:\n\n" + format_many(planes)
            )

        elif tipo == "especifico":
            plan = find_plan(criterio)
            if plan:
                price = get_price(plan, modality)
                result = format_one(plan)
                if price < current_cost - 1.0:
                    result += f"\n\n⚠️ Para activarlo: Soporte 800 220 9518 o CAC."
                return result
            price_match = re.search(r'\$?(\d{3,5})', criterio)
            if price_match:
                target_price = float(price_match.group(1))
                candidates = sorted(eligible, key=lambda p: abs(get_price(p, modality) - target_price))
                if candidates:
                    return format_one(candidates[0])
            return no_plans_found()

        else:  # "general"
            if eligible:
                return (
                    "RESPONDE EXACTAMENTE CON ESTE TEXTO SIN MODIFICAR NADA:\n\n"
                    f"Planes disponibles en modalidad *{modality}*:\n\n" + format_many(eligible)
                )
            return no_plans_found()

    return [iniciar_contratacion, responder_por_que, presentar_planes]
