"""
tools/telcel_tools.py

Herramienta de acción de ReniAgent.

El catálogo de planes y la lógica de objeciones/derivaciones están en el
system prompt. El agente solo necesita una herramienta para registrar
el momento en que el cliente confirma que quiere activar un plan.
"""


import logging
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

logger = logging.getLogger(__name__)


def make_tools(state):
    """Fabrica las herramientas de acción para una sesión específica."""

    @tool
    def iniciar_contratacion(plan_id: str) -> str:
        """
        Inicia el proceso de contratación cuando el cliente confirma que quiere
        activar un plan. Úsala SOLO cuando el cliente haya dado una confirmación
        clara de querer activar (acepto, sí quiero, actívalo, confirmo,
        acepto el cambio, acepto el plan, acepto la migración, de acuerdo,
        estoy de acuerdo, quiero proceder, proceder con el cambio,
        adelante, dale, hazlo, que siga, continúa).
        NUNCA respondas con texto informativo cuando el cliente confirma —
        invoca esta herramienta directamente.

        Úsala también cuando el cliente redirija a otro plan:
        - "no, mejor el libre que me recomendaste"
        - "prefiero el que me mostraste al inicio"
        - "mejor el Telcel Libre 2"
        - Cualquier expresión donde el cliente elija un plan específico
          después de explorar otras opciones

        Args:
            plan_id: ID exacto del plan a contratar. Ej: "Telcel Libre 5"
        """
        logger.info("[TOOL] iniciar_contratacion plan_id='%s' phone=%s", plan_id, state.phone_number)
        plan = find_plan(plan_id)
        if not plan:
            logger.warning("[TOOL] plan no encontrado plan_id='%s' phone=%s", plan_id, state.phone_number)
            return (
                f"No encontré el plan '{plan_id}' en el catálogo. "
                f"Verifica el nombre con el cliente antes de iniciar la contratación."
            )

        modality = state.subscription_type
        price = get_price(plan, modality)
        cashback = get_cashback(plan, modality)
        has_promo = bool(state.has_promotion)

        if price < state.current_cost - 1.0:
            logger.warning("[TOOL] precio_bajo plan_id='%s' precio=%.0f renta_actual=%.0f phone=%s",
                           plan_id, price, state.current_cost, state.phone_number)
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
        state.awaiting_contract_confirmation = False
        state.awaiting_otp = False
        state.otp_attempt_count = 0
        state.stage = "CONTRACT"
        logger.info("[TOOL] CONTRATACIÓN_INICIADA plan='%s' precio=%.0f phone=%s → stage=CONTRACT",
                    plan.plan_id, price, state.phone_number)

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
            tema: "plan" | "promocion" | "modalidad" | "criterio" | "canal"

            Usa tema="canal" cuando el cliente pregunte:
            - "¿por qué tengo que ir al CAC?"
            - "¿por qué tengo que llamar a Soporte?"
            - "¿no puedes cambiarlo tú?"
            - "¿por qué no puedes activarlo aquí?"
            - "¿por qué me mandas con soporte?"
            - "¿no puedes hacer tú el cambio?"
        """
        plan_name = state.plan_anclado or "el plan recomendado"

        plan_obj = next(
            (p for p in CATALOG if f"{p.plan_id} {state.subscription_type}" == state.plan_anclado),
            None,
        )
        es_ultra = plan_obj and plan_obj.family == "Telcel Ultra"
        beneficios_extra = "más GB" if es_ultra else "más GB, cashback mensual y apps ilimitadas"

        RESPUESTAS = {
            "plan": (
                "RESPONDE EXACTAMENTE CON ESTE TEXTO SIN MODIFICAR NADA:\n\n"
                f"Le recomendamos el {plan_name} porque ofrece más beneficios "
                f"para su perfil: {beneficios_extra} incluidas.\n\n"
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
            "canal": (
                "RESPONDE EXACTAMENTE CON ESTE TEXTO SIN MODIFICAR NADA:\n\n"
                f"Algunos cambios requieren gestión a través de nuestros canales "
                f"especializados para garantizar la mejor atención. "
                f"Soporte al 800 220 9518 y los CAC cuentan con las herramientas "
                f"necesarias para ese trámite.\n\n"
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
                "mas_barato"  — cuando el cliente quiere planes más económicos:
                                - "¿tienes planes más baratos?"
                                - "¿existen planes más baratos?"
                                - "¿hay algo más económico?"
                                - "¿tienes planes mas baratos?" (sin tilde)
                                - "planes mas baratos" (sin tilde)
                                - "algo más barato"
                                - "más económico"
                                - "menos costoso"

                                NUNCA uses tipo="general" cuando el cliente
                                pide algo más barato.
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

                                NUNCA uses tipo="libre" cuando el cliente menciona
                                un precio específico junto con "libre":
                                "plan libre de 700 pesos" → tipo="especifico", criterio="700"
                                "libre de $500" → tipo="especifico", criterio="500"
                                Para esos casos usa tipo="especifico".

                                NUNCA uses tipo="general" cuando el cliente
                                menciona "libre" — siempre usa tipo="libre".
                "especifico"  — pregunta por un plan concreto (por nombre, precio o GB):
                                - "¿tienes datos ilimitados?" → criterio="ilimitados", tipo="especifico"
                                - "¿hay plan ilimitado?" → criterio="ilimitados", tipo="especifico"
                                - "plan de 700 pesos" → criterio="700", tipo="especifico"
                                - "algo de $700" → criterio="700", tipo="especifico"
                                - "plan aproximadamente de $700" → criterio="700", tipo="especifico"
                                - "plan libre de 700 pesos" → criterio="700", tipo="especifico"
                                - "algo libre de $700" → criterio="700", tipo="especifico"
                                - "un libre de 700" → criterio="700", tipo="especifico"
                                - "plan ultra de 500 pesos" → criterio="500", tipo="especifico"

                                REGLA CRÍTICA: cuando el cliente menciona una familia
                                (libre, ultra) junto con un precio, SIEMPRE usa
                                tipo="especifico" con el precio como criterio.
                                NUNCA uses tipo="libre" o tipo="ultra" cuando hay
                                un precio específico en el mensaje.

                                NUNCA uses tipo="rango_precios" — no existe.
                                Para búsquedas por precio aproximado usa tipo="especifico".

                                Úsala también cuando el cliente insista en un plan específico
                                que ya se mostró antes:
                                - "quiero el libre 1"
                                - "me quedo con el libre 1"
                                - "prefiero el libre 1"
                                → tipo="especifico", criterio=nombre del plan

                                NUNCA respondas con el fallback cuando el cliente pide
                                un plan por nombre — siempre usa presentar_planes.
                "apps"        — pregunta qué apps están incluidas (criterio = nombre de la app
                                o "general" si no menciona una app específica)
                "mismo_precio" — cuando el cliente busca planes con precio similar o igual
                                a su renta actual: "¿tienes algo al mismo precio?",
                                "¿hay planes similares a lo que pago?",
                                "¿algo parecido a mi renta actual?"
                "general"     — cualquier otra consulta de planes o catálogo

            Cuando el cliente pide planes de una modalidad diferente a la suya:
            - "¿tienes planes controlados?" (cliente es Abierto)
            - "¿y en controlado?"
            - "¿algún plan controlado?"
            → incluye la modalidad en el criterio:
              criterio="controlado", tipo="general"

            NUNCA uses criterio="general" cuando el cliente menciona
            explícitamente una modalidad diferente a la suya.
        """
        print(f"[TOOLS-TIPO] tipo={tipo!r} criterio={criterio!r}")
        modality = state.subscription_type
        current_cost = state.current_cost
        has_promo = bool(state.has_promotion)
        eligible = eligible_plans(current_cost, modality)

        # Detectar si el cliente pide planes de modalidad diferente
        criterio_lower = criterio.lower()
        alt_modality = "Abierto" if modality == "Controlado" else "Controlado"

        pide_modalidad_diferente = (
            alt_modality.lower() in criterio_lower or
            (modality == "Abierto" and "controlado" in criterio_lower) or
            (modality == "Controlado" and "abierto" in criterio_lower)
        )

        if pide_modalidad_diferente:
            return (
                f"RESPONDE EXACTAMENTE CON ESTE TEXTO SIN MODIFICAR NADA:\n\n"
                f"Para planes en modalidad {alt_modality}, puede gestionar "
                f"el cambio en un Centro de Atención a Clientes (CAC) "
                f"o comunicarse con Soporte al 800 220 9518.\n\n"
                f"Dicho esto, en su modalidad actual contamos con el "
                f"*{state.plan_anclado}* que le ofrece más GB y beneficios "
                f"sin necesidad de cambiar de modalidad.\n\n"
                f"¿Le gustaría activar el *{state.plan_anclado}*?"
            )

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
                "llamadas_sms": plan.calls_sms,
                "apps_ilimitadas": apps,
                "beneficios": ["Claro Drive 20 GB", "Claro Video"],
                "instruccion": (
                    "Comienza con 'Contamos con el [nombre del plan] que...' "
                    "USA ÚNICAMENTE estos datos para presentar el plan. "
                    "Presenta los beneficios de forma atractiva y comercial — "
                    "como un vendedor que destaca el valor de cada beneficio. "
                    "Menciona llamadas_sms como beneficio incluido. "
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
                f"En este momento no contamos con planes que se ajusten a ese criterio "
                f"en modalidad {modality}.\n\n"
                f"¿Le gustaría activar el *{plan_name}*?"
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
                return (
                    f"RESPONDE EXACTAMENTE CON ESTE TEXTO SIN MODIFICAR NADA:\n\n"
                    f"No contamos con planes de menor precio en modalidad {modality}.\n\n"
                    f"¿Le gustaría activar el *{state.plan_anclado}*?"
                )
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
                gb_str = "Ilimitados" if p.is_unlimited else f"{p.gb_base:g} GB"
                lista_planes += f"• *{p.plan_id} {modality}*: ${price:.0f}/mes · {gb_str}{cb_str}\n"
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
                    f"📞 {plan.calls_sms}\n"
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
            # Actualizar plan anclado al Ultra más cercano elegible
            state.plan_anclado = f"{ultra_cercano.plan_id} {modality}"
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
            # Si el criterio es un precio numérico, redirigir a especifico
            _precio_en_criterio = re.search(r'^\d{3,4}$', criterio.strip())
            if _precio_en_criterio:
                return presentar_planes(criterio=criterio, tipo="especifico")
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
                gb_match = re.search(r'(\d+)\s*(?:gb|gigas?)', criterio.lower())
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
                cashback = get_cashback(plan, modality)
                cashback_str = f"💰 Cashback ${cashback:.2f}/mes\n" if cashback > 0 else ""
                apps_str = (
                    "📱 Apps ilimitadas: Facebook, WhatsApp, Messenger, X, Instagram, Snapchat y Uber\n"
                    if plan.family == "Telcel Libre" else
                    "📱 WhatsApp ilimitado\n"
                )
                return (
                    f"RESPONDE EXACTAMENTE CON ESTE TEXTO SIN MODIFICAR NADA:\n\n"
                    f"*{plan.plan_id} {modality}* a ${price:.0f}/mes incluye:\n\n"
                    f"📶 {gb_label(plan)}\n"
                    f"📞 {plan.calls_sms}\n"
                    f"{cashback_str}"
                    f"{apps_str}"
                    f"🎬 Claro Video\n"
                    f"💾 Claro Drive 20 GB\n\n"
                    f"¿Le gustaría activar el *{state.plan_anclado}*?"
                )

            return (
                f"RESPONDE EXACTAMENTE CON ESTE TEXTO SIN MODIFICAR NADA:\n\n"
                f"El *{plan.plan_id} {modality}* a ${price:.0f}/mes con {gb_label(plan)}.\n\n"
                f"Para activarlo, comuníquese con Soporte al 800 220 9518 "
                f"o acuda a un Centro de Atención a Clientes.\n\n"
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

        elif criterio not in ("", "general") and re.search(r'^\d+$', criterio.strip()):
            # El LLM pasó un precio numérico como criterio con cualquier tipo —
            # redirigir siempre a especifico para buscar el plan más cercano
            return presentar_planes(criterio=criterio, tipo="especifico")

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
        - "¿cuántos gigas tiene mi plan?"
        - "¿cuántos GB tengo?"
        - "¿cuántos datos tengo?"
        - "¿cuánto tiene mi plan?"
        - "¿qué gigas tengo?"
        - "¿cuál es mi plan?"
        - "¿cuánto pago?"
        - "¿qué tengo contratado?"
        - "no recuerdo mi plan"
        - "¿tú sabes qué plan tengo?"

        NO la uses cuando el cliente busca planes similares a su precio actual.
        Para eso usar presentar_planes con tipo="mismo_precio".

        NO la uses cuando el cliente pregunta qué gana o qué beneficios obtiene
        comparado con su plan actual. Para esos casos usa comparar_planes:
        - "¿qué beneficios nuevos gano?"
        - "¿qué beneficios gano comparado con mi plan actual?"
        - "¿qué gano comparado con lo que tengo?"
        - "¿en qué mejora respecto a mi plan?"
        - "¿qué cambia respecto a mi plan actual?"
        - "¿qué diferencia hay con mi plan actual?"

        NO la uses cuando el cliente pide un plan específico por nombre o expresa preferencia por uno:
        - "quiero el libre 1"
        - "dame el libre 4"
        - "me interesa el ultra 5"
        - "me gusta el libre 1"
        - "prefiero el libre 3"
        - "ese plan me gusta"
        Para esos casos usa comparar_planes con el plan_id mencionado.

        Solo úsala cuando el cliente pregunta por SU plan actual contratado,
        no cuando pide ver o activar un plan nuevo.

        NO la uses para preguntas sobre facturación o cobros:
        - "¿cuándo sería el nuevo cobro?"
        - "¿cuándo me cobran?"
        - "¿en qué fecha se hace el cobro?"
        - "¿cuándo entra en vigor?"
        Para esas preguntas, responde directamente indicando que
        para detalles de facturación puede consultar con Soporte
        al 800 220 9518 o en la app Mi Telcel.

        NO la uses cuando el cliente expresa preferencia o interés por un plan específico:
        - "me gusta el libre 1"
        - "me interesa el libre 3"
        - "prefiero ese plan"
        - "ese me llama la atención"
        Para esos casos usa comparar_planes con el plan_id mencionado.
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

        Úsala también para indecisión o duda:
        - "no lo sé"
        - "no sé"
        - "no estoy seguro/a"
        - "tengo dudas"
        - "déjame pensarlo"

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
        - "qué beneficios nuevos gano?"
        - "qué beneficios gano comparado con mi plan actual?"
        - "qué gano comparado con lo que tengo?"
        - "en qué mejora respecto a mi plan?"
        - "qué cambia respecto a mi plan actual?"
        - "qué diferencia hay con mi plan actual?"
        - "me gusta el libre 1"
        - "me interesa el libre 1"
        - "me llama la atención el ultra 5"
        - "prefiero el libre 3"
        - "ese plan me gusta"
        - "quiero saber más del libre 1"

        NO la uses cuando el cliente pregunte específicamente por llamadas:
        - "¿y las llamadas?"
        - "¿incluye llamadas?"
        - "¿tiene llamadas ilimitadas?"
        Para esas preguntas usa presentar_planes con tipo="apps"
        y criterio="llamadas", o responde directamente con el dato
        de plan.calls_sms.

        Args:
            plan_id: nombre exacto del plan que menciona el cliente.
                     Extrae LITERALMENTE lo que dijo el cliente:
                     - "ultra 9 controlado" → plan_id="Telcel Ultra 9 Controlado"
                     - "libre 4" → plan_id="Telcel Libre 4"
                     - "el vip" → plan_id="Telcel Libre VIP"
                     Si el cliente no menciona un plan específico,
                     deja plan_id="" para usar el plan anclado.
                     NUNCA uses el plan anclado si el cliente mencionó
                     un plan diferente explícitamente.
        """
        from app.catalog.plans import find_plan, get_price, get_cashback, get_legacy_gb

        modality = state.subscription_type
        current_cost = state.current_cost
        has_promo = bool(state.has_promotion)

        # Limpiar el plan_id — quitar modalidad si viene incluida
        plan_id_clean = plan_id.replace(f" {modality}", "").strip()
        # Agregar "Telcel" si no viene
        if not plan_id_clean.lower().startswith("telcel"):
            plan_id_clean = f"Telcel {plan_id_clean}"

        if plan_id:
            plan = find_plan(plan_id_clean)
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

        lineas.append(
            f"📞 {plan.calls_sms}"
        )

        comparativa = "\n".join(lineas)

        if es_activable:
            state.plan_anclado = f"{plan.plan_id} {modality}"
            cierre = f"¿Le gustaría activar el *{state.plan_anclado}*?"
            return (
                "RESPONDE EXACTAMENTE CON ESTE TEXTO SIN MODIFICAR NADA:\n\n"
                f"Lo que gana con el cambio al *{plan.plan_id} {modality}*:\n\n"
                f"{comparativa}\n\n"
                f"{cierre}"
            )
        else:
            return (
                "RESPONDE EXACTAMENTE CON ESTE TEXTO SIN MODIFICAR NADA:\n\n"
                f"El *{plan.plan_id} {modality}* solo puede activarse en un "
                f"Centro de Atención a Clientes o llamando a Soporte al 800 220 9518.\n\n"
                f"¿Le gustaría activar el *{state.plan_anclado}*?"
            )

    return [iniciar_contratacion, responder_por_que, presentar_planes,
            informar_plan_actual, manejar_objecion, comparar_planes]
