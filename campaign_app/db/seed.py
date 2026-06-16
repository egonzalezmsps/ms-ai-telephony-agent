"""
Seed the campaign DB from the canonical plans.py catalog.
Idempotent: safe to re-run; uses get-or-create for every record.
"""
import sys
import os
import importlib.util

_here = os.path.dirname(os.path.abspath(__file__))
_campaign_app = os.path.normpath(os.path.join(_here, ".."))
_project_root = os.path.normpath(os.path.join(_here, "..", ".."))

if _campaign_app not in sys.path:
    sys.path.insert(0, _campaign_app)

from db.database import get_db, init_db
from db.models import Familia, Plan, Beneficio, Servicio

_plans_path = os.path.join(_project_root, "app", "catalog", "plans.py")
_spec = importlib.util.spec_from_file_location("plans", _plans_path)
catalog = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(catalog)


# ── Beneficios y Servicios — planes vigentes ──────────────────────────────────

_BENEFICIOS_LIBRE = [
    ("Apps ilimitadas", "Facebook, WhatsApp, Messenger, X, Instagram, Snapchat, Uber"),
    ("Llamadas y SMS ilimitados", "Minutos y mensajes sin límite a nivel nacional"),
]

_BENEFICIOS_ULTRA = [
    ("WhatsApp ilimitado", "WhatsApp sin consumo de datos"),
    ("Llamadas y SMS ilimitados", "Minutos y mensajes sin límite a nivel nacional"),
]

_SERVICIOS_LIBRE = [
    ("Claro Video", "Plataforma de streaming de entretenimiento", "suscripcion", "Incluido en el plan"),
    ("Claro Drive", "Almacenamiento en la nube", "acceso", "20 GB incluidos"),
]

_SERVICIOS_ULTRA = [
    ("Claro Video", "Plataforma de streaming de entretenimiento", "suscripcion", "Incluido en el plan"),
    ("Claro Drive", "Almacenamiento en la nube", "acceso", "20 GB incluidos"),
]

# ── Beneficios y Servicios — planes legacy ────────────────────────────────────
# Verificar y complementar desde documentación oficial si hay cambios.

_BENEFICIOS_TMSL = [
    ("Apps ilimitadas", "Facebook, WhatsApp, Messenger, X, Instagram, Snapchat, Uber"),
    ("Llamadas y SMS ilimitados", "Minutos y mensajes sin límite a nivel nacional"),
]

_BENEFICIOS_TELCEL_PLUS = [
    ("Apps ilimitadas", "Facebook, WhatsApp, Messenger, X, Instagram, Snapchat, Uber"),
    ("Llamadas y SMS ilimitados", "Minutos y mensajes sin límite a nivel nacional"),
]

_SERVICIOS_TMSL = [
    ("Claro Video", "Plataforma de streaming de entretenimiento", "suscripcion", "Incluido en el plan"),
]

_SERVICIOS_TELCEL_PLUS = []

# ── Planes legacy: nombre → (gb, familia) ────────────────────────────────────
# Fuente: LEGACY_PLANS_GB en plans.py. Precios omitidos (variaban por contrato).

_LEGACY_PLANES = {
    # Telcel Max Sin Límite — GB según número de plan (MB allowance original)
    "Telcel Max Sin Limite 1000":  (1.0,  "Telcel Max Sin Límite"),
    "Telcel Max Sin Limite 1500":  (1.5,  "Telcel Max Sin Límite"),
    "Telcel Max Sin Limite 2000":  (2.0,  "Telcel Max Sin Límite"),
    "Telcel Max Sin Limite 3000":  (3.0,  "Telcel Max Sin Límite"),
    "Telcel Max Sin Limite 5000":  (5.0,  "Telcel Max Sin Límite"),
    "Telcel Max Sin Limite 6000":  (7.0,  "Telcel Max Sin Límite"),
    "Telcel Max Sin Limite 6500":  (8.0,  "Telcel Max Sin Límite"),
    "Telcel Max Sin Limite 7000":  (10.0, "Telcel Max Sin Límite"),
    "Telcel Max Sin Limite 8000":  (11.0, "Telcel Max Sin Límite"),
    "Telcel Max Sin Limite 9000":  (13.0, "Telcel Max Sin Límite"),
    "Telcel Max Sin Limite 12000": (15.0, "Telcel Max Sin Límite"),
    "Telcel Max Sin Limite 20000": (20.0, "Telcel Max Sin Límite"),
    # Telcel Plus
    "Telcel Plus 1":    (3.0,  "Telcel Plus"),
    "Telcel Plus 1.5":  (3.5,  "Telcel Plus"),
    "Telcel Plus 2":    (4.0,  "Telcel Plus"),
    "Telcel Plus 3":    (6.0,  "Telcel Plus"),
    "Telcel Plus 4":    (10.0, "Telcel Plus"),
    "Telcel Plus 5":    (14.0, "Telcel Plus"),
    "Telcel Plus 6":    (18.0, "Telcel Plus"),
    "Telcel Plus 7":    (22.0, "Telcel Plus"),
    "Telcel Plus 8":    (26.0, "Telcel Plus"),
    "Telcel Plus 9":    (32.0, "Telcel Plus"),
    "Telcel Plus 12":   (45.0, "Telcel Plus"),
    "Telcel Plus 14":   (60.0, "Telcel Plus"),
    "Telcel Plus VIP":  (35.0, "Telcel Plus"),
}

