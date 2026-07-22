"""
agent/reni_agent.py

ReniAgent con persistencia de historial de conversación.
El agente recuerda todos los turnos anteriores de la sesión.
"""

import logging
import os
import re
import unicodedata
import warnings
from typing import List, Dict, Tuple

from strands import Agent

from app.catalog.plans import CATALOG, PRICE_TOLERANCE_MXN, find_plan, get_price, recommend_plan
from app.config.oci_model import oci_model
from app.prompts.system_prompt import build_system_prompt
from app.tools.telcel_tools import make_tools
from app.state.session import SessionState
from app.contract.contract_flow import handle_contract_turn, build_summary_template
from app.contract.post_sale import build_post_sale_message
from app.router.semantic_router import classify

DEBUG_WHATSAPP = os.getenv("DEBUG_WHATSAPP", "false").lower() == "true"


def _apply_debug(response_text: str, tools_invoked: list = None,
                  user_message: str = "") -> str:
    if not DEBUG_WHATSAPP:
        return response_text
    tools_str = f"[TOOLS] {tools_invoked if tools_invoked else 'ninguna'}"
    return f"{tools_str}\n{response_text}"


# Silencia los WARNING internos de Strands (ej. "overriding stop reason due to toolUse").
# El mensaje viene de strands.event_loop.streaming como logger.warning() y no debe
# llegar al cliente. Mantenemos ERROR y CRITICAL para fallos reales.
logging.getLogger("strands").setLevel(logging.ERROR)
logger = logging.getLogger(__name__)


def clean_response(
    text: str,
    is_rejection: bool = False,
    session=None,
    user_message: str = "",
) -> str:
    """
    Safety net: si la respuesta tiene más de una pregunta, elimina todas
    excepto la última (que siempre debe ser la de activación).

    En caso de rechazo explícito, elimina la última pregunta de activación
    cuando el texto inicia con una frase de empatía ante el rechazo.

    Ejemplo:
      ANTES: "Entiendo... ¿Desea activar el plan?"
      DESPUÉS: "Entiendo..."
    """
    # Eliminar nombres de tools escritos como texto literal
    text = re.sub(
        r'\([a-z_]+(?:_[a-z]+)*,\s*(?:tipo|criterio|tema|motivo|plan_id)=[^)]*\)',
        '',
        text,
        flags=re.IGNORECASE
    )
    text = re.sub(
        r'\[[a-z_]+(?:_[a-z]+)*\]',
        '',
        text,
        flags=re.IGNORECASE
    )
    # Eliminar corchetes vacíos que Llama a veces emite como artefacto
    text = re.sub(r'\[\s*\]', '', text).strip()
    text = re.sub(r'\n{3,}', '\n\n', text).strip()

    text = _fix_tuteo(text)
    text = _strip_technical_cac_reasons(text)
    if session is not None:
        text = _fix_incorrect_promo(text, session)
        text = _filter_ineligible_plans(text, user_message, session)
        text = _filter_wrong_modality(text, session)

    # Elimina paréntesis incompletos y su contenido hasta fin de texto
    if text.count('(') > text.count(')'):
        logger.warning("[PARENTESIS_INCOMPLETO] text='%s' phone=%s", text[-100:], session.phone_number if session else "")
        text = re.sub(r'\([^)]*$', '', text).strip()
        text = re.sub(r'[\s,+\.]+$', '', text).strip()

    if is_rejection:
        rejection_phrases = ("entiendo", "comprendo", "respetamos su decisión")
        normalized = text.strip().lower()
        if normalized.startswith(rejection_phrases):
            last_q = text.rfind("¿")
            if last_q != -1:
                question = text[last_q:]
                if any(w in question.upper() for w in ["ACTIVAR", "ACTIVARLO", "PROCEDER"]):
                    text = text[:last_q].rstrip()

    if text.count("?") <= 1:
        return text

    # Buscar el inicio de la última pregunta (último "¿")
    last_q_open = text.rfind("¿")
    if last_q_open == -1:
        return text

    before = text[:last_q_open].rstrip()
    last_q = text[last_q_open:].strip()

    # Si el texto anterior también contiene preguntas, filtrar esas líneas
    if "?" in before:
        lines = re.split(r"\n+", before)
        before = "\n".join(l for l in lines if "?" not in l).rstrip()

    return (before + "\n\n" + last_q).strip() if before else last_q

_CAC_MARKERS = ["cac", "800 220 9518", "centro de atención a clientes"]

_TECHNICAL_CAC_PHRASES = [
    re.compile(r"ya que su precio \(\$[\d,]+/mes\) es menor a su renta actual \(\$[\d,]+/mes\)", re.IGNORECASE),
    re.compile(r"ya que su precio es menor a su renta actual[^.]*\.", re.IGNORECASE),
    re.compile(r"debido a que su precio es menor[^.]*\.", re.IGNORECASE),
    re.compile(r"porque su precio \(\$[\d,]+\) es menor[^.]*\.", re.IGNORECASE),
    re.compile(r"ya que su renta actual es de \$[\d,]+[^.]*precio menor[^.]*\.", re.IGNORECASE),
    re.compile(r"ya que su precio \(\$[\d,]+/mes\) es mayor a su renta actual[^.]*\.", re.IGNORECASE),
    re.compile(r"ya que el precio del plan[^.]*es mayor[^.]*\.", re.IGNORECASE),
    re.compile(r"y requiere cambio de plan en un CAC[^.]*\.", re.IGNORECASE),
    re.compile(r"requiere cambio de plan en un CAC[^.]*\.", re.IGNORECASE),
    re.compile(r"ya que su precio \(\$[\d,]+\) es mayor[^.]*\.", re.IGNORECASE),
    re.compile(r"ya que su precio es menor a tu renta actual[^.]*\.", re.IGNORECASE),
    re.compile(r"ya que su precio es menor a su renta actual[^.]*\.", re.IGNORECASE),
    re.compile(r"ya que el precio.*menor.*renta[^.]*\.", re.IGNORECASE),
    re.compile(r"por ser más barato que su renta actual[^.]*\.", re.IGNORECASE),
    re.compile(r"por ser más barato que tu renta actual[^.]*\.", re.IGNORECASE),
    re.compile(r"ya que su precio \(\$[\d,]+\) es menor[^.]*\.", re.IGNORECASE),
    re.compile(r"ya que su precio \(\$[\d,]+/mes\) es igual a su renta actual[^.]*\.", re.IGNORECASE),
    re.compile(r"ya que su precio es igual a su renta actual[^.]*\.", re.IGNORECASE),
    re.compile(r"porque su precio.*igual.*renta[^.]*\.", re.IGNORECASE),
    re.compile(r"dado que su precio.*igual[^.]*\.", re.IGNORECASE),
    re.compile(r"ya que su nuevo plan \(\$[\d,]+/mes\) es más caro que su renta actual[^.]*\.", re.IGNORECASE),
    re.compile(r"ya que su nuevo plan.*más caro[^.]*\.", re.IGNORECASE),
    re.compile(r"desde la activación, ya que[^.]*\.", re.IGNORECASE),
    re.compile(r"aplica durante \d+ meses desde la activación, ya que[^.]*\.", re.IGNORECASE),
    re.compile(r"este plan es más barato que su renta actual[^.]*\.", re.IGNORECASE),
    re.compile(r"no es elegible para activarse directamente en este canal[^.]*\.", re.IGNORECASE),
    re.compile(r"por lo tanto, no es elegible[^.]*\.", re.IGNORECASE),
    re.compile(r"tenga en cuenta que este plan es más barato[^.]*\.", re.IGNORECASE),
    re.compile(r"La promoción de GB aplica cuando el precio del plan nuevo es mayor[^.]*\.", re.IGNORECASE),
    re.compile(r"aplica cuando el precio.*mayor.*renta[^.]*\.", re.IGNORECASE),
    re.compile(r"tiene promoción porque es mayor a su renta actual[^.]*\.", re.IGNORECASE),
    re.compile(r"tiene promoción porque.*mayor[^.]*\.", re.IGNORECASE),
    re.compile(r"reversible[^.]*\.", re.IGNORECASE),
    re.compile(r"puede revertirse[^.]*\.", re.IGNORECASE),
    re.compile(r"puede cambiar de plan nuevamente[^.]*\.", re.IGNORECASE),
    re.compile(r"puede volver a su plan anterior[^.]*\.", re.IGNORECASE),
    re.compile(r"no hay penalización por cancelar[^.]*\.", re.IGNORECASE),
]


