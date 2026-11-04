"""
catalog/plans.py

Catálogo de planes Telcel — fuente de verdad única.
Espejo de docs/catalog/plans.md.
"""

from dataclasses import dataclass
from typing import List, Optional

PRICE_EPSILON_MXN = 0.005  # margen puramente técnico (medio centavo) para errores de precisión float — NO es tolerancia de negocio
PROMO_VIGENCIA = "30/05/2026"
PROMO_TERM_MONTHS = 24


@dataclass(frozen=True)
class Plan:
    plan_code: str                 # código corto del plan para integraciones (ej. "TL5", "TU3")
    plan_id: str
    family: str                    # "Telcel Libre" | "Telcel Ultra"
    price_abierto: float
    price_controlado: float
    gb_base: float                 # 0 = ilimitado
    gb_promo: float                # igual a gb_base si no hay promo
    cashback_abierto: float
    cashback_controlado: float
    has_social_apps: bool          # True = Libre (7 apps), False = Ultra (solo WhatsApp)
    is_unlimited: bool             # True solo para Ultra Ilimitado
    calls_sms: str = "Llamadas y SMS ilimitados a México, EUA y Canadá"
    telcel_product_id_abierto: Optional[str] = None     # id de catálogo Telcel para CreateProductOrder (modalidad Abierto)
    telcel_product_id_controlado: Optional[str] = None  # id de catálogo Telcel para CreateProductOrder (modalidad Controlado)


CATALOG: List[Plan] = [
    # ── Telcel Libre ─────────────────────────────────────────────────────────
    Plan("TL1",    "Telcel Libre 1",          "Telcel Libre",   249,  299,  4,   6.0,  12.45,  14.95, True,  False, telcel_product_id_abierto="700116628", telcel_product_id_controlado="700116579"),
    Plan("TL2",    "Telcel Libre 2",          "Telcel Libre",   319,  369,  5,   7.5,  15.95,  18.45, True,  False, telcel_product_id_abierto="700116599", telcel_product_id_controlado="700116680"),
    Plan("TL3",    "Telcel Libre 3",          "Telcel Libre",   399,  449,  6,   9.0,  39.90,  44.90, True,  False, telcel_product_id_abierto="700116629", telcel_product_id_controlado="700116665"),
    Plan("TL4",    "Telcel Libre 4",          "Telcel Libre",   499,  549, 10,  15.0,  74.85,  82.35, True,  False, telcel_product_id_abierto="700116641", telcel_product_id_controlado="700116700"),
    Plan("TL5",    "Telcel Libre 5",          "Telcel Libre",   599,  699, 20,  30.0,  89.85, 104.85, True,  False, telcel_product_id_abierto="700116630", telcel_product_id_controlado="700116635"),
    Plan("TL6",    "Telcel Libre 6",          "Telcel Libre",   699,  799, 30,  45.0, 104.85, 119.85, True,  False, telcel_product_id_abierto="700116631", telcel_product_id_controlado="700116646"),
    Plan("TL7",    "Telcel Libre 7",          "Telcel Libre",   799,  899, 40,  60.0, 119.85, 134.85, True,  False, telcel_product_id_abierto="700116642", telcel_product_id_controlado="700116681"),
    Plan("TL9",    "Telcel Libre 9",          "Telcel Libre",   999, 1099, 45,  67.5, 149.85, 164.85, True,  False, telcel_product_id_abierto="700116643", telcel_product_id_controlado="700116666"),
    Plan("TL12",   "Telcel Libre 12",         "Telcel Libre",  1299, 1399, 55,  82.5, 194.85, 209.85, True,  False, telcel_product_id_abierto="700116577", telcel_product_id_controlado="700116647"),
    Plan("TLVIP",  "Telcel Libre VIP",        "Telcel Libre",  1499, 1599, 40,  60.0, 629.58, 671.58, True,  False, telcel_product_id_abierto="700116644", telcel_product_id_controlado="700116682"),
    # ── Telcel Ultra ─────────────────────────────────────────────────────────
    Plan("TU3",    "Telcel Ultra 3",          "Telcel Ultra",   349,  399, 15,  15.0,   0.00,   0.00, False, False, telcel_product_id_abierto="700090802", telcel_product_id_controlado="700090591"),
    Plan("TU4",    "Telcel Ultra 4",          "Telcel Ultra",   449,  499, 25,  25.0,   0.00,   0.00, False, False, telcel_product_id_abierto="700090677", telcel_product_id_controlado="700090638"),
    Plan("TU5",    "Telcel Ultra 5",          "Telcel Ultra",   549,  599, 40,  40.0,   0.00,   0.00, False, False, telcel_product_id_abierto="700089461", telcel_product_id_controlado="700090697"),
    Plan("TU7",    "Telcel Ultra 7",          "Telcel Ultra",   749,  799, 60,  60.0,   0.00,   0.00, False, False, telcel_product_id_abierto="700089404", telcel_product_id_controlado="700090592"),
    Plan("TU9",    "Telcel Ultra 9",          "Telcel Ultra",   949,  999,100, 100.0,   0.00,   0.00, False, False, telcel_product_id_abierto="700116664", telcel_product_id_controlado="700116652"),
    Plan("TUILIM", "Telcel Ultra Ilimitado",  "Telcel Ultra",  1349, 1399,  0,   0.0,   0.00,   0.00, False, True,  telcel_product_id_abierto="700116634", telcel_product_id_controlado="700116686"),
]


