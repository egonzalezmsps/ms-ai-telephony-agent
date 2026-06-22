import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import csv
import io
from datetime import datetime
import httpx
import streamlit as st
from dotenv import load_dotenv

from db import crud

# ── Mapeos CSV → modelo ───────────────────────────────────────────────────────
# El CSV de Telcel usa nombres de columna distintos al modelo de BD.
_CSV_COL_MAP = {
    "plan":                              "plan_actual_nombre",
    "tiposuscripcion":                   "tipo_suscripcion",
    "rentaplan":                         "renta_plan",
    "facturacion_promedio_3meses":       "facturacion_promedio",
    "conmbtotal_promedio_3meses":        "consumo_mb_total_prom",
    "conmbwhatsapp_prom3meses":          "consumo_mb_whatsapp_prom",
    "conmbredsoc_prom3meses":            "consumo_mb_redes_prom",
    "conmbyoutube_prom3meses":           "consumo_mb_youtube_prom",
    "conmbuber_prom3meses":              "consumo_mb_uber_prom",
    "conmbinstagr_prom3meses":           "consumo_mb_instagram_prom",
    "conmbotros_prom3meses":             "consumo_mb_otros_prom",
    "totalmb_nacexcedentes_prom3meses":  "excedentes_nac_mb_prom",
    "totalmb_intexcedentes_prom3meses":  "excedentes_int_mb_prom",
    "total_ingresos_nacexce_prom3meses": "ingresos_exc_nac_prom",
    "total_ingresos_intcexce_prom3meses":"ingresos_exc_int_prom",
}

_SUSCRIPCION_MAP = {
    "POSTPAGO": "Abierto",
    "MIXTO":    "Controlado",
}


def _normalize_csv_row(row: dict, valid_cols: set) -> dict:
    """Rename CSV columns to model names, map subscription values, keep only valid cols."""
    renamed = {}
    for k, v in row.items():
        model_key = _CSV_COL_MAP.get(k.lower(), k)
        renamed[model_key] = v
    # Map subscription type value
    if "tipo_suscripcion" in renamed:
        renamed["tipo_suscripcion"] = _SUSCRIPCION_MAP.get(
            renamed["tipo_suscripcion"].upper(), renamed["tipo_suscripcion"]
        )
    return {k: v for k, v in renamed.items() if k in valid_cols and v != ""}

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

st.set_page_config(page_title="Campañas", page_icon="📢", layout="wide")
st.title("📢 Campañas")

API_BASE = os.environ.get("CAMPAIGN_API_BASE", "http://localhost:8000")
API_KEY = os.environ.get("CAMPAIGN_API_KEY") or os.environ.get("API_KEY", "")

# ── Helpers ───────────────────────────────────────────────────────────────────

def _estado_badge(estado: str) -> str:
    colors = {
        "borrador": "🟡",
        "activa":   "🟢",
        "pausada":  "🟠",
        "cerrada":  "🔴",
    }
    return f"{colors.get(estado, '⚪')} {estado.capitalize()}"


