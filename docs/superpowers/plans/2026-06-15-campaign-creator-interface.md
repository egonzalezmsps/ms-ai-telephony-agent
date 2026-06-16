# Campaign Creator Interface Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Streamlit-based campaign management interface backed by PostgreSQL for creating, configuring, and monitoring Telcel sales campaigns, with full conversation traceability from dispatch through close.

**Architecture:** `campaign_app/` at project root holds the Streamlit multipágina app. DB layer uses SQLAlchemy on the same PostgreSQL instance as ReniAgent (`DATABASE_URL`). Streamlit manages catalog/campaign tables directly via SQLAlchemy; campaign dispatch reuses the existing FastAPI `POST /campaign` endpoint via HTTP; conversation traceability hooks into `main.py` after `run_turn()`.

**Tech Stack:** Streamlit, SQLAlchemy, PostgreSQL, httpx, pandas, plotly, pytest

---

## File Map

**Create:**
- `campaign_app/__init__.py`
- `campaign_app/app.py` — dashboard entry point
- `campaign_app/pages/1_Catalogo.py` — familias, planes, beneficios, servicios, FAQs
- `campaign_app/pages/2_Promociones.py`
- `campaign_app/pages/3_Campanas.py`
- `campaign_app/pages/4_Seguimiento.py`
- `campaign_app/pages/5_Crear_desde_imagen.py`
- `campaign_app/db/__init__.py`
- `campaign_app/db/models.py` — 11 SQLAlchemy models
- `campaign_app/db/database.py` — engine, session context manager
- `campaign_app/db/crud.py` — all CRUD operations
- `campaign_app/db/seed.py` — populate DB from plans.py + CSV
- `campaign_app/components/__init__.py`
- `campaign_app/components/md_importer.py` — Markdown FAQ parser
- `tests/campaign_app/__init__.py`
- `tests/campaign_app/conftest.py`
- `tests/campaign_app/test_models.py`
- `tests/campaign_app/test_crud.py`
- `tests/campaign_app/test_md_importer.py`

**Modify:**
- `main.py` — add CampanaCliente update after `run_turn()`

**Run the app from project root:**
```bash
streamlit run campaign_app/app.py
```
Streamlit adds `campaign_app/` to `sys.path` automatically, so pages use `from db.xxx import ...`.

---

## Task 1: Install dependencies and scaffold

**Files:** `campaign_app/__init__.py`, `campaign_app/db/__init__.py`, `campaign_app/components/__init__.py`, `tests/campaign_app/__init__.py`, `tests/campaign_app/conftest.py`

- [ ] **Step 1: Install dependencies**

```bash
.venv\Scripts\activate
pip install streamlit httpx pandas plotly
```
Verify: `pip show streamlit` should print a version line.

- [ ] **Step 2: Create directories**

```bash
mkdir campaign_app campaign_app\db campaign_app\pages campaign_app\components tests\campaign_app
```

- [ ] **Step 3: Create empty `__init__.py` files**

Create four empty files:
- `campaign_app/__init__.py`
- `campaign_app/db/__init__.py`
- `campaign_app/components/__init__.py`
- `tests/campaign_app/__init__.py`

- [ ] **Step 4: Create `tests/campaign_app/conftest.py`**

```python
import sys
import os

# Add campaign_app/ to path so tests import the same way pages do
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "campaign_app"))
```

- [ ] **Step 5: Commit scaffold**

```bash
git add campaign_app/ tests/campaign_app/
git commit -m "feat: scaffold campaign_app directory structure"
```

---

## Task 2: Database models

**Files:** `campaign_app/db/models.py`, `tests/campaign_app/test_models.py`

- [ ] **Step 1: Write failing model tests**

`tests/campaign_app/test_models.py`:
```python
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
```

- [ ] **Step 2: Run tests — confirm they fail**

```bash
python -m pytest tests/campaign_app/test_models.py -v
```
Expected: `ImportError: No module named 'db'`

- [ ] **Step 3: Write `campaign_app/db/models.py`**

```python
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
```

- [ ] **Step 4: Run tests — confirm they pass**

```bash
python -m pytest tests/campaign_app/test_models.py -v
```
Expected: 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add campaign_app/db/models.py tests/campaign_app/test_models.py
git commit -m "feat: SQLAlchemy models for campaign interface"
```

---

## Task 3: DB connection

**Files:** `campaign_app/db/database.py`

- [ ] **Step 1: Write `campaign_app/db/database.py`**

```python
import os
from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

_engine = None


def get_engine():
    global _engine
    if _engine is None:
        url = os.environ.get("DATABASE_URL", "")
        if not url:
            raise ValueError("DATABASE_URL not set in .env")
        _engine = create_engine(url, pool_pre_ping=True)
    return _engine


def init_db():
    from db.models import Base
    Base.metadata.create_all(get_engine())


@contextmanager
def get_db():
    Session = sessionmaker(bind=get_engine(), expire_on_commit=False)
    session = Session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
```

- [ ] **Step 2: Verify tables create against real DB**

```bash
python -c "
import sys; sys.path.insert(0, 'campaign_app')
from db.database import init_db
init_db()
print('OK — tables created')
"
```
Expected: `OK — tables created`

- [ ] **Step 3: Commit**

```bash
git add campaign_app/db/database.py
git commit -m "feat: DB connection and init_db for campaign app"
```

---

## Task 4: CRUD operations

**Files:** `campaign_app/db/crud.py`, `tests/campaign_app/test_crud.py`

- [ ] **Step 1: Write failing CRUD tests**

`tests/campaign_app/test_crud.py`:
```python
import pytest
from contextlib import contextmanager
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from db.models import Base, Familia, Beneficio, Plan
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
    b_id = crud.create_beneficio("Apps ilimitadas", "7 apps").id
    crud.link_beneficio_to_familia(b_id, familia.id)
    db_session.refresh(familia)
    assert len(familia.beneficios) == 1
    crud.unlink_beneficio_from_familia(b_id, familia.id)
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
    from db.models import Campana, Cliente, CampanaCliente
    campana = Campana(nombre="C1", estado="activa")
    c1 = Cliente(linea="111", nombre="A")
    c2 = Cliente(linea="222", nombre="B")
    db_session.add_all([campana, c1, c2])
    db_session.flush()
    db_session.add(CampanaCliente(campana_id=campana.id, linea="111", estado_envio="enviado", estado_interaccion="en_conversacion", num_turnos=1))
    db_session.add(CampanaCliente(campana_id=campana.id, linea="222", estado_envio="pendiente", estado_interaccion="pendiente", num_turnos=0))
    db_session.commit()
    pendientes = crud.get_campana_clientes_pendientes(campana.id)
    assert len(pendientes) == 1
    assert pendientes[0].linea == "222"
```

- [ ] **Step 2: Run tests — confirm they fail**

```bash
python -m pytest tests/campaign_app/test_crud.py -v
```
Expected: `ImportError: No module named 'db.crud'`

- [ ] **Step 3: Write `campaign_app/db/crud.py`**

```python
from datetime import datetime
from typing import Optional
from db.database import get_db
from db.models import (
    Familia, Plan, Beneficio, Servicio, PreguntaFrecuente,
    Promocion, Campana, CampanaPlan, Cliente, CampanaCliente,
)


# ── Familia ───────────────────────────────────────────────────────────────────

def get_all_familias():
    with get_db() as db:
        return db.query(Familia).order_by(Familia.nombre).all()


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
        return db.query(Plan).order_by(Plan.familia_id, Plan.precio_abierto).all()


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
        return db.query(Beneficio).order_by(Beneficio.nombre).all()


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
        return db.query(Servicio).order_by(Servicio.nombre).all()


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
    """items: list of dicts with keys pregunta, respuesta, ambito, beneficio_id?, servicio_id?"""
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
        return db.query(CampanaPlan).filter_by(campana_id=campana_id).all()


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
        return db.query(CampanaCliente).filter_by(campana_id=campana_id).all()