FAMILY_BENEFITS = {
    "Telcel Libre": (
        "📱 Apps ilimitadas: Facebook, WhatsApp, Messenger, X, Instagram, Snapchat, Uber\n"
        "🎬 Claro Video (streaming)\n"
        "☁️ Claro Drive 20 GB en la nube\n"
        "💰 Cashback mensual Telcel\n"
        "📞 Llamadas y SMS ilimitados a México, EUA y Canadá"
    ),
    "Telcel Ultra": (
        "📱 WhatsApp ilimitado\n"
        "🎬 Claro Video (streaming)\n"
        "☁️ Claro Drive 20 GB en la nube\n"
        "📞 Llamadas y SMS ilimitados a México, EUA y Canadá"
    ),
}


def get_price(plan: Plan, modality: str) -> float:
    return plan.price_controlado if modality == "Controlado" else plan.price_abierto


def get_cashback(plan: Plan, modality: str) -> float:
    return plan.cashback_controlado if modality == "Controlado" else plan.cashback_abierto


def get_product_id(plan: Plan, modality: str) -> Optional[str]:
    return plan.telcel_product_id_controlado if modality == "Controlado" else plan.telcel_product_id_abierto


def eligible_plans(current_cost: float, modality: str) -> List[Plan]:
    """Planes con precio >= renta actual (sin tolerancia de negocio)."""
    return [p for p in CATALOG if get_price(p, modality) >= current_cost - PRICE_EPSILON_MXN]


def recommend_plan(current_cost: float, modality: str) -> Optional[Plan]:
    """Plan con precio más cercano por encima de la renta actual.
    En empate de precio, Telcel Libre tiene prioridad sobre Telcel Ultra.
    """
    eligible = [p for p in CATALOG if get_price(p, modality) >= current_cost - PRICE_EPSILON_MXN]
    if not eligible:
        return None
    return min(eligible, key=lambda p: (get_price(p, modality), 0 if p.family == "Telcel Libre" else 1))


