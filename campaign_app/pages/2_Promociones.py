import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
from datetime import datetime
import streamlit as st
from db import crud

st.set_page_config(page_title="Promociones", page_icon="🎁", layout="wide")
st.title("🎁 Promociones")

# ── Schema de configuración ───────────────────────────────────────────────────
# La configuración se almacena como JSON con esta estructura fija:
#   {"tipo": str, "valor": float, "meses_vigencia": int}
#
# El agente recibe este JSON cuando un plan de la campaña tiene esta promoción
# asignada. Lo usa para enriquecer el mensaje de campaña y la conversación.

_TIPOS = {
    "gb_extra":            "GB extra sobre el plan",
    "descuento_porcentaje":"Descuento en precio (%)",
    "descuento_monto":     "Descuento en precio ($)",
    "meses_gratis":        "Meses sin costo",
    "informativa":         "Solo informativa (sin beneficio numérico)",
}

_TIPO_LABELS = {v: k for k, v in _TIPOS.items()}
_TIPO_OPTIONS = list(_TIPOS.values())


_GB_UNIDAD_OPTIONS = ["Porcentaje (%)", "Cantidad absoluta (GB)"]
_GB_UNIDAD_MAP = {"porcentaje": "Porcentaje (%)", "absoluto": "Cantidad absoluta (GB)"}
_GB_UNIDAD_KEY = {"Porcentaje (%)": "porcentaje", "Cantidad absoluta (GB)": "absoluto"}


def _cfg_to_fields(cfg: dict) -> tuple[str, float, int, str]:
    """Parse stored JSON → (tipo_label, valor, meses, gb_unidad)."""
    tipo_key = cfg.get("tipo", "informativa")
    tipo_label = _TIPOS.get(tipo_key, _TIPO_OPTIONS[-1])
    valor = float(cfg.get("valor", 0))
    meses = int(cfg.get("meses_vigencia", 0))
    gb_unidad = cfg.get("unidad", "porcentaje")
    return tipo_label, valor, meses, gb_unidad


def _fields_to_cfg(tipo_label: str, valor: float, meses: int,
                   gb_unidad: str = "porcentaje") -> dict:
    tipo_key = _TIPO_LABELS.get(tipo_label, "informativa")
    cfg: dict = {"tipo": tipo_key}
    if tipo_key == "gb_extra":
        cfg["valor"] = valor
        cfg["unidad"] = gb_unidad
    elif tipo_key != "informativa":
        cfg["valor"] = valor
    if meses > 0:
        cfg["meses_vigencia"] = meses
    return cfg


def _beneficio_preview(cfg: dict) -> str:
    tipo = cfg.get("tipo", "informativa")
    valor = cfg.get("valor", 0)
    meses = cfg.get("meses_vigencia", 0)
    unidad = cfg.get("unidad", "porcentaje")
    sufijo = f" durante {meses} mes{'es' if meses != 1 else ''}" if meses else ""
    if tipo == "gb_extra":
        if unidad == "porcentaje":
            return f"{valor:g}% más GB{sufijo}"
        return f"{valor:g} GB extra{sufijo}"
    if tipo == "descuento_porcentaje":
        return f"{valor:g}% de descuento{sufijo}"
    if tipo == "descuento_monto":
        return f"\\${valor:g} de descuento{sufijo}"
    if tipo == "meses_gratis":
        return f"{int(valor)} mes{'es' if valor != 1 else ''} sin costo"
    return "Solo informativa"


