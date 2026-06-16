import pytest
from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from db.models import Base, Familia, Plan, Campana, Cliente, CampanaCliente
import db.crud as crud


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


@pytest.fixture(autouse=True)
def patch_get_db(db_session, monkeypatch):
    @contextmanager
    def mock_get_db():
        yield db_session
    monkeypatch.setattr(crud, "get_db", mock_get_db)


def test_create_and_get_familia(db_session):
    crud.create_familia("Telcel Libre", "Familia Libre")
    familias = crud.get_all_familias()
    assert len(familias) == 1
    assert familias[0].nombre == "Telcel Libre"


def test_create_plan(db_session):
    familia = Familia(nombre="Telcel Libre")
    db_session.add(familia)
    db_session.flush()
    crud.create_plan(
        familia_id=familia.id,
        nombre="Telcel Libre 1",
        precio_abierto=249.0,
        precio_controlado=299.0,
        gb_base=4.0,
        tiene_cashback=True,
        cashback_porcentaje=5.0,
    )
    planes = crud.get_all_planes()
    assert len(planes) == 1
    assert planes[0].cashback_porcentaje == 5.0


def test_link_and_unlink_beneficio_to_familia(db_session):
    familia = Familia(nombre="Telcel Libre")
    db_session.add(familia)
    db_session.flush()
    b = crud.create_beneficio("Apps ilimitadas", "7 apps")
    crud.link_beneficio_to_familia(b.id, familia.id)
    db_session.refresh(familia)
    assert len(familia.beneficios) == 1
    crud.unlink_beneficio_from_familia(b.id, familia.id)
    db_session.refresh(familia)
    assert len(familia.beneficios) == 0


def test_upsert_cliente_updates_on_duplicate(db_session):
    crud.upsert_cliente({"linea": "5511111111", "nombre": "Roberto", "renta_plan": 229.0})
    crud.upsert_cliente({"linea": "5511111111", "nombre": "Roberto Updated", "renta_plan": 249.0})
    clientes = crud.get_all_clientes()
    assert len(clientes) == 1
    assert clientes[0].nombre == "Roberto Updated"


def test_bulk_upsert_clientes(db_session):
    rows = [
        {"linea": "111", "nombre": "A", "renta_plan": 100.0},
        {"linea": "222", "nombre": "B", "renta_plan": 200.0},
    ]
    crud.bulk_upsert_clientes(rows)
    assert len(crud.get_all_clientes()) == 2


def test_create_campana_and_add_plan(db_session):
    familia = Familia(nombre="Telcel Libre")
    db_session.add(familia)
    db_session.flush()
    plan = Plan(
        familia_id=familia.id, nombre="Libre 1",
        precio_abierto=249.0, precio_controlado=299.0,
        gb_base=4.0, tiene_cashback=True, cashback_porcentaje=5.0,
    )
    db_session.add(plan)
    db_session.flush()
    campana = crud.create_campana("Test Campaign", "desc")
    crud.add_plan_to_campana(campana.id, plan.id, promocion_id=None)
    planes = crud.get_campana_planes(campana.id)
    assert len(planes) == 1
    assert planes[0].plan_id == plan.id


def test_get_campana_clientes_pendientes(db_session):
    campana = Campana(nombre="C1", estado="activa")
    c1 = Cliente(linea="111", nombre="A")
    c2 = Cliente(linea="222", nombre="B")
    db_session.add_all([campana, c1, c2])
    db_session.flush()
    db_session.add(CampanaCliente(campana_id=campana.id, linea="111",
                                   estado_envio="enviado", estado_interaccion="en_conversacion", num_turnos=1))
    db_session.add(CampanaCliente(campana_id=campana.id, linea="222",
                                   estado_envio="pendiente", estado_interaccion="pendiente", num_turnos=0))
    db_session.commit()
    pendientes = crud.get_campana_clientes_pendientes(campana.id)
    assert len(pendientes) == 1
    assert pendientes[0].linea == "222"
