from datetime import datetime
from typing import Optional
from .database import get_db
from .models import (
    Familia, Plan, Beneficio, Servicio, PreguntaFrecuente,
    Promocion, Campana, CampanaPlan, Cliente, CampanaCliente,
)
from sqlalchemy.orm import selectinload


# ── Familia ───────────────────────────────────────────────────────────────────

def get_all_familias():
    with get_db() as db:
        return (
            db.query(Familia)
            .options(
                selectinload(Familia.beneficios),
                selectinload(Familia.servicios),
                selectinload(Familia.planes),
            )
            .order_by(Familia.nombre)
            .all()
        )


def create_familia(nombre: str, descripcion: str = "") -> Familia:
    with get_db() as db:
        obj = Familia(nombre=nombre, descripcion=descripcion)
        db.add(obj)
        db.flush()
        db.refresh(obj)
        return obj


def update_familia(familia_id: int, **kwargs) -> Familia:
    with get_db() as db:
        obj = db.query(Familia).filter_by(id=familia_id).first()
        for k, v in kwargs.items():
            setattr(obj, k, v)
        db.flush()
        db.refresh(obj)
        return obj


# ── Plan ──────────────────────────────────────────────────────────────────────

def get_all_planes():
    with get_db() as db:
        return (
            db.query(Plan)
            .options(selectinload(Plan.familia))
            .order_by(Plan.familia_id, Plan.precio_abierto)
            .all()
        )


def get_planes_by_familia(familia_id: int):
    with get_db() as db:
        return db.query(Plan).filter_by(familia_id=familia_id).order_by(Plan.precio_abierto).all()


def create_plan(familia_id: int, nombre: str, precio_abierto: float,
                precio_controlado: float, gb_base: float,
                tiene_cashback: bool = False, cashback_porcentaje: float = 0.0) -> Plan:
    with get_db() as db:
        obj = Plan(
            familia_id=familia_id, nombre=nombre,
            precio_abierto=precio_abierto, precio_controlado=precio_controlado,
            gb_base=gb_base, tiene_cashback=tiene_cashback,
            cashback_porcentaje=cashback_porcentaje, activo=True,
        )
        db.add(obj)
        db.flush()
        db.refresh(obj)
        return obj


def update_plan(plan_id: int, **kwargs) -> Plan:
    with get_db() as db:
        obj = db.query(Plan).filter_by(id=plan_id).first()
        for k, v in kwargs.items():
            setattr(obj, k, v)
        db.flush()
        db.refresh(obj)
        return obj


def toggle_plan_activo(plan_id: int):
    with get_db() as db:
        obj = db.query(Plan).filter_by(id=plan_id).first()
        obj.activo = not obj.activo


# ── Beneficio ─────────────────────────────────────────────────────────────────

def get_all_beneficios():
    with get_db() as db:
        return (
            db.query(Beneficio)
            .options(selectinload(Beneficio.familias))
            .order_by(Beneficio.nombre)
            .all()
        )


def create_beneficio(nombre: str, descripcion: str = "") -> Beneficio:
    with get_db() as db:
        obj = Beneficio(nombre=nombre, descripcion=descripcion, activo=True)
        db.add(obj)
        db.flush()
        db.refresh(obj)
        return obj


def link_beneficio_to_familia(beneficio_id: int, familia_id: int):
    with get_db() as db:
        familia = db.query(Familia).filter_by(id=familia_id).first()
        beneficio = db.query(Beneficio).filter_by(id=beneficio_id).first()
        if beneficio not in familia.beneficios:
            familia.beneficios.append(beneficio)


def unlink_beneficio_from_familia(beneficio_id: int, familia_id: int):
    with get_db() as db:
        familia = db.query(Familia).filter_by(id=familia_id).first()
        beneficio = db.query(Beneficio).filter_by(id=beneficio_id).first()
        if beneficio in familia.beneficios:
            familia.beneficios.remove(beneficio)


def toggle_beneficio_activo(beneficio_id: int):
    with get_db() as db:
        obj = db.query(Beneficio).filter_by(id=beneficio_id).first()
        obj.activo = not obj.activo


# ── Servicio ──────────────────────────────────────────────────────────────────

def get_all_servicios():
    with get_db() as db:
        return (
            db.query(Servicio)
            .options(selectinload(Servicio.familias))
            .order_by(Servicio.nombre)
            .all()
        )


def create_servicio(nombre: str, descripcion: str, tipo_acceso: str, detalle: str = "") -> Servicio:
    with get_db() as db:
        obj = Servicio(nombre=nombre, descripcion=descripcion,
                       tipo_acceso=tipo_acceso, detalle=detalle, activo=True)
        db.add(obj)
        db.flush()
        db.refresh(obj)
        return obj