def _send_campaign(campana_id: int, lineas: list[str]) -> dict:
    """Call POST /campaign/dispatch on the Reni FastAPI backend."""
    try:
        resp = httpx.post(
            f"{API_BASE}/campaign/dispatch",
            json={"campana_id": campana_id, "lineas": lineas},
            headers={"x-api-key": API_KEY},
            timeout=30,
        )
        if not resp.is_success:
            return {"error": f"HTTP {resp.status_code} — {resp.text}"}
        return resp.json()
    except Exception as e:
        return {"error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
# SELECTOR DE CAMPAÑA (sidebar)
# ═══════════════════════════════════════════════════════════════════════════════

campanas = crud.get_all_campanas()
campana_opts = {f"[{c.id}] {c.nombre}": c.id for c in campanas}

st.sidebar.header("Campaña activa")
if campana_opts:
    sel_label = st.sidebar.selectbox("Seleccionar campaña",
                                      ["— nueva —"] + list(campana_opts.keys()))
    campana_id = campana_opts.get(sel_label)
else:
    sel_label = "— nueva —"
    campana_id = None

# ═══════════════════════════════════════════════════════════════════════════════
# CREAR NUEVA CAMPAÑA
# ═══════════════════════════════════════════════════════════════════════════════

if sel_label == "— nueva —":
    st.subheader("Nueva campaña")
    with st.form("nueva_campana"):
        nombre = st.text_input("Nombre")
        desc = st.text_area("Descripción")
        col_vi, col_vf = st.columns(2)
        vi = col_vi.date_input("Fecha de inicio (opcional)", value=None)
        vf = col_vf.date_input("Fecha de finalización (opcional)", value=None)
        if st.form_submit_button("Crear campaña"):
            if not nombre:
                st.warning("El nombre es obligatorio.")
            else:
                vi_dt = datetime.combine(vi, datetime.min.time()) if vi else None
                vf_dt = datetime.combine(vf, datetime.min.time()) if vf else None
                c = crud.create_campana(nombre, desc, vi_dt, vf_dt)
                st.success(f"Campaña '{nombre}' creada (ID {c.id}).")
                st.rerun()
    st.stop()

# ═══════════════════════════════════════════════════════════════════════════════
# PANEL DE CAMPAÑA SELECCIONADA
# ═══════════════════════════════════════════════════════════════════════════════

campana = next(c for c in campanas if c.id == campana_id)

col_title, col_estado = st.columns([4, 1])
col_title.subheader(f"{campana.nombre}")
col_estado.markdown(f"**{_estado_badge(campana.estado)}**")
st.caption(campana.descripcion or "")

# Estado transitions
allowed_states = ["borrador", "activa", "pausada", "cerrada"]
col_e1, col_e2, col_e3 = st.columns([3, 1, 1])
new_estado = col_e1.selectbox("Cambiar estado",
                               allowed_states,
                               index=allowed_states.index(campana.estado))
if col_e2.button("Aplicar"):
    crud.update_campana(campana_id, estado=new_estado)
    st.success(f"Estado actualizado a '{new_estado}'.")
    st.rerun()

_del_key = f"del_confirm_{campana_id}"
if col_e3.button("🗑️ Eliminar", type="secondary"):
    st.session_state[_del_key] = True

if st.session_state.get(_del_key):
    st.warning(f"¿Eliminar la campaña **{campana.nombre}** y todos sus datos? Esta acción no se puede deshacer.")
    col_yes, col_no, _ = st.columns([1, 1, 6])
    if col_yes.button("Sí, eliminar", type="primary"):
        crud.delete_campana(campana_id)
        del st.session_state[_del_key]
        st.success("Campaña eliminada.")
        st.rerun()
    if col_no.button("Cancelar"):
        del st.session_state[_del_key]
        st.rerun()

st.divider()

tab_planes, tab_clientes, tab_envio = st.tabs(["Planes", "Clientes", "Envío"])


# ── Tab: Planes ───────────────────────────────────────────────────────────────

with tab_planes:
    st.subheader("Planes de la campaña")

    campana_planes = crud.get_campana_planes(campana_id)
    plan_ids_in_campana = {cp.plan_id for cp in campana_planes}

    all_planes = crud.get_all_planes()
    all_promos = crud.get_all_promociones()
    promo_opts = {"(ninguna)": None} | {p.nombre: p.id for p in all_promos if p.activo}

    if campana_planes:
        st.markdown("**Planes actuales:**")
        for cp in campana_planes:
            plan = next((p for p in all_planes if p.id == cp.plan_id), None)
            if not plan:
                continue
            promo_name = next((p.nombre for p in all_promos if p.id == cp.promocion_id), "—")
            col_p, col_rm = st.columns([5, 1])
            col_p.markdown(f"- **{plan.nombre}** · Promo: {promo_name}")
            if col_rm.button("Quitar", key=f"rm_plan_{campana_id}_{plan.id}"):
                crud.remove_plan_from_campana(campana_id, plan.id)
                st.rerun()
    else:
        st.info("No hay planes asignados aún.")

    st.markdown("**Agregar planes:**")
    available = [p for p in all_planes if p.id not in plan_ids_in_campana and p.activo]

    add_tab_ind, add_tab_fam = st.tabs(["Plan individual", "Familia completa"])

    with add_tab_ind:
        if available:
            plan_opts = {p.nombre: p.id for p in available}
            col_ps, col_prom, col_add = st.columns([3, 3, 1])
            plan_sel = col_ps.selectbox("Plan", list(plan_opts.keys()), key="add_plan_sel")
            promo_sel = col_prom.selectbox("Promoción", list(promo_opts.keys()),
                                            key="add_plan_promo")
            if col_add.button("Agregar", key="btn_add_plan_ind"):
                crud.add_plan_to_campana(campana_id, plan_opts[plan_sel],
                                          promo_opts[promo_sel])
                st.success(f"Plan '{plan_sel}' agregado.")
                st.rerun()
        else:
            st.info("Todos los planes activos ya están en la campaña.")

    with add_tab_fam:
        all_familias = crud.get_all_familias()
        fam_disponibles = []
        for f in all_familias:
            planes_fam_disp = [p for p in f.planes if p.activo and p.id not in plan_ids_in_campana]
            if planes_fam_disp:
                fam_disponibles.append((f, planes_fam_disp))

        if fam_disponibles:
            fam_opts_map = {f.nombre: (f, ps) for f, ps in fam_disponibles}
            col_fs, col_fprom, col_fadd = st.columns([3, 3, 1])
            fam_sel = col_fs.selectbox("Familia", list(fam_opts_map.keys()), key="add_fam_sel")
            fprom_sel = col_fprom.selectbox("Promoción", list(promo_opts.keys()),
                                             key="add_fam_promo")
            _, planes_a_agregar = fam_opts_map[fam_sel]
            col_fs.caption(f"{len(planes_a_agregar)} planes se agregarán: "
                           f"{', '.join(p.nombre for p in planes_a_agregar)}")
            if col_fadd.button("Agregar", key="btn_add_plan_fam"):
                for p in planes_a_agregar:
                    crud.add_plan_to_campana(campana_id, p.id, promo_opts[fprom_sel])
                st.success(f"{len(planes_a_agregar)} planes de '{fam_sel}' agregados.")
                st.rerun()
        else:
            st.info("Todos los planes de todas las familias ya están en la campaña.")


# ── Tab: Clientes ─────────────────────────────────────────────────────────────

with tab_clientes:
    import pandas as pd

    st.subheader("Clientes de la campaña")

    campana_clientes = crud.get_campana_clientes(campana_id)
    lineas_en_campana = {cc.linea for cc in campana_clientes}

    # ── Métricas ──────────────────────────────────────────────────────────────
    col_tot, col_pend, col_env, col_fall = st.columns(4)
    col_tot.metric("Total", len(campana_clientes))
    col_pend.metric("Pendientes",
                    sum(1 for cc in campana_clientes if cc.estado_envio == "pendiente"))
    col_env.metric("Enviados",
                   sum(1 for cc in campana_clientes if cc.estado_envio == "enviado"))
    col_fall.metric("Fallidos",
                    sum(1 for cc in campana_clientes if cc.estado_envio == "fallido"))

    # ── Tabla de clientes ─────────────────────────────────────────────────────
    if campana_clientes:
        _ESTADO_ICON = {"pendiente": "🕐", "enviado": "✅", "fallido": "❌"}
        tabla = []
        for cc in campana_clientes:
            c = cc.cliente
            nombre_completo = " ".join(filter(None, [c.nombre, c.apellidos])) or "—"
            tabla.append({
                "Línea":       cc.linea,
                "Nombre":      nombre_completo,
                "Plan actual": c.plan_actual_nombre or "—",
                "Tipo":        c.tipo_suscripcion or "—",
                "Renta":       f"${c.renta_plan:.0f}" if c.renta_plan else "—",
                "Envío":       f"{_ESTADO_ICON.get(cc.estado_envio, '')} {cc.estado_envio}",
                "Interacción": cc.estado_interaccion or "—",
            })
        st.dataframe(pd.DataFrame(tabla), use_container_width=True, hide_index=True)
    else:
        st.info("No hay clientes en esta campaña aún.")

    st.divider()

    # ── Cargar CSV ────────────────────────────────────────────────────────────
    with st.expander("📂 Cargar lista CSV"):
        st.caption("El CSV debe tener al menos la columna `linea`. Columnas opcionales: nombre, "
                   "apellidos, plan_actual_nombre, tipo_suscripcion, renta_plan, etc.")
        uploaded = st.file_uploader("Subir CSV", type=["csv"], key="csv_upload")
        if uploaded:
            content = uploaded.read().decode("utf-8-sig")
            reader = csv.DictReader(io.StringIO(content))
            rows = list(reader)
            if not rows or "linea" not in rows[0]:
                st.error("El CSV no tiene la columna 'linea'.")
            else:
                nuevas = [r["linea"] for r in rows if r["linea"] not in lineas_en_campana]
                st.write(f"{len(rows)} filas leídas · {len(nuevas)} líneas nuevas a agregar.")

                if st.button("Importar clientes"):
                    _numeric = {
                        "renta_plan", "facturacion_promedio",
                        "consumo_mb_total_prom", "consumo_mb_whatsapp_prom",
                        "consumo_mb_redes_prom", "consumo_mb_youtube_prom",
                        "consumo_mb_uber_prom", "consumo_mb_instagram_prom",
                        "consumo_mb_otros_prom", "excedentes_nac_mb_prom",
                        "excedentes_int_mb_prom", "ingresos_exc_nac_prom",
                        "ingresos_exc_int_prom",
                    }
                    from db.models import Cliente as ClienteModel
                    valid_cols = {c.name for c in ClienteModel.__table__.columns}
                    cleaned = []
                    for row in rows:
                        data = _normalize_csv_row(row, valid_cols)
                        for f in _numeric:
                            if f in data:
                                try:
                                    data[f] = float(str(data[f]).replace(",", "."))
                                except ValueError:
                                    del data[f]
                        cleaned.append(data)
                    crud.bulk_upsert_clientes(cleaned)
                    crud.add_clientes_to_campana(campana_id,
                                                  [r["linea"] for r in cleaned])
                    st.success(f"{len(cleaned)} clientes importados.")
                    st.rerun()

    # ── Agregar individual ────────────────────────────────────────────────────
    with st.expander("➕ Agregar línea individual"):
        with st.form("add_linea"):
            col_l, col_n, col_a = st.columns(3)
            linea = col_l.text_input("Número de línea *")
            nombre = col_n.text_input("Nombre")
            apellidos = col_a.text_input("Apellidos")

            col_plan, col_tipo, col_renta = st.columns(3)
            plan_actual = col_plan.text_input("Plan actual (nombre)",
                                              help="Nombre del plan legacy que tiene el cliente")
            tipo_susc = col_tipo.selectbox("Tipo de suscripción",
                                           ["", "Abierto", "Controlado"],
                                           help="Modalidad del plan actual")
            renta = col_renta.number_input("Renta mensual actual ($)",
                                           min_value=0.0, value=0.0,
                                           help="Requerido para calcular planes elegibles")

            if st.form_submit_button("Agregar"):
                if not linea:
                    st.warning("El número de línea es obligatorio.")
                else:
                    data = {"linea": linea}
                    if nombre:      data["nombre"] = nombre
                    if apellidos:   data["apellidos"] = apellidos
                    if plan_actual: data["plan_actual_nombre"] = plan_actual
                    if tipo_susc:   data["tipo_suscripcion"] = tipo_susc
                    if renta > 0:   data["renta_plan"] = renta
                    crud.upsert_cliente(data)
                    crud.add_clientes_to_campana(campana_id, [linea])
                    st.success(f"Línea {linea} agregada.")
                    st.rerun()


# ── Tab: Envío ────────────────────────────────────────────────────────────────

with tab_envio:
    import pandas as pd

    st.subheader("Envío")

    pendientes = crud.get_campana_clientes_pendientes(campana_id)

    if not pendientes:
        st.success("No hay clientes pendientes de envío.")
    else:
        _pend_map = {cc.linea: cc for cc in pendientes}

        # Inicializar checkboxes en session_state (todos seleccionados por defecto)
        for cc in pendientes:
            key = f"chk_{campana_id}_{cc.linea}"
            if key not in st.session_state:
                st.session_state[key] = True

        # Botones de selección masiva
        col_all, col_none, _ = st.columns([1, 1, 6])
        if col_all.button("Seleccionar todos"):
            for cc in pendientes:
                st.session_state[f"chk_{campana_id}_{cc.linea}"] = True
            st.rerun()
        if col_none.button("Ninguno"):
            for cc in pendientes:
                st.session_state[f"chk_{campana_id}_{cc.linea}"] = False
            st.rerun()

        # Cabecera de tabla
        h0, h1, h2, h3, h4, h5, h6 = st.columns([0.4, 1.5, 2, 2.5, 1.2, 1, 1])
        h1.markdown("**Línea**")
        h2.markdown("**Nombre**")
        h3.markdown("**Plan actual**")
        h4.markdown("**Tipo**")
        h5.markdown("**Renta**")
        h6.markdown("**Estado**")

        # Filas con checkbox individual
        lineas_sel = []
        for cc in pendientes:
            c = _pend_map[cc.linea].cliente
            nombre = " ".join(filter(None, [c.nombre, c.apellidos])) or "—"
            chk_key = f"chk_{campana_id}_{cc.linea}"
            estado_icon = "🔴 Fallido" if cc.estado_envio == "fallido" else "🕐 Pendiente"
            c0, c1, c2, c3, c4, c5, c6 = st.columns([0.4, 1.5, 2, 2.5, 1.2, 1, 1])
            checked = c0.checkbox("", key=chk_key, label_visibility="collapsed")
            c1.write(cc.linea)
            c2.write(nombre)
            c3.write(c.plan_actual_nombre or "—")
            c4.write(c.tipo_suscripcion or "—")
            c5.write(f"${c.renta_plan:.0f}" if c.renta_plan else "—")
            c6.write(estado_icon)
            if checked:
                lineas_sel.append(cc.linea)

        st.caption(f"{len(lineas_sel)} de {len(pendientes)} clientes seleccionados")

        if st.button("📤 Enviar a seleccionados",
                     disabled=not lineas_sel or campana.estado != "activa"):
            with st.spinner(f"Enviando a {len(lineas_sel)} clientes..."):
                result = _send_campaign(campana_id, lineas_sel)
            st.session_state[f"send_result_{campana_id}"] = result
            st.rerun()

        if campana.estado != "activa":
            st.caption("Activa la campaña para habilitar el envío.")

    # ── Resultado del último envío ─────────────────────────────────────────────
    result_key = f"send_result_{campana_id}"
    if result_key in st.session_state:
        res = st.session_state[result_key]
        st.divider()
        st.markdown("**Resultado del último envío**")

        if "error" in res:
            st.error(f"Error de conexión: {res['error']}")
        else:
            sent  = res.get("sent", [])
            failed = res.get("failed", [])
            col_s, col_f = st.columns(2)
            col_s.metric("✅ Enviados", len(sent))
            col_f.metric("❌ Fallidos", len(failed))

            if failed:
                st.markdown("**Detalle de fallidos:**")
                for f in failed:
                    linea_f = f.get("linea", "?") if isinstance(f, dict) else f
                    reason  = f.get("reason", "—")  if isinstance(f, dict) else "—"
                    st.caption(f"• `{linea_f}` — {reason}")

        if st.button("Cerrar resultados", key=f"close_result_{campana_id}"):
            del st.session_state[result_key]
            st.rerun()