def _strip_technical_cac_reasons(text: str) -> str:
    """Elimina explicaciones técnicas de elegibilidad que nunca deben llegar al cliente."""
    for pattern in _TECHNICAL_CAC_PHRASES:
        text = pattern.sub("", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


_TUTEO_MAP = {
    'tienes': 'tiene',
    'podrías': 'podría',
    'recibirías': 'recibiría',
    'tendrías': 'tendría',
}
_TUTEO_PATTERN = re.compile(
    r'\b(tienes|podr[ií]as|recibir[ií]as|tendr[ií]as)\b',
    re.IGNORECASE | re.UNICODE,
)

_PROMO_PATTERNS = [
    r'\+50%\s*(?:de\s*)?GB[^\s,\.]*',
    r'\d+(?:[,\.]\d+)?\s*GB\s*(?:de\s*)?(?:promoción|promo)\b[^,\.\n]*',
    r'\d+(?:[,\.]\d+)?\s*GB\s*extra\b[^,\.\n]*',
    r'\d+(?:[,\.]\d+)?\s*GB\s*adicionales\b[^,\.\n]*',
    r'\(.*?\d+\s*GB\s*base\s*\+\s*\d+(?:[,\.]\d+)?\s*GB[^\)]*\)',
]


def _fix_tuteo(text: str) -> str:
    def _repl(m: re.Match) -> str:
        original = m.group(0)
        formal = _TUTEO_MAP.get(original.lower(), original)
        return formal[0].upper() + formal[1:] if original[0].isupper() else formal
    return _TUTEO_PATTERN.sub(_repl, text)


def _fix_incorrect_promo(text: str, session) -> str:
    """
    Si el primer precio mencionado en la respuesta coincide con la renta actual
    del cliente (±$1), elimina las menciones de promoción de GB — no aplica.
    """
    # Buscar TODOS los precios y verificar que NINGUNO sea diferente
    # a la renta actual — si hay un precio diferente, la promoción sí aplica
    prices = re.findall(r'\$(\d+)/mes', text)
    if not prices:
        return text
    # Si algún precio es diferente a la renta actual, no eliminar promoción
    if any(abs(float(p) - session.current_cost) > 1.0 for p in prices):
        return text
    for pattern in _PROMO_PATTERNS:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    return re.sub(r'\n{3,}', '\n\n', text).strip()


_CHEAPER_REQUEST_PATTERN = re.compile(
    r'\b(m[aá]s\s+barato|econ[oó]mico|m[eé]nos\s+(?:caro|precio)|precio\s*m[aá]s\s*bajo|'
    r'm[aá]s\s+econ[oó]mico|plan\s+barato|algo\s+(?:m[aá]s\s+)?barato)\b',
    re.IGNORECASE | re.UNICODE,
)
_PRICE_IN_LINE_PATTERN = re.compile(r'\$(\d[\d,\.]*)/mes', re.IGNORECASE)
# Líneas que parecen listado de planes: bullet/tabla con nombre Telcel
_PLAN_LISTING_LINE = re.compile(
    r'^\s*(?:[•\-\*\|]|\d+[\.\)]\s)\s*Telcel\s+(?:Libre|Ultra)'
    r'|^Telcel\s+(?:Libre|Ultra)',
    re.IGNORECASE,
)

# Patrón de activación en modalidad incorrecta (para cliente Controlado)
_WRONG_MODAL_ACTIVATION = re.compile(
    r'(?:activar|activarlo|activarla|contratar|migrar|se\s+activa|puede\s+activar)'
    r'.*?\bmodalidad\s+abierto\b'
    r'|\bmodalidad\s+abierto\b.*?(?:activar|activarlo|contratar|migrar|se\s+activa)',
    re.IGNORECASE | re.DOTALL,
)


def _filter_ineligible_plans(text: str, user_message: str, session) -> str:
    """
    Elimina líneas de planes con precio < renta actual cuando no fueron pedidos.
    Solo actúa sobre líneas que parecen listado de planes (bullet o tabla con 'Telcel').
    """
    if session is None:
        return text
    _CHEAPER_WORDS = [
        "barato", "económico", "economico", "menor costo", "menor precio",
        "accesible", "más barato", "mas barato", "menos caro",
    ]
    if _CHEAPER_REQUEST_PATTERN.search(user_message) or any(
        w in user_message.lower() for w in _CHEAPER_WORDS
    ):
        return text  # cliente pidió explícitamente ver opciones más baratas

    current_cost = session.current_cost
    lines = text.split('\n')
    result = []
    for line in lines:
        if _PLAN_LISTING_LINE.match(line.strip()):
            prices = _PRICE_IN_LINE_PATTERN.findall(line)
            if prices:
                # Usar solo el primer precio (precio del plan) — no cashback ni otros
                # Quitar separadores de miles (coma o punto antes de 3 dígitos)
                raw = re.sub(r'[,.](?=\d{3}(?:\D|$))', '', prices[0])
                plan_price = float(raw.replace(',', ''))
                if plan_price < current_cost - 1.0:
                    continue  # omitir línea no elegible
        result.append(line)

    return re.sub(r'\n{3,}', '\n\n', '\n'.join(result))


def _filter_wrong_modality(text: str, session) -> str:
    """
    Para clientes Controlado: elimina líneas que sugieren activar un plan en
    modalidad Abierto — la activación en modalidad diferente siempre requiere CAC
    y no debe aparecer como opción directa.
    Preserva menciones informativas de precios en Abierto (sin verbos de activación).
    """
    if session is None or session.subscription_type != "Controlado":
        return text

    lines = text.split('\n')
    result = [line for line in lines if not _WRONG_MODAL_ACTIVATION.search(line)]
    return '\n'.join(result)


_NOT_TITULAR_KEYWORDS = [
    "no soy", "no es mi nombre", "soy su esposa", "soy su hijo",
    "soy su madre", "no me llamo", "equivocado de persona",
    "número equivocado", "este no es mi número",
]

_WRONG_NAME_PHRASES = [
    "mi nombre es", "me llamo",
    "el nombre está mal", "nombre equivocado",
    "el nombre está equivocado",
    "yo soy", "soy ", "mi nombre",
]


def _norm_name(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s.strip().lower())
        if unicodedata.category(c) != "Mn"
    )