def _promo_form_fields(prefix: str, cfg: dict):
    """Renders benefit fields. Returns (tipo_label, valor, meses, gb_unidad)."""
    tipo_label, valor_default, meses_default, gb_unidad_default = _cfg_to_fields(cfg)

    tipo_sel = st.selectbox(
        "Tipo de beneficio",
        _TIPO_OPTIONS,
        index=_TIPO_OPTIONS.index(tipo_label),
        key=f"{prefix}_tipo",
        help="Define qué ofrece la promoción. El agente usa esto para personalizar el mensaje.",
    )
    tipo_key = _TIPO_LABELS[tipo_sel]

    col_v, col_m = st.columns(2)
    gb_unidad = "porcentaje"

    if tipo_key == "gb_extra":
        unidad_sel = st.radio(
            "El valor es:",
            _GB_UNIDAD_OPTIONS,
            index=0 if gb_unidad_default == "porcentaje" else 1,
            horizontal=True,
            key=f"{prefix}_unidad",
        )
        gb_unidad = _GB_UNIDAD_KEY[unidad_sel]
        if gb_unidad == "porcentaje":
            valor = col_v.number_input(
                "GB adicionales (%)",
                min_value=0.0, max_value=500.0, value=float(valor_default), step=5.0,
                key=f"{prefix}_valor",
                help="Ej: 50 = el cliente recibe 50% más GB (plan de 10 GB → 15 GB).",
            )
        else:
            valor = col_v.number_input(
                "GB adicionales (cantidad)",
                min_value=0.0, value=float(valor_default), step=1.0,
                key=f"{prefix}_valor",
                help="Ej: 10 = el cliente recibe 10 GB extra sobre los del plan.",
            )
        meses = col_m.number_input("Meses de vigencia del bono (0 = toda la vida del plan)",
                                    min_value=0, value=meses_default,
                                    key=f"{prefix}_meses")
    elif tipo_key == "descuento_porcentaje":
        valor = col_v.number_input("Descuento (%)", min_value=0.0, max_value=100.0,
                                   value=float(valor_default), step=1.0,
                                   key=f"{prefix}_valor")
        meses = col_m.number_input("Meses con descuento (0 = permanente)",
                                    min_value=0, value=meses_default,
                                    key=f"{prefix}_meses")
    elif tipo_key == "descuento_monto":
        valor = col_v.number_input("Descuento ($)", min_value=0.0,
                                   value=float(valor_default), step=10.0,
                                   key=f"{prefix}_valor")
        meses = col_m.number_input("Meses con descuento (0 = permanente)",
                                    min_value=0, value=meses_default,
                                    key=f"{prefix}_meses")
    elif tipo_key == "meses_gratis":
        valor = col_v.number_input("Meses sin costo", min_value=1.0,
                                   value=max(float(valor_default), 1.0), step=1.0,
                                   key=f"{prefix}_valor")
        meses = 0
        col_m.empty()
    else:  # informativa
        valor = 0.0
        meses = 0
        st.caption("La promoción es solo un nombre/etiqueta. No agrega beneficio numérico.")

    return tipo_sel, valor, int(meses), gb_unidad


# ═══════════════════════════════════════════════════════════════════════════════
# LISTA DE PROMOCIONES
# ═══════════════════════════════════════════════════════════════════════════════

promociones = crud.get_all_promociones()

