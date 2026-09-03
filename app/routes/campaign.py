"""
routes/campaign.py

Endpoints de campañas: envío, dispatch, reportes, migraciones e import de clientes.
"""

import csv
import io
import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel

from app.state.session import SessionState
from app.state.persistence import save_session
from app.state.serializer import session_to_dict
from app.prompts.campaign_template import build_campaign_message, build_template_params
from app.whatsapp.sender import send_whatsapp_message, send_whatsapp_template
from app.state.campaign_traceability import campaign_crud, CAMPAIGN_DB_AVAILABLE, CAMPAIGN_DB_ERROR
from app.routes.deps import require_api_key

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_api_key)])


def _require_campaign_db():
    if not CAMPAIGN_DB_AVAILABLE:
        raise HTTPException(status_code=503, detail=f"Campaign DB not available: {CAMPAIGN_DB_ERROR}")


class CampaignRequest(BaseModel):
    lineas: list[str]


class DispatchRequest(BaseModel):
    campana_id: int
    lineas: list[str]


class DispatchLoteRequest(BaseModel):
    campana_id: int
    limite: int = 100


@router.post("/campaign")
def campaign(request: CampaignRequest):
    """
    Envía el template de campaña a los clientes de la tabla 'clientes' (Postgres)
    cuya línea (número de teléfono) esté en la lista 'lineas' recibida (uno o varios).
    """
    _require_campaign_db()

    todos_clientes = campaign_crud.get_all_clientes()
    por_linea = {c.linea: c for c in todos_clientes}

    results = {"sent": [], "failed": []}
    seleccionados = []
    for linea in request.lineas:
        cliente = por_linea.get(linea)
        if cliente is None:
            results["failed"].append({"phone_number": linea, "reason": "cliente no encontrado"})
        else:
            seleccionados.append(cliente)

    for cliente in seleccionados:
        phone_number = cliente.linea

        try:
            session = SessionState(
                first_name=(cliente.nombre or "Cliente").split()[0].title(),
                full_name=f"{cliente.nombre or ''} {cliente.apellidos or ''}".strip(),
                phone_number=phone_number,
                current_plan_name=cliente.plan_actual_nombre or "Plan Legado",
                current_cost=cliente.renta_plan or 0.0,
                subscription_type=cliente.tipo_suscripcion or "Abierto",
                is_titular=True,
            )
            template_result = build_template_params(session)
            campaign_msg = build_campaign_message(session)

            wa_id = phone_number
            sent_template = False
            template_name = None
            delivered = False

            if template_result is None:
                # Sin plan elegible — texto plano como fallback
                try:
                    send_whatsapp_message(phone_number, campaign_msg)
                    delivered = True
                except Exception as e:
                    logger.error(f"CAMPAIGN | {phone_number} texto plano falló: {e}")
                logger.info(f"CAMPAIGN | {phone_number} — sin plan elegible, texto plano enviado")
            else:
                template_name = template_result["template_name"]
                try:
                    wa_resp = send_whatsapp_template(
                        to=phone_number,
                        template_name=template_name,
                        params=template_result["params"],
                    )
                    # wa_id es el número en formato canónico de Meta — es la clave que llega en webhooks
                    wa_id = wa_resp.get("contacts", [{}])[0].get("wa_id", phone_number)
                    logger.info(f"CAMPAIGN | {phone_number} → wa_id={wa_id} — template '{template_name}' enviado")
                    sent_template = True
                    delivered = True
                except Exception as e:
                    logger.warning(f"CAMPAIGN | {phone_number} template falló, usando texto plano: {e}")
                    try:
                        send_whatsapp_message(phone_number, campaign_msg)
                        delivered = True
                    except Exception as e2:
                        logger.error(f"CAMPAIGN | {phone_number} fallback texto también falló: {e2}")

            if not delivered:
                results["failed"].append({"phone_number": phone_number, "reason": "envío de WhatsApp falló (template y texto plano)"})
                continue

            campaign_crud.marcar_estado_cliente(phone_number, "Enviada")

            # Guardar sesión bajo wa_id para que el webhook la encuentre al recibir la respuesta
            save_session(
                phone_number=wa_id,
                session_data=session_to_dict(session),
                history=[{"role": "assistant", "content": campaign_msg}],
            )

            results["sent"].append({
                "phone_number": phone_number,
                "wa_id": wa_id,
                "sent_template": sent_template,
                "template_name": template_name if sent_template else None,
            })
        except Exception as e:
            logger.error(f"CAMPAIGN | {phone_number} error inesperado: {e}", exc_info=True)
            results["failed"].append({"phone_number": phone_number, "reason": str(e)})

    return results


