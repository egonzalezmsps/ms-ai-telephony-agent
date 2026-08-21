"""
contract/contract_flow.py

Flujo de contratación determinístico (sin LLM).
Maneja: confirmación verbal → OTP → autenticación → post-venta.
"""

import logging
import uuid
from typing import Optional

from app.catalog.plans import find_plan, get_price, get_cashback
from app.integrations.telcel_apis.client import (
    TelcelAPIError,
    call_communication_message,
    call_create_process,
    call_create_product_order,
)

logger = logging.getLogger(__name__)

MAX_OTP_ATTEMPTS = 3
MAX_OTP_RESENDS = 3

_SOPORTE_TEL = "800 220 9518"
_OTP_INVALID_CODE = "BE_MP_BPS_0040"



_APPS_LIBRES = "Facebook, Instagram, WhatsApp, X, Snapchat, Uber"

_VAGUE_CONFIRMATIONS = {
    "SI", "SÍ", "SIP", "OK", "DALE", "ORALE", "VA", "CLARO",
    "BUENO", "PERFECTO", "SALE", "VALE", "ESO", "ANDALE",
    "SI QUIERO", "SÍ QUIERO", "QUIERO", "LO QUIERO",
    "SI POR FAVOR", "SÍ POR FAVOR", "POR FAVOR",
    "ADELANTE", "PROCEDE", "PROCEDER",
}


def _to_msisdn(phone_number: str) -> str:
    """Normaliza a 10 dígitos (msisdn) para las APIs Telcel. Mismo patrón que _to_linea() en main.py."""
    n = (phone_number or "").lstrip("+")
    if n.startswith("521") and len(n) == 13:
        return n[3:]
    if n.startswith("52") and len(n) == 12:
        return n[2:]
    return n


def _technical_failure(session) -> str:
    session.stage = "END"
    session.end_reason = "blocked"
    return (
        "Tuvimos un problema técnico al procesar su solicitud. "
        f"Por favor comuníquese con Soporte al {_SOPORTE_TEL}."
    )


def _run_telcel_call(session, api_name: str, fn, *args):
    """Ejecuta una llamada a una API Telcel; loggea y retorna (False, None) ante cualquier falla."""
    try:
        return True, fn(*args)
    except Exception as exc:
        logger.error(
            "[TELCEL_API_ERROR] %s phone=%s error=%s",
            api_name, session.phone_number, exc, exc_info=True,
        )
        return False, None


def _is_otp_invalid(exc: TelcelAPIError) -> bool:
    body = exc.raw_body if isinstance(exc.raw_body, dict) else {}
    detail = body.get("detailResponse") or {}
    if str(detail.get("code")) == _OTP_INVALID_CODE:
        return True
    meaning = f"{detail.get('businessMeaning', '')} {detail.get('description', '')}".upper()
    return "OTP" in meaning


def build_summary_template(session) -> str:
    """Template fijo del resumen del plan a contratar."""
    plan = find_plan(session.plan_selected)
    modality = session.subscription_type
    has_promo = bool(session.has_promotion)

    if plan:
        price = get_price(plan, modality)
        cashback = get_cashback(plan, modality)
        if plan.is_unlimited:
            gb_str = "Ilimitados (PUJ)"
        elif has_promo and price > session.current_cost + 1.0 and plan.gb_promo > plan.gb_base and plan.family == "Telcel Libre":
            extra = plan.gb_promo - plan.gb_base
            gb_str = f"{plan.gb_base:g} GB base + {extra:g} GB de promoción = {plan.gb_promo:g} GB totales"
        else:
            gb_str = f"{plan.gb_base:g} GB"
        is_libre = plan.family == "Telcel Libre"
    else:
        price = 0.0
        cashback = 0.0
        gb_str = "N/D"
        is_libre = False

    cashback_line = f"💰 Cashback ${cashback:.2f}/mes\n" if cashback > 0 else ""
    apps_line = f"📱 Apps ilimitadas: {_APPS_LIBRES}\n" if is_libre else ""

    return (
        f"{session.first_name}, está por confirmar el cambio de plan:\n\n"
        f"Plan actual: {session.current_plan_name} {modality} — ${session.current_cost:.0f}/mes\n"
        f"Nuevo plan: {session.plan_selected} {modality} — ${price:.0f}/mes\n\n"
        f"📶 {gb_str}\n"
        f"{cashback_line}"
        f"📞 {plan.calls_sms if plan else 'Llamadas y SMS ilimitados a México, EUA y Canadá'}\n"
        f"{apps_line}"
        f"🎬 Claro Video\n"
        f"💾 Claro Drive (20 GB)\n\n"
        f"⚠️ Este cambio es definitivo y no podrá revertirse al plan anterior."
    )


