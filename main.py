"""
main.py — Entry point FastAPI para ReniAgent con persistencia PostgreSQL.
"""

import os
import logging
from dotenv import load_dotenv

load_dotenv()  # Debe ejecutarse antes de importar módulos que lean os.environ al cargarse

from app.config.logging_config import setup_logging
setup_logging()  # Debe correr antes de importar módulos que loguean al cargarse (p.ej. oci_model)

from fastapi import FastAPI

from app.state.persistence import init_db
from app.router.semantic_router import load_reference_embeddings
from app.state.campaign_traceability import CAMPAIGN_DB_AVAILABLE
from app.routes import chat as chat_routes
from app.routes import webhook as webhook_routes
from app.routes import campaign as campaign_routes
from app.routes import diagnostics as diagnostics_routes

logger = logging.getLogger(__name__)

app = FastAPI(
    title="ReniAgent — Telcel Sales Agent",
    version="2.0.0",
    description="Agente de ventas Telcel con Strands Agents + OCI + PostgreSQL",
)


@app.on_event("startup")
def startup():
    """Crea las tablas en PostgreSQL al arrancar."""
    logger.info("[DEPLOY] Modelo OCI activo: %s", os.environ.get("OCI_MODEL_ID", "desconocido"))
    init_db()
    if CAMPAIGN_DB_AVAILABLE:
        try:
            from campaign_app.db.models import Base as CampaignBase
            from campaign_app.db.database import get_engine
            CampaignBase.metadata.create_all(get_engine())
            logger.info("Tablas de campaña listas")
        except Exception as e:
            logger.warning(f"No se pudieron crear tablas de campaña: {e}")
    load_reference_embeddings()
    logger.info("ReniAgent iniciado — tablas PostgreSQL listas")


@app.get("/actuator/health", include_in_schema=False)
def health():
    return {"status": "UP"}


@app.get("/health", include_in_schema=False)
def health_simple():
    return "ok"


app.include_router(chat_routes.router)
app.include_router(webhook_routes.router)
app.include_router(campaign_routes.router)
app.include_router(diagnostics_routes.router)