def get_campana_clientes_pendientes(campana_id: int):
    with get_db() as db:
        return db.query(CampanaCliente).filter_by(
            campana_id=campana_id, estado_envio="pendiente").all()


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
    """Called from main.py after run_turn() to update conversation progress."""
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
    """Called when stage=END — persists conversation history permanently."""
    with get_db() as db:
        obj = db.query(CampanaCliente).filter_by(
            campana_id=campana_id, linea=linea).first()
        if obj:
            obj.historial_conversacion = history
            obj.session_data_snapshot = session_data


def find_active_campana_cliente(linea: str) -> Optional[CampanaCliente]:
    """Find the most recent active CampanaCliente for this phone number."""
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
```

- [ ] **Step 4: Run tests — confirm they pass**

```bash
python -m pytest tests/campaign_app/test_crud.py -v
```
Expected: 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add campaign_app/db/crud.py tests/campaign_app/test_crud.py
git commit -m "feat: CRUD operations for campaign interface"
```

---

## Task 5: Seed script

**Files:** `campaign_app/db/seed.py`

- [ ] **Step 1: Write `campaign_app/db/seed.py`**

```python
"""
Seed the campaign DB from the existing plans.py catalog and the Masivo_clientes.csv.
Idempotent — safe to run multiple times.
Run from project root: python campaign_app/db/seed.py
"""
import sys
import os

# Resolve project root so we can import both campaign_app and app.catalog
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CAMPAIGN_APP = os.path.join(PROJECT_ROOT, "campaign_app")
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, CAMPAIGN_APP)

import csv
from db.database import init_db, get_db
from db.models import Familia, Plan, Beneficio, Servicio
from app.catalog.plans import CATALOG

CSV_PATH = os.path.join(PROJECT_ROOT, "docs", "Masivo_clientes.csv")

FAMILIAS_DATA = [
    {"nombre": "Telcel Libre",  "descripcion": "Familia de planes Libre con apps ilimitadas y cashback"},
    {"nombre": "Telcel Ultra",  "descripcion": "Familia de planes Ultra con datos generosos y WhatsApp ilimitado"},
]

BENEFICIOS_DATA = [
    {"nombre": "Minutos y SMS ilimitados", "descripcion": "Llamadas y mensajes de texto ilimitados a todo México", "familias": ["Telcel Libre", "Telcel Ultra"]},
    {"nombre": "Apps ilimitadas",           "descripcion": "Facebook, WhatsApp, Messenger, X, Instagram, Snapchat, Uber sin consumir datos", "familias": ["Telcel Libre"]},
    {"nombre": "WhatsApp ilimitado",        "descripcion": "WhatsApp sin consumir datos del paquete", "familias": ["Telcel Ultra"]},
]

SERVICIOS_DATA = [
    {"nombre": "Claro Video",  "descripcion": "Plataforma de streaming de contenido", "tipo_acceso": "suscripcion", "detalle": None,         "familias": ["Telcel Libre", "Telcel Ultra"]},
    {"nombre": "Claro Drive",  "descripcion": "Almacenamiento en la nube",            "tipo_acceso": "acceso",      "detalle": "20 GB",       "familias": ["Telcel Libre", "Telcel Ultra"]},
]


def seed():
    init_db()
    with get_db() as db:
        # Familias
        familia_map = {}
        for fd in FAMILIAS_DATA:
            obj = db.query(Familia).filter_by(nombre=fd["nombre"]).first()
            if not obj:
                obj = Familia(**{k: v for k, v in fd.items()})
                db.add(obj)
                db.flush()
            familia_map[fd["nombre"]] = obj

        # Beneficios
        for bd in BENEFICIOS_DATA:
            obj = db.query(Beneficio).filter_by(nombre=bd["nombre"]).first()
            if not obj:
                obj = Beneficio(nombre=bd["nombre"], descripcion=bd["descripcion"], activo=True)
                db.add(obj)
                db.flush()
            for fname in bd["familias"]:
                if obj not in familia_map[fname].beneficios:
                    familia_map[fname].beneficios.append(obj)

        # Servicios
        for sd in SERVICIOS_DATA:
            obj = db.query(Servicio).filter_by(nombre=sd["nombre"]).first()
            if not obj:
                obj = Servicio(
                    nombre=sd["nombre"], descripcion=sd["descripcion"],
                    tipo_acceso=sd["tipo_acceso"], detalle=sd["detalle"], activo=True,
                )
                db.add(obj)
                db.flush()
            for fname in sd["familias"]:
                if obj not in familia_map[fname].servicios:
                    familia_map[fname].servicios.append(obj)

        # Planes from CATALOG
        for p in CATALOG:
            familia = familia_map.get(p.family)
            if not familia:
                continue
            existing = db.query(Plan).filter_by(nombre=p.plan_id).first()
            if not existing:
                cashback_pct = round(p.cashback_abierto / p.price_abierto * 100, 2) if p.cashback_abierto > 0 else 0.0
                db.add(Plan(
                    familia_id=familia.id,
                    nombre=p.plan_id,
                    precio_abierto=float(p.price_abierto),
                    precio_controlado=float(p.price_controlado),
                    gb_base=float(p.gb_base),
                    tiene_cashback=p.cashback_abierto > 0,
                    cashback_porcentaje=cashback_pct,
                    activo=True,
                ))

        # Clientes from CSV
        if os.path.exists(CSV_PATH):
            with open(CSV_PATH, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                from db.models import Cliente
                for row in reader:
                    linea = row.get("linea", "").strip()
                    if not linea:
                        continue
                    if not db.query(Cliente).filter_by(linea=linea).first():
                        db.add(Cliente(
                            linea=linea,
                            nombre=row.get("nombre", ""),
                            apellidos=row.get("apellidos", ""),
                            plan_actual_nombre=row.get("plan", ""),
                            familia_plan=row.get("familia_plan", ""),
                            tipo_suscripcion=row.get("tiposuscripcion", ""),
                            renta_plan=float(row.get("rentaplan") or 0),
                            facturacion_promedio=float(row.get("facturacion_promedio_3meses") or 0),
                            consumo_mb_total_prom=float(row.get("conmbtotal_promedio_3meses") or 0),
                            consumo_mb_whatsapp_prom=float(row.get("conmbwhatsapp_prom3meses") or 0),
                            consumo_mb_redes_prom=float(row.get("conmbredsoc_prom3meses") or 0),
                            consumo_mb_youtube_prom=float(row.get("conmbyoutube_prom3meses") or 0),
                            consumo_mb_uber_prom=float(row.get("conmbuber_prom3meses") or 0),
                            consumo_mb_instagram_prom=float(row.get("conmbinstagr_prom3meses") or 0),
                            consumo_mb_otros_prom=float(row.get("conmbotros_prom3meses") or 0),
                            excedentes_nac_mb_prom=float(row.get("totalmb_nacexcedentes_prom3meses") or 0),
                            excedentes_int_mb_prom=float(row.get("totalmb_intexcedentes_prom3meses") or 0),
                            ingresos_exc_nac_prom=float(row.get("total_ingresos_nacexce_prom3meses") or 0),
                            ingresos_exc_int_prom=float(row.get("total_ingresos_intcexce_prom3meses") or 0),
                        ))
        print("Seed complete.")


if __name__ == "__main__":
    seed()
```

- [ ] **Step 2: Run the seed and verify**

```bash
python campaign_app/db/seed.py
```
Expected: `Seed complete.`