def _detect_titular_issues(session, user_message: str):
    """
    Safety net pre-LLM: detecta no-titular y discrepancia de nombre.
    Retorna mensaje de respuesta o None si no aplica.
    """
    msg_lower = user_message.strip().lower()

    # A) No titular
    if session.is_titular and any(kw in msg_lower for kw in _NOT_TITULAR_KEYWORDS):
        session.is_titular = False
        return (
            "Entendemos. El cambio de plan solo puede ser gestionado por el "
            "titular de la línea. Si usted es familiar o conocido del titular, "
            "le pedimos que le informe sobre esta oferta.\n"
            "Con gusto respondemos cualquier consulta sobre los planes disponibles."
        )

    # B) Nombre incorrecto — solo si sigue considerado titular
    if session.is_titular and not session.nombre_incorrecto:
        if any(kw in msg_lower for kw in _WRONG_NAME_PHRASES):
            name_is_different = False
            name_match = re.search(
                r'(?:mi nombre es|me llamo|yo soy|soy)\s+([a-záéíóúüñ]+)',
                msg_lower,
            )
            if name_match:
                claimed = _norm_name(name_match.group(1))
                registered = _norm_name(session.first_name)
                name_is_different = bool(claimed) and claimed != registered
            elif any(
                kw in msg_lower
                for kw in ["el nombre está mal", "nombre equivocado", "el nombre está equivocado"]
            ):
                name_is_different = True

            if name_is_different:
                session.nombre_incorrecto = True
                return (
                    "Entendemos que usted es el titular de la línea. Sin embargo, "
                    "existe una discrepancia en el nombre registrado en nuestros sistemas, "
                    "lo que impide formalizar el cambio de plan desde este canal.\n\n"
                    "Para proceder con la activación, le invitamos a corregir sus datos "
                    "acudiendo a un Centro de Atención a Clientes (CAC):\n"
                    "📍 https://www.telcel.com/personas/atencion-a-clientes/puntos-de-contacto/centro-atencion"
                )

    return None


def _strip_incorrect_cac(
    text: str,
    user_message: str,
    session: SessionState,
) -> str:
    """
    Safety net: si el LLM derivó al CAC para un plan que es activable en este canal
    (misma modalidad y precio >= renta actual), elimina esa derivación y cierra
    con la pregunta de activación correcta.
    """
    if not any(m in text.lower() for m in _CAC_MARKERS):
        return text

    # Buscar plan mencionado en el mensaje del cliente
    msg_lower = user_message.lower()
    mentioned_plan = None
    for plan in CATALOG:
        if plan.plan_id.lower() in msg_lower:
            mentioned_plan = plan
            break
    if mentioned_plan is None:
        for m in re.findall(r'(?:libre|ultra)\s+\w+', msg_lower):
            mentioned_plan = find_plan("telcel " + m)
            if mentioned_plan:
                break

    if mentioned_plan is None:
        return text

    # Verificar activabilidad: precio >= renta actual en la modalidad del cliente
    plan_price = get_price(mentioned_plan, session.subscription_type)
    if plan_price < session.current_cost - 1.0:
        return text  # plan genuinamente más barato → CAC es correcto

    # Verificar si el cliente pide explícitamente modalidad diferente a la suya
    msg_upper = user_message.upper()
    if "ABIERTO" in msg_upper and session.subscription_type == "Controlado":
        return text
    if "CONTROLADO" in msg_upper and session.subscription_type == "Abierto":
        return text

    # Eliminar párrafos/líneas que contengan derivación al CAC o Soporte
    paragraphs = re.split(r'\n+', text)
    cleaned = [p for p in paragraphs if not any(m in p.lower() for m in _CAC_MARKERS)]
    clean_text = "\n".join(cleaned).strip()

    # Agregar pregunta de activación si no hay una
    if "¿Le gustaría activar" not in clean_text:
        activation_q = (
            f"¿Le gustaría activar el "
            f"{mentioned_plan.plan_id} {session.subscription_type}?"
        )
        clean_text = (clean_text + "\n\n" + activation_q).strip()

    return clean_text


def _check_invented_plans(text: str, session: SessionState) -> str:
    plan_mentions = re.findall(
        r'Telcel\s+(?:Libre|Ultra)\s+(?:\d+|VIP|Ilimitado)',
        text,
        re.IGNORECASE
    )
    for mention in plan_mentions:
        clean = re.sub(r'\s+(Controlado|Abierto)$', '', mention.strip(), flags=re.IGNORECASE)
        plan_obj = find_plan(clean)

        # Plan no existe
        if not plan_obj:
            logger.warning("[PLAN_INVENTADO] '%s' phone=%s", clean, session.phone_number)
            plan = session.plan_anclado if session.plan_anclado else "el plan recomendado"
            return f"¿Le gustaría activar el *{plan}*?"

        # Plan existe pero verificar precio — buscar precio justo después del nombre del plan
        price_real = get_price(plan_obj, session.subscription_type)
        pattern = re.escape(mention) + r'[^$]*\$(\d{3,4})/mes'
        price_match = re.search(pattern, text, re.IGNORECASE)
        if price_match:
            price_mentioned = float(price_match.group(1))
            price_alt = get_price(plan_obj, "Abierto" if session.subscription_type == "Controlado" else "Controlado")
            if abs(price_mentioned - price_real) > PRICE_TOLERANCE_MXN and abs(price_mentioned - price_alt) > PRICE_TOLERANCE_MXN:
                logger.warning("[PRECIO_INCORRECTO] plan='%s' real=$%.0f mencionado=$%.0f phone=%s",
                               clean, price_real, price_mentioned, session.phone_number)
                plan = session.plan_anclado if session.plan_anclado else "el plan recomendado"
                return f"¿Le gustaría activar el *{plan}*?"

    return text


def create_agent(session: SessionState, messages: List[Dict] = None) -> Agent:
    """Crea el agente con system prompt, herramientas e historial inicial."""
    return Agent(
        model=oci_model,
        system_prompt=build_system_prompt(session),
        tools=make_tools(session),
        callback_handler=None,
        messages=messages or [],
    )