if promociones:
    for promo in promociones:
        estado = "✅ Activa" if promo.activo else "⛔ Inactiva"
        vigencia = (f"{promo.vigencia_inicio.strftime('%d/%m/%Y')} – "
                    f"{promo.vigencia_fin.strftime('%d/%m/%Y')}")
        cfg_actual = promo.configuracion or {}
        preview = _beneficio_preview(cfg_actual)

        with st.expander(f"{estado} **{promo.nombre}** · {vigencia} · {preview}"):
            st.caption(promo.descripcion or "Sin descripción")

            cols = st.columns([2, 2])
            new_nombre = cols[0].text_input("Nombre", value=promo.nombre,
                                             key=f"pr_nom_{promo.id}")
            new_desc = cols[1].text_area("Descripción", value=promo.descripcion or "",
                                          key=f"pr_desc_{promo.id}")

            col_vi, col_vf = st.columns(2)
            new_vi = col_vi.date_input("Fecha de inicio",
                                        value=promo.vigencia_inicio.date(),
                                        key=f"pr_vi_{promo.id}")
            new_vf = col_vf.date_input("Fecha de finalización",
                                        value=promo.vigencia_fin.date(),
                                        key=f"pr_vf_{promo.id}")

            new_cond = st.text_area(
                "Condición de elegibilidad",
                value=promo.condicion or "",
                key=f"pr_cond_{promo.id}",
                help="Texto libre que describe quién aplica (ej. 'Solo clientes con renta > $399'). "
                     "El agente lo recibe en el contexto de la campaña.",
            )

            st.markdown("**Beneficio**")
            tipo_sel, valor_sel, meses_sel, unidad_sel = _promo_form_fields(
                f"pr_{promo.id}", cfg_actual
            )
            new_cfg = _fields_to_cfg(tipo_sel, valor_sel, meses_sel, unidad_sel)

            st.info(f"El agente recibirá: **{_beneficio_preview(new_cfg)}**  \n"
                    f"JSON almacenado: `{json.dumps(new_cfg, ensure_ascii=False)}`")

            col_save, col_tog, col_del = st.columns(3)
            if col_save.button("Guardar", key=f"pr_save_{promo.id}"):
                crud.update_promocion(
                    promo.id,
                    nombre=new_nombre,
                    descripcion=new_desc,
                    vigencia_inicio=datetime.combine(new_vi, datetime.min.time()),
                    vigencia_fin=datetime.combine(new_vf, datetime.min.time()),
                    condicion=new_cond,
                    configuracion=new_cfg,
                )
                st.success("Guardado")
                st.rerun()

            if col_tog.button("Activar/Desactivar", key=f"pr_tog_{promo.id}"):
                crud.toggle_promocion_activo(promo.id)
                st.rerun()

            confirm_key = f"pr_del_confirm_{promo.id}"
            if st.session_state.get(confirm_key):
                st.warning(f"¿Eliminar **{promo.nombre}**? Esta acción no se puede deshacer.")
                c1, c2 = st.columns(2)
                if c1.button("Sí, eliminar", key=f"pr_del_yes_{promo.id}", type="primary"):
                    crud.delete_promocion(promo.id)
                    st.session_state.pop(confirm_key, None)
                    st.rerun()
                if c2.button("Cancelar", key=f"pr_del_no_{promo.id}"):
                    st.session_state.pop(confirm_key, None)
                    st.rerun()
            else:
                if col_del.button("Eliminar", key=f"pr_del_{promo.id}"):
                    st.session_state[confirm_key] = True
                    st.rerun()
else:
    st.info("No hay promociones aún.")

# ═══════════════════════════════════════════════════════════════════════════════
# NUEVA PROMOCIÓN
# ═══════════════════════════════════════════════════════════════════════════════

st.divider()
st.subheader("Nueva promoción")

with st.form("nueva_promo"):
    nombre = st.text_input("Nombre")
    desc = st.text_area("Descripción")
    col_vi, col_vf = st.columns(2)
    vi = col_vi.date_input("Fecha de inicio")
    vf = col_vf.date_input("Fecha de finalización")
    condicion = st.text_area(
        "Condición de elegibilidad",
        help="Texto libre que describe quién aplica. El agente lo recibe en el contexto.",
    )

    st.markdown("**Beneficio**")
    st.caption(
        "Define qué ofrece la promoción. El agente inyecta esto en la conversación "
        "cuando el plan de la campaña tiene esta promoción asignada."
    )
    tipo_sel_n, valor_sel_n, meses_sel_n, unidad_sel_n = _promo_form_fields("nueva", {})

    if st.form_submit_button("Crear"):
        if not nombre:
            st.warning("El nombre es obligatorio.")
        elif vf < vi:
            st.warning("La fecha de finalización debe ser posterior a la de inicio.")
        else:
            cfg = _fields_to_cfg(tipo_sel_n, valor_sel_n, meses_sel_n, unidad_sel_n)
            crud.create_promocion(
                nombre=nombre,
                descripcion=desc,
                vigencia_inicio=datetime.combine(vi, datetime.min.time()),
                vigencia_fin=datetime.combine(vf, datetime.min.time()),
                configuracion=cfg,
                condicion=condicion,
            )
            st.success(f"Promoción '{nombre}' creada.")
            st.rerun()