Then verify in psql or via Python:
```bash
python -c "
import sys; sys.path.insert(0, 'campaign_app')
from db.database import get_db
from db.models import Familia, Plan, Cliente
with get_db() as db:
    print('Familias:', db.query(Familia).count())
    print('Planes:', db.query(Plan).count())
    print('Clientes:', db.query(Cliente).count())
"
```
Expected: `Familias: 2`, `Planes: 16`, `Clientes: 19` (or however many rows the CSV has).

- [ ] **Step 3: Commit**

```bash
git add campaign_app/db/seed.py
git commit -m "feat: seed script from plans.py catalog and CSV"
```

---

## Task 6: Markdown FAQ importer

**Files:** `campaign_app/components/md_importer.py`, `tests/campaign_app/test_md_importer.py`

- [ ] **Step 1: Write failing tests**

`tests/campaign_app/test_md_importer.py`:
```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "campaign_app"))
from components.md_importer import parse_md_faqs


HEADER_STYLE = """
## ¿Qué apps incluye Telcel Libre?
Facebook, WhatsApp, Messenger, X, Instagram, Snapchat y Uber.

## ¿Qué es Claro Video?
Es la plataforma de streaming incluida en todos los planes.

## ¿Cómo solicito mi cashback?
Se acredita automáticamente en tu siguiente factura.
"""

QA_STYLE = """
**Pregunta:** ¿Cuántos GB incluye Telcel Libre 1?
**Respuesta:** Incluye 4 GB base más 2 GB de promoción durante 24 meses.

**Pregunta:** ¿El plan Libre tiene llamadas ilimitadas?
**Respuesta:** Sí, minutos y SMS ilimitados a todo México.
"""

MIXED = """
# Sección de Preguntas Frecuentes

## ¿Qué es el cashback?
Es un beneficio exclusivo de la familia Libre.

**Pregunta:** ¿Cómo funciona el OTP?
**Respuesta:** Recibirás un SMS con tu código de verificación.
"""


def test_parse_header_style():
    items = parse_md_faqs(HEADER_STYLE)
    assert len(items) == 3
    assert items[0]["pregunta"] == "¿Qué apps incluye Telcel Libre?"
    assert "Facebook" in items[0]["respuesta"]


def test_parse_qa_style():
    items = parse_md_faqs(QA_STYLE)
    assert len(items) == 2
    assert "4 GB" in items[0]["respuesta"]


def test_parse_mixed_style():
    items = parse_md_faqs(MIXED)
    assert len(items) == 2


def test_empty_input_returns_empty_list():
    assert parse_md_faqs("") == []
    assert parse_md_faqs("# Just a heading\n\nNo questions here.") == []


def test_all_items_have_required_keys():
    items = parse_md_faqs(HEADER_STYLE)
    for item in items:
        assert "pregunta" in item
        assert "respuesta" in item
        assert item["pregunta"].strip()
        assert item["respuesta"].strip()
```

- [ ] **Step 2: Run tests — confirm they fail**

```bash
python -m pytest tests/campaign_app/test_md_importer.py -v
```
Expected: `ImportError`

- [ ] **Step 3: Write `campaign_app/components/md_importer.py`**

```python
import re
from typing import List, Dict


def parse_md_faqs(text: str) -> List[Dict[str, str]]:
    """
    Extract Q&A pairs from Markdown text.
    Supports two patterns:
      1. ## Heading as question + following paragraph as answer
      2. **Pregunta:** ... / **Respuesta:** ... pairs
    Returns list of {"pregunta": str, "respuesta": str}.
    """
    results = []

    # Pattern 1: **Pregunta:** / **Respuesta:** blocks
    qa_pattern = re.compile(
        r"\*\*Pregunta:\*\*\s*(.+?)\s*\n\*\*Respuesta:\*\*\s*(.+?)(?=\n\*\*Pregunta|\Z)",
        re.DOTALL,
    )
    for m in qa_pattern.finditer(text):
        pregunta = m.group(1).strip()
        respuesta = m.group(2).strip()
        if pregunta and respuesta:
            results.append({"pregunta": pregunta, "respuesta": respuesta})

    # Remove already-matched segments before applying header pattern
    cleaned = qa_pattern.sub("", text)

    # Pattern 2: ## or ### heading + paragraph (skip # top-level headings)
    header_pattern = re.compile(
        r"^#{2,3}\s+(.+?)\n([\s\S]+?)(?=^#{1,3}\s|\Z)",
        re.MULTILINE,
    )
    for m in header_pattern.finditer(cleaned):
        pregunta = m.group(1).strip()
        respuesta = m.group(2).strip()
        # Skip lines that are just sub-headings or empty
        if not respuesta or pregunta.startswith("#"):
            continue
        # Drop any nested headings that leaked into the answer
        respuesta = re.sub(r"^#{1,3}\s.*$", "", respuesta, flags=re.MULTILINE).strip()
        if pregunta and respuesta:
            results.append({"pregunta": pregunta, "respuesta": respuesta})

    return results
```

- [ ] **Step 4: Run tests — confirm they pass**

```bash
python -m pytest tests/campaign_app/test_md_importer.py -v
```
Expected: 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add campaign_app/components/md_importer.py tests/campaign_app/test_md_importer.py
git commit -m "feat: Markdown FAQ importer with dual-format parser"
```

---

## Task 7: Streamlit app scaffold and dashboard

**Files:** `campaign_app/app.py`

- [ ] **Step 1: Write `campaign_app/app.py`**

```python
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st
from db.database import init_db
from db.crud import get_all_campanas, get_all_clientes, get_campana_clientes

st.set_page_config(page_title="Reni — Campaign Manager", page_icon="📢", layout="wide")

init_db()

st.title("📢 Campaign Manager — Reni")
st.caption("Gestión de campañas de migración Telcel")

campanas = get_all_campanas()
activas = [c for c in campanas if c.estado == "activa"]
borradores = [c for c in campanas if c.estado == "borrador"]

col1, col2, col3, col4 = st.columns(4)
col1.metric("Campañas activas", len(activas))
col2.metric("En borrador", len(borradores))
col3.metric("Total campañas", len(campanas))
col4.metric("Clientes registrados", len(get_all_clientes()))

st.divider()
st.subheader("Campañas activas")

if not activas:
    st.info("No hay campañas activas. Ve a **Campañas** para crear una.")
else:
    for c in activas:
        clientes = get_campana_clientes(c.id)
        enviados = sum(1 for cc in clientes if cc.estado_envio == "enviado")
        convertidos = sum(1 for cc in clientes if cc.estado_interaccion == "convertido")
        total = len(clientes)
        with st.expander(f"**{c.nombre}** — {enviados}/{total} enviados · {convertidos} convertidos"):
            col_a, col_b, col_c = st.columns(3)
            col_a.metric("Enviados", enviados)
            col_b.metric("Convertidos", convertidos)
            col_c.metric("Pendientes", total - enviados)
            if c.vigencia_fin:
                st.caption(f"Vigencia hasta: {c.vigencia_fin.strftime('%d/%m/%Y')}")

st.divider()
st.caption("Navega por el menú lateral para gestionar el catálogo, promociones y campañas.")
```

- [ ] **Step 2: Run the app and verify dashboard loads**

```bash
streamlit run campaign_app/app.py
```
Open `http://localhost:8501` in browser. Expected: dashboard with 4 metrics and "Campañas activas" section.

- [ ] **Step 3: Commit**

```bash
git add campaign_app/app.py
git commit -m "feat: Streamlit dashboard entry point"
```

---

## Task 8: Catálogo page

**Files:** `campaign_app/pages/1_Catalogo.py`

