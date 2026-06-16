import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st
from db.database import init_db

st.set_page_config(
    page_title="Campaign Creator — Reni Agent",
    page_icon="📢",
    layout="wide",
)

# Ensure tables exist on first run (idempotent)
try:
    init_db()
except Exception as e:
    st.error(f"Error al conectar con la base de datos: {e}")
    st.stop()

st.title("📢 Campaign Creator")
st.markdown(
    """
    Bienvenido al panel de administración de campañas para **Reni Agent**.

    Usa el menú de la izquierda para navegar:

    | Sección | Descripción |
    |---|---|
    | **Catálogo** | Gestiona familias, planes, beneficios, servicios y FAQs |
    | **Promociones** | Crea y administra promociones activas |
    | **Campañas** | Arma campañas, agrega clientes y planes, envía mensajes |
    | **Seguimiento** | Revisa el estado de cada cliente dentro de una campaña |
    | **Crear desde imagen** | (Próximamente) Genera campañas a partir de imágenes |
    """
)