def handle_contract_turn(session, user_message: str) -> Optional[str]:
    """
    Maneja un turno dentro del flujo de contratación.

    Returns:
        str  — mensaje a enviar al cliente sin pasar por el LLM
        None — señal para que el llamador decida según session.stage:
               POST_SALE  → generar mensaje post-venta
               PERSUASION → volver al flujo normal
               CONTRACT   → invocar LLM (pregunta durante espera)
    """
    # 0. Restricciones de titular y nombre
    if not session.is_titular:
        return (
            "El cambio de plan solo puede ser gestionado por el titular. "
            "Si usted es el titular, puede continuar con la activación."
        )

    if session.nombre_incorrecto:
        return (
            "Para proceder con la activación debe corregir primero sus datos "
            "en un Centro de Atención a Clientes (CAC)."
        )

    # 1. Bloqueado por intentos fallidos de OTP — el aviso ya se mostró al
    # momento del bloqueo (ver punto 2). Libera el turno hacia el flujo normal
    # en vez de repetir el mensaje ante cualquier pregunta no relacionada;
    # iniciar_contratacion ya rechaza un nuevo intento de activación mientras
    # authentication_locked siga activo.
    if session.authentication_locked:
        session.stage = "END"
        session.end_reason = "blocked"
        return None

    # 2. Esperando OTP — CreateProductOrder valida el código implícitamente
    # del lado de Telcel (ningún request de las 3 APIs tiene un campo de OTP;
    # el error de negocio BE_MP_BPS_0040 es la señal de "código incorrecto").
    if session.awaiting_otp:
        plan = find_plan(session.plan_selected)
        if not plan or not plan.telcel_product_id:
            logger.error(
                "[TELCEL_PRODUCT_ID_MISSING] plan=%s phone=%s",
                session.plan_selected, session.phone_number,
            )
            return _technical_failure(session)

        try:
            call_create_product_order(plan.telcel_product_id, session.process_id_api)
        except TelcelAPIError as exc:
            if _is_otp_invalid(exc):
                session.otp_attempt_count += 1
                if session.otp_attempt_count >= MAX_OTP_ATTEMPTS:
                    session.authentication_locked = True
                    session.awaiting_otp = False
                    return (
                        "Ha superado el número de intentos permitidos. "
                        f"Comuníquese con Soporte al {_SOPORTE_TEL}."
                    )

                remaining = MAX_OTP_ATTEMPTS - session.otp_attempt_count
                return (
                    f"El código ingresado no es correcto. "
                    f"Le quedan {remaining} intento(s). "
                    f"Por favor, ingrese el código que recibió por SMS."
                )

            logger.error(
                "[TELCEL_API_ERROR] create_product_order phone=%s error=%s",
                session.phone_number, exc,
            )
            return _technical_failure(session)
        except Exception as exc:
            logger.error(
                "[TELCEL_API_ERROR] create_product_order phone=%s error=%s",
                session.phone_number, exc, exc_info=True,
            )
            return _technical_failure(session)

        session.is_authenticated = True
        session.awaiting_otp = False
        session.contract_folio = f"TC-{uuid.uuid4().hex[:8].upper()}"
        session.stage = "POST_SALE"
        return None  # → generar post-venta

    # 3. Esperando confirmación verbal del resumen
    if session.awaiting_contract_confirmation:
        msg = user_message.strip().upper().strip("!.¿? ")
        palabras = set(msg.strip().upper().split())

        # Primero verificar rechazo — tiene prioridad sobre ACEPTO
        if "NO" in palabras or msg.startswith("NO"):
            session.stage = "PERSUASION"
            session.awaiting_contract_confirmation = False
            session.plan_selected = None
            return None

        # Solo ACEPTO o CONFIRMO proceden con la activación
        elif "ACEPTO" in palabras or "CONFIRMO" in palabras:
            plan = find_plan(session.plan_selected)
            if plan:
                new_price = get_price(plan, session.subscription_type)
                is_same_price = abs(new_price - session.current_cost) <= 1.0
            else:
                is_same_price = False

            session.awaiting_contract_confirmation = False

            if not plan or not plan.telcel_product_id:
                logger.error(
                    "[TELCEL_PRODUCT_ID_MISSING] plan=%s phone=%s",
                    session.plan_selected, session.phone_number,
                )
                return _technical_failure(session)

            ok, process_result = _run_telcel_call(
                session, "create_process", call_create_process, _to_msisdn(session.phone_number),
            )
            if not ok:
                return _technical_failure(session)

            process_id = (process_result.get("decrypted") or {}).get("processId")
            if not process_id:
                logger.error(
                    "[TELCEL_API_ERROR] create_process sin processId phone=%s raw=%s",
                    session.phone_number, process_result.get("raw"),
                )
                return _technical_failure(session)

            session.process_id_api = process_id

            if is_same_price:
                ok, _ = _run_telcel_call(
                    session, "create_product_order",
                    call_create_product_order, plan.telcel_product_id, process_id,
                )
                if not ok:
                    return _technical_failure(session)

                session.is_authenticated = True
                session.contract_folio = f"TC-{uuid.uuid4().hex[:8].upper()}"
                session.stage = "POST_SALE"
                return None  # → generar post-venta directo sin OTP
            else:
                ok, _ = _run_telcel_call(
                    session, "communication_message", call_communication_message, process_id,
                )
                if not ok:
                    return _technical_failure(session)

                session.awaiting_otp = True
                session.otp_sent = True
                phone_masked = session.phone_number[-4:] if session.phone_number else "****"
                return (
                    f"Para verificar su identidad, le hemos enviado un código "
                    f"de verificación al número terminado en {phone_masked}.\n\n"
                    f"Por favor, ingrese el código para confirmar la activación "
                    f"del {session.plan_selected}."
                )
        # Afirmación vaga — pedir confirmación explícita
        elif msg in _VAGUE_CONFIRMATIONS:
            return (
                f"Para confirmar la activación del {session.plan_selected}, "
                f"presione *Sí, activar* o responda *ACEPTO*.\n\n"
                f"Para cancelar presione *No, cancelar*."
            )

        # Todo lo demás → recordar que debe confirmar o cancelar
        else:
            return (
                f"Para continuar, presione *Sí, activar* o responda *ACEPTO* "
                f"para confirmar la activación del *{session.plan_selected}*.\n\n"
                f"O presione *No, cancelar* para cancelar y continuar la conversación."
            )

    # 4. Primer ingreso al flujo — mostrar resumen
    session.awaiting_contract_confirmation = True
    return build_summary_template(session)