LEGACY_PLANS_GB: dict = {
    "TELCEL MAX SIN LIMITE 1000":  1.0,
    "TELCEL MAX SIN LIMITE 1500":  1.5,
    "TELCEL MAX SIN LIMITE 2000":  2.0,
    "TELCEL MAX SIN LIMITE 3000":  3.0,
    "TELCEL MAX SIN LIMITE 5000":  5.0,
    "TELCEL MAX SIN LIMITE 6000":  7.0,
    "TELCEL MAX SIN LIMITE 6500":  8.0,
    "TELCEL MAX SIN LIMITE 7000": 10.0,
    "TELCEL MAX SIN LIMITE 8000": 11.0,
    "TELCEL MAX SIN LIMITE 9000": 13.0,
    "TELCEL MAX SIN LIMITE 12000": 15.0,
    "TELCEL MAX SIN LIMITE 20000": 20.0,
    # Telcel Plus — nombre completo
    "TELCEL PLUS 1":   3.0,
    "TELCEL PLUS 1.5": 3.5,
    "TELCEL PLUS 2":   4.0,
    "TELCEL PLUS 3":   6.0,
    "TELCEL PLUS 4":  10.0,
    "TELCEL PLUS 5":  14.0,
    "TELCEL PLUS 6":  18.0,
    "TELCEL PLUS 7":  22.0,
    "TELCEL PLUS 8":  26.0,
    "TELCEL PLUS 9":  32.0,
    "TELCEL PLUS 12": 45.0,
    "TELCEL PLUS 14": 60.0,
    "TELCEL PLUS VIP": 35.0,
    # Telcel Plus — abreviación TP (variante CSV)
    "TP1":   3.0,
    "TP1.5": 3.5,
    "TP2":   4.0,
    "TP3":   6.0,
    "TP4":  10.0,
    "TP5":  14.0,
    "TP6":  18.0,
    "TP7":  22.0,
    "TP8":  26.0,
    "TP9":  32.0,
    "TP12": 45.0,
    "TP14": 60.0,
    "TPVIP": 35.0,
}


def get_legacy_gb(plan_name: str) -> Optional[float]:
    """Retorna los GB del plan legacy o None si no se encuentra.
    Normaliza tildes y mayúsculas para que 'Límite' y 'Limite' sean equivalentes.
    """
    import unicodedata

    def _norm(s: str) -> str:
        return "".join(
            c for c in unicodedata.normalize("NFD", s.strip().upper())
            if unicodedata.category(c) != "Mn"
        )

    key = _norm(plan_name)
    for k, v in LEGACY_PLANS_GB.items():
        if _norm(k) == key:
            return v
    return None


def find_plan(plan_id: str) -> Optional[Plan]:
    """Busca un plan por ID exacto o nombre parcial."""
    import unicodedata

    def norm(s: str) -> str:
        return "".join(
            c for c in unicodedata.normalize("NFD", s.strip().lower())
            if unicodedata.category(c) != "Mn"
        )

    pid = norm(plan_id)

    # Ignorar modalidad si viene incluida al final
    for suffix in [" controlado", " abierto"]:
        if pid.endswith(suffix):
            pid = pid[: -len(suffix)].strip()
            break

    for p in CATALOG:
        if norm(p.plan_id) == pid:
            return p
    for p in CATALOG:
        if norm(p.plan_id).replace("telcel ", "") == pid:
            return p
    return None


def format_plan_for_agent(plan: Plan, modality: str, has_promo: bool = True) -> str:
    """
    Genera el bloque de texto que el agente usa para presentar un plan.
    Formato optimizado para WhatsApp con negritas y emojis.
    """
    price = get_price(plan, modality)
    cashback = get_cashback(plan, modality)
    benefits = FAMILY_BENEFITS.get(plan.family, "")

    if plan.is_unlimited:
        gb_label = "Datos ilimitados (sujeto a PUJ)"
    elif has_promo and plan.gb_promo > plan.gb_base and plan.family == "Telcel Libre":
        extra = plan.gb_promo - plan.gb_base
        gb_label = f"{plan.gb_base:g} GB base + {extra:g} GB de promoción = {plan.gb_promo:g} GB totales"
    else:
        gb_label = f"{plan.gb_base:g} GB"

    lines = [
        f"*{plan.plan_id} {modality}*",
        f"💰 *${price:.0f}/mes*",
        f"📶 *{gb_label}*",
    ]

    if cashback > 0:
        lines.append(f"💰 Cashback: *${cashback:.2f}/mes*")

    lines.append("")
    lines.append("Beneficios incluidos:")
    lines.append(benefits)

    if has_promo and plan.gb_promo > plan.gb_base and plan.family == "Telcel Libre":
        lines.append(f"\n🎁 Promoción vigente hasta el {PROMO_VIGENCIA} · GB extra durante {PROMO_TERM_MONTHS} meses")

    return "\n".join(lines)


