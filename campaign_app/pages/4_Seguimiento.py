import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import streamlit as st
from db import crud

st.set_page_config(page_title="Seguimiento", page_icon="📊", layout="wide")
st.title("📊 Seguimiento de campañas")

campanas = crud.get_all_campanas()
if not campanas:
    st.info("No hay campañas aún. Créalas en la sección Campañas.")
    st.stop()

campana_opts = {f"[{c.id}] {c.nombre}": c.id for c in campanas}
sel = st.selectbox("Campaña", list(campana_opts.keys()))
campana_id = campana_opts[sel]
campana = next(c for c in campanas if c.id == campana_id)

# ── Métricas resumen ──────────────────────────────────────────────────────────

clientes = crud.get_campana_clientes(campana_id)
total = len(clientes)

if not clientes:
    st.info("Esta campaña no tiene clientes aún.")
    st.stop()

enviados     = sum(1 for c in clientes if c.estado_envio == "enviado")
pendientes   = sum(1 for c in clientes if c.estado_envio == "pendiente")
fallidos     = sum(1 for c in clientes if c.estado_envio == "fallido")
conversando  = sum(1 for c in clientes if c.estado_interaccion == "en_conversacion")
contrataron  = sum(1 for c in clientes if c.estado_interaccion == "contratado")
rechazaron   = sum(1 for c in clientes if c.estado_interaccion == "rechazado")
sin_resp     = sum(1 for c in clientes if c.estado_interaccion == "sin_respuesta")

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total", total)
col2.metric("Enviados", enviados)
col3.metric("Pendientes", pendientes)
col4.metric("Fallidos", fallidos)

st.divider()

col5, col6, col7, col8 = st.columns(4)
col5.metric("En conversación", conversando)
col6.metric("Contrataron", contrataron)
col7.metric("Rechazaron", rechazaron)
col8.metric("Sin respuesta", sin_resp)

if total:
    pct = f"{contrataron / total * 100:.1f}%"
    st.caption(f"Tasa de conversión: **{pct}**")

# ── Tabla de clientes ─────────────────────────────────────────────────────────

st.subheader("Detalle por cliente")

# Filters
col_f1, col_f2, col_f3 = st.columns(3)
f_envio = col_f1.multiselect("Estado envío",
                               ["pendiente", "enviado", "fallido"],
                               default=["pendiente", "enviado", "fallido"])
f_interac = col_f2.multiselect("Estado interacción",
                                 ["pendiente", "en_conversacion", "contratado",
                                  "rechazado", "sin_respuesta"],
                                 default=["pendiente", "en_conversacion",
                                          "contratado", "rechazado", "sin_respuesta"])
f_buscar = col_f3.text_input("Buscar línea o plan")

filtered = [
    c for c in clientes
    if c.estado_envio in f_envio
    and c.estado_interaccion in f_interac
    and (not f_buscar or f_buscar in (c.linea or "") or f_buscar in (c.plan_seleccionado or ""))
]

st.caption(f"Mostrando {len(filtered)} de {total} clientes")

for cc in filtered:
    fecha_envio = cc.fecha_envio.strftime("%d/%m %H:%M") if cc.fecha_envio else "—"
    fecha_sel   = cc.fecha_seleccion.strftime("%d/%m") if cc.fecha_seleccion else "—"
    c = cc.cliente
    nombre = " ".join(filter(None, [c.nombre, c.apellidos])).title() if c else ""
    nombre_str = f" · {nombre}" if nombre else ""
    label = (
        f"📱 **{cc.linea}**{nombre_str} · "
        f"Envío: {cc.estado_envio} ({fecha_envio}) · "
        f"Interacción: {cc.estado_interaccion} · "
        f"Turnos: {cc.num_turnos}"
    )
    with st.expander(label):
        cols = st.columns(3)
        cols[0].markdown(f"**Plan seleccionado:** {cc.plan_seleccionado or '—'}")
        cols[1].markdown(f"**Fecha selección:** {fecha_sel}")
        cols[2].markdown(f"**Folio contrato:** {cc.folio_contrato or '—'}")

        if cc.historial_conversacion:
            with st.expander("Ver historial de conversación"):
                for msg in cc.historial_conversacion:
                    role = msg.get("role", "?")
                    content = msg.get("content", "")
                    if role == "user":
                        st.markdown(f"👤 **Cliente:** {content}")
                    else:
                        st.markdown(f"🤖 **Reni:** {content}")

        if cc.session_data_snapshot:
            with st.expander("Ver snapshot de sesión"):
                st.json(cc.session_data_snapshot)