- [ ] **Step 1: Write `campaign_app/pages/1_Catalogo.py`**

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
import json
from db.crud import (
    get_all_familias, create_familia, update_familia,
    get_all_planes, create_plan, update_plan, toggle_plan_activo,
    get_all_beneficios, create_beneficio, toggle_beneficio_activo,
    link_beneficio_to_familia, unlink_beneficio_from_familia,
    get_all_servicios, create_servicio, toggle_servicio_activo,
    link_servicio_to_familia, unlink_servicio_from_familia,
    get_all_preguntas, create_pregunta, bulk_create_preguntas, delete_pregunta,
)
from components.md_importer import parse_md_faqs

st.set_page_config(page_title="Catálogo", layout="wide")
st.title("📋 Catálogo")

tabs = st.tabs(["Familias", "Planes", "Beneficios", "Servicios", "Preguntas Frecuentes"])

# ── Tab: Familias ─────────────────────────────────────────────────────────────
with tabs[0]:
    st.subheader("Familias de planes")
    familias = get_all_familias()
    for f in familias:
        with st.expander(f.nombre):
            with st.form(f"edit_familia_{f.id}"):
                nombre = st.text_input("Nombre", value=f.nombre)
                desc = st.text_area("Descripción", value=f.descripcion or "")
                if st.form_submit_button("Guardar"):
                    update_familia(f.id, nombre=nombre, descripcion=desc)
                    st.success("Guardado")
                    st.rerun()

    st.divider()
    with st.expander("➕ Nueva familia"):
        with st.form("new_familia"):
            nombre = st.text_input("Nombre")
            desc = st.text_area("Descripción")
            if st.form_submit_button("Crear") and nombre:
                create_familia(nombre, desc)
                st.success(f"Familia '{nombre}' creada")
                st.rerun()

# ── Tab: Planes ───────────────────────────────────────────────────────────────
with tabs[1]:
    st.subheader("Planes")
    familias = get_all_familias()
    familia_options = {f.nombre: f.id for f in familias}
    selected_familia = st.selectbox("Filtrar por familia", ["Todas"] + list(familia_options.keys()))

    planes = get_all_planes()
    if selected_familia != "Todas":
        planes = [p for p in planes if p.familia_id == familia_options[selected_familia]]

    for p in planes:
        label = f"{'✅' if p.activo else '⛔'} {p.nombre}"
        with st.expander(label):
            with st.form(f"edit_plan_{p.id}"):
                col1, col2 = st.columns(2)
                precio_a = col1.number_input("Precio Abierto", value=p.precio_abierto, step=10.0)
                precio_c = col2.number_input("Precio Controlado", value=p.precio_controlado, step=10.0)
                gb = st.number_input("GB base (0 = ilimitado)", value=p.gb_base, step=1.0)
                tiene_cb = st.checkbox("¿Tiene cashback?", value=p.tiene_cashback)
                cb_pct = st.number_input("Cashback %", value=p.cashback_porcentaje, step=0.5,
                                         disabled=not tiene_cb)
                col_s, col_t = st.columns(2)
                if col_s.form_submit_button("Guardar"):
                    update_plan(p.id, precio_abierto=precio_a, precio_controlado=precio_c,
                                gb_base=gb, tiene_cashback=tiene_cb, cashback_porcentaje=cb_pct)
                    st.success("Guardado")
                    st.rerun()
                if col_t.form_submit_button("Activar / Desactivar"):
                    toggle_plan_activo(p.id)
                    st.rerun()

    st.divider()
    with st.expander("➕ Nuevo plan"):
        with st.form("new_plan"):
            familia_sel = st.selectbox("Familia", list(familia_options.keys()))
            nombre = st.text_input("Nombre del plan")
            col1, col2 = st.columns(2)
            precio_a = col1.number_input("Precio Abierto", step=10.0)
            precio_c = col2.number_input("Precio Controlado", step=10.0)
            gb = st.number_input("GB base (0 = ilimitado)", step=1.0)
            tiene_cb = st.checkbox("¿Tiene cashback?")
            cb_pct = st.number_input("Cashback %", step=0.5, disabled=not tiene_cb)
            if st.form_submit_button("Crear") and nombre:
                create_plan(
                    familia_id=familia_options[familia_sel],
                    nombre=nombre, precio_abierto=precio_a, precio_controlado=precio_c,
                    gb_base=gb, tiene_cashback=tiene_cb, cashback_porcentaje=cb_pct,
                )
                st.success(f"Plan '{nombre}' creado")
                st.rerun()

# ── Tab: Beneficios ───────────────────────────────────────────────────────────
with tabs[2]:
    st.subheader("Beneficios (atributos intrínsecos de la familia)")
    familias = get_all_familias()
    beneficios = get_all_beneficios()

    for b in beneficios:
        linked_families = [f.nombre for f in b.familias]
        with st.expander(f"{'✅' if b.activo else '⛔'} {b.nombre} — {', '.join(linked_families) or 'Sin familia'}"):
            st.write(b.descripcion or "")
            for f in familias:
                linked = f in b.familias
                new_val = st.checkbox(f"Incluir en {f.nombre}", value=linked, key=f"ben_{b.id}_fam_{f.id}")
                if new_val != linked:
                    if new_val:
                        link_beneficio_to_familia(b.id, f.id)
                    else:
                        unlink_beneficio_from_familia(b.id, f.id)
                    st.rerun()
            if st.button(f"{'Desactivar' if b.activo else 'Activar'}", key=f"toggle_ben_{b.id}"):
                toggle_beneficio_activo(b.id)
                st.rerun()

    st.divider()
    with st.expander("➕ Nuevo beneficio"):
        with st.form("new_beneficio"):
            nombre = st.text_input("Nombre")
            desc = st.text_area("Descripción")
            if st.form_submit_button("Crear") and nombre:
                create_beneficio(nombre, desc)
                st.success(f"Beneficio '{nombre}' creado")
                st.rerun()

# ── Tab: Servicios ────────────────────────────────────────────────────────────
with tabs[3]:
    st.subheader("Servicios (añadidos de la familia)")
    familias = get_all_familias()
    servicios = get_all_servicios()

    for s in servicios:
        linked_families = [f.nombre for f in s.familias]
        with st.expander(f"{'✅' if s.activo else '⛔'} {s.nombre} ({s.tipo_acceso}) — {', '.join(linked_families) or 'Sin familia'}"):
            st.write(s.descripcion or "")
            if s.detalle:
                st.caption(f"Detalle: {s.detalle}")
            for f in familias:
                linked = f in s.familias
                new_val = st.checkbox(f"Incluir en {f.nombre}", value=linked, key=f"srv_{s.id}_fam_{f.id}")
                if new_val != linked:
                    if new_val:
                        link_servicio_to_familia(s.id, f.id)
                    else:
                        unlink_servicio_from_familia(s.id, f.id)
                    st.rerun()
            if st.button(f"{'Desactivar' if s.activo else 'Activar'}", key=f"toggle_srv_{s.id}"):
                toggle_servicio_activo(s.id)
                st.rerun()

    st.divider()
    with st.expander("➕ Nuevo servicio"):
        with st.form("new_servicio"):
            nombre = st.text_input("Nombre")
            desc = st.text_area("Descripción")
            tipo = st.selectbox("Tipo de acceso", ["suscripcion", "acceso"])
            detalle = st.text_input("Detalle (opcional)", placeholder="ej. 20 GB en la nube")
            if st.form_submit_button("Crear") and nombre:
                create_servicio(nombre, desc, tipo, detalle)
                st.success(f"Servicio '{nombre}' creado")
                st.rerun()

