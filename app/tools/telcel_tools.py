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
    CATALOG, find_plan, get_price, get_cashback, recommend_plan, eligible_plans, get_legacy_gb,
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

        Úsala también cuando el cliente redirija a otro plan:
        - "no, mejor el libre que me recomendaste"
        - "prefiero el que me mostraste al inicio"
        - "mejor el Telcel Libre 2"
        - Cualquier expresión donde el cliente elija un plan específico
          después de explorar otras opciones

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
        plan_name = state.plan_anclado or "el plan recomendado"

        RESPUESTAS = {
            "plan": (
                "RESPONDE EXACTAMENTE CON ESTE TEXTO SIN MODIFICAR NADA:\n\n"
                f"Le recomendamos el {plan_name} porque ofrece más beneficios "
                f"para su perfil: más GB, cashback mensual y apps ilimitadas incluidas.\n\n"
                f"¿Le gustaría activar el *{state.plan_anclado}*?"
            ),
            "promocion": (
                "RESPONDE EXACTAMENTE CON ESTE TEXTO SIN MODIFICAR NADA:\n\n"
                f"Las promociones son beneficios que Telcel activa en planes "
                f"seleccionados para darles más valor. "
                f"El {plan_name} sí incluye esta promoción.\n\n"
                f"¿Le gustaría activar el *{state.plan_anclado}*?"
            ),
            "modalidad": (
                "RESPONDE EXACTAMENTE CON ESTE TEXTO SIN MODIFICAR NADA:\n\n"
                f"Le ofrecemos planes en modalidad {state.subscription_type} "
                f"porque es la misma que tiene en su plan actual. "
                f"Para cambiar de modalidad puede acudir a un CAC "
                f"o llamar al 800 220 9518.\n\n"
                f"¿Le gustaría activar el *{state.plan_anclado}*?"
            ),
            "criterio": (
                "RESPONDE EXACTAMENTE CON ESTE TEXTO SIN MODIFICAR NADA:\n\n"
                f"Las promociones son beneficios que Telcel activa en planes "
                f"seleccionados para darles más valor. "
                f"El {plan_name} sí incluye esta promoción.\n\n"
                f"¿Le gustaría activar el *{state.plan_anclado}*?"
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
                "ultra"       — pregunta por planes de la familia Telcel Ultra:
                                "quiero uno ultra", "muéstrame los ultra",
                                "tienes ultras?", "qué hay en ultra?",
                                "planes ultra", "ultra disponibles"

                                Úsalo también cuando el cliente mencione "ultra"
                                sin más contexto:
                                "quiero el ultra"
                                "dame uno ultra"
                                "el ultra"
                                "quiero ultra"
                                "un plan ultra"
                                → tipo="ultra", criterio="general"

                                NUNCA uses tipo="general" cuando el cliente
                                menciona "ultra" — siempre usa tipo="ultra".
                "libre"       — pregunta por planes de la familia Telcel Libre

                                Úsalo también cuando el cliente mencione "libre"
                                sin más contexto:
                                "quiero el libre"
                                "dame uno libre"
                                "el libre"
                                "quiero libre"
                                "un plan libre"
                                → tipo="libre", criterio="general"

                                NUNCA uses tipo="general" cuando el cliente
                                menciona "libre" — siempre usa tipo="libre".
                "especifico"  — pregunta por un plan concreto (por nombre, precio o GB):
                                - "¿tienes datos ilimitados?" → criterio="ilimitados", tipo="especifico"
                                - "¿hay plan ilimitado?" → criterio="ilimitados", tipo="especifico"
                "apps"        — pregunta qué apps están incluidas (criterio = nombre de la app
                                o "general" si no menciona una app específica)
                "mismo_precio" — cuando el cliente busca planes con precio similar o igual
                                a su renta actual: "¿tienes algo al mismo precio?",
                                "¿hay planes similares a lo que pago?",
                                "¿algo parecido a mi renta actual?"
                "general"     — cualquier otra consulta de planes o catálogo
        """
        print(f"[TOOLS-TIPO] tipo={tipo!r} criterio={criterio!r}")
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
                "beneficios": ["Claro Drive 20 GB", "Claro Video"],
                "instruccion": (
                    "Comienza con 'Contamos con el [nombre del plan] que...' "
                    "USA ÚNICAMENTE estos datos para presentar el plan. "
                    "Presenta los beneficios de forma atractiva y comercial — "
                    "como un vendedor que destaca el valor de cada beneficio. "
                    "Orden de presentación: primero GB y cashback, luego apps ilimitadas, "
                    "luego Claro Drive, luego Claro Video. "
                    "Claro Drive: menciona como 20 GB de almacenamiento en la nube incluido. "
                    "Claro Video: menciona como plataforma de streaming de series y películas incluida. "
                    "NO digas que Claro Video es ilimitado — sí consume GB del plan. "
                    "NUNCA menciones Amazon Prime ni ningún otro beneficio que no esté en estos datos."
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
            plan_name = state.plan_anclado or "el plan recomendado"
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
                return json.dumps({
                    "apps_ilimitadas": _LISTA_APPS,
                    "consume_gb": False,
                    "nota": "Cualquier otra app (YouTube, TikTok, Netflix, etc.) sí consume GB del plan.",
                    "instruccion": (
                        "USA ÚNICAMENTE estos datos para responder. "
                        "No agregues apps adicionales ni información de tu conocimiento general. "
                        "Al final agrega la pregunta de activación del último plan sugerido."
                    ),
                }, ensure_ascii=False)
            if app_norm in APPS_INCLUIDAS:
                return json.dumps({
                    "app_consultada": criterio,
                    "incluida": True,
                    "consume_gb": False,
                    "lista_apps_incluidas": _LISTA_APPS,
                    "instruccion": (
                        "USA ÚNICAMENTE estos datos para responder. "
                        "No agregues apps adicionales ni información de tu conocimiento general. "
                        "Al final agrega la pregunta de activación del último plan sugerido."
                    ),
                }, ensure_ascii=False)
            return json.dumps({
                "app_consultada": criterio,
                "incluida": False,
                "consume_gb": True,
                "lista_apps_incluidas": _LISTA_APPS,
                "instruccion": (
                    "USA ÚNICAMENTE estos datos para responder. "
                    "No agregues apps adicionales ni información de tu conocimiento general. "
                    "Al final agrega la pregunta de activación del último plan sugerido."
                ),
            }, ensure_ascii=False)

        elif tipo == "mas_barato":
            cheaper = [p for p in CATALOG if get_price(p, modality) < current_cost - 1.0]
            if not cheaper:
                return no_plans_found()
            # más cercanos a la renta actual primero (descendente por precio)
            planes_mostrar = sorted(cheaper, key=lambda p: get_price(p, modality), reverse=True)[:3]

            # Cierre contextual usando el plan anclado
            plan_rec = state.plan_anclado
            if plan_rec:
                anclado_id = plan_rec.removesuffix(f" {modality}").strip()
                anclado_obj = find_plan(anclado_id)
            else:
                anclado_obj = recommend_plan(current_cost, modality)
                plan_rec = f"{anclado_obj.plan_id} {modality}" if anclado_obj else ""

            if anclado_obj:
                rec_price = get_price(anclado_obj, modality)
                rec_gb = (
                    anclado_obj.gb_promo
                    if (has_promo and anclado_obj.gb_promo > anclado_obj.gb_base and rec_price > current_cost + 1.0)
                    else anclado_obj.gb_base
                )
                diferencia_precio = rec_price - current_cost
                current_gb = state.current_plan_gb or get_legacy_gb(state.current_plan_name)

                if current_gb and not anclado_obj.is_unlimited:
                    diferencia_vs_actual = rec_gb - current_gb
                    if abs(rec_price - current_cost) <= 1.0:
                        cierre = (
                            f"Pagando su renta actual de ${current_cost:.0f}/mes, "
                            f"con el *{plan_rec}* que le estamos ofreciendo obtendría {rec_gb:g} GB — "
                            f"{diferencia_vs_actual:g} GB más que su plan actual.\n\n"
                            f"¿Le gustaría activar el *{plan_rec}*?"
                        )
                    else:
                        cierre = (
                            f"Por ${diferencia_precio:.0f} pesos más que su renta actual, "
                            f"con el *{plan_rec}* que le estamos ofreciendo obtendría {rec_gb:g} GB — "
                            f"{diferencia_vs_actual:g} GB más que su plan actual.\n\n"
                            f"¿Le gustaría activar el *{plan_rec}*?"
                        )
                else:
                    cierre = f"¿Le gustaría activar el *{plan_rec}*?"
            else:
                cierre = "¿Le gustaría explorar alguna de estas opciones?"

            if len(planes_mostrar) == 1:
                plan = planes_mostrar[0]
                price = get_price(plan, modality)
                cashback = get_cashback(plan, modality)
                cashback_str = f" y ${cashback:.2f}/mes de cashback" if cashback > 0 else ""
                return (
                    f"RESPONDE EXACTAMENTE CON ESTE TEXTO SIN MODIFICAR NADA:\n\n"
                    f"En modalidad {modality}, el plan más económico disponible es el "
                    f"*{plan.plan_id} {modality}* "
                    f"a ${price:.0f}/mes con {plan.gb_base:g} GB{cashback_str}.\n\n"
                    f"Para activarlo, comuníquese con Soporte al 800 220 9518 "
                    f"o acuda a un Centro de Atención a Clientes.\n\n"
                    f"{cierre}"
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
                f"{cierre}"
            )

        elif tipo == "mas_caro":
            planes = sorted(eligible, key=lambda p: get_price(p, modality))
            if not planes:
                return no_plans_found()
            if len(planes) == 1:
                plan = planes[0]
                price = get_price(plan, modality)
                cashback = get_cashback(plan, modality)
                cb_str = f" · ${cashback:.2f}/mes de cashback" if cashback > 0 else ""
                plan_rec = state.plan_anclado or f"{plan.plan_id} {modality}"
                return (
                    f"RESPONDE EXACTAMENTE CON ESTE TEXTO SIN MODIFICAR NADA:\n\n"
                    f"El plan más premium disponible es el *{plan.plan_id} {modality}* "
                    f"a ${price:.0f}/mes con {gb_label(plan)}{cb_str}.\n\n"
                    f"¿Le gustaría activar el *{plan_rec}*?"
                )
            plan_rec = state.plan_anclado
            lista = ""
            for p in planes[:5]:
                price = get_price(p, modality)
                cashback = get_cashback(p, modality)
                cb_str = f" · Cashback ${cashback:.2f}/mes" if cashback > 0 else ""
                lista += f"• *{p.plan_id} {modality}*: ${price:.0f}/mes · {gb_label(p)}{cb_str}\n"
            return (
                f"RESPONDE EXACTAMENTE CON ESTE TEXTO SIN MODIFICAR NADA:\n\n"
                f"Planes disponibles por encima de su renta actual:\n\n"
                f"{lista}\n"
                f"¿Le gustaría activar el *{plan_rec}*?"
            )

        elif tipo == "ultra":
            planes = [p for p in eligible if p.family == "Telcel Ultra"]
            if not planes:
                return no_plans_found()
            if len(planes) == 1:
                plan = planes[0]
                price = get_price(plan, modality)
                cashback = get_cashback(plan, modality)
                cashback_str = f"💰 Cashback ${cashback:.2f}/mes\n" if cashback > 0 else ""
                apps_str = (
                    "📱 Apps ilimitadas: Facebook, WhatsApp, Messenger, X, Instagram, Snapchat y Uber\n"
                    if plan.family == "Telcel Libre" else
                    "📱 WhatsApp ilimitado\n"
                )
                state.plan_anclado = f"{plan.plan_id} {modality}"
                return (
                    f"RESPONDE EXACTAMENTE CON ESTE TEXTO SIN MODIFICAR NADA:\n\n"
                    f"En la familia Telcel Ultra contamos con el "
                    f"*{plan.plan_id} {modality}* a ${price:.0f}/mes:\n\n"
                    f"📶 {gb_label(plan)}\n"
                    f"{cashback_str}"
                    f"{apps_str}"
                    f"🎬 Claro Video\n"
                    f"💾 Claro Drive 20 GB\n\n"
                    f"¿Le gustaría activar el *{state.plan_anclado}*?"
                )
            lista = ""
            for p in planes:
                price = get_price(p, modality)
                lista += f"• *{p.plan_id} {modality}*: ${price:.0f}/mes · {gb_label(p)}\n"
            ultra_cercano = min(
                [p for p in planes if get_price(p, modality) >= current_cost],
                key=lambda p: get_price(p, modality),
                default=planes[0],
            )
            ultra_price = get_price(ultra_cercano, modality)
            ultra_gb = ultra_cercano.gb_base
            return (
                f"RESPONDE EXACTAMENTE CON ESTE TEXTO SIN MODIFICAR NADA:\n\n"
                f"Si busca más GB, los planes *Telcel Ultra {modality}* "
                f"son una excelente opción:\n\n"
                f"{lista}\n"
                f"El más cercano a su renta actual es el *{ultra_cercano.plan_id} {modality}* "
                f"a ${ultra_price:.0f}/mes con {ultra_gb:g} GB.\n\n"
                f"¿Le gustaría activar el *{state.plan_anclado}*?"
            )

        elif tipo == "libre":
            planes = [p for p in eligible if p.family == "Telcel Libre"]
            if not planes:
                return no_plans_found()
            if len(planes) == 1:
                state.plan_anclado = f"{planes[0].plan_id} {modality}"
                return format_one(planes[0])
            plan_rec = state.plan_anclado
            lista = ""
            for p in planes:
                price = get_price(p, modality)
                lista += f"• *{p.plan_id} {modality}*: ${price:.0f}/mes · {gb_label(p)}\n"
            return (
                f"RESPONDE EXACTAMENTE CON ESTE TEXTO SIN MODIFICAR NADA:\n\n"
                f"Si busca cashback y apps ilimitadas, los planes *Telcel Libre {modality}* "
                f"son una excelente opción:\n\n"
                f"{lista}\n"
                f"¿Le gustaría activar el *{plan_rec}*?"
            )

        elif tipo == "especifico":
            plan = find_plan(criterio)
            if not plan:
                price_match = re.search(r'\$?(\d{3,5})', criterio)
                if price_match:
                    target_price = float(price_match.group(1))
                    candidates = sorted(CATALOG, key=lambda p: abs(get_price(p, modality) - target_price))
                    plan = candidates[0] if candidates else None
            if not plan:
                # Búsqueda por datos ilimitados
                if any(w in criterio.lower() for w in ["ilimitado", "ilimitados", "sin limite", "sin límite"]):
                    planes_ilimitados = [p for p in CATALOG if p.is_unlimited and
                                         get_price(p, modality) >= current_cost - 1.0]
                    if planes_ilimitados:
                        plan = planes_ilimitados[0]
                        price = get_price(plan, modality)
                        state.plan_anclado = f"{plan.plan_id} {modality}"
                        return (
                            f"RESPONDE EXACTAMENTE CON ESTE TEXTO SIN MODIFICAR NADA:\n\n"
                            f"Contamos con el *{plan.plan_id} {modality}* a ${price:.0f}/mes "
                            f"con datos ilimitados (sujeto a Política de Uso Justo).\n\n"
                            f"📱 WhatsApp ilimitado\n"
                            f"🎬 Claro Video\n"
                            f"💾 Claro Drive 20 GB\n\n"
                            f"¿Le gustaría activar el *{state.plan_anclado}*?"
                        )
                    return no_plans_found()
                # Búsqueda por GB
                gb_match = re.search(r'(\d+)\s*gb', criterio.lower())
                if gb_match:
                    target_gb = float(gb_match.group(1))
                    candidates = sorted(CATALOG, key=lambda p: abs(p.gb_base - target_gb))
                    plan = candidates[0] if candidates else None
            if not plan:
                return no_plans_found()

            price = get_price(plan, modality)
            es_activable = price >= current_cost - 1.0

            if es_activable:
                state.plan_anclado = f"{plan.plan_id} {modality}"
                canal_str = ""
            else:
                canal_str = (
                    f"\nPara activarlo, comuníquese con Soporte al 800 220 9518 "
                    f"o acuda a un Centro de Atención a Clientes."
                )

            return (
                f"RESPONDE EXACTAMENTE CON ESTE TEXTO SIN MODIFICAR NADA:\n\n"
                f"El plan más cercano es el *{plan.plan_id} {modality}* "
                f"a ${price:.0f}/mes con {gb_label(plan)}."
                f"{canal_str}\n\n"
                f"¿Le gustaría activar el *{state.plan_anclado}*?"
            )

        elif tipo == "mismo_precio":
            planes = [p for p in eligible if abs(get_price(p, modality) - current_cost) <= 1.0]
            if not planes:
                plan_rec = state.plan_anclado
                if plan_rec:
                    anclado_id = plan_rec.removesuffix(f" {modality}").strip()
                    anclado_obj = find_plan(anclado_id)
                else:
                    anclado_obj = recommend_plan(current_cost, modality)
                    plan_rec = f"{anclado_obj.plan_id} {modality}" if anclado_obj else None
                if plan_rec and anclado_obj:
                    rec_price = get_price(anclado_obj, modality)
                    rec_gb = (
                        anclado_obj.gb_promo
                        if (has_promo and anclado_obj.gb_promo > anclado_obj.gb_base and rec_price > current_cost + 1.0)
                        else anclado_obj.gb_base
                    )
                    rec_cashback = get_cashback(anclado_obj, modality)
                    return (
                        f"RESPONDE EXACTAMENTE CON ESTE TEXTO SIN MODIFICAR NADA:\n\n"
                        f"En modalidad {modality} no contamos con un plan "
                        f"al mismo precio de ${current_cost:.0f}/mes.\n\n"
                        f"El más cercano es el *{plan_rec}* a ${rec_price:.0f}/mes "
                        f"con {rec_gb:g} GB y ${rec_cashback:.2f}/mes de cashback.\n\n"
                        f"¿Le gustaría activar el *{plan_rec}*?"
                    )
                return no_plans_found()
            if len(planes) == 1:
                state.plan_anclado = f"{planes[0].plan_id} {modality}"
                return format_one(planes[0])
            return format_many(planes)

        else:  # "general"
            if eligible:
                plan_rec = state.plan_anclado
                lista_planes = ""
                for p in eligible:
                    price = get_price(p, modality)
                    cashback = get_cashback(p, modality)
                    cb_str = f" · Cashback ${cashback:.2f}/mes" if cashback > 0 else ""
                    gb = gb_label(p)
                    lista_planes += f"• *{p.plan_id} {modality}*: ${price:.0f}/mes · {gb}{cb_str}\n"
                return (
                    f"RESPONDE EXACTAMENTE CON ESTE TEXTO SIN MODIFICAR NADA:\n\n"
                    f"Le presentamos los planes y promociones disponibles para usted "
                    f"en modalidad *{modality}*:\n\n"
                    f"{lista_planes}\n"
                    f"De todas estas opciones, consideramos que el *{plan_rec}* "
                    f"es la más adecuada para usted.\n\n"
                    f"¿Le gustaría activar el *{plan_rec}*?"
                )
            return no_plans_found()

    @tool
    def informar_plan_actual() -> str:
        """
        Informa al cliente sobre su plan actual y lo compara con el recomendado.
        Úsala cuando el cliente pregunte QUÉ plan tiene o CUÁNTO paga:
        - "¿cuál es mi plan?"
        - "¿cuánto pago?"
        - "¿qué tengo contratado?"
        - "no recuerdo mi plan"
        - "¿tú sabes qué plan tengo?"

        NO la uses cuando el cliente busca planes similares a su precio actual.
        Para eso usar presentar_planes con tipo="mismo_precio".
        """
        modality = state.subscription_type
        current_cost = state.current_cost
        has_promo = bool(state.has_promotion)

        current_gb = state.current_plan_gb or get_legacy_gb(state.current_plan_name)
        gb_actual_str = f"{current_gb:g} GB" if current_gb else "datos limitados"

        if state.plan_anclado:
            anclado_id = state.plan_anclado.removesuffix(f" {modality}").strip()
            target = find_plan(anclado_id) or recommend_plan(current_cost, modality)
            plan_rec = state.plan_anclado
        else:
            target = recommend_plan(current_cost, modality)
            plan_rec = f"{target.plan_id} {modality}" if target else None

        if not target:
            return (
                "RESPONDE EXACTAMENTE CON ESTE TEXTO SIN MODIFICAR NADA:\n\n"
                f"Su plan actual es *{state.current_plan_name} {modality}* "
                f"a ${current_cost:.0f}/mes con {gb_actual_str}."
            )

        price = get_price(target, modality)
        cashback = get_cashback(target, modality)

        if has_promo and target.gb_promo > target.gb_base and price > current_cost + 1.0:
            gb_nuevo_str = f"{target.gb_promo:g} GB"
        else:
            gb_nuevo_str = f"{target.gb_base:g} GB"

        if abs(price - current_cost) <= 1.0:
            precio_contexto = f"manteniendo su renta de ${current_cost:.0f}/mes"
        else:
            precio_contexto = f"a ${price:.0f}/mes"

        cashback_line = f", más ${cashback:.2f}/mes de cashback" if cashback > 0 else ""

        return (
            "RESPONDE EXACTAMENTE CON ESTE TEXTO SIN MODIFICAR NADA:\n\n"
            f"Su plan actual es *{state.current_plan_name} {modality}* "
            f"a ${current_cost:.0f}/mes con {gb_actual_str}.\n\n"
            f"Le recomendamos el *{plan_rec}* {precio_contexto} "
            f"con {gb_nuevo_str}{cashback_line}.\n\n"
            f"¿Le gustaría activar el *{plan_rec}*?"
        )

    @tool
    def manejar_objecion(motivo: str = "") -> str:
        """
        Úsala cuando el cliente rechaza el plan o expresa desinterés.
        Úsala para:
        - "no me interesa"
        - "no lo necesito"
        - "no quiero"
        - "no gracias"
        - "no por ahora"
        - "estoy bien con mi plan"
        - Cualquier rechazo explícito del plan ofrecido

        NO la uses cuando el cliente dice "no" seguido de una
        preferencia ("no, mejor el Libre") — eso es una redirección,
        no un rechazo.

        Args:
            motivo: SOLO si el cliente menciona una razón específica
                    de servicio o problema (mal servicio, cobertura,
                    precio muy alto, tiene contrato con otra empresa).

                    Dejar motivo="" cuando el cliente dice:
                    - "no me interesa"
                    - "no lo necesito"
                    - "no quiero"
                    - "no gracias"
                    - Cualquier rechazo sin razón específica de servicio

                    Pasar motivo con texto cuando el cliente dice:
                    - "su servicio es malo" → motivo="mal servicio"
                    - "no tengo cobertura" → motivo="cobertura"
                    - "es muy caro" → motivo="precio"
                    - "ya tengo contrato con AT&T" → motivo="otro operador"
        """
        current_count = state.rejection_count
        state.rejection_count += 1

        if current_count == 0:
            if motivo:
                _MOTIVOS_SERVICIO = {"servicio", "cobertura", "señal", "lento",
                                     "malo", "mal", "falla", "problema"}
                motivo_lower = motivo.lower()
                es_servicio = any(w in motivo_lower for w in _MOTIVOS_SERVICIO)
                soporte = (
                    "\nPara reportar el problema puede comunicarse con "
                    "Soporte al 800 220 9518.\n\n"
                    if es_servicio else "\n\n"
                )
                return (
                    "RESPONDE EXACTAMENTE CON ESTE TEXTO SIN MODIFICAR NADA:\n\n"
                    f"Entendemos, {state.first_name}. Lamentamos escuchar eso.{soporte}"
                    "Cuando guste revisar sus opciones, aquí estaremos para ayudarle."
                )
            return (
                "RESPONDE EXACTAMENTE CON ESTE TEXTO SIN MODIFICAR NADA:\n\n"
                f"Entendemos, {state.first_name}. No hay ninguna obligación.\n\n"
                "¿Hay algo en particular que le genera duda sobre el plan?"
            )

        elif current_count == 1:
            if motivo:
                _MOTIVOS_SERVICIO = {"servicio", "cobertura", "señal",
                                     "lento", "malo", "mal", "falla", "problema"}
                es_servicio = any(w in motivo.lower() for w in _MOTIVOS_SERVICIO)
                soporte = (
                    "\nPara reportar el problema puede comunicarse con "
                    "Soporte al 800 220 9518.\n\n"
                    if es_servicio else "\n\n"
                )
                return (
                    "RESPONDE EXACTAMENTE CON ESTE TEXTO SIN MODIFICAR NADA:\n\n"
                    f"Entendemos, {state.first_name}. Lamentamos escuchar eso.{soporte}"
                    "Cuando guste revisar sus opciones, aquí estaremos para ayudarle."
                )
            return (
                "RESPONDE EXACTAMENTE CON ESTE TEXTO SIN MODIFICAR NADA:\n\n"
                f"Con gusto, {state.first_name}. Cuando guste revisar "
                f"sus opciones, aquí estaremos para ayudarle."
            )

        else:
            return (
                "RESPONDE EXACTAMENTE CON ESTE TEXTO SIN MODIFICAR NADA:\n\n"
                f"Entendido, {state.first_name}. "
                f"Si en algún momento desea explorar opciones, "
                f"puede comunicarse con nosotros o acudir a un CAC."
            )

    @tool
    def comparar_planes(plan_id: str = "") -> str:
        """
        Compara el plan actual del cliente con el plan anclado o con un plan específico.
        Úsala cuando el cliente pida comparar planes o preguntar qué gana con el cambio:
        - "compáralo con mi plan actual"
        - "qué gano con el cambio?"
        - "qué diferencia hay?"
        - "vale la pena el cambio?"
        - "en qué mejora?"
        - "qué tiene de mejor?"
        - "por qué es mejor ese plan?"

        Args:
            plan_id: nombre del plan a comparar. Si está vacío, usa el plan anclado.
        """
        from app.catalog.plans import find_plan, get_price, get_cashback, get_legacy_gb

        modality = state.subscription_type
        current_cost = state.current_cost
        has_promo = bool(state.has_promotion)

        if plan_id:
            plan = find_plan(plan_id)
        else:
            plan = find_plan(state.plan_anclado.replace(f" {modality}", "").strip())

        if not plan:
            return (
                "RESPONDE EXACTAMENTE CON ESTE TEXTO SIN MODIFICAR NADA:\n\n"
                f"¿Le gustaría activar el *{state.plan_anclado}*?"
            )

        new_price = get_price(plan, modality)
        es_activable = new_price >= current_cost - 1.0
        new_cashback = get_cashback(plan, modality)
        has_promo_plan = has_promo and plan.gb_promo > plan.gb_base and new_price > current_cost + 1.0
        new_gb = plan.gb_promo if has_promo_plan else plan.gb_base

        current_gb = state.current_plan_gb or get_legacy_gb(state.current_plan_name)
        current_cashback = state.current_plan_cashback or 0.0

        lineas = []

        if current_gb:
            diferencia_gb = new_gb - current_gb
            if diferencia_gb > 0:
                lineas.append(
                    f"📶 Datos: pasa de {current_gb:g} GB a {new_gb:g} GB "
                    f"— {diferencia_gb:g} GB más para navegar."
                )
            else:
                lineas.append(f"📶 Datos: {new_gb:g} GB incluidos.")
        else:
            lineas.append(f"📶 Datos: {new_gb:g} GB incluidos.")

        diferencia_precio = new_price - current_cost
        if abs(diferencia_precio) <= 1.0:
            lineas.append(f"💰 Precio: mantiene su renta de ${current_cost:.0f}/mes.")
        elif diferencia_precio > 0:
            lineas.append(f"💰 Precio: ${new_price:.0f}/mes — ${diferencia_precio:.0f} más que su renta actual.")
        else:
            lineas.append(f"💰 Precio: ${new_price:.0f}/mes — ${abs(diferencia_precio):.0f} menos que su renta actual.")

        if new_cashback > 0 and current_cashback == 0:
            lineas.append(f"💳 Cashback: gana ${new_cashback:.2f}/mes para usar en servicios Telcel.")
        elif new_cashback > current_cashback:
            lineas.append(f"💳 Cashback: aumenta de ${current_cashback:.2f} a ${new_cashback:.2f}/mes.")
        elif new_cashback > 0:
            lineas.append(f"💳 Cashback: ${new_cashback:.2f}/mes incluido.")

        if plan.family == "Telcel Libre":
            lineas.append(
                "📱 Apps ilimitadas: Facebook, WhatsApp, Messenger, X, Instagram, Snapchat y Uber "
                "(no consumen GB)."
            )

        comparativa = "\n".join(lineas)

        if es_activable:
            state.plan_anclado = f"{plan.plan_id} {modality}"
            cierre = f"¿Le gustaría activar el *{state.plan_anclado}*?"
        else:
            cierre = (
                f"Para activar el *{plan.plan_id} {modality}*, "
                f"comuníquese con Soporte al 800 220 9518 "
                f"o acuda a un Centro de Atención a Clientes.\n\n"
                f"¿Le gustaría activar el *{state.plan_anclado}*?"
            )

        return (
            "RESPONDE EXACTAMENTE CON ESTE TEXTO SIN MODIFICAR NADA:\n\n"
            f"Lo que gana con el cambio al *{plan.plan_id} {modality}*:\n\n"
            f"{comparativa}\n\n"
            f"{cierre}"
        )

    return [iniciar_contratacion, responder_por_que, presentar_planes,
            informar_plan_actual, manejar_objecion, comparar_planes]
