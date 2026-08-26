"""
tools/prospect_loader.py

Carga perfiles de clientes desde el CSV y construye SessionState.
Soporta el comando /select N para pruebas locales.
"""

import csv
import os
from typing import List, Optional
from app.state.session import SessionState


# Ruta al CSV — relativa a la raíz del proyecto
CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "docs", "Masivo_clientes.csv")

# Mapeo de tiposuscripcion del CSV → modalidad del agente
MODALITY_MAP = {
    "POSTPAGO": "Abierto",
    "MIXTO": "Controlado",
}

# Mapeo de MB → GB para el consumo promedio
def _mb_to_gb(mb: float) -> float:
    return round(mb / 1024, 2)


def _build_usage_summary(row: dict) -> str:
    """
    Genera un resumen legible del perfil de consumo del cliente.
    Sin revelar datos crudos — conecta con hábitos positivos.
    """
    total_gb = _mb_to_gb(float(row.get("conmbtotal_promedio_3meses") or 0))
    whatsapp_gb = _mb_to_gb(float(row.get("conmbwhatsapp_prom3meses") or 0))
    youtube_gb = _mb_to_gb(float(row.get("conmbyoutube_prom3meses") or 0))
    redes_gb = _mb_to_gb(float(row.get("conmbredsoc_prom3meses") or 0))
    instagram_gb = _mb_to_gb(float(row.get("conmbinstagr_prom3meses") or 0))

    parts = []

    if total_gb > 0:
        if total_gb >= 20:
            parts.append("uso intensivo de datos")
        elif total_gb >= 8:
            parts.append("uso moderado-alto de datos")
        else:
            parts.append("uso moderado de datos")

    if youtube_gb > 1:
        parts.append("consume video streaming")
    if (redes_gb + instagram_gb) > 0.5:
        parts.append("activo en redes sociales")
    if whatsapp_gb > 0.3:
        parts.append("comunicación frecuente por WhatsApp")

    if not parts:
        return "perfil de uso estándar"

    return ", ".join(parts)


def load_prospects() -> List[dict]:
    """Carga todos los prospectos del CSV."""
    path = os.path.abspath(CSV_PATH)
    if not os.path.exists(path):
        return []

    prospects = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            prospects.append(row)
    return prospects


def build_session_from_row(row: dict) -> SessionState:
    """Construye un SessionState desde una fila del CSV."""
    nombre_raw = row.get("nombre", "Cliente").strip()
    apellidos = row.get("apellidos", "").strip()
    full_name = f"{nombre_raw} {apellidos}".strip()
    # Solo el primer nombre, en Title Case: "ANA GARCIA" → "Ana", "LUISA" → "Luisa"
    first_name = nombre_raw.split()[0].title() if nombre_raw else "Cliente"
    modality = MODALITY_MAP.get(row.get("tiposuscripcion", "POSTPAGO"), "Abierto")

    return SessionState(
        first_name=first_name,
        full_name=full_name,
        phone_number=str(row.get("linea", "")).strip(),
        current_plan_name=row.get("plan", "").strip().title(),
        current_cost=float(row.get("rentaplan") or 0),
        subscription_type=modality,
        has_promotion=True,
        usage_summary=_build_usage_summary(row),
    )


def _update_fields(linea: str, **campos) -> None:
    """Actualiza una o más columnas del cliente con esa línea en el CSV.
    Agrega la columna al encabezado si todavía no existe."""
    path = os.path.abspath(CSV_PATH)
    if not os.path.exists(path):
        return

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    for campo in campos:
        if campo not in fieldnames:
            fieldnames.append(campo)

    for row in rows:
        if row.get("linea") == linea:
            row.update(campos)

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _update_estado(linea: str, nuevo_estado: str) -> None:
    """Actualiza la columna 'estado' del cliente con esa línea en el CSV."""
    _update_fields(linea, estado=nuevo_estado)


def mark_as_changed(linea: str, plan_code: str) -> None:
    """Marca al cliente como 'CAMBIADO' y registra el plan_code activado
    en la columna 'nuevoplan' — se llama cuando el cambio de plan se
    confirma exitosamente (API de create_product respondió OK)."""
    _update_fields(linea, estado="CAMBIADO", nuevoplan=plan_code)


def get_prospect_list_text() -> str:
    """Genera el texto del listado de prospectos para el comando /list."""
    prospects = load_prospects()
    if not prospects:
        return "No se encontraron prospectos en el CSV."

    lines = ["Prospectos disponibles:\n"]
    for i, row in enumerate(prospects, 1):
        nombre = row.get("nombre", "?")
        plan = row.get("plan", "?").title()
        renta = row.get("rentaplan", "?")
        tipo = MODALITY_MAP.get(row.get("tiposuscripcion", ""), "?")
        lines.append(f"  {i:2}. {nombre} — {plan} — ${renta}/mes ({tipo})")

    lines.append(f"\nUsa /select N para cargar el perfil N.")
    return "\n".join(lines)


def select_prospect(n: int) -> Optional[SessionState]:
    """
    Carga el prospecto número N (base 1) del CSV.
    Retorna None si el índice está fuera de rango.

    Simula el envío de la invitación: marca la fila del cliente como
    'ENVIADO' en la columna 'estado' del CSV.
    """
    prospects = load_prospects()
    if not prospects or n < 1 or n > len(prospects):
        return None
    row = prospects[n - 1]
    _update_estado(row.get("linea", ""), "ENVIADO")
    return build_session_from_row(row)