# ── Tab: Preguntas Frecuentes ─────────────────────────────────────────────────
with tabs[4]:
    st.subheader("Preguntas Frecuentes")

    subtabs = st.tabs(["Ver y crear", "Importar desde Markdown"])

    with subtabs[0]:
        ambito_filter = st.selectbox("Filtrar por ámbito", ["Todos", "general", "beneficio", "servicio"])
        preguntas = get_all_preguntas(ambito=None if ambito_filter == "Todos" else ambito_filter)

        for p in preguntas:
            with st.expander(f"[{p.ambito}] {p.pregunta[:80]}"):
                st.write("**Respuesta:**", p.respuesta)
                if st.button("Eliminar", key=f"del_p_{p.id}"):
                    delete_pregunta(p.id)
                    st.rerun()

        st.divider()
        with st.expander("➕ Nueva pregunta"):
            with st.form("new_pregunta"):
                pregunta = st.text_area("Pregunta")
                respuesta = st.text_area("Respuesta")
                ambito = st.selectbox("Ámbito", ["general", "beneficio", "servicio"])
                beneficio_id = servicio_id = None
                if ambito == "beneficio":
                    bens = get_all_beneficios()
                    sel = st.selectbox("Beneficio", bens, format_func=lambda b: b.nombre)
                    beneficio_id = sel.id if sel else None
                elif ambito == "servicio":
                    srvs = get_all_servicios()
                    sel = st.selectbox("Servicio", srvs, format_func=lambda s: s.nombre)
                    servicio_id = sel.id if sel else None
                if st.form_submit_button("Crear") and pregunta and respuesta:
                    create_pregunta(pregunta, respuesta, ambito, beneficio_id, servicio_id)
                    st.success("Pregunta creada")
                    st.rerun()

    with subtabs[1]:
        st.markdown("### Importar FAQs desde Markdown")
        st.info("Sube un archivo `.md`. Se detectarán preguntas con formato `## Pregunta / párrafo` o `**Pregunta:** / **Respuesta:**`.")

        uploaded = st.file_uploader("Archivo Markdown", type=["md"])
        if uploaded:
            content = uploaded.read().decode("utf-8")
            parsed = parse_md_faqs(content)

            if not parsed:
                st.warning("No se detectaron pares pregunta/respuesta en el archivo.")
            else:
                st.success(f"{len(parsed)} preguntas detectadas. Revisa y ajusta antes de insertar.")
                bens = get_all_beneficios()
                srvs = get_all_servicios()
                ben_opts = {b.nombre: b.id for b in bens}
                srv_opts = {s.nombre: s.id for s in srvs}
                all_ambitos = ["general", "beneficio", "servicio"]

                edited = []
                for i, item in enumerate(parsed):
                    with st.expander(f"{i+1}. {item['pregunta'][:60]}"):
                        pregunta = st.text_area("Pregunta", value=item["pregunta"], key=f"q_{i}")
                        respuesta = st.text_area("Respuesta", value=item["respuesta"], key=f"a_{i}")
                        ambito = st.selectbox("Ámbito", all_ambitos, key=f"amb_{i}")
                        ben_id = srv_id = None
                        if ambito == "beneficio" and ben_opts:
                            ben_sel = st.selectbox("Beneficio", list(ben_opts.keys()), key=f"ben_{i}")
                            ben_id = ben_opts[ben_sel]
                        elif ambito == "servicio" and srv_opts:
                            srv_sel = st.selectbox("Servicio", list(srv_opts.keys()), key=f"srv_{i}")
                            srv_id = srv_opts[srv_sel]
                        include = st.checkbox("Incluir en importación", value=True, key=f"inc_{i}")
                        if include:
                            edited.append({"pregunta": pregunta, "respuesta": respuesta,
                                           "ambito": ambito, "beneficio_id": ben_id, "servicio_id": srv_id})

                if st.button(f"Insertar {len(edited)} seleccionadas"):
                    n = bulk_create_preguntas(edited)
                    st.success(f"{n} preguntas insertadas correctamente.")
                    st.rerun()
```

- [ ] **Step 2: Verify page loads in the running app**

With `streamlit run campaign_app/app.py` running, navigate to "Catálogo" in the sidebar. Verify all 5 tabs load without error and show seeded data (familias: Telcel Libre / Ultra, 16 planes, beneficios, servicios).

- [ ] **Step 3: Commit**

```bash
git add campaign_app/pages/1_Catalogo.py
git commit -m "feat: Catalogo page with families, plans, benefits, services, and FAQ import"
```

---

## Task 9: Promociones page

**Files:** `campaign_app/pages/2_Promociones.py`

- [ ] **Step 1: Write `campaign_app/pages/2_Promociones.py`**

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import streamlit as st
from datetime import datetime
from db.crud import (
    get_all_promociones, create_promocion, update_promocion, toggle_promocion_activo,
)

st.set_page_config(page_title="Promociones", layout="wide")
st.title("🎯 Promociones")

promociones = get_all_promociones()
now = datetime.utcnow()

for p in promociones:
    vencida = p.vigencia_fin < now
    proxima = p.vigencia_inicio > now
    badge = "🔴 Vencida" if vencida else ("🟡 Próxima" if proxima else "🟢 Activa")
    estado = "✅" if p.activo else "⛔"
    with st.expander(f"{estado} {p.nombre}  —  {badge}  ({p.vigencia_inicio.strftime('%d/%m/%Y')} → {p.vigencia_fin.strftime('%d/%m/%Y')})"):
        with st.form(f"edit_promo_{p.id}"):
            nombre = st.text_input("Nombre", value=p.nombre)
            desc = st.text_area("Descripción", value=p.descripcion or "")
            col1, col2 = st.columns(2)
            vi = col1.date_input("Vigencia inicio", value=p.vigencia_inicio.date())
            vf = col2.date_input("Vigencia fin", value=p.vigencia_fin.date())
            condicion = st.text_input("Condición", value=p.condicion or "",
                                      placeholder="ej. upsell, precio mayor que renta actual")
            config_str = st.text_area(
                "Configuración (JSON)",
                value=json.dumps(p.configuracion, indent=2, ensure_ascii=False) if p.configuracion else "{}",
                height=100,
            )
            col_s, col_t = st.columns(2)
            if col_s.form_submit_button("Guardar"):
                try:
                    config = json.loads(config_str)
                    update_promocion(
                        p.id, nombre=nombre, descripcion=desc,
                        vigencia_inicio=datetime.combine(vi, datetime.min.time()),
                        vigencia_fin=datetime.combine(vf, datetime.min.time()),
                        condicion=condicion, configuracion=config,
                    )
                    st.success("Guardado")
                    st.rerun()
                except json.JSONDecodeError:
                    st.error("El JSON de configuración no es válido.")
            if col_t.form_submit_button("Activar / Desactivar"):
                toggle_promocion_activo(p.id)
                st.rerun()

st.divider()
with st.expander("➕ Nueva promoción"):
    with st.form("new_promo"):
        nombre = st.text_input("Nombre")
        desc = st.text_area("Descripción")
        col1, col2 = st.columns(2)
        vi = col1.date_input("Vigencia inicio")
        vf = col2.date_input("Vigencia fin")
        condicion = st.text_input("Condición", placeholder="ej. upsell")
        config_str = st.text_area("Configuración (JSON)", value='{"tipo": "multiplicador_gb", "valor": 1.5}', height=80)
        if st.form_submit_button("Crear") and nombre:
            try:
                config = json.loads(config_str)
                create_promocion(
                    nombre=nombre, descripcion=desc,
                    vigencia_inicio=datetime.combine(vi, datetime.min.time()),
                    vigencia_fin=datetime.combine(vf, datetime.min.time()),
                    configuracion=config, condicion=condicion,
                )
                st.success(f"Promoción '{nombre}' creada")
                st.rerun()
            except json.JSONDecodeError:
                st.error("El JSON de configuración no es válido.")
```

- [ ] **Step 2: Verify in browser**

Navigate to "Promociones" in sidebar. Create a test promotion with JSON `{"tipo": "multiplicador_gb", "valor": 1.5}`. Verify it appears in the list with badge "Activa" or "Próxima".