@router.get("/reportes/campana-clientes")
def get_campana_clientes(
    campana_id: Optional[int] = Query(default=None, description="Si se omite, trae todas las campañas"),
    full: bool = Query(default=False, description="Incluir historial_conversacion y session_data_snapshot"),
):
    """
    Devuelve el contenido de la tabla 'campana_clientes', con los datos del
    cliente asociado (join con 'clientes'). Si 'campana_id' se omite, trae
    las filas de todas las campañas.
    """
    _require_campaign_db()

    if campana_id is None:
        rows = campaign_crud.get_all_campana_clientes()
    else:
        rows = campaign_crud.get_campana_clientes(campana_id)

    resultado = []
    for r in rows:
        item = {
            "campana_id": r.campana_id,
            "linea": r.linea,
            "estado_envio": r.estado_envio,
            "fecha_envio": r.fecha_envio.isoformat() if r.fecha_envio else None,
            "estado_interaccion": r.estado_interaccion,
            "plan_seleccionado": r.plan_seleccionado,
            "fecha_seleccion": r.fecha_seleccion.isoformat() if r.fecha_seleccion else None,
            "num_turnos": r.num_turnos,
            "folio_contrato": r.folio_contrato,
            "cliente": {
                "nombre": r.cliente.nombre,
                "apellidos": r.cliente.apellidos,
                "plan_actual_nombre": r.cliente.plan_actual_nombre,
                "tipo_suscripcion": r.cliente.tipo_suscripcion,
                "renta_plan": r.cliente.renta_plan,
                "estado": r.cliente.estado,
            } if r.cliente else None,
        }
        if full:
            item["historial_conversacion"] = r.historial_conversacion
            item["session_data_snapshot"] = r.session_data_snapshot
        resultado.append(item)

    return resultado


@router.post("/campaign/dispatch")
def campaign_dispatch(request: DispatchRequest):
    """
    Batch-dispatch campaign messages from the Streamlit UI.
    For each linea, looks up the client in the DB, sends the WhatsApp template,
    and updates the CampanaCliente row accordingly.
    """
    _require_campaign_db()

    results = {"sent": [], "failed": []}

    for linea in request.lineas:
        try:
            from campaign_app.db.database import get_db
            from campaign_app.db.models import Cliente as ClienteModel
            with get_db() as db:
                cliente = db.query(ClienteModel).filter_by(linea=linea).first()

            if not cliente:
                results["failed"].append({"linea": linea, "reason": "cliente no encontrado"})
                continue

            session = SessionState(
                first_name=(cliente.nombre or "Cliente").split()[0].title(),
                full_name=f"{cliente.nombre or ''} {cliente.apellidos or ''}".strip(),
                phone_number=linea,
                current_plan_name=cliente.plan_actual_nombre or "Plan Legado",
                current_cost=cliente.renta_plan or 0.0,
                subscription_type=cliente.tipo_suscripcion or "Abierto",
                is_titular=True,
            )

            template_result = build_template_params(session)
            campaign_msg = build_campaign_message(session)

            logger.info(
                f"DISPATCH | {linea} | plan={session.current_plan_name} "
                f"costo=${session.current_cost:.0f} tipo={session.subscription_type}"
            )

            wa_id = linea  # fallback si Meta no devuelve wa_id
            try:
                if template_result:
                    from app.whatsapp.sender import _normalize_phone
                    numero_normalizado = _normalize_phone(linea)
                    logger.info(
                        f"DISPATCH | {linea} | enviando template='{template_result['template_name']}' "
                        f"idioma={os.environ.get('TEMPLATE_LANGUAGE', 'es_MX')} "
                        f"numero_normalizado={numero_normalizado} "
                        f"params={template_result['params']}"
                    )
                    wa_resp = send_whatsapp_template(
                        to=linea,
                        template_name=template_result["template_name"],
                        params=template_result["params"],
                    )
                    wa_id = wa_resp.get("contacts", [{}])[0].get("wa_id", linea)
                    logger.info(f"DISPATCH | {linea} → wa_id={wa_id} | respuesta Meta: {wa_resp}")
                else:
                    logger.info(f"DISPATCH | {linea} | sin plan elegible, enviando texto plano")
                    send_whatsapp_message(linea, campaign_msg)
                campaign_crud.mark_enviado(request.campana_id, linea)
                results["sent"].append(linea)
            except Exception as e:
                logger.error(f"DISPATCH | {linea} falló: {e}")
                campaign_crud.mark_fallido(request.campana_id, linea)
                results["failed"].append({"linea": linea, "reason": str(e)})

            # Guardar sesión bajo el wa_id canónico de Meta para que el webhook la encuentre
            save_session(
                phone_number=wa_id,
                session_data=session_to_dict(session),
                history=[{"role": "assistant", "content": campaign_msg}],
            )

        except Exception as e:
            logger.error(f"DISPATCH | {linea} error inesperado: {e}", exc_info=True)
            results["failed"].append({"linea": linea, "reason": str(e)})

    return results