def link_servicio_to_familia(servicio_id: int, familia_id: int):
    with get_db() as db:
        familia = db.query(Familia).filter_by(id=familia_id).first()
        servicio = db.query(Servicio).filter_by(id=servicio_id).first()
        if servicio not in familia.servicios:
            familia.servicios.append(servicio)


def unlink_servicio_from_familia(servicio_id: int, familia_id: int):
    with get_db() as db:
        familia = db.query(Familia).filter_by(id=familia_id).first()
        servicio = db.query(Servicio).filter_by(id=servicio_id).first()
        if servicio in familia.servicios:
            familia.servicios.remove(servicio)


def toggle_servicio_activo(servicio_id: int):
    with get_db() as db:
        obj = db.query(Servicio).filter_by(id=servicio_id).first()
        obj.activo = not obj.activo


# ── PreguntaFrecuente ─────────────────────────────────────────────────────────

def get_all_preguntas(ambito: Optional[str] = None,
                      beneficio_id: Optional[int] = None,
                      servicio_id: Optional[int] = None):
    with get_db() as db:
        q = db.query(PreguntaFrecuente)
        if ambito:
            q = q.filter_by(ambito=ambito)
        if beneficio_id:
            q = q.filter_by(beneficio_id=beneficio_id)
        if servicio_id:
            q = q.filter_by(servicio_id=servicio_id)
        return q.order_by(PreguntaFrecuente.id).all()


def create_pregunta(pregunta: str, respuesta: str, ambito: str = "general",
                    beneficio_id: Optional[int] = None,
                    servicio_id: Optional[int] = None) -> PreguntaFrecuente:
    with get_db() as db:
        obj = PreguntaFrecuente(
            pregunta=pregunta, respuesta=respuesta, ambito=ambito,
            beneficio_id=beneficio_id, servicio_id=servicio_id, activo=True,
        )
        db.add(obj)
        db.flush()
        db.refresh(obj)
        return obj


def bulk_create_preguntas(items: list) -> int:
    with get_db() as db:
        objs = [
            PreguntaFrecuente(
                pregunta=item["pregunta"],
                respuesta=item["respuesta"],
                ambito=item.get("ambito", "general"),
                beneficio_id=item.get("beneficio_id"),
                servicio_id=item.get("servicio_id"),
                activo=True,
            )
            for item in items
        ]
        db.add_all(objs)
        return len(objs)


def delete_pregunta(pregunta_id: int):
    with get_db() as db:
        obj = db.query(PreguntaFrecuente).filter_by(id=pregunta_id).first()
        if obj:
            db.delete(obj)


# ── Promocion ─────────────────────────────────────────────────────────────────

def get_all_promociones():
    with get_db() as db:
        return db.query(Promocion).order_by(Promocion.vigencia_fin.desc()).all()


def create_promocion(nombre: str, descripcion: str, vigencia_inicio: datetime,
                     vigencia_fin: datetime, configuracion: dict = None,
                     condicion: str = "") -> Promocion:
    with get_db() as db:
        obj = Promocion(
            nombre=nombre, descripcion=descripcion,
            vigencia_inicio=vigencia_inicio, vigencia_fin=vigencia_fin,
            configuracion=configuracion, condicion=condicion, activo=True,
        )
        db.add(obj)
        db.flush()
        db.refresh(obj)
        return obj


def update_promocion(promocion_id: int, **kwargs) -> Promocion:
    with get_db() as db:
        obj = db.query(Promocion).filter_by(id=promocion_id).first()
        for k, v in kwargs.items():
            setattr(obj, k, v)
        db.flush()
        db.refresh(obj)
        return obj


def toggle_promocion_activo(promocion_id: int):
    with get_db() as db:
        obj = db.query(Promocion).filter_by(id=promocion_id).first()
        obj.activo = not obj.activo


def delete_promocion(promocion_id: int):
    with get_db() as db:
        obj = db.query(Promocion).filter_by(id=promocion_id).first()
        if obj:
            db.delete(obj)


# ── Campana ───────────────────────────────────────────────────────────────────

def get_all_campanas():
    with get_db() as db:
        return db.query(Campana).order_by(Campana.creado_en.desc()).all()


def create_campana(nombre: str, descripcion: str = "",
                   vigencia_inicio: Optional[datetime] = None,
                   vigencia_fin: Optional[datetime] = None) -> Campana:
    with get_db() as db:
        obj = Campana(
            nombre=nombre, descripcion=descripcion,
            vigencia_inicio=vigencia_inicio, vigencia_fin=vigencia_fin,
            estado="borrador",
        )
        db.add(obj)
        db.flush()
        db.refresh(obj)
        return obj


def update_campana(campana_id: int, **kwargs) -> Campana:
    with get_db() as db:
        obj = db.query(Campana).filter_by(id=campana_id).first()
        for k, v in kwargs.items():
            setattr(obj, k, v)
        db.flush()
        db.refresh(obj)
        return obj