- [ ] **Step 3: Commit**

```bash
git add campaign_app/pages/2_Promociones.py
git commit -m "feat: Promociones page with CRUD and vigency badges"
```

---

## Task 10: Campañas page

**Files:** `campaign_app/pages/3_Campanas.py`

- [ ] **Step 1: Write `campaign_app/pages/3_Campanas.py`**

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import io
import httpx
import pandas as pd
import streamlit as st
from datetime import datetime
from dotenv import load_dotenv
from db.crud import (
    get_all_campanas, create_campana, update_campana,
    get_all_planes, get_all_promociones,
    get_campana_planes, add_plan_to_campana, remove_plan_from_campana,
    get_all_clientes, bulk_upsert_clientes,
    get_campana_clientes, get_campana_clientes_pendientes,
    add_clientes_to_campana, mark_enviado, mark_fallido,
)

load_dotenv()

REQUIRED_CSV_COLS = {"linea", "nombre", "apellidos", "plan", "tiposuscripcion", "rentaplan"}
API_BASE = os.getenv("CAMPAIGN_APP_API_URL", "http://localhost:8000")
API_KEY = os.getenv("API_KEY", "")

st.set_page_config(page_title="Campañas", layout="wide")
st.title("📢 Campañas")

view = st.radio("Vista", ["Lista de campañas", "Nueva campaña"], horizontal=True)

if view == "Nueva campaña":
    with st.form("new_campana"):
        nombre = st.text_input("Nombre de la campaña")
        desc = st.text_area("Descripción")
        col1, col2 = st.columns(2)
        vi = col1.date_input("Inicio de vigencia")
        vf = col2.date_input("Fin de vigencia")
        if st.form_submit_button("Crear campaña") and nombre:
            c = create_campana(
                nombre=nombre, descripcion=desc,
                vigencia_inicio=datetime.combine(vi, datetime.min.time()),
                vigencia_fin=datetime.combine(vf, datetime.min.time()),
            )
            st.success(f"Campaña '{nombre}' creada con estado **borrador**.")
            st.rerun()

else:
    campanas = get_all_campanas()
    if not campanas:
        st.info("No hay campañas. Crea una nueva.")
        st.stop()

    campana_sel_nombre = st.selectbox(
        "Selecciona campaña",
        [f"[{c.estado.upper()}] {c.nombre}" for c in campanas],
    )
    campana = campanas[[f"[{c.estado.upper()}] {c.nombre}" for c in campanas].index(campana_sel_nombre)]

    tab_config, tab_clientes, tab_estado = st.tabs(["Configuración", "Clientes", "Estado"])

    # ── Tab: Configuración ────────────────────────────────────────────────────
    with tab_config:
        with st.form("edit_campana"):
            nombre = st.text_input("Nombre", value=campana.nombre)
            desc = st.text_area("Descripción", value=campana.descripcion or "")
            col1, col2 = st.columns(2)
            vi = col1.date_input("Inicio", value=campana.vigencia_inicio.date() if campana.vigencia_inicio else None)
            vf = col2.date_input("Fin",    value=campana.vigencia_fin.date()    if campana.vigencia_fin    else None)
            estado = st.selectbox("Estado", ["borrador", "activa", "pausada", "finalizada"],
                                  index=["borrador", "activa", "pausada", "finalizada"].index(campana.estado))
            if st.form_submit_button("Guardar"):
                update_campana(
                    campana.id, nombre=nombre, descripcion=desc, estado=estado,
                    vigencia_inicio=datetime.combine(vi, datetime.min.time()) if vi else None,
                    vigencia_fin=datetime.combine(vf, datetime.min.time()) if vf else None,
                )
                st.success("Guardado")
                st.rerun()

        st.subheader("Planes disponibles en esta campaña")
        all_planes = get_all_planes()
        promociones = get_all_promociones()
        promo_opts = {p.nombre: p.id for p in promociones}
        promo_opts_with_none = {"Sin promoción": None, **promo_opts}
        campana_planes = {cp.plan_id: cp for cp in get_campana_planes(campana.id)}

        for p in all_planes:
            in_campana = p.id in campana_planes
            col1, col2, col3 = st.columns([3, 3, 2])
            col1.write(f"{'✅' if in_campana else '⬜'} **{p.nombre}**")
            if in_campana:
                cp = campana_planes[p.id]
                promo_actual = cp.promocion.nombre if cp.promocion else "Sin promoción"
                col2.caption(f"Promo: {promo_actual}")
                if col3.button("Quitar", key=f"rm_plan_{p.id}"):
                    remove_plan_from_campana(campana.id, p.id)
                    st.rerun()
            else:
                promo_sel = col2.selectbox("Promo", list(promo_opts_with_none.keys()),
                                           key=f"promo_sel_{p.id}", label_visibility="collapsed")
                if col3.button("Agregar", key=f"add_plan_{p.id}"):
                    add_plan_to_campana(campana.id, p.id, promo_opts_with_none[promo_sel])
                    st.rerun()

    # ── Tab: Clientes ─────────────────────────────────────────────────────────
    with tab_clientes:
        st.subheader("Carga de clientes")
        upload_method = st.radio("Método", ["CSV", "Individual"], horizontal=True)

        if upload_method == "CSV":
            uploaded = st.file_uploader("Archivo CSV", type=["csv"])
            if uploaded:
                df = pd.read_csv(uploaded, dtype=str)
                missing = REQUIRED_CSV_COLS - set(df.columns)
                if missing:
                    st.error(f"Columnas faltantes: {', '.join(missing)}")
                else:
                    st.dataframe(df.head(10))
                    st.caption(f"{len(df)} filas detectadas.")
                    if st.button("Cargar clientes y agregar a campaña"):
                        rows = df.rename(columns={
                            "plan": "plan_actual_nombre",
                            "familia_plan": "familia_plan",
                            "tiposuscripcion": "tipo_suscripcion",
                            "rentaplan": "renta_plan",
                            "facturacion_promedio_3meses": "facturacion_promedio",
                            "conmbtotal_promedio_3meses": "consumo_mb_total_prom",
                            "conmbwhatsapp_prom3meses": "consumo_mb_whatsapp_prom",
                            "conmbredsoc_prom3meses": "consumo_mb_redes_prom",
                            "conmbyoutube_prom3meses": "consumo_mb_youtube_prom",
                            "conmbuber_prom3meses": "consumo_mb_uber_prom",
                            "conmbinstagr_prom3meses": "consumo_mb_instagram_prom",
                            "conmbotros_prom3meses": "consumo_mb_otros_prom",
                            "totalmb_nacexcedentes_prom3meses": "excedentes_nac_mb_prom",
                            "totalmb_intexcedentes_prom3meses": "excedentes_int_mb_prom",
                            "total_ingresos_nacexce_prom3meses": "ingresos_exc_nac_prom",
                            "total_ingresos_intcexce_prom3meses": "ingresos_exc_int_prom",
                        }).to_dict(orient="records")
                        n = bulk_upsert_clientes(rows)
                        add_clientes_to_campana(campana.id, [r["linea"] for r in rows])
                        st.success(f"{n} clientes cargados y agregados a la campaña.")
                        st.rerun()

        else:
            with st.form("add_individual"):
                linea = st.text_input("Número de línea")
                nombre = st.text_input("Nombre")
                apellidos = st.text_input("Apellidos")
                plan_actual = st.text_input("Plan actual")
                tipo_sus = st.selectbox("Tipo suscripción", ["Abierto", "Controlado", "Mixto", "Postpago"])
                renta = st.number_input("Renta mensual", step=10.0)
                if st.form_submit_button("Agregar") and linea:
                    bulk_upsert_clientes([{
                        "linea": linea, "nombre": nombre, "apellidos": apellidos,
                        "plan_actual_nombre": plan_actual, "tipo_suscripcion": tipo_sus,
                        "renta_plan": renta,
                    }])
                    add_clientes_to_campana(campana.id, [linea])
                    st.success(f"Cliente {linea} agregado.")
                    st.rerun()

        st.divider()
        st.subheader("Envío de mensajes")
        clientes = get_campana_clientes(campana.id)
        pendientes = [cc for cc in clientes if cc.estado_envio == "pendiente"]
        enviados = [cc for cc in clientes if cc.estado_envio == "enviado"]
        st.write(f"Total: {len(clientes)} · Pendientes: {len(pendientes)} · Enviados: {len(enviados)}")

        col_all, col_subset = st.columns(2)

        if col_all.button(f"Enviar a todos los pendientes ({len(pendientes)})"):
            if campana.estado != "activa":
                st.error("Activa la campaña antes de enviar.")
            else:
                _send_batch(campana, pendientes)

        subset_n = col_subset.number_input("Enviar a los primeros N pendientes", min_value=1,
                                            max_value=max(len(pendientes), 1), step=1)
        if col_subset.button("Enviar subconjunto"):
            if campana.estado != "activa":
                st.error("Activa la campaña antes de enviar.")
            else:
                _send_batch(campana, pendientes[:int(subset_n)])


