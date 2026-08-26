from datetime import datetime
from sqlalchemy import (
    Column, String, Float, Boolean, Integer,
    DateTime, JSON, Text, ForeignKey, Table,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

familia_beneficio = Table(
    "familia_beneficio", Base.metadata,
    Column("familia_id", Integer, ForeignKey("familias.id"), primary_key=True),
    Column("beneficio_id", Integer, ForeignKey("beneficios.id"), primary_key=True),
)

familia_servicio = Table(
    "familia_servicio", Base.metadata,
    Column("familia_id", Integer, ForeignKey("familias.id"), primary_key=True),
    Column("servicio_id", Integer, ForeignKey("servicios.id"), primary_key=True),
)


class Familia(Base):
    __tablename__ = "familias"
    id = Column(Integer, primary_key=True, autoincrement=True)
    nombre = Column(String(100), nullable=False, unique=True)
    descripcion = Column(Text, nullable=True)
    planes = relationship("Plan", back_populates="familia")
    beneficios = relationship("Beneficio", secondary=familia_beneficio, back_populates="familias")
    servicios = relationship("Servicio", secondary=familia_servicio, back_populates="familias")


class Plan(Base):
    __tablename__ = "planes"
    id = Column(Integer, primary_key=True, autoincrement=True)
    familia_id = Column(Integer, ForeignKey("familias.id"), nullable=False)
    nombre = Column(String(100), nullable=False, unique=True)
    precio_abierto = Column(Float, nullable=False)
    precio_controlado = Column(Float, nullable=False)
    gb_base = Column(Float, nullable=False)
    tiene_cashback = Column(Boolean, default=False, nullable=False)
    cashback_porcentaje = Column(Float, default=0.0, nullable=False)
    activo = Column(Boolean, default=True, nullable=False)
    es_legacy = Column(Boolean, default=False, nullable=True)
    familia = relationship("Familia", back_populates="planes")
    campana_planes = relationship("CampanaPlan", back_populates="plan")


class Beneficio(Base):
    __tablename__ = "beneficios"
    id = Column(Integer, primary_key=True, autoincrement=True)
    nombre = Column(String(200), nullable=False)
    descripcion = Column(Text, nullable=True)
    activo = Column(Boolean, default=True, nullable=False)
    familias = relationship("Familia", secondary=familia_beneficio, back_populates="beneficios")
    preguntas = relationship("PreguntaFrecuente", back_populates="beneficio", cascade="all, delete-orphan")


class Servicio(Base):
    __tablename__ = "servicios"
    id = Column(Integer, primary_key=True, autoincrement=True)
    nombre = Column(String(200), nullable=False)
    descripcion = Column(Text, nullable=True)
    tipo_acceso = Column(String(20), nullable=False)
    detalle = Column(String(200), nullable=True)
    activo = Column(Boolean, default=True, nullable=False)
    familias = relationship("Familia", secondary=familia_servicio, back_populates="servicios")
    preguntas = relationship("PreguntaFrecuente", back_populates="servicio", cascade="all, delete-orphan")


class PreguntaFrecuente(Base):
    __tablename__ = "preguntas_frecuentes"
    id = Column(Integer, primary_key=True, autoincrement=True)
    beneficio_id = Column(Integer, ForeignKey("beneficios.id", ondelete="CASCADE"), nullable=True)
    servicio_id = Column(Integer, ForeignKey("servicios.id", ondelete="CASCADE"), nullable=True)
    ambito = Column(String(20), nullable=False, default="general")
    pregunta = Column(Text, nullable=False)
    respuesta = Column(Text, nullable=False)
    activo = Column(Boolean, default=True, nullable=False)
    beneficio = relationship("Beneficio", back_populates="preguntas")
    servicio = relationship("Servicio", back_populates="preguntas")


class Promocion(Base):
    __tablename__ = "promociones"
    id = Column(Integer, primary_key=True, autoincrement=True)
    nombre = Column(String(200), nullable=False)
    descripcion = Column(Text, nullable=True)
    vigencia_inicio = Column(DateTime, nullable=False)
    vigencia_fin = Column(DateTime, nullable=False)
    configuracion = Column(JSON, nullable=True)
    condicion = Column(Text, nullable=True)
    activo = Column(Boolean, default=True, nullable=False)
    campana_planes = relationship("CampanaPlan", back_populates="promocion")


class Campana(Base):
    __tablename__ = "campanas"
    id = Column(Integer, primary_key=True, autoincrement=True)
    nombre = Column(String(200), nullable=False)
    descripcion = Column(Text, nullable=True)
    creado_en = Column(DateTime, default=datetime.utcnow, nullable=False)
    vigencia_inicio = Column(DateTime, nullable=True)
    vigencia_fin = Column(DateTime, nullable=True)
    estado = Column(String(20), default="borrador", nullable=False)
    reglas_elegibilidad = Column(JSON, nullable=True)
    planes = relationship("CampanaPlan", back_populates="campana")
    clientes = relationship("CampanaCliente", back_populates="campana")


class CampanaPlan(Base):
    __tablename__ = "campana_planes"
    campana_id = Column(Integer, ForeignKey("campanas.id"), primary_key=True)
    plan_id = Column(Integer, ForeignKey("planes.id"), primary_key=True)
    promocion_id = Column(Integer, ForeignKey("promociones.id"), nullable=True)
    campana = relationship("Campana", back_populates="planes")
    plan = relationship("Plan", back_populates="campana_planes")
    promocion = relationship("Promocion", back_populates="campana_planes")


class Cliente(Base):
    __tablename__ = "clientes"
    linea = Column(String(20), primary_key=True)
    nombre = Column(String(100), nullable=True)
    apellidos = Column(String(200), nullable=True)
    plan_actual_nombre = Column(String(200), nullable=True)
    familia_plan = Column(String(100), nullable=True)
    tipo_suscripcion = Column(String(20), nullable=True)
    renta_plan = Column(Float, nullable=True)
    facturacion_promedio = Column(Float, nullable=True)
    consumo_mb_total_prom = Column(Float, nullable=True)
    consumo_mb_whatsapp_prom = Column(Float, nullable=True)
    consumo_mb_redes_prom = Column(Float, nullable=True)
    consumo_mb_youtube_prom = Column(Float, nullable=True)
    consumo_mb_uber_prom = Column(Float, nullable=True)
    consumo_mb_instagram_prom = Column(Float, nullable=True)
    consumo_mb_otros_prom = Column(Float, nullable=True)
    excedentes_nac_mb_prom = Column(Float, nullable=True)
    excedentes_int_mb_prom = Column(Float, nullable=True)
    ingresos_exc_nac_prom = Column(Float, nullable=True)
    ingresos_exc_int_prom = Column(Float, nullable=True)
    orden = Column(Integer, nullable=True)
    estado = Column(String(20), nullable=True, default="Pendiente")
    creado_en = Column(DateTime, default=datetime.utcnow)
    campanas = relationship("CampanaCliente", back_populates="cliente")


class CampanaCliente(Base):
    __tablename__ = "campana_clientes"
    campana_id = Column(Integer, ForeignKey("campanas.id"), primary_key=True)
    linea = Column(String(20), ForeignKey("clientes.linea"), primary_key=True)
    estado_envio = Column(String(20), default="pendiente", nullable=False)
    fecha_envio = Column(DateTime, nullable=True)
    estado_interaccion = Column(String(30), default="pendiente", nullable=False)
    plan_seleccionado = Column(String(100), nullable=True)
    fecha_seleccion = Column(DateTime, nullable=True)
    num_turnos = Column(Integer, default=0, nullable=False)
    folio_contrato = Column(String(50), nullable=True)
    historial_conversacion = Column(JSON, nullable=True)
    session_data_snapshot = Column(JSON, nullable=True)
    campana = relationship("Campana", back_populates="clientes")
    cliente = relationship("Cliente", back_populates="campanas")