# ── Tabla de productos Telcel (código de oferta, nombre, precio) ─────────────
# Copia literal de la tabla entregada por Telcel. Independiente de CATALOG.
# Nota: 700090698 aparece en ULTRA CONTROLADO 4 y en ULTRA CONTROLADO ILIMITADO.

@dataclass(frozen=True)
class TelcelProduct:
    codigo: str
    nombre: str
    precio: float


TELCEL_PRODUCTS: List[TelcelProduct] = [
    TelcelProduct("700116628", "TELCEL LIBRE 1",                   249),
    TelcelProduct("700116599", "TELCEL LIBRE 2",                   319),
    TelcelProduct("700116629", "TELCEL LIBRE 3",                   399),
    TelcelProduct("700116641", "TELCEL LIBRE 4",                   499),
    TelcelProduct("700116630", "TELCEL LIBRE 5",                   599),
    TelcelProduct("700116631", "TELCEL LIBRE 6",                   699),
    TelcelProduct("700116642", "TELCEL LIBRE 7",                   799),
    TelcelProduct("700116643", "TELCEL LIBRE 9",                   999),
    TelcelProduct("700116577", "TELCEL LIBRE 12",                 1299),
    TelcelProduct("700116644", "TELCEL LIBRE VIP",                1499),
    TelcelProduct("700116579", "TELCEL LIBRE CONTROLADO 1",        299),
    TelcelProduct("700116680", "TELCEL LIBRE CONTROLADO 2",        369),
    TelcelProduct("700116665", "TELCEL LIBRE CONTROLADO 3",        449),
    TelcelProduct("700116700", "TELCEL LIBRE CONTROLADO 4",        549),
    TelcelProduct("700116635", "TELCEL LIBRE CONTROLADO 5",        699),
    TelcelProduct("700116646", "TELCEL LIBRE CONTROLADO 6",        799),
    TelcelProduct("700116681", "TELCEL LIBRE CONTROLADO 7",        899),
    TelcelProduct("700116666", "TELCEL LIBRE CONTROLADO 9",       1099),
    TelcelProduct("700116647", "TELCEL LIBRE CONTROLADO 12",      1399),
    TelcelProduct("700116682", "TELCEL LIBRE CONTROLADO VIP",     1599),
    TelcelProduct("700090802", "TELCEL ULTRA 3",                   349),
    TelcelProduct("700090677", "TELCEL ULTRA 4",                   449),
    TelcelProduct("700090678", "TELCEL ULTRA 5",                   549),
    TelcelProduct("700090679", "TELCEL ULTRA 7",                   749),
    TelcelProduct("700090680", "TELCEL ULTRA 9",                   999),
    TelcelProduct("700090697", "TELCEL ULTRA ILIMITADO",          1349),
    TelcelProduct("700090801", "TELCEL ULTRA CONTROLADO 3",        399),
    TelcelProduct("700090698", "TELCEL ULTRA CONTROLADO 4",        499),
    TelcelProduct("700090699", "TELCEL ULTRA CONTROLADO 5",        599),
    TelcelProduct("700090700", "TELCEL ULTRA CONTROLADO 7",        799),
    TelcelProduct("700090701", "TELCEL ULTRA CONTROLADO 9",       1049),
    TelcelProduct("700090698", "TELCEL ULTRA CONTROLADO ILIMITADO", 1399),
]


def get_telcel_product_by_name(nombre: str) -> Optional[TelcelProduct]:
    """Busca un producto por nombre exacto (sin importar mayúsculas/espacios extra)."""
    key = " ".join(nombre.upper().split())
    for p in TELCEL_PRODUCTS:
        if p.nombre == key:
            return p
    return None


def get_telcel_products_by_code(codigo: str) -> List[TelcelProduct]:
    """Productos con ese código de oferta (puede haber más de uno, ver nota de 700090698)."""
    codigo = codigo.strip()
    return [p for p in TELCEL_PRODUCTS if p.codigo == codigo]