def _send_batch(campana, clientes_cc):
    """Call POST /campaign for each pending CampanaCliente."""
    from db.crud import get_all_clientes
    from db.database import get_db
    from db.models import Cliente as ClienteModel

    ok, fail = 0, 0
    progress = st.progress(0, text="Enviando...")
    total = len(clientes_cc)

    with get_db() as db:
        for i, cc in enumerate(clientes_cc):
            cliente = db.query(ClienteModel).filter_by(linea=cc.linea).first()
            if not cliente:
                mark_fallido(campana.id, cc.linea)
                fail += 1
                continue
            payload = {
                "phone_number": cliente.linea,
                "first_name": cliente.nombre or "Cliente",
                "full_name": f"{cliente.nombre or ''} {cliente.apellidos or ''}".strip(),
                "current_plan_name": cliente.plan_actual_nombre or "",
                "current_cost": cliente.renta_plan or 0.0,
                "subscription_type": _normalize_suscripcion(cliente.tipo_suscripcion),
            }
            try:
                resp = httpx.post(
                    f"{API_BASE}/campaign",
                    json=payload,
                    headers={"x-api-key": API_KEY},
                    timeout=10,
                )
                resp.raise_for_status()
                mark_enviado(campana.id, cc.linea)
                ok += 1
            except Exception as e:
                mark_fallido(campana.id, cc.linea)
                fail += 1
            progress.progress((i + 1) / total, text=f"Enviando {i+1}/{total}...")

    progress.empty()
    st.success(f"Enviados: {ok} · Fallidos: {fail}")
    st.rerun()


def _normalize_suscripcion(tipo: str) -> str:
    if not tipo:
        return "Abierto"
    tipo_lower = tipo.lower()
    if "control" in tipo_lower:
        return "Controlado"
    return "Abierto"

    # ── Tab: Estado ───────────────────────────────────────────────────────────
