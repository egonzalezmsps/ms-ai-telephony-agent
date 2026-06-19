import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
from db import crud
from components.md_importer import parse_faq_md

st.set_page_config(page_title="Catálogo", page_icon="📋", layout="wide")
st.title("📋 Catálogo")

tab_fam, tab_plan, tab_ben, tab_svc, tab_faq = st.tabs(
    ["Familias", "Planes", "Beneficios", "Servicios", "FAQs"]
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _familia_options():
    return {f.nombre: f.id for f in crud.get_all_familias()}


def _beneficio_options():
    return {b.nombre: b.id for b in crud.get_all_beneficios()}


def _servicio_options():
    return {s.nombre: s.id for s in crud.get_all_servicios()}


# ═══════════════════════════════════════════════════════════════════════════════
# TAB: FAMILIAS
# ═══════════════════════════════════════════════════════════════════════════════
with tab_fam:
    st.subheader("Familias de planes")

    familias = crud.get_all_familias()
    if familias:
        for f in familias:
            with st.expander(f"**{f.nombre}**"):
                st.caption(f.descripcion or "Sin descripción")
                cols = st.columns([3, 1])
                new_desc = cols[0].text_input("Descripción", value=f.descripcion or "",
                                               key=f"fam_desc_{f.id}")
                if cols[1].button("Guardar", key=f"fam_save_{f.id}"):
                    crud.update_familia(f.id, descripcion=new_desc)
                    st.success("Guardado")
                    st.rerun()

                # Planes de esta familia (solo lectura — se asignan desde la tab Planes)
                st.markdown("**Planes de esta familia:**")
                if f.planes:
                    activos = [p for p in f.planes if p.activo]
                    inactivos = [p for p in f.planes if not p.activo]
                    for p in sorted(activos, key=lambda x: x.precio_abierto):
                        gb_label = "Ilimitado" if p.gb_base == 0 else f"{p.gb_base:g} GB"
                        st.markdown(f"✅ {p.nombre} — \\${p.precio_abierto:.0f}/\\${p.precio_controlado:.0f} · {gb_label}")
                    for p in sorted(inactivos, key=lambda x: x.precio_abierto):
                        gb_label = "Ilimitado" if p.gb_base == 0 else f"{p.gb_base:g} GB"
                        st.markdown(f"⛔ {p.nombre} — \\${p.precio_abierto:.0f}/\\${p.precio_controlado:.0f} · {gb_label}")
                else:
                    st.markdown("Sin planes aún.")

                st.divider()

                # Beneficios linked
                st.markdown("**Beneficios vinculados:**")
                all_bens = crud.get_all_beneficios()
                linked_bens = {b.id for b in f.beneficios}
                for b in all_bens:
                    checked = b.id in linked_bens
                    new_checked = st.checkbox(b.nombre, value=checked,
                                              key=f"fam_{f.id}_ben_{b.id}")
                    if new_checked != checked:
                        if new_checked:
                            crud.link_beneficio_to_familia(b.id, f.id)
                        else:
                            crud.unlink_beneficio_from_familia(b.id, f.id)
                        st.rerun()

                # Servicios linked
                st.markdown("**Servicios vinculados:**")
                all_svcs = crud.get_all_servicios()
                linked_svcs = {s.id for s in f.servicios}
                for s in all_svcs:
                    checked = s.id in linked_svcs
                    new_checked = st.checkbox(s.nombre, value=checked,
                                              key=f"fam_{f.id}_svc_{s.id}")
                    if new_checked != checked:
                        if new_checked:
                            crud.link_servicio_to_familia(s.id, f.id)
                        else:
                            crud.unlink_servicio_from_familia(s.id, f.id)
                        st.rerun()
    else:
        st.info("No hay familias aún.")

    st.divider()
    st.subheader("Agregar familia")
    with st.form("nueva_familia"):
        nombre = st.text_input("Nombre")
        desc = st.text_area("Descripción")
        if st.form_submit_button("Crear"):
            if nombre:
                crud.create_familia(nombre, desc)
                st.success(f"Familia '{nombre}' creada.")
                st.rerun()
            else:
                st.warning("El nombre es obligatorio.")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB: PLANES
# ═══════════════════════════════════════════════════════════════════════════════
with tab_plan:
    st.subheader("Planes")

    familias = crud.get_all_familias()
    fam_opts = {f.nombre: f.id for f in familias}

    planes = crud.get_all_planes()
    if planes:
        from itertools import groupby

        vigentes = [p for p in planes if not p.es_legacy]
        legacy   = [p for p in planes if p.es_legacy]

        def _render_plan_expander(p, editable: bool = True):
            gb_label = "Ilimitado" if p.gb_base == 0 else f"{p.gb_base:g} GB"
            if p.es_legacy:
                precio_str = "Precio según contrato"
                label = f"📦 {p.nombre} · {gb_label}"
            else:
                precio_str = f"\\${p.precio_abierto:.0f}/\\${p.precio_controlado:.0f}"
                label = f"{'✅' if p.activo else '⛔'} {p.nombre} — {precio_str} · {gb_label}"
            with st.expander(label):
                if p.es_legacy:
                    st.caption("Plan legacy — solo referencia informativa, no activable en este canal.")
                c1, c2, c3 = st.columns(3)
                if p.es_legacy:
                    c1.metric("GB", f"{p.gb_base:g}")
                    new_gb = c1.number_input("Actualizar GB", value=p.gb_base,
                                              min_value=0.0, key=f"p_gb_{p.id}")
                    if c2.button("Guardar GB", key=f"p_save_{p.id}"):
                        crud.update_plan(p.id, gb_base=new_gb)
                        st.success("Guardado")
                        st.rerun()
                else:
                    new_pa = c1.number_input("Precio Abierto", value=p.precio_abierto,
                                             min_value=0.0, key=f"p_pa_{p.id}")
                    new_pc = c2.number_input("Precio Controlado", value=p.precio_controlado,
                                             min_value=0.0, key=f"p_pc_{p.id}")
                    new_gb = c3.number_input("GB Base (0=ilimitado)", value=p.gb_base,
                                              min_value=0.0, key=f"p_gb_{p.id}")
                    c4, c5, c6 = st.columns(3)
                    new_cb = c4.checkbox("Tiene cashback", value=p.tiene_cashback,
                                          key=f"p_cb_{p.id}")
                    new_pct = c5.number_input("Cashback %", value=p.cashback_porcentaje,
                                               min_value=0.0, max_value=100.0,
                                               key=f"p_pct_{p.id}", disabled=not new_cb)
                    if c6.button("Guardar cambios", key=f"p_save_{p.id}"):
                        crud.update_plan(p.id, precio_abierto=new_pa,
                                         precio_controlado=new_pc, gb_base=new_gb,
                                         tiene_cashback=new_cb,
                                         cashback_porcentaje=new_pct if new_cb else 0.0)
                        st.success("Guardado")
                        st.rerun()
                    if st.button("Activar/Desactivar", key=f"p_tog_{p.id}"):
                        crud.toggle_plan_activo(p.id)
                        st.rerun()

        # Planes vigentes agrupados por familia
        key_fn = lambda p: (p.familia.nombre if p.familia else "—")
        for fam_name, grupo in groupby(vigentes, key=key_fn):
            st.markdown(f"### {fam_name}")
            for p in grupo:
                _render_plan_expander(p)

        # Planes legacy
        if legacy:
            st.divider()
            st.markdown("### 📦 Planes Legacy *(solo referencia — no activables)*")
            st.caption(
                "Planes de generaciones anteriores. Se usan para conocer los beneficios "
                "actuales del cliente y comparar con los planes vigentes."
            )
            for fam_name, grupo in groupby(legacy, key=key_fn):
                st.markdown(f"**{fam_name}**")
                for p in grupo:
                    _render_plan_expander(p)
    else:
        st.info("No hay planes aún.")

    st.divider()
    st.subheader("Agregar plan")
    with st.form("nuevo_plan"):
        if not fam_opts:
            st.warning("Crea al menos una familia primero.")
            st.form_submit_button("Crear", disabled=True)
        else:
            fam_sel = st.selectbox("Familia", list(fam_opts.keys()))
            nombre = st.text_input("Nombre del plan")
            c1, c2, c3 = st.columns(3)
            pa = c1.number_input("Precio Abierto", min_value=0.0)
            pc = c2.number_input("Precio Controlado", min_value=0.0)
            gb = c3.number_input("GB Base (0=ilimitado)", min_value=0.0)
            c4, c5 = st.columns(2)
            cb = c4.checkbox("Tiene cashback")
            pct = c5.number_input("Cashback %", min_value=0.0, max_value=100.0,
                                   disabled=not cb)
            if st.form_submit_button("Crear"):
                if nombre:
                    crud.create_plan(fam_opts[fam_sel], nombre, pa, pc, gb,
                                     cb, pct if cb else 0.0)
                    st.success(f"Plan '{nombre}' creado.")
                    st.rerun()
                else:
                    st.warning("El nombre es obligatorio.")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB: BENEFICIOS
# ═══════════════════════════════════════════════════════════════════════════════
with tab_ben:
    st.subheader("Beneficios")

    beneficios = crud.get_all_beneficios()
    if beneficios:
        for b in beneficios:
            label = f"{'✅' if b.activo else '⛔'} {b.nombre}"
            with st.expander(label):
                st.caption(b.descripcion or "Sin descripción")
                cols = st.columns([3, 1])
                new_desc = cols[0].text_area("Descripción", value=b.descripcion or "",
                                              key=f"ben_desc_{b.id}")
                col_save, col_tog = cols[1].columns(2)
                if col_save.button("Guardar", key=f"ben_save_{b.id}"):
                    from db.database import get_db
                    from db.models import Beneficio as BenModel
                    with get_db() as db:
                        obj = db.query(BenModel).filter_by(id=b.id).first()
                        obj.descripcion = new_desc
                    st.success("Guardado")
                    st.rerun()
                if col_tog.button("Activar/Des.", key=f"ben_tog_{b.id}"):
                    crud.toggle_beneficio_activo(b.id)
                    st.rerun()
    else:
        st.info("No hay beneficios aún.")

    st.divider()
    st.subheader("Agregar beneficio")
    with st.form("nuevo_beneficio"):
        nombre = st.text_input("Nombre")
        desc = st.text_area("Descripción")
        if st.form_submit_button("Crear"):
            if nombre:
                crud.create_beneficio(nombre, desc)
                st.success(f"Beneficio '{nombre}' creado.")
                st.rerun()
            else:
                st.warning("El nombre es obligatorio.")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB: SERVICIOS
# ═══════════════════════════════════════════════════════════════════════════════
with tab_svc:
    st.subheader("Servicios adicionales")

    servicios = crud.get_all_servicios()
    if servicios:
        for s in servicios:
            label = f"{'✅' if s.activo else '⛔'} {s.nombre} ({s.tipo_acceso})"
            with st.expander(label):
                cols = st.columns([2, 1, 1])
                new_desc = cols[0].text_area("Descripción", value=s.descripcion or "",
                                              key=f"svc_desc_{s.id}")
                new_tipo = cols[1].selectbox("Tipo acceso",
                                              ["suscripcion", "acceso", "addon"],
                                              index=["suscripcion", "acceso", "addon"].index(
                                                  s.tipo_acceso) if s.tipo_acceso in
                                              ["suscripcion", "acceso", "addon"] else 0,
                                              key=f"svc_tipo_{s.id}")
                new_det = cols[2].text_input("Detalle", value=s.detalle or "",
                                              key=f"svc_det_{s.id}")
                col_save, col_tog = st.columns(2)
                if col_save.button("Guardar", key=f"svc_save_{s.id}"):
                    from db.database import get_db
                    from db.models import Servicio as SvcModel
                    with get_db() as db:
                        obj = db.query(SvcModel).filter_by(id=s.id).first()
                        obj.descripcion = new_desc
                        obj.tipo_acceso = new_tipo
                        obj.detalle = new_det
                    st.success("Guardado")
                    st.rerun()
                if col_tog.button("Activar/Desactivar", key=f"svc_tog_{s.id}"):
                    crud.toggle_servicio_activo(s.id)
                    st.rerun()
    else:
        st.info("No hay servicios aún.")

    st.divider()
    st.subheader("Agregar servicio")
    with st.form("nuevo_servicio"):
        nombre = st.text_input("Nombre")
        desc = st.text_area("Descripción")
        tipo = st.selectbox("Tipo de acceso", ["suscripcion", "acceso", "addon"])
        det = st.text_input("Detalle (ej. 20 GB incluidos)")
        if st.form_submit_button("Crear"):
            if nombre:
                crud.create_servicio(nombre, desc, tipo, det)
                st.success(f"Servicio '{nombre}' creado.")
                st.rerun()
            else:
                st.warning("El nombre es obligatorio.")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB: FAQs
# ═══════════════════════════════════════════════════════════════════════════════
with tab_faq:
    st.subheader("Preguntas frecuentes")

    # Mapas id→nombre para mostrar en la lista
    ben_map = {b.id: b.nombre for b in crud.get_all_beneficios()}
    svc_map = {s.id: s.nombre for s in crud.get_all_servicios()}

    # ── Filtros ───────────────────────────────────────────────────────────────
    col_f1, col_f2, col_f3 = st.columns(3)
    ambito_filter = col_f1.text_input("Filtrar por ámbito")
    ben_filter_opts = {"(todos)": None} | _beneficio_options()
    svc_filter_opts = {"(todos)": None} | _servicio_options()
    ben_filter_sel = col_f2.selectbox("Filtrar por beneficio",
                                       list(ben_filter_opts.keys()))
    svc_filter_sel = col_f3.selectbox("Filtrar por servicio",
                                       list(svc_filter_opts.keys()))

    preguntas = crud.get_all_preguntas(
        ambito=ambito_filter or None,
        beneficio_id=ben_filter_opts[ben_filter_sel],
        servicio_id=svc_filter_opts[svc_filter_sel],
    )
    if preguntas:
        for pq in preguntas:
            # Mostrar nombres, no IDs
            entity_parts = []
            if pq.beneficio_id:
                entity_parts.append(f"Beneficio: {ben_map.get(pq.beneficio_id, str(pq.beneficio_id))}")
            if pq.servicio_id:
                entity_parts.append(f"Servicio: {svc_map.get(pq.servicio_id, str(pq.servicio_id))}")
            entity_label = " · ".join(entity_parts) if entity_parts else pq.ambito
            tag = f"[{entity_label}]"

            with st.expander(f"{tag} — {pq.pregunta[:80]}"):
                st.markdown(f"**Pregunta:** {pq.pregunta}")
                st.markdown(f"**Respuesta:** {pq.respuesta}")
                st.caption(f"Ámbito: {pq.ambito}")
                if st.button("Eliminar", key=f"faq_del_{pq.id}"):
                    crud.delete_pregunta(pq.id)
                    st.rerun()
    else:
        st.info("No hay preguntas frecuentes con ese filtro.")

    st.divider()

    # ── Agregar individual ─────────────────────────────────────────────────────
    # Nota: beneficio/servicio y ámbito no son redundantes — el ámbito se
    # auto-sugiere del beneficio/servicio seleccionado. Solo edítalo si la FAQ
    # no pertenece a ninguno (preguntas generales de la campaña, por ejemplo).
    with st.expander("➕ Agregar FAQ individual"):
        ben_opts_i = {"(ninguno)": None} | _beneficio_options()
        svc_opts_i = {"(ninguno)": None} | _servicio_options()
        col_bi, col_si = st.columns(2)
        ben_sel_i = col_bi.selectbox("Beneficio relacionado",
                                      list(ben_opts_i.keys()), key="ind_ben")
        svc_sel_i = col_si.selectbox("Servicio relacionado",
                                      list(svc_opts_i.keys()), key="ind_svc")

        # Ámbito se auto-sugiere del beneficio/servicio seleccionado
        if ben_sel_i != "(ninguno)":
            suggested_ambito_i = ben_sel_i
        elif svc_sel_i != "(ninguno)":
            suggested_ambito_i = svc_sel_i
        else:
            suggested_ambito_i = "general"
        ambito_i = st.text_input("Ámbito (auto-sugerido, editable)",
                                   value=suggested_ambito_i, key="ind_ambito")
        st.caption("Si seleccionas beneficio o servicio, el ámbito se llena automáticamente.")

        with st.form("nueva_faq"):
            pregunta_i = st.text_area("Pregunta")
            respuesta_i = st.text_area("Respuesta")
            if st.form_submit_button("Agregar"):
                if pregunta_i and respuesta_i:
                    crud.create_pregunta(pregunta_i, respuesta_i, ambito_i,
                                         beneficio_id=ben_opts_i[ben_sel_i],
                                         servicio_id=svc_opts_i[svc_sel_i])
                    st.success("FAQ agregada.")
                    st.rerun()
                else:
                    st.warning("Pregunta y respuesta son obligatorias.")

    # ── Importar desde Markdown ────────────────────────────────────────────────
    with st.expander("📄 Importar FAQs desde Markdown"):

        if "faq_queue" not in st.session_state:
            st.session_state.faq_queue = []
            st.session_state.faq_idx = 0

        queue = st.session_state.faq_queue
        idx = st.session_state.faq_idx

        # ── Modo revisión activo ───────────────────────────────────────────────
        if queue and idx < len(queue):
            item = queue[idx]
            total = len(queue)

            st.progress(idx / total, text=f"Revisando {idx + 1} de {total}")
            st.markdown(f"### FAQ {idx + 1} / {total}")

            # Widgets fuera del form para que sean reactivos
            ben_opts_r = {"(ninguno)": None} | _beneficio_options()
            svc_opts_r = {"(ninguno)": None} | _servicio_options()
            ben_keys_r = list(ben_opts_r.keys())
            svc_keys_r = list(svc_opts_r.keys())

            cur_ben_r = next((k for k, v in ben_opts_r.items()
                              if v == item.get("beneficio_id")), "(ninguno)")
            cur_svc_r = next((k for k, v in svc_opts_r.items()
                              if v == item.get("servicio_id")), "(ninguno)")

            col_b, col_s = st.columns(2)
            ben_sel_r = col_b.selectbox("Beneficio", ben_keys_r,
                                         index=ben_keys_r.index(cur_ben_r),
                                         key=f"rev_ben_{idx}")
            svc_sel_r = col_s.selectbox("Servicio", svc_keys_r,
                                         index=svc_keys_r.index(cur_svc_r),
                                         key=f"rev_svc_{idx}")

            # Ámbito auto-sugerido del beneficio/servicio seleccionado
            if ben_sel_r != "(ninguno)":
                suggested_ambito = ben_sel_r
            elif svc_sel_r != "(ninguno)":
                suggested_ambito = svc_sel_r
            else:
                suggested_ambito = item.get("ambito", "general")

            new_ambito = st.text_input(
                "Ámbito (auto-sugerido del beneficio/servicio, editable)",
                value=suggested_ambito,
                key=f"rev_ambito_{idx}",
            )
            st.caption("El ámbito identifica el tema para búsquedas internas. "
                       "Si hay beneficio o servicio seleccionado, no hace falta cambiarlo.")

            new_pregunta = st.text_area("Pregunta", value=item["pregunta"],
                                         height=80, key=f"rev_q_{idx}")
            new_respuesta = st.text_area("Respuesta", value=item["respuesta"],
                                          height=200, key=f"rev_r_{idx}")

            col_save, col_skip, col_cancel = st.columns(3)
            if col_save.button("✅ Guardar y siguiente", key=f"rev_save_{idx}"):
                crud.create_pregunta(
                    pregunta=new_pregunta,
                    respuesta=new_respuesta,
                    ambito=new_ambito,
                    beneficio_id=ben_opts_r[ben_sel_r],
                    servicio_id=svc_opts_r[svc_sel_r],
                )
                st.session_state.faq_idx += 1
                st.rerun()

            if col_skip.button("⏭️ Omitir", key=f"rev_skip_{idx}"):
                st.session_state.faq_idx += 1
                st.rerun()

            if col_cancel.button("❌ Cancelar todo", key=f"rev_cancel_{idx}"):
                st.session_state.faq_queue = []
                st.session_state.faq_idx = 0
                st.rerun()

        elif queue and idx >= len(queue):
            saved = sum(1 for _ in range(idx))
            st.success(f"Revisión completa — {idx} FAQs procesadas.")
            if st.button("Importar otro archivo"):
                st.session_state.faq_queue = []
                st.session_state.faq_idx = 0
                st.rerun()

        else:
            # ── Carga ──────────────────────────────────────────────────────────
            st.markdown(
                "Soporta dos formatos:\n\n"
                "**Simple:** `## Sección` → heading como ámbito · `**¿Pregunta?**` → bold como pregunta\n\n"
                "**FAQ:** `## FAQ N: ¿Pregunta?` → heading como pregunta · `**Respuesta:**` marca el cuerpo · "
                "`**Límites:**` / `**Cómo usar…**` se descartan automáticamente"
            )

            tab_paste, tab_upload = st.tabs(["Pegar texto", "Subir archivo"])

            with tab_paste:
                md_text = st.text_area("Contenido Markdown", height=300, key="md_paste")
                if st.button("Parsear texto", key="btn_parse_paste"):
                    parsed = parse_faq_md(md_text)
                    if parsed:
                        st.session_state.faq_queue = parsed
                        st.session_state.faq_idx = 0
                        st.rerun()
                    else:
                        st.warning("No se encontraron preguntas en el texto.")

            with tab_upload:
                uploaded = st.file_uploader("Archivo .md", type=["md"], key="md_upload")
                if uploaded:
                    content = uploaded.read().decode("utf-8")
                    parsed = parse_faq_md(content)
                    st.info(f"Se encontraron **{len(parsed)}** preguntas. "
                            "Pulsa el botón para comenzar la revisión.")
                    if parsed and st.button("Comenzar revisión", key="btn_start_review"):
                        st.session_state.faq_queue = parsed
                        st.session_state.faq_idx = 0
                        st.rerun()