_FAMILIA_BENEFICIOS = {
    "Telcel Libre":          _BENEFICIOS_LIBRE,
    "Telcel Ultra":          _BENEFICIOS_ULTRA,
    "Telcel Max Sin Límite": _BENEFICIOS_TMSL,
    "Telcel Plus":           _BENEFICIOS_TELCEL_PLUS,
}

_FAMILIA_SERVICIOS = {
    "Telcel Libre":          _SERVICIOS_LIBRE,
    "Telcel Ultra":          _SERVICIOS_ULTRA,
    "Telcel Max Sin Límite": _SERVICIOS_TMSL,
    "Telcel Plus":           _SERVICIOS_TELCEL_PLUS,
}

_LEGACY_FAMILIAS = {"Telcel Max Sin Límite", "Telcel Plus"}


def _get_or_create(db, model, filter_kwargs, create_kwargs=None):
    obj = db.query(model).filter_by(**filter_kwargs).first()
    if not obj:
        kwargs = {**filter_kwargs, **(create_kwargs or {})}
        obj = model(**kwargs)
        db.add(obj)
        db.flush()
    return obj


def run():
    init_db()

    with get_db() as db:
        # ── Familias ──────────────────────────────────────────────────────────
        all_family_names = (
            "Telcel Libre", "Telcel Ultra",
            "Telcel Max Sin Límite", "Telcel Plus",
        )
        familias: dict[str, Familia] = {}
        for nombre in all_family_names:
            es_leg = nombre in _LEGACY_FAMILIAS
            f = _get_or_create(
                db, Familia, {"nombre": nombre},
                {"descripcion": f"Familia de planes {nombre}"
                               + (" (legacy — referencia informativa)" if es_leg else "")},
            )
            familias[nombre] = f

        # ── Beneficios ────────────────────────────────────────────────────────
        for nombre_fam, bens in _FAMILIA_BENEFICIOS.items():
            familia = familias[nombre_fam]
            for nombre_ben, desc_ben in bens:
                b = _get_or_create(db, Beneficio, {"nombre": nombre_ben},
                                   {"descripcion": desc_ben, "activo": True})
                if b not in familia.beneficios:
                    familia.beneficios.append(b)

        # ── Servicios ─────────────────────────────────────────────────────────
        for nombre_fam, svcs in _FAMILIA_SERVICIOS.items():
            familia = familias[nombre_fam]
            for nombre_svc, desc_svc, tipo_acc, detalle in svcs:
                s = _get_or_create(db, Servicio, {"nombre": nombre_svc},
                                   {"descripcion": desc_svc, "tipo_acceso": tipo_acc,
                                    "detalle": detalle, "activo": True})
                if s not in familia.servicios:
                    familia.servicios.append(s)

        # ── Planes vigentes (Libre / Ultra) ───────────────────────────────────
        planes_seeded = 0
        for p in catalog.CATALOG:
            familia = familias[p.family]
            tiene_cashback = p.cashback_abierto > 0 or p.cashback_controlado > 0
            cashback_pct = (p.cashback_abierto / p.price_abierto * 100) if tiene_cashback else 0.0
            existing = db.query(Plan).filter_by(nombre=p.plan_id).first()
            if not existing:
                db.add(Plan(
                    familia_id=familia.id,
                    nombre=p.plan_id,
                    precio_abierto=p.price_abierto,
                    precio_controlado=p.price_controlado,
                    gb_base=p.gb_base,
                    tiene_cashback=tiene_cashback,
                    cashback_porcentaje=round(cashback_pct, 2),
                    activo=True,
                    es_legacy=False,
                ))
                planes_seeded += 1
            else:
                existing.precio_abierto = p.price_abierto
                existing.precio_controlado = p.price_controlado
                existing.gb_base = p.gb_base
                existing.tiene_cashback = tiene_cashback
                existing.cashback_porcentaje = round(cashback_pct, 2)
                if existing.es_legacy is None:
                    existing.es_legacy = False

        # ── Planes legacy ─────────────────────────────────────────────────────
        legacy_seeded = 0
        for nombre_plan, (gb, nombre_fam) in _LEGACY_PLANES.items():
            familia = familias[nombre_fam]
            existing = db.query(Plan).filter_by(nombre=nombre_plan).first()
            if not existing:
                db.add(Plan(
                    familia_id=familia.id,
                    nombre=nombre_plan,
                    precio_abierto=0.0,   # precio variable por contrato
                    precio_controlado=0.0,
                    gb_base=gb,
                    tiene_cashback=False,
                    cashback_porcentaje=0.0,
                    activo=False,   # no activable en este canal
                    es_legacy=True,
                ))
                legacy_seeded += 1
            else:
                existing.gb_base = gb
                existing.es_legacy = True
                existing.activo = False

        db.flush()

        familias_count = db.query(Familia).count()
        beneficios_count = db.query(Beneficio).count()
        servicios_count = db.query(Servicio).count()
        planes_vigentes = db.query(Plan).filter_by(es_legacy=False).count()
        planes_legacy = db.query(Plan).filter_by(es_legacy=True).count()

    print("Seed complete:")
    print(f"  Familias:        {familias_count}")
    print(f"  Beneficios:      {beneficios_count}")
    print(f"  Servicios:       {servicios_count}")
    print(f"  Planes vigentes: {planes_vigentes} ({planes_seeded} nuevos)")
    print(f"  Planes legacy:   {planes_legacy} ({legacy_seeded} nuevos)")


if __name__ == "__main__":
    run()