with tab_estado:
    st.subheader("Estado de clientes en esta campaña")
    clientes_cc = get_campana_clientes(campana.id)
    if not clientes_cc:
        st.info("No hay clientes en esta campaña.")
    else:
        rows = []
        for cc in clientes_cc:
            rows.append({
                "Línea": cc.linea,
                "Envío": cc.estado_envio,
                "Interacción": cc.estado_interaccion,
                "Plan seleccionado": cc.plan_seleccionado or "—",
                "Turnos": cc.num_turnos,
                "Folio": cc.folio_contrato or "—",
                "Fecha envío": cc.fecha_envio.strftime("%d/%m %H:%M") if cc.fecha_envio else "—",
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True)
```

- [ ] **Step 2: Fix the indentation bug — `tab_estado` block must be at top level, not inside `_send_batch`**

The `with tab_estado:` block at the bottom of the file must NOT be inside the `_send_batch` function definition. Move it so it follows the function at the same indent level as `tab_config` and `tab_clientes`. The final file structure is:

```
else:  # Lista de campañas
    ...
    tab_config, tab_clientes, tab_estado = st.tabs(...)

    with tab_config:
        ...

    with tab_clientes:
        ...

def _send_batch(...):
    ...

def _normalize_suscripcion(...):
    ...

with tab_estado:
    ...
```

This works because Streamlit evaluates the `with tab_estado:` block when the script runs, and `tab_estado` is in scope from the `else` branch.

- [ ] **Step 3: Add `CAMPAIGN_APP_API_URL` to `.env.example` (if it exists) or document it in `.env`**

Add this line to your `.env`:
```
CAMPAIGN_APP_API_URL=http://localhost:8000
```

- [ ] **Step 4: Verify in browser**

Navigate to "Campañas". Create a campaign, add plans, upload the existing CSV, verify clients appear. Change campaign estado to "activa" and send to 1 client — verify the `/campaign` endpoint is called (check FastAPI logs).

- [ ] **Step 5: Commit**

```bash
git add campaign_app/pages/3_Campanas.py
git commit -m "feat: Campanas page with configuration, client management, and batch dispatch"
```

---

## Task 11: Seguimiento page and IA placeholder

**Files:** `campaign_app/pages/4_Seguimiento.py`, `campaign_app/pages/5_Crear_desde_imagen.py`

- [ ] **Step 1: Write `campaign_app/pages/4_Seguimiento.py`**

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd
import plotly.express as px
import streamlit as st
from db.crud import get_all_campanas, get_campana_clientes

st.set_page_config(page_title="Seguimiento", layout="wide")
st.title("📊 Seguimiento")

campanas = get_all_campanas()
if not campanas:
    st.info("No hay campañas registradas.")
    st.stop()

campana_sel = st.selectbox(
    "Campaña",
    campanas,
    format_func=lambda c: f"[{c.estado.upper()}] {c.nombre}",
)

clientes_cc = get_campana_clientes(campana_sel.id)

if not clientes_cc:
    st.info("Esta campaña no tiene clientes aún.")
    st.stop()

# Métricas
total = len(clientes_cc)
enviados = sum(1 for cc in clientes_cc if cc.estado_envio == "enviado")
en_conv  = sum(1 for cc in clientes_cc if cc.estado_interaccion == "en_conversacion")
conv     = sum(1 for cc in clientes_cc if cc.estado_interaccion == "convertido")
rech     = sum(1 for cc in clientes_cc if cc.estado_interaccion == "rechazado")

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Total clientes", total)
col2.metric("Enviados",       enviados)
col3.metric("En conversación", en_conv)
col4.metric("Convertidos",    conv)
col5.metric("Rechazados",     rech)

# Gráfica de estado de interacción
interaccion_counts = {}
for cc in clientes_cc:
    interaccion_counts[cc.estado_interaccion] = interaccion_counts.get(cc.estado_interaccion, 0) + 1

fig = px.pie(
    names=list(interaccion_counts.keys()),
    values=list(interaccion_counts.values()),
    title="Distribución de estado de interacción",
    color_discrete_sequence=px.colors.qualitative.Set2,
)
st.plotly_chart(fig, use_container_width=True)

# Tabla detallada
st.subheader("Detalle por cliente")
filtro = st.multiselect(
    "Filtrar por estado interacción",
    ["pendiente", "en_conversacion", "interesado", "convertido", "rechazado"],
    default=[],
)
rows = []
for cc in clientes_cc:
    if filtro and cc.estado_interaccion not in filtro:
        continue
    rows.append({
        "Línea":            cc.linea,
        "Envío":            cc.estado_envio,
        "Interacción":      cc.estado_interaccion,
        "Plan seleccionado": cc.plan_seleccionado or "—",
        "Turnos":           cc.num_turnos,
        "Folio":            cc.folio_contrato or "—",
        "Fecha envío":      cc.fecha_envio.strftime("%d/%m/%Y %H:%M") if cc.fecha_envio else "—",
        "Fecha selección":  cc.fecha_seleccion.strftime("%d/%m/%Y %H:%M") if cc.fecha_seleccion else "—",
    })

if rows:
    st.dataframe(pd.DataFrame(rows), use_container_width=True)
else:
    st.info("No hay clientes que coincidan con el filtro.")

# Historial de conversación (solo sesiones cerradas)
st.divider()
st.subheader("Historial de conversación (sesiones cerradas)")
cerradas = [cc for cc in clientes_cc if cc.historial_conversacion]
if not cerradas:
    st.info("No hay conversaciones cerradas con historial guardado todavía.")
else:
    sel_linea = st.selectbox("Cliente", [cc.linea for cc in cerradas])
    cc_sel = next(cc for cc in cerradas if cc.linea == sel_linea)
    for msg in cc_sel.historial_conversacion:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        with st.chat_message(role):
            st.write(content)
```

- [ ] **Step 2: Write `campaign_app/pages/5_Crear_desde_imagen.py`**

```python
import streamlit as st

st.set_page_config(page_title="Crear desde imagen", layout="wide")
st.title("🤖 Crear campaña desde imagen")

st.info(
    "**Próximamente:** análisis automático de imágenes para extraer configuración de campaña. "
    "Sube una imagen con los datos de la campaña (brief, PDF, captura de pantalla) "
    "y el sistema extraerá automáticamente nombre, planes, promoción y reglas de elegibilidad."
)

uploaded = st.file_uploader("Sube una imagen o PDF (función no disponible aún)", type=["png", "jpg", "jpeg", "pdf"], disabled=True)

st.divider()
st.caption("El hook de integración está preparado en este componente para cuando se defina la fuente de datos.")
```

- [ ] **Step 3: Verify both pages load without errors in the browser**

Navigate to "Seguimiento" — should show metrics and empty table with seed data. Navigate to "Crear desde imagen" — should show info box and disabled uploader.

- [ ] **Step 4: Commit**

```bash
git add campaign_app/pages/4_Seguimiento.py campaign_app/pages/5_Crear_desde_imagen.py
git commit -m "feat: Seguimiento page with metrics and charts, IA placeholder page"
```

---

## Task 12: Reni agent integration

**Files:** `main.py`

This task adds a call to `update_interaction()` (and optionally `close_session_snapshot()`) in `main.py` after `run_turn()` completes. The agent itself (`reni_agent.py`) does NOT change.

- [ ] **Step 1: Add the helper function and imports to `main.py`**

At the top of `main.py`, add after the existing imports:

```python
# Campaign traceability (campaign_app integration)
import sys as _sys
import os as _os
_sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), "campaign_app"))
try:
    from db.crud import find_active_campana_cliente, update_interaction, close_session_snapshot
    from db.database import init_db as _init_campaign_db
    _CAMPAIGN_DB_AVAILABLE = True
except ImportError:
    _CAMPAIGN_DB_AVAILABLE = False
```

- [ ] **Step 2: Add helper function `_maybe_update_campana_cliente` to `main.py`**

Add this function before the route handlers:

```python
def _stage_to_interaccion(stage: str, plan_selected: str | None) -> str:
    if stage == "END" and plan_selected:
        return "convertido"
    if stage == "END":
        return "rechazado"
    if stage in ("CONTRACT", "POST_SALE"):
        return "interesado"
    return "en_conversacion"


def _maybe_update_campana_cliente(session, history: list):
    if not _CAMPAIGN_DB_AVAILABLE:
        return
    try:
        cc = find_active_campana_cliente(session.phone_number)
        if not cc:
            return
        estado = _stage_to_interaccion(session.stage, session.plan_selected)
        update_interaction(
            campana_id=cc.campana_id,
            linea=session.phone_number,
            num_turnos=len(history) // 2,
            estado_interaccion=estado,
            plan_seleccionado=session.plan_selected,
            folio_contrato=session.contract_folio,
        )
        if session.stage == "END":
            from app.state.serializer import session_to_dict
            close_session_snapshot(
                campana_id=cc.campana_id,
                linea=session.phone_number,
                history=history,
                session_data=session_to_dict(session),
            )
    except Exception as e:
        logger.warning(f"[CAMPAIGN] update failed for {session.phone_number}: {e}")
```

- [ ] **Step 3: Call `_maybe_update_campana_cliente` in the `/chat` endpoint**

In the `chat()` function in `main.py`, after `save_session(...)` and before the `return ChatResponse(...)`, add:

```python
    _maybe_update_campana_cliente(session, updated_history)

    return ChatResponse(...)
```

- [ ] **Step 4: Call `_maybe_update_campana_cliente` in `_process_whatsapp_message`**

In `_process_whatsapp_message`, after `save_session(...)` and before `send_whatsapp_message(...)`, add:

```python
            _maybe_update_campana_cliente(session, updated_history)
            send_whatsapp_message(phone_number, response_text)
```

- [ ] **Step 5: Initialize campaign DB tables on startup**

In the `startup()` function in `main.py`, add:

```python
@app.on_event("startup")
def startup():
    init_db()
    if _CAMPAIGN_DB_AVAILABLE:
        try:
            _init_campaign_db()
            logger.info("Campaign DB tables initialized")
        except Exception as e:
            logger.warning(f"Campaign DB init failed: {e}")
    logger.info("ReniAgent iniciado — tablas PostgreSQL listas")
```

- [ ] **Step 6: Test the integration end-to-end**

1. Start the FastAPI server: `python -m uvicorn main:app --reload`
2. Start the Streamlit app: `streamlit run campaign_app/app.py`
3. In Streamlit: create a campaign → add a plan → add client `5511111111` from seed data → activate campaign → send
4. In the CLI: `python scripts/test_agent.py` → `/select 1` → send a few messages
5. Refresh the Seguimiento page — verify `num_turnos` increments and `estado_interaccion` updates

- [ ] **Step 7: Commit**

```bash
git add main.py
git commit -m "feat: update CampanaCliente after each run_turn for conversation traceability"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task |
|---|---|
| Streamlit multipágina | Tasks 7-11 |
| DB: Familia, Plan, Beneficio, Servicio, FAQ | Tasks 2-4 |
| DB: Promocion, Campana, CampanaPlan, Cliente, CampanaCliente | Tasks 2-4 |
| PK compuesta CampanaPlan y CampanaCliente | Task 2 (models) |
| gb_base=0 para ilimitado, tiene_cashback + cashback_porcentaje | Task 2 |
| FamiliaBeneficio y FamiliaServicio M2M | Task 2 |
| FAQ cascade delete en beneficio/servicio | Task 2 (test incluido) |
| Seed desde plans.py + CSV | Task 5 |
| Importar FAQs desde Markdown | Task 6 + Task 8 |
| Envío usando POST /campaign existente | Task 10 |
| Enviar a subconjunto sin reenviar a ya enviados | Task 10 |
| Seguimiento: métricas, gráfica, historial | Task 11 |
| Placeholder IA imagen | Task 11 |
| Trazabilidad: update_interaction + close_session_snapshot | Task 12 |
| conversation_sessions coexiste sin cambios | Tasks 12 (no toca persistence.py) |
| Badge de promoción vencida | Task 9 |
| Validación columnas CSV | Task 10 |
| JSON flexible en Promocion.configuracion | Tasks 4 (crud) + Task 9 |

All spec requirements covered. No TBDs or placeholders in code steps.