@router.post("/campaign/dispatch/lote")
def campaign_dispatch_lote(request: DispatchLoteRequest):
    """
    Envía a los próximos N clientes pendientes (estado_envio='pendiente') de
    una campaña — evita tener que armar la lista de líneas a mano en cada
    lote. Internamente resuelve las líneas y reusa campaign_dispatch().
    """
    _require_campaign_db()

    from campaign_app.db.database import get_db
    from campaign_app.db.models import CampanaCliente, Cliente as ClienteModel

    with get_db() as db:
        pendientes = (
            db.query(CampanaCliente)
            .join(ClienteModel, CampanaCliente.linea == ClienteModel.linea)
            .filter(
                CampanaCliente.campana_id == request.campana_id,
                CampanaCliente.estado_envio == "pendiente",
            )
            .order_by(ClienteModel.creado_en.asc())
            .limit(request.limite)
            .all()
        )
        lineas = [cc.linea for cc in pendientes]

    if not lineas:
        return {"sent": [], "failed": [], "detail": "No hay clientes pendientes para esta campaña"}

    logger.info(f"DISPATCH_LOTE | campana_id={request.campana_id} resueltos={len(lineas)} de limite={request.limite}")
    return campaign_dispatch(DispatchRequest(campana_id=request.campana_id, lineas=lineas))


@router.post("/campaign/migrate-orden")
def campaign_migrate_orden():
    """
    Agrega la columna 'orden' a 'clientes' si aún no existe en esta BD, y le
    asigna un valor secuencial (por creado_en) a los clientes que no lo tengan.
    Idempotente — se puede llamar varias veces sin efectos raros.
    """
    _require_campaign_db()

    result = campaign_crud.ensure_orden_column()
    logger.info(
        f"MIGRATE_ORDEN | columna_agregada={result['columna_agregada']} "
        f"filas_backfilled={result['filas_backfilled']}"
    )
    return result


@router.post("/campaign/migrate-plan-seleccionado")
def campaign_migrate_plan_seleccionado():
    """
    Agrega la columna 'plan_seleccionado' a 'clientes' si aún no existe en esta BD.
    Idempotente — se puede llamar varias veces sin efectos raros.
    """
    _require_campaign_db()

    result = campaign_crud.ensure_plan_seleccionado_column()
    logger.info(f"MIGRATE_PLAN_SELECCIONADO | columna_agregada={result['columna_agregada']}")
    return result


@router.post("/campaign/import-clientes")
def campaign_import_clientes(
    file: UploadFile = File(...),
    campana_id: Optional[int] = Form(default=None),
    reemplazar: bool = Form(default=False),
):
    """
    Importa/actualiza clientes en la tabla 'clientes' a partir de un CSV subido
    (mismo formato que docs/Masivo_backup.csv).
    Si se manda 'campana_id', además vincula las líneas importadas a esa campaña
    en 'campana_clientes' (estado_envio='pendiente'), listas para /campaign/dispatch/lote.
    Si 'reemplazar' es true, borra TODOS los clientes y vínculos de campaña
    existentes antes de importar — el CSV subido pasa a ser el único contenido
    de la tabla (en vez de mezclarse con lo que ya había).
    """
    _require_campaign_db()

    nombre_archivo = file.filename or "sin_nombre.csv"
    logger.info(f"IMPORT_CLIENTES | archivo='{nombre_archivo}' | recibido | campana_id={campana_id} | reemplazar={reemplazar}")

    try:
        content = file.file.read().decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(content))
        rows = list(reader)
        if not rows or "linea" not in rows[0]:
            logger.warning(f"IMPORT_CLIENTES | archivo='{nombre_archivo}' | rechazado: CSV vacío o sin columna 'linea'")
            raise HTTPException(status_code=400, detail="El CSV no tiene la columna 'linea'.")

        logger.info(f"IMPORT_CLIENTES | archivo='{nombre_archivo}' | {len(rows)} filas leídas, columnas={reader.fieldnames}")

        borrado = None
        if reemplazar:
            borrado = campaign_crud.delete_all_clientes()
            logger.warning(
                f"IMPORT_CLIENTES | archivo='{nombre_archivo}' | reemplazar=true | borrados antes de importar: "
                f"{borrado['clientes_borrados']} clientes, {borrado['campana_clientes_borrados']} vínculos"
            )

        result = campaign_crud.import_clientes_csv(rows)
        if borrado is not None:
            result["reemplazados"] = borrado

        if result["skipped"]:
            logger.warning(f"IMPORT_CLIENTES | archivo='{nombre_archivo}' | {len(result['skipped'])} filas omitidas: {result['skipped']}")

        if campana_id is not None and result["imported"]:
            campaign_crud.add_clientes_to_campana(campana_id, result["imported"])
            result["campana_id"] = campana_id
            logger.info(f"IMPORT_CLIENTES | archivo='{nombre_archivo}' | {len(result['imported'])} líneas vinculadas a campana_id={campana_id}")

        logger.info(
            f"IMPORT_CLIENTES | archivo='{nombre_archivo}' | completado | {result['total']} filas | "
            f"{len(result['imported'])} importados | {len(result['skipped'])} omitidos"
        )
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"IMPORT_CLIENTES | archivo='{nombre_archivo}' | error inesperado: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error importando CSV: {e}")


