import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st

st.set_page_config(page_title="Crear desde imagen", page_icon="🖼️", layout="wide")
st.title("🖼️ Crear campaña desde imagen")

st.info(
    "**Próximamente.**\n\n"
    "Esta sección permitirá subir una imagen (brief de campaña, flyer, tabla de precios) "
    "y usar un modelo de visión para extraer automáticamente la información de la campaña: "
    "nombre, planes, vigencia, condiciones y clientes objetivo.\n\n"
    "El resultado generado deberá ser revisado y validado antes de guardarse."
)

st.divider()

st.subheader("Prototipo (sin IA activa)")
uploaded = st.file_uploader("Sube una imagen", type=["png", "jpg", "jpeg", "webp"])
if uploaded:
    st.image(uploaded, caption="Imagen subida", use_container_width=True)
    st.markdown("*(Aquí se mostraría el resultado extraído por el modelo de visión)*")