def run_turn(
    session: SessionState,
    user_message: str,
    history: List[Dict] = None,
) -> Tuple[str, List[Dict]]:
    """
    Ejecuta un turno de conversación con historial persistente.

    Args:
        session:      Estado actual de la sesión.
        user_message: Mensaje del cliente en este turno.
        history:      Historial simple [{role, content}] de turnos anteriores.

    Returns:
        Tupla (respuesta_texto, historial_actualizado)
    """
    history = history or []

    # Inicializar plan_anclado al primer turno real (antes de cualquier
    # bloque pre-LLM, ya que varios de ellos lo referencian directamente)
    if not session.plan_anclado:
        _anclado_target = recommend_plan(session.current_cost, session.subscription_type)
        if _anclado_target:
            session.plan_anclado = f"{_anclado_target.plan_id} {session.subscription_type}"

    # ── Detección pre-LLM: titular y nombre ───────────────────────────────────
    titular_msg = _detect_titular_issues(session, user_message)
    if titular_msg is not None:
        updated_history = history + [
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": titular_msg},
        ]
        return _apply_debug(titular_msg, [], user_message), updated_history

    # ── Stage END — cambio ya procesado ──────────────────────────────────────
    if session.stage == "END" and session.end_reason == "success":
        # mostrar detalle del cambio procesado
        _cierre = (
            f"Su cambio de plan ya fue procesado, {session.first_name}.\n\n"
            f"🔄 *Detalle del cambio:*\n"
            f"- Plan anterior: *{session.previous_plan_name} {session.subscription_type}*\n"
            f"- Plan nuevo: *{session.plan_selected} {session.subscription_type}*\n\n"
            f"En breve nos contactaremos para dar seguimiento.\n\n"
            f"Si tiene alguna duda puede comunicarse con Soporte al 800 220 9518."
        )
        updated_history = history + [
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": _cierre},
        ]
        return _apply_debug(_cierre, [], user_message), updated_history
    elif session.stage == "END" and session.end_reason == "blocked":
        # solo responder preguntas informativas normalmente
        pass  # continúa al flujo normal

    # ── Flujo de contratación — tiene prioridad sobre detecciones pre-LLM ────
    # Se mueve aquí para que ninguna detección pre-LLM intercepte mensajes como
    # "ACEPTO cuando comienza el cobro" mientras se espera confirmación.
    if session.stage == "CONTRACT":
        contract_msg = handle_contract_turn(session, user_message)

        if contract_msg is not None:
            updated_history = history + [
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": contract_msg},
            ]
            return _apply_debug(contract_msg, [], user_message), updated_history

        if session.stage == "POST_SALE":
            post_sale_text = build_post_sale_message(session)
            session.stage = "END"
            updated_history = history + [
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": post_sale_text},
            ]
            return _apply_debug(post_sale_text, [], user_message), updated_history

        if session.stage == "PERSUASION":
            # Cliente canceló — respuesta empática sin LLM
            from app.tools.telcel_tools import make_tools
            tools = make_tools(session)
            manejar_fn = next((t for t in tools if t.tool_name == "manejar_objecion"), None)
            if manejar_fn:
                result = manejar_fn(motivo="")
                response_text = result.replace(
                    "RESPONDE EXACTAMENTE CON ESTE TEXTO SIN MODIFICAR NADA:\n\n", ""
                )
                updated_history = history + [
                    {"role": "user", "content": user_message},
                    {"role": "assistant", "content": response_text},
                ]
                return _apply_debug(response_text, ["manejar_objecion"], user_message), updated_history
        # else: pregunta durante espera → continúa al LLM con contexto de contrato

    # ── Detección pre-LLM: botones quick_reply del mensaje de campaña ────────
    # ("Sí, compáralo" / "En otro momento") — coincidencia determinística por
    # id de botón interactivo o por texto/payload de botón de template, sin
    # depender del router semántico.
    _msg_btn_norm = re.sub(r'[¿?¡!,\.]', ' ', user_message.strip().lower())
    _msg_btn_norm = _norm_name(_msg_btn_norm)
    _msg_btn_norm = re.sub(r'\s+', ' ', _msg_btn_norm).strip()

    if _msg_btn_norm in {"comparar", "si comparalo"}:
        from app.tools.telcel_tools import make_tools
        tools = make_tools(session)
        comparar_fn = next((t for t in tools if t.tool_name == "comparar_planes"), None)
        if comparar_fn:
            result = comparar_fn(plan_id="")
            response_text = result.replace(
                "RESPONDE EXACTAMENTE CON ESTE TEXTO SIN MODIFICAR NADA:\n\n", ""
            )
            updated_history = history + [
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": response_text},
            ]
            return _apply_debug(response_text, ["comparar_planes"], user_message), updated_history

    if _msg_btn_norm in {"despues", "en otro momento"} and session.stage == "PERSUASION":
        from app.tools.telcel_tools import make_tools
        tools = make_tools(session)
        manejar_fn = next((t for t in tools if t.tool_name == "manejar_objecion"), None)
        if manejar_fn:
            result = manejar_fn(motivo="")
            response_text = result.replace(
                "RESPONDE EXACTAMENTE CON ESTE TEXTO SIN MODIFICAR NADA:\n\n", ""
            )
            updated_history = history + [
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": response_text},
            ]
            return _apply_debug(response_text, ["manejar_objecion"], user_message), updated_history

    msg_lower = user_message.lower()

    # ── Clasificación semántica de intención ─────────────────────────────────
    _intencion = classify(user_message)

    # ── Router semántico — reemplaza todos los bloques pre-LLM de listas ─────
    if _intencion == "vigencia_promo":
        response_text = (
            f"Esta promoción tiene vigencia el día de hoy. "
            f"Si en otro momento desea revisarla, con gusto le ayudamos "
            f"a encontrar la mejor opción disponible para usted.\n\n"
            f"¿Le gustaría activar el *{session.plan_anclado}*?"
        )
        updated_history = history + [
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": response_text},
        ]
        return _apply_debug(response_text, [], user_message), updated_history

    elif _intencion == "criterio_promo":
        target = recommend_plan(session.current_cost, session.subscription_type)
        plan_name = f"{target.plan_id} {session.subscription_type}" if target else "el plan recomendado"
        if target:
            plan_price = get_price(target, session.subscription_type)
            tiene_promo_gb = (
                session.has_promotion
                and target.family == "Telcel Libre"
                and plan_price > session.current_cost + 1.0
            )
        else:
            tiene_promo_gb = False
        if tiene_promo_gb:
            msg_promo = (
                f"Las promociones son beneficios que Telcel activa en planes "
                f"seleccionados para darles más valor. "
                f"El {plan_name} sí incluye esta promoción."
            )
        else:
            msg_promo = (
                f"El {plan_name} incluye más GB y beneficios "
                f"para su línea sin costo adicional."
            )
        response_text = f"{msg_promo}\n\n¿Le gustaría activar el {plan_name}?"
        updated_history = history + [
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": response_text},
        ]
        return _apply_debug(response_text, [], user_message), updated_history

    elif _intencion == "reglas_internas":
        _BENEFICIO_KEYWORDS = [
            "cashback", "claro video", "claro drive", "apps", "gigas",
            "datos", "llamadas", "sms", "roaming", "cobertura", "plan",
            "beneficio", "promocion", "promoción",
        ]
        if not any(b in msg_lower for b in _BENEFICIO_KEYWORDS):
            response_text = (
                "Solo puedo ayudarle con información sobre planes y "
                "beneficios de Telcel.\n\n"
                "¿Le gustaría que le muestre las opciones disponibles "
                "para usted?"
            )
            updated_history = history + [
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": response_text},
            ]
            return _apply_debug(response_text, [], user_message), updated_history

    elif _intencion == "proceso_activacion":
        response_text = (
            f"Es muy sencillo — solo confirme que desea el cambio "
            f"y nosotros nos encargamos del resto.\n\n"
            f"¿Le gustaría activar el *{session.plan_anclado}*?"
        )
        updated_history = history + [
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": response_text},
        ]
        return _apply_debug(response_text, [], user_message), updated_history

    elif _intencion == "por_que_cac":
        response_text = (
            f"Algunos cambios requieren gestión a través de nuestros "
            f"canales especializados para garantizar la mejor atención. "
            f"Soporte al 800 220 9518 y los CAC cuentan con las "
            f"herramientas necesarias para ese trámite.\n\n"
            f"¿Le gustaría activar el *{session.plan_anclado}*?"
        )
        updated_history = history + [
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": response_text},
        ]
        return _apply_debug(response_text, [], user_message), updated_history

    elif _intencion == "facturacion":
        response_text = (
            "Para detalles sobre su facturación y fechas de cobro, "
            "le recomiendo consultar con Soporte al 800 220 9518 "
            "o revisar su información en la app Mi Telcel.\n\n"
            f"¿Le gustaría activar el *{session.plan_anclado}*?"
        )
        updated_history = history + [
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": response_text},
        ]
        return _apply_debug(response_text, [], user_message), updated_history

    elif _intencion == "info_plan_actual":
        from app.tools.telcel_tools import make_tools
        tools = make_tools(session)
        informar_fn = next((t for t in tools if t.tool_name == "informar_plan_actual"), None)
        if informar_fn:
            result = informar_fn()
            response_text = result.replace(
                "RESPONDE EXACTAMENTE CON ESTE TEXTO SIN MODIFICAR NADA:\n\n", ""
            )
            updated_history = history + [
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": response_text},
            ]
            return _apply_debug(response_text, ["informar_plan_actual"], user_message), updated_history

    elif _intencion == "comparar_beneficios":
        from app.tools.telcel_tools import make_tools
        tools = make_tools(session)
        comparar_fn = next((t for t in tools if t.tool_name == "comparar_planes"), None)
        if comparar_fn:
            result = comparar_fn(plan_id="")
            response_text = result.replace(
                "RESPONDE EXACTAMENTE CON ESTE TEXTO SIN MODIFICAR NADA:\n\n", ""
            )
            updated_history = history + [
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": response_text},
            ]
            return _apply_debug(response_text, ["comparar_planes"], user_message), updated_history

    elif _intencion == "planes_mas_baratos":
        _QUEJA_KEYWORDS = [
            "quejar", "queja", "descuento", "resuelvelo", "resolvelo",
            "mal servicio", "no me ayudas", "no sirve", "exijo",
        ]
        if not any(k in msg_lower for k in _QUEJA_KEYWORDS):
            from app.tools.telcel_tools import make_tools
            tools = make_tools(session)
            presentar_fn = next((t for t in tools if t.tool_name == "presentar_planes"), None)
            if presentar_fn:
                result = presentar_fn(criterio="mas barato", tipo="mas_barato")
                if result.startswith("RESPONDE EXACTAMENTE CON ESTE TEXTO"):
                    response_text = result.replace(
                        "RESPONDE EXACTAMENTE CON ESTE TEXTO SIN MODIFICAR NADA:\n\n", ""
                    )
                    updated_history = history + [
                        {"role": "user", "content": user_message},
                        {"role": "assistant", "content": response_text},
                    ]
                    return _apply_debug(response_text, ["presentar_planes"], user_message), updated_history

    elif _intencion == "planes_mas_caros":
        from app.tools.telcel_tools import make_tools
        tools = make_tools(session)
        presentar_fn = next((t for t in tools if t.tool_name == "presentar_planes"), None)
        if presentar_fn:
            result = presentar_fn(criterio="mas caro", tipo="mas_caro")
            if result.startswith("RESPONDE EXACTAMENTE CON ESTE TEXTO"):
                response_text = result.replace(
                    "RESPONDE EXACTAMENTE CON ESTE TEXTO SIN MODIFICAR NADA:\n\n", ""
                )
                updated_history = history + [
                    {"role": "user", "content": user_message},
                    {"role": "assistant", "content": response_text},
                ]
                return _apply_debug(response_text, ["presentar_planes"], user_message), updated_history

    elif _intencion == "planes_ultra":
        from app.tools.telcel_tools import make_tools
        tools = make_tools(session)
        presentar_fn = next((t for t in tools if t.tool_name == "presentar_planes"), None)
        if presentar_fn:
            result = presentar_fn(criterio="general", tipo="ultra")
            if result.startswith("RESPONDE EXACTAMENTE CON ESTE TEXTO"):
                response_text = result.replace(
                    "RESPONDE EXACTAMENTE CON ESTE TEXTO SIN MODIFICAR NADA:\n\n", ""
                )
                updated_history = history + [
                    {"role": "user", "content": user_message},
                    {"role": "assistant", "content": response_text},
                ]
                return _apply_debug(response_text, ["presentar_planes"], user_message), updated_history

    elif _intencion == "planes_libre":
        from app.tools.telcel_tools import make_tools
        tools = make_tools(session)
        presentar_fn = next((t for t in tools if t.tool_name == "presentar_planes"), None)
        if presentar_fn:
            result = presentar_fn(criterio="general", tipo="libre")
            if result.startswith("RESPONDE EXACTAMENTE CON ESTE TEXTO"):
                response_text = result.replace(
                    "RESPONDE EXACTAMENTE CON ESTE TEXTO SIN MODIFICAR NADA:\n\n", ""
                )
                updated_history = history + [
                    {"role": "user", "content": user_message},
                    {"role": "assistant", "content": response_text},
                ]
                return _apply_debug(response_text, ["presentar_planes"], user_message), updated_history

    elif _intencion == "planes_mas_gb":
        from app.tools.telcel_tools import make_tools
        tools = make_tools(session)
        presentar_fn = next((t for t in tools if t.tool_name == "presentar_planes"), None)
        if presentar_fn:
            result = presentar_fn(criterio="general", tipo="mas_gb")
            if result.startswith("RESPONDE EXACTAMENTE CON ESTE TEXTO"):
                response_text = result.replace(
                    "RESPONDE EXACTAMENTE CON ESTE TEXTO SIN MODIFICAR NADA:\n\n", ""
                )
                updated_history = history + [
                    {"role": "user", "content": user_message},
                    {"role": "assistant", "content": response_text},
                ]
                return _apply_debug(response_text, ["presentar_planes"], user_message), updated_history

    elif _intencion == "otra_recomendacion":
        session.esperando_criterio_recomendacion = True
        response_text = (
            f"Con gusto, {session.first_name}. ¿Qué beneficio es más "
            f"importante para usted?\n\n"
            f"• 📶 Más GB de datos\n"
            f"• 💳 Mayor cashback\n"
            f"• 📱 Apps ilimitadas incluidas\n\n"
            f"¿Cuál prefiere?"
        )
        updated_history = history + [
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": response_text},
        ]
        return _apply_debug(response_text, [], user_message), updated_history

    elif _intencion == "confirmacion_activacion":
        from app.tools.telcel_tools import make_tools
        tools = make_tools(session)
        iniciar_fn = next((t for t in tools if t.tool_name == "iniciar_contratacion"), None)
        if iniciar_fn and session.plan_anclado:
            plan_id = session.plan_anclado.removesuffix(f" {session.subscription_type}").strip()
            iniciar_fn(plan_id=plan_id)
            if session.stage == "CONTRACT":
                response_text = build_summary_template(session)
                session.awaiting_contract_confirmation = True
                updated_history = history + [
                    {"role": "user", "content": user_message},
                    {"role": "assistant", "content": response_text},
                ]
                if len(updated_history) > 20:
                    updated_history = updated_history[-20:]
                return _apply_debug(response_text, ["iniciar_contratacion"], user_message), updated_history

    # ── Fallbacks pre-LLM que NO van al router semántico ──────────────────────
    msg_lower_clean = re.sub(r'[¿?¡!,\.]', ' ', msg_lower).strip()

    # ── Detección pre-LLM: pregunta sobre por qué se deriva al CAC/Soporte ───
    # (conservado como fallback — por_que_cac ya está en el router)
    _CAC_QUESTIONS = [
        "porque tengo que comunicarme",
        "por qué tengo que comunicarme",
        "porque tengo que ir al cac",
        "por qué tengo que ir al cac",
        "no puedes cambiarlo tu",
        "no puedes cambiarlo tú",
        "no lo puedes cambiar",
        "por que me mandas",
        "por qué me mandas",
        "no puedes hacerlo tu",
        "no puedes hacerlo tú",
        "porque no puedes",
        "por qué no puedes",
    ]
    if any(q in msg_lower_clean for q in _CAC_QUESTIONS):
        response_text = (
            f"Algunos cambios requieren gestión a través de nuestros "
            f"canales especializados para garantizar la mejor atención. "
            f"Soporte al 800 220 9518 y los CAC cuentan con las "
            f"herramientas necesarias para ese trámite.\n\n"
            f"¿Le gustaría activar el *{session.plan_anclado}*?"
        )
        updated_history = history + [
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": response_text},
        ]
        return _apply_debug(response_text, [], user_message), updated_history

    # ── Detección pre-LLM: cliente pregunta por GB específicos ───────────────
    _GB_ESPECIFICO_MATCH = re.search(r'\b(\d+)\s*(?:gb|gigas?)\b', msg_lower_clean)
    if _GB_ESPECIFICO_MATCH and not any(w in msg_lower_clean for w in [
        "cuantos", "cuántos", "tengo", "tiene mi plan", "tiene el plan",
    ]):
        from app.tools.telcel_tools import make_tools
        tools = make_tools(session)
        presentar_fn = next((t for t in tools if t.tool_name == "presentar_planes"), None)
        if presentar_fn:
            criterio_gb = _GB_ESPECIFICO_MATCH.group(0)
            result = presentar_fn(criterio=criterio_gb, tipo="especifico")
            if result.startswith("RESPONDE EXACTAMENTE CON ESTE TEXTO"):
                response_text = result.replace(
                    "RESPONDE EXACTAMENTE CON ESTE TEXTO SIN MODIFICAR NADA:\n\n", ""
                )
                updated_history = history + [
                    {"role": "user", "content": user_message},
                    {"role": "assistant", "content": response_text},
                ]
                return _apply_debug(response_text, ["presentar_planes"], user_message), updated_history

    # ── Detección pre-LLM: cliente pide modalidad diferente ─────────
    alt_modality = "Abierto" if session.subscription_type == "Controlado" else "Controlado"
    if alt_modality.lower() in msg_lower_clean:
        from app.tools.telcel_tools import make_tools
        tools = make_tools(session)
        presentar_fn = next((t for t in tools if t.tool_name == "presentar_planes"), None)
        if presentar_fn:
            result = presentar_fn(criterio=alt_modality, tipo="general")
            if result.startswith("RESPONDE EXACTAMENTE CON ESTE TEXTO"):
                response_text = result.replace(
                    "RESPONDE EXACTAMENTE CON ESTE TEXTO SIN MODIFICAR NADA:\n\n", ""
                )
                updated_history = history + [
                    {"role": "user", "content": user_message},
                    {"role": "assistant", "content": response_text},
                ]
                return _apply_debug(response_text, ["presentar_planes"], user_message), updated_history

    # ── Detección pre-LLM: solicitud de otra recomendación ──────────
    _OTRA_RECOMENDACION = [
        "otra recomendacion", "otra recomendación",
        "dame otra", "otra opcion", "otra opción",
        "recomiendame otro", "recomiéndame otro",
        "que mas recomiendas", "qué más recomiendas",
        "cual me recomiendas", "cuál me recomiendas",
    ]
    if any(q in msg_lower_clean for q in _OTRA_RECOMENDACION):
        session.esperando_criterio_recomendacion = True
        response_text = (
            f"Con gusto, {session.first_name}. ¿Qué beneficio es más "
            f"importante para usted?\n\n"
            f"• 📶 Más GB de datos\n"
            f"• 💳 Mayor cashback\n"
            f"• 📱 Apps ilimitadas incluidas\n\n"
            f"¿Cuál prefiere?"
        )
        updated_history = history + [
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": response_text},
        ]
        return _apply_debug(response_text, [], user_message), updated_history

    # ── Detección pre-LLM: respuesta al criterio de recomendación ────
    if session.esperando_criterio_recomendacion:
        session.esperando_criterio_recomendacion = False
        from app.tools.telcel_tools import make_tools
        tools = make_tools(session)
        presentar_fn = next((t for t in tools if t.tool_name == "presentar_planes"), None)
        if presentar_fn:
            if any(w in msg_lower_clean for w in ["giga", "gb", "datos", "navegacion"]):
                result = presentar_fn(criterio="mas gb", tipo="mas_caro")
            elif any(w in msg_lower_clean for w in ["cashback", "dinero", "descuento", "precio"]):
                result = presentar_fn(criterio="cashback", tipo="libre")
            elif any(w in msg_lower_clean for w in ["apps", "aplicaciones", "redes", "sociales"]):
                result = presentar_fn(criterio="apps libres", tipo="libre")
            else:
                result = presentar_fn(criterio="general", tipo="mas_caro")
            # Si el resultado no es texto rígido (ej. tipo="libre" con un solo
            # plan elegible devuelve JSON para que el LLM lo redacte), dejar
            # pasar el turno al flujo normal del LLM en vez de interceptar.
            if result.startswith("RESPONDE EXACTAMENTE CON ESTE TEXTO"):
                response_text = result.replace(
                    "RESPONDE EXACTAMENTE CON ESTE TEXTO SIN MODIFICAR NADA:\n\n", ""
                )
                updated_history = history + [
                    {"role": "user", "content": user_message},
                    {"role": "assistant", "content": response_text},
                ]
                return _apply_debug(response_text, ["presentar_planes"], user_message), updated_history

    # ── Detección pre-LLM: rechazo corto ─────────────────────────────
    _RECHAZOS_CORTOS = {"no", "no.", "no!", "nope", "nel", "nop", "paso"}
    if user_message.strip().lower() in _RECHAZOS_CORTOS and session.stage == "PERSUASION":
        from app.tools.telcel_tools import make_tools
        tools = make_tools(session)
        manejar_fn = next((t for t in tools if t.tool_name == "manejar_objecion"), None)
        if manejar_fn:
            result = manejar_fn(motivo="")
            response_text = result.replace(
                "RESPONDE EXACTAMENTE CON ESTE TEXTO SIN MODIFICAR NADA:\n\n", ""
            )
            updated_history = history + [
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": response_text},
            ]
            return _apply_debug(response_text, ["manejar_objecion"], user_message), updated_history

    # ── Flujo de contratación determinístico (sin LLM) ────────────────────────
    if session.stage == "CONTRACT":
        contract_msg = handle_contract_turn(session, user_message)

        if contract_msg is not None:
            # Respuesta determinística — enviar directamente
            updated_history = history + [
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": contract_msg},
            ]
            return _apply_debug(contract_msg, [], user_message), updated_history

        if session.stage == "POST_SALE":
            # OTP validado — generar mensaje de confirmación
            post_sale_text = build_post_sale_message(session)
            session.stage = "END"
            updated_history = history + [
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": post_sale_text},
            ]
            return _apply_debug(post_sale_text, [], user_message), updated_history

        if session.stage == "PERSUASION":
            from app.tools.telcel_tools import make_tools
            tools = make_tools(session)
            manejar_fn = next((t for t in tools if t.tool_name == "manejar_objecion"), None)
            if manejar_fn:
                result = manejar_fn(motivo="")
                response_text = result.replace(
                    "RESPONDE EXACTAMENTE CON ESTE TEXTO SIN MODIFICAR NADA:\n\n", ""
                )
                updated_history = history + [
                    {"role": "user", "content": user_message},
                    {"role": "assistant", "content": response_text},
                ]
                return _apply_debug(response_text, ["manejar_objecion"], user_message), updated_history
        # else: pregunta durante espera → continúa al LLM con contexto de contrato

    # ── Flujo conversacional con LLM ─────────────────────────────────────────

    # Convertir historial simple al formato Strands / Bedrock Converse API.
    # El formato correcto de un content block de texto es {"text": "..."} —
    # NO {"type": "text", "text": "..."}.
    prior_messages = [
        {"role": msg["role"], "content": [{"text": msg["content"]}]}
        for msg in history
    ]

    # El historial va en el constructor, no como kwarg de agent().
    # Pasar messages= a agent() lo mete en **kwargs (deprecado) y no
    # tiene efecto en la memoria de la conversación.
    logger.info("[HISTORIAL] %d mensajes previos phone=%s",
                len(prior_messages), session.phone_number)
    logger.info("[HISTORIAL_DETALLE] %d mensajes phone=%s ultimo_rol=%s ultimo_preview='%s'",
                len(prior_messages),
                session.phone_number,
                prior_messages[-1].get("role", "?") if prior_messages else "ninguno",
                str(prior_messages[-1].get("content", ""))[:80] if prior_messages else "")
    agent = create_agent(session, messages=prior_messages)

    try:
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=UserWarning, module="strands")
            response = agent(user_message)
    except UnicodeError:
        model_params = oci_model.config.get("params", {})
        logger.error(
            "[UNICODE_ERROR] fallo de codificación en la llamada al modelo "
            "phone=%s stage=%s temperature=%s max_tokens=%s msg='%s'",
            session.phone_number, session.stage,
            model_params.get("temperature"), model_params.get("max_tokens"),
            user_message[:120], exc_info=True,
        )
        raise
    except Exception:
        model_params = oci_model.config.get("params", {})
        logger.error(
            "[LLM_ERROR] fallo en la llamada al modelo "
            "phone=%s stage=%s temperature=%s max_tokens=%s msg='%s'",
            session.phone_number, session.stage,
            model_params.get("temperature"), model_params.get("max_tokens"),
            user_message[:120], exc_info=True,
        )
        raise

    response_text = ""
    if hasattr(response, "message") and response.message:
        for block in response.message.get("content", []):
            if isinstance(block, dict) and "text" in block:
                response_text += block.get("text", "")
    response_text = response_text.strip()
    logger.info("[RESPONSE_DEBUG] stop_reason=%s text_len=%d phone=%s",
                getattr(response, "stop_reason", "?"),
                len(response_text),
                session.phone_number)
    if hasattr(response, "message") and response.message:
        logger.info("[RESPONSE_MESSAGE] %s phone=%s",
                    str(response.message)[:200],
                    session.phone_number)
    # Eliminar corchetes vacíos que Llama a veces emite como artefacto
    response_text = re.sub(r'\[\s*\]', '', response_text).strip()

    # Detectar y loggear terminaciones anómalas del modelo
    stop_reason = getattr(response, "stop_reason", None)
    usage = getattr(response, "usage", None)
    if usage:
        input_tokens = getattr(usage, "input_tokens", "?")
        output_tokens = getattr(usage, "output_tokens", "?")
        logger.info("[TOKENS] input=%s output=%s phone=%s",
                    input_tokens, output_tokens, session.phone_number)
    if stop_reason == "max_tokens":
        logger.warning("[TRUNCATED] respuesta cortada por max_tokens phone=%s msg='%s'",
                       session.phone_number, user_message[:60])
    elif stop_reason not in ("end_turn", "tool_use", None):
        logger.warning("[STOP_REASON] terminación inesperada reason=%s phone=%s msg='%s'",
                       stop_reason, session.phone_number, user_message[:60])

    # Safety net — si el LLM revela lógica interna del proceso de verificación
    # reemplazar la respuesta completa con el mensaje programado de proceso
    logger.info("[RESPONSE_TEXT_RAW]\n%s\nphone=%s", response_text, session.phone_number)

    _INTERNAL_LEAK_TERMS = [
        "CONTRATACION_INICIADA",
        "Verificación de seguridad",
        "OTP",
        "(OTP)",
        "invocaré iniciar_contratacion",
        "invocar iniciar_contratacion",
        "flujo completo de contratación",
        "flujo de contratación",
        "siga el flujo",
        "necesito seguir el proceso",
        "el proceso establecido",
        "recibirá las instrucciones para completar",
    ]
    if any(t in response_text for t in _INTERNAL_LEAK_TERMS):
        if "CONTRATACION_INICIADA" in response_text:
            session.stage = "CONTRACT"
            contract_msg = build_summary_template(session)
            session.awaiting_contract_confirmation = True
            response_text = contract_msg
        else:
            plan = session.plan_anclado if session.plan_anclado else "el plan"
            response_text = (
                f"Es muy sencillo — solo confirme que desea el cambio "
                f"y nosotros nos encargamos del resto.\n\n"
                f"¿Le gustaría activar el *{plan}*?"
            )

    # Safety net — si estamos esperando confirmación del contrato,
    # siempre recordar al cliente que debe responder
    if session.awaiting_contract_confirmation and response_text:
        if not any(w in response_text.upper() for w in ["ACEPTO", "CONFIRMO"]):
            response_text = (
                response_text.rstrip() +
                "\n\nPara continuar, presione *Sí, activar* para confirmar, "
                "o *No, cancelar* para cancelar y continuar con la conversación."
            )

    # Safety net — si el response_text contiene el recuadro interno
    # de iniciar_contratacion, reemplazarlo con el template correcto
    if "┌─────" in response_text or "Resumen de activación" in response_text:
        contract_msg = handle_contract_turn(session, user_message)
        if contract_msg:
            response_text = contract_msg

    # ── Interceptar iniciar_contratacion — ignorar response_text del LLM ────────
    # Cuando el LLM invocó iniciar_contratacion, su response_text nunca llega
    # al cliente: se reemplaza siempre con el template determinístico y se
    # retorna de inmediato, sin pasar por clean_response ni tool-pattern check.
    _tools_invoked = [
        block["toolUse"]["name"]
        for msg in agent.messages
        for block in msg.get("content", [])
        if isinstance(block, dict) and "toolUse" in block
    ]
    if "iniciar_contratacion" in _tools_invoked and session.stage == "CONTRACT":
        contract_msg = build_summary_template(session)
        session.awaiting_contract_confirmation = True
        response_text = contract_msg  # reemplaza COMPLETAMENTE el response_text del LLM
        updated_history = history + [
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": response_text},
        ]
        if len(updated_history) > 20:
            updated_history = updated_history[-20:]
        return _apply_debug(response_text, _tools_invoked, user_message), updated_history

    # Interceptar cualquier tool que retorne texto rígido ("RESPONDE EXACTAMENTE...")
    _rigid_text = None
    for msg in agent.messages:
        if _rigid_text:
            break
        for block in msg.get("content", []):
            if isinstance(block, dict) and "toolResult" in block:
                tool_content = block["toolResult"].get("content", [])
                if tool_content:
                    tool_text = tool_content[0].get("text", "")
                    if tool_text and "RESPONDE EXACTAMENTE CON ESTE TEXTO" in tool_text:
                        _rigid_text = tool_text.replace(
                            "RESPONDE EXACTAMENTE CON ESTE TEXTO SIN MODIFICAR NADA:\n\n",
                            ""
                        )
                        break

    if _rigid_text:
        if "CONTRATACION_INICIADA" in _rigid_text:
            contract_msg = build_summary_template(session)
            session.awaiting_contract_confirmation = True
            _rigid_text = contract_msg
        updated_history = history + [
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": _rigid_text},
        ]
        if len(updated_history) > 20:
            updated_history = updated_history[-20:]
        return _apply_debug(_rigid_text, _tools_invoked, user_message), updated_history

    # ── Fallback: respuesta vacía o solo caracteres especiales ("()") ─────────
    if not response_text or response_text.strip("() \n") == "":
        response_text = (
            "Solo puedo ayudarle con información sobre planes Telcel. "
            "Para consultas adicionales puede comunicarse con Soporte al 800 220 9518 "
            "o acudir a un Centro de Atención a Clientes.\n\n"
            "¿Le gustaría que continuemos?"
        )

    # Llama 4 Maverick a veces escribe herramientas como texto literal:
    # "[tool_name]" o "tool_name(param='valor')" en lugar de invocarlas.
    # Si se detecta ese patrón, se reintenta una vez con un agente fresco.
    _TOOL_PATTERN = re.compile(
        r'(\[[a-z_]+(?:\([^)]*\))?\]|[a-z_]+\([^)]*\)|\([a-z_]+,\s*\w+=)',
        re.IGNORECASE
    )
    if _TOOL_PATTERN.search(response_text):
        logger.warning(
            "[TOOL_LEAK_RETRY] patrón de tool detectado en texto, reintentando "
            "phone=%s stage=%s original='%s'",
            session.phone_number, session.stage, response_text[:200],
        )
        agent_retry = create_agent(session, messages=prior_messages)
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=UserWarning, module="strands")
                response2 = agent_retry(user_message)
        except Exception:
            model_params = oci_model.config.get("params", {})
            logger.error(
                "[LLM_ERROR] fallo en el reintento por tool-leak "
                "phone=%s stage=%s temperature=%s max_tokens=%s msg='%s'",
                session.phone_number, session.stage,
                model_params.get("temperature"), model_params.get("max_tokens"),
                user_message[:120], exc_info=True,
            )
            raise
        retry_text = ""
        if hasattr(response2, "message") and response2.message:
            for block in response2.message.get("content", []):
                if isinstance(block, dict) and "text" in block:
                    retry_text += block.get("text", "")
        retry_text = _TOOL_PATTERN.sub('', retry_text).strip()
        if retry_text:
            response_text = retry_text
            logger.info(
                "[TOOL_LEAK_RETRY] reintento exitoso phone=%s", session.phone_number
            )
        else:
            response_text = "Por favor, ¿podría repetir su pregunta?"
            logger.warning(
                "[TOOL_LEAK_RETRY] reintento devolvió vacío, usando fallback phone=%s",
                session.phone_number,
            )

    REJECTION_WORDS = {
        "no",
        "no quiero",
        "no me interesa",
        "no gracias",
        "no por ahora",
        "paso",
        "no aplica",
    }
    is_rejection = user_message.strip().lower() in REJECTION_WORDS
    response_text = _check_invented_plans(response_text, session)
    response_text = clean_response(response_text, is_rejection=is_rejection, session=session, user_message=user_message)
    response_text = _strip_incorrect_cac(response_text, user_message, session)

    updated_history = history + [
        {"role": "user", "content": user_message},
        {"role": "assistant", "content": response_text},
    ]

    # Limitar a los últimos 20 mensajes (10 intercambios)
    if len(updated_history) > 20:
        updated_history = updated_history[-20:]

    # Último safety net — si response_text es la señal de contratación
    if "CONTRATACION_INICIADA" in response_text:
        session.stage = "CONTRACT"
        contract_msg = build_summary_template(session)
        session.awaiting_contract_confirmation = True
        updated_history = history + [
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": contract_msg},
        ]
        if len(updated_history) > 20:
            updated_history = updated_history[-20:]
        return _apply_debug(contract_msg, ["iniciar_contratacion"], user_message), updated_history

    # Safety net — LLM generó resumen de contratación sin invocar iniciar_contratacion
    if (session.stage == "PERSUASION" and
        session.plan_anclado and
        "está por confirmar el cambio de plan" in response_text and
        "Plan actual:" in response_text and
        "Nuevo plan:" in response_text):
        session.stage = "CONTRACT"
        session.plan_selected = session.plan_anclado.removesuffix(
            f" {session.subscription_type}"
        ).strip()
        session.awaiting_contract_confirmation = True
        logger.info("[SAFETY_CONTRACT] LLM generó resumen sin tool phone=%s",
                    session.phone_number)

    return _apply_debug(response_text, _tools_invoked, user_message), updated_history