@router.get("/campaign/clientes")
def campaign_get_all_clientes():
    """
    Lista TODOS los clientes de la tabla 'clientes', sin filtrar por campaña
    (a diferencia de /campaign/{campana_id}/clientes, que solo trae los vinculados
    a esa campaña en 'campana_clientes').
    """
    _require_campaign_db()

    clientes = campaign_crud.get_all_clientes()
    result = [{
        "fila": i,
        "orden": c.orden,
        "linea": c.linea,
        "nombre": c.nombre,
        "apellidos": c.apellidos,
        "plan_actual_nombre": c.plan_actual_nombre,
        "plan_seleccionado": c.plan_seleccionado,
        "familia_plan": c.familia_plan,
        "tipo_suscripcion": c.tipo_suscripcion,
        "renta_plan": c.renta_plan,
        "facturacion_promedio": c.facturacion_promedio,
        "estado": c.estado,
        "creado_en": c.creado_en.isoformat() if c.creado_en else None,
    } for i, c in enumerate(clientes, start=1)]

    return {"total": len(result), "clientes": result}


@router.get("/campaign/{campana_id}/clientes")
def campaign_get_clientes(campana_id: int):
    """
    Lista los clientes de una campaña tal como quedaron guardados en BD
    (join de 'clientes' + 'campana_clientes'), para verificar una importación.
    """
    _require_campaign_db()

    campana_clientes = campaign_crud.get_campana_clientes(campana_id)
    clientes = []
    for i, cc in enumerate(campana_clientes, start=1):
        c = cc.cliente
        clientes.append({
            "fila": i,
            "orden": c.orden if c else None,
            "linea": cc.linea,
            "nombre": c.nombre if c else None,
            "apellidos": c.apellidos if c else None,
            "plan_actual_nombre": c.plan_actual_nombre if c else None,
            "familia_plan": c.familia_plan if c else None,
            "tipo_suscripcion": c.tipo_suscripcion if c else None,
            "renta_plan": c.renta_plan if c else None,
            "estado": c.estado if c else None,
            "estado_envio": cc.estado_envio,
            "estado_interaccion": cc.estado_interaccion,
            "fecha_envio": cc.fecha_envio.isoformat() if cc.fecha_envio else None,
            "plan_seleccionado": cc.plan_seleccionado,
            "folio_contrato": cc.folio_contrato,
            "num_turnos": cc.num_turnos,
        })

    return {"campana_id": campana_id, "total": len(clientes), "clientes": clientes}


@router.delete("/campaign/clientes")
def campaign_delete_all_clientes(confirm: bool = Query(default=False)):
    """
    Borra TODOS los registros de 'clientes' y sus vínculos en 'campana_clientes'.
    Irreversible. Requiere ?confirm=true para evitar disparos accidentales.
    """
    _require_campaign_db()

    if not confirm:
        raise HTTPException(status_code=400, detail="Falta ?confirm=true — esta acción borra TODOS los clientes.")

    result = campaign_crud.delete_all_clientes()
    logger.warning(
        f"DELETE_ALL_CLIENTES | {result['clientes_borrados']} clientes, "
        f"{result['campana_clientes_borrados']} vínculos de campaña borrados"
    )
    return result