def get_campana_planes(campana_id: int):
    with get_db() as db:
        return (
            db.query(CampanaPlan)
            .options(selectinload(CampanaPlan.plan), selectinload(CampanaPlan.promocion))
            .filter_by(campana_id=campana_id)
            .all()
        )


def add_plan_to_campana(campana_id: int, plan_id: int,
                        promocion_id: Optional[int] = None):
    with get_db() as db:
        existing = db.query(CampanaPlan).filter_by(
            campana_id=campana_id, plan_id=plan_id).first()
        if not existing:
            db.add(CampanaPlan(campana_id=campana_id, plan_id=plan_id,
                               promocion_id=promocion_id))


def remove_plan_from_campana(campana_id: int, plan_id: int):
    with get_db() as db:
        obj = db.query(CampanaPlan).filter_by(
            campana_id=campana_id, plan_id=plan_id).first()
        if obj:
            db.delete(obj)


# ── Cliente ───────────────────────────────────────────────────────────────────

def get_all_clientes():
    with get_db() as db:
        return db.query(Cliente).order_by(Cliente.linea).all()


def upsert_cliente(data: dict) -> Cliente:
    with get_db() as db:
        obj = db.query(Cliente).filter_by(linea=data["linea"]).first()
        if obj:
            for k, v in data.items():
                setattr(obj, k, v)
        else:
            obj = Cliente(**data)
            db.add(obj)
        db.flush()
        db.refresh(obj)
        return obj


def bulk_upsert_clientes(rows: list) -> int:
    with get_db() as db:
        for data in rows:
            obj = db.query(Cliente).filter_by(linea=data["linea"]).first()
            if obj:
                for k, v in data.items():
                    setattr(obj, k, v)
            else:
                db.add(Cliente(**data))
        return len(rows)


# ── CampanaCliente ────────────────────────────────────────────────────────────

def get_campana_clientes(campana_id: int):
    with get_db() as db:
        return (
            db.query(CampanaCliente)
            .options(selectinload(CampanaCliente.cliente))
            .filter_by(campana_id=campana_id)
            .all()
        )


def get_campana_clientes_pendientes(campana_id: int):
    with get_db() as db:
        return (
            db.query(CampanaCliente)
            .options(selectinload(CampanaCliente.cliente))
            .filter(
                CampanaCliente.campana_id == campana_id,
                CampanaCliente.estado_envio.in_(["pendiente", "fallido"]),
            )
            .all()
        )


def add_clientes_to_campana(campana_id: int, lineas: list):
    with get_db() as db:
        for linea in lineas:
            existing = db.query(CampanaCliente).filter_by(
                campana_id=campana_id, linea=linea).first()
            if not existing:
                db.add(CampanaCliente(
                    campana_id=campana_id, linea=linea,
                    estado_envio="pendiente", estado_interaccion="pendiente",
                    num_turnos=0,
                ))


def mark_enviado(campana_id: int, linea: str):
    with get_db() as db:
        obj = db.query(CampanaCliente).filter_by(
            campana_id=campana_id, linea=linea).first()
        if obj:
            obj.estado_envio = "enviado"
            obj.fecha_envio = datetime.utcnow()


def mark_fallido(campana_id: int, linea: str):
    with get_db() as db:
        obj = db.query(CampanaCliente).filter_by(
            campana_id=campana_id, linea=linea).first()
        if obj:
            obj.estado_envio = "fallido"


def update_interaction(campana_id: int, linea: str, num_turnos: int,
                       estado_interaccion: str,
                       plan_seleccionado: Optional[str] = None,
                       folio_contrato: Optional[str] = None):
    with get_db() as db:
        obj = db.query(CampanaCliente).filter_by(
            campana_id=campana_id, linea=linea).first()
        if not obj:
            return
        obj.num_turnos = num_turnos
        obj.estado_interaccion = estado_interaccion
        if plan_seleccionado:
            obj.plan_seleccionado = plan_seleccionado
            if not obj.fecha_seleccion:
                obj.fecha_seleccion = datetime.utcnow()
        if folio_contrato:
            obj.folio_contrato = folio_contrato


def close_session_snapshot(campana_id: int, linea: str,
                            history: list, session_data: dict):
    with get_db() as db:
        obj = db.query(CampanaCliente).filter_by(
            campana_id=campana_id, linea=linea).first()
        if obj:
            obj.historial_conversacion = history
            obj.session_data_snapshot = session_data


def find_active_campana_cliente(linea: str) -> Optional[CampanaCliente]:
    with get_db() as db:
        return (
            db.query(CampanaCliente)
            .join(Campana)
            .filter(
                CampanaCliente.linea == linea,
                Campana.estado.in_(["activa", "pausada"]),
            )
            .order_by(CampanaCliente.campana_id.desc())
            .first()
        )
