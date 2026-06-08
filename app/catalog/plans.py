"""
catalog/plans.py

Catálogo de planes Telcel — fuente de verdad única.
Espejo de docs/catalog/plans.md.
"""

from dataclasses import dataclass
from typing import List, Optional

PRICE_TOLERANCE_MXN = 1.0
PROMO_VIGENCIA = "30/05/2026"
PROMO_TERM_MONTHS = 24


@dataclass(frozen=True)
class Plan:
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


CATALOG: List[Plan] = [
    # ── Telcel Libre ─────────────────────────────────────────────────────────
    Plan("Telcel Libre 1",          "Telcel Libre",   249,  299,  4,   6.0,  12.45,  14.95, True,  False),
    Plan("Telcel Libre 2",          "Telcel Libre",   319,  369,  5,   7.5,  15.95,  18.45, True,  False),
    Plan("Telcel Libre 3",          "Telcel Libre",   399,  449,  6,   9.0,  39.90,  44.90, True,  False),
    Plan("Telcel Libre 4",          "Telcel Libre",   499,  549, 10,  15.0,  74.85,  82.35, True,  False),
    Plan("Telcel Libre 5",          "Telcel Libre",   599,  699, 20,  30.0,  89.85, 104.85, True,  False),
    Plan("Telcel Libre 6",          "Telcel Libre",   699,  799, 30,  45.0, 104.85, 119.85, True,  False),
    Plan("Telcel Libre 7",          "Telcel Libre",   799,  899, 40,  60.0, 119.85, 134.85, True,  False),
    Plan("Telcel Libre 9",          "Telcel Libre",   999, 1099, 45,  67.5, 149.85, 164.85, True,  False),
    Plan("Telcel Libre 12",         "Telcel Libre",  1299, 1399, 55,  82.5, 194.85, 209.85, True,  False),
    Plan("Telcel Libre VIP",        "Telcel Libre",  1499, 1599, 40,  60.0, 629.58, 671.58, True,  False),
    # ── Telcel Ultra ─────────────────────────────────────────────────────────
    Plan("Telcel Ultra 3",          "Telcel Ultra",   349,  399, 15,  15.0,   0.00,   0.00, False, False),
    Plan("Telcel Ultra 4",          "Telcel Ultra",   449,  499, 25,  25.0,   0.00,   0.00, False, False),
    Plan("Telcel Ultra 5",          "Telcel Ultra",   549,  599, 40,  40.0,   0.00,   0.00, False, False),
    Plan("Telcel Ultra 7",          "Telcel Ultra",   749,  799, 60,  60.0,   0.00,   0.00, False, False),
    Plan("Telcel Ultra 9",          "Telcel Ultra",   949,  999,100, 100.0,   0.00,   0.00, False, False),
    Plan("Telcel Ultra Ilimitado",  "Telcel Ultra",  1349, 1399,  0,   0.0,   0.00,   0.00, False, True),
]


FAMILY_BENEFITS = {
    "Telcel Libre": (
        "📱 Apps ilimitadas: Facebook, WhatsApp, Messenger, X, Instagram, Snapchat, Uber\n"
        "🎬 Claro Video (streaming)\n"
        "☁️ Claro Drive 20 GB en la nube\n"
        "🛒 Amazon Prime incluido\n"
        "💰 Cashback mensual Telcel\n"
        "📞 Minutos y SMS ilimitados"
    ),
    "Telcel Ultra": (
        "📱 WhatsApp ilimitado\n"
        "🎬 Claro Video (streaming)\n"
        "☁️ Claro Drive 20 GB en la nube\n"
        "🛒 Amazon Prime incluido\n"
        "📞 Minutos y SMS ilimitados"
    ),
}


def get_price(plan: Plan, modality: str) -> float:
    return plan.price_controlado if modality == "Controlado" else plan.price_abierto


def get_cashback(plan: Plan, modality: str) -> float:
    return plan.cashback_controlado if modality == "Controlado" else plan.cashback_abierto


def eligible_plans(current_cost: float, modality: str) -> List[Plan]:
    """Planes con precio >= renta actual (tolerancia $1)."""
    return [p for p in CATALOG if get_price(p, modality) >= current_cost - PRICE_TOLERANCE_MXN]


def recommend_plan(current_cost: float, modality: str) -> Optional[Plan]:
    """Plan similar: el elegible más barato (precio más cercano desde arriba)."""
    eligible = [p for p in CATALOG
                if get_price(p, modality) >= current_cost - PRICE_TOLERANCE_MXN
                and p.family == "Telcel Libre"]
    if not eligible:
        return None
    return min(eligible, key=lambda p: get_price(p, modality))


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
