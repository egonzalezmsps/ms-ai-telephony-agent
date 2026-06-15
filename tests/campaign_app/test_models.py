import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from db.models import (
    Base, Familia, Plan, Beneficio, Servicio,
    PreguntaFrecuente, Promocion, Campana,
    CampanaPlan, Cliente, CampanaCliente,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


def test_familia_plan_relationship(db):
    familia = Familia(nombre="Telcel Libre", descripcion="Familia Libre")
    db.add(familia)
    db.flush()
    plan = Plan(
        familia_id=familia.id,
        nombre="Telcel Libre 1",
        precio_abierto=249.0,
        precio_controlado=299.0,
        gb_base=4.0,
        tiene_cashback=True,
        cashback_porcentaje=5.0,
        activo=True,
    )
    db.add(plan)
    db.commit()
    assert db.query(Plan).count() == 1
    assert plan.familia.nombre == "Telcel Libre"


def test_beneficio_familia_m2m(db):
    familia = Familia(nombre="Telcel Libre")
    beneficio = Beneficio(nombre="Apps ilimitadas", activo=True)
    familia.beneficios.append(beneficio)
    db.add(familia)
    db.commit()
    assert beneficio in db.query(Familia).first().beneficios


def test_servicio_familia_m2m(db):
    familia = Familia(nombre="Telcel Ultra")
    servicio = Servicio(nombre="Claro Video", tipo_acceso="suscripcion", activo=True)
    familia.servicios.append(servicio)
    db.add(familia)
    db.commit()
    assert servicio in db.query(Familia).first().servicios


def test_pregunta_cascade_delete_on_beneficio(db):
    beneficio = Beneficio(nombre="Apps ilimitadas", activo=True)
    db.add(beneficio)
    db.flush()
    pregunta = PreguntaFrecuente(
        beneficio_id=beneficio.id,
        ambito="beneficio",
        pregunta="¿Qué apps incluye?",
        respuesta="Facebook, WhatsApp, Messenger, X, Instagram, Snapchat, Uber",
        activo=True,
    )
    db.add(pregunta)
    db.commit()
    assert db.query(PreguntaFrecuente).count() == 1
    db.delete(beneficio)
    db.commit()
    assert db.query(PreguntaFrecuente).count() == 0


def test_campana_cliente_composite_pk(db):
    campana = Campana(nombre="Migración Legacy", estado="borrador")
    cliente = Cliente(linea="5511111111", nombre="Roberto")
    db.add_all([campana, cliente])
    db.flush()
    cc = CampanaCliente(
        campana_id=campana.id,
        linea=cliente.linea,
        estado_envio="pendiente",
        estado_interaccion="pendiente",
        num_turnos=0,
    )
    db.add(cc)
    db.commit()
    assert db.query(CampanaCliente).count() == 1


def test_plan_gb_base_zero_is_ilimitado(db):
    familia = Familia(nombre="Telcel Ultra")
    db.add(familia)
    db.flush()
    plan = Plan(
        familia_id=familia.id,
        nombre="Telcel Ultra Ilimitado",
        precio_abierto=1349.0,
        precio_controlado=1399.0,
        gb_base=0.0,
        tiene_cashback=False,
        cashback_porcentaje=0.0,
        activo=True,
    )
    db.add(plan)
    db.commit()
    assert plan.gb_base == 0.0
