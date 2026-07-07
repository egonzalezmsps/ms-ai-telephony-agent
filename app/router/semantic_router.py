"""
router/semantic_router.py

Clasificador semántico de intenciones usando embeddings de Cohere en OCI.
Reemplaza los bloques pre-LLM de matching exacto en reni_agent.py.
"""

import os
import math
import logging
from typing import Optional

import oci
from oci.generative_ai_inference import GenerativeAiInferenceClient
from oci.generative_ai_inference.models import (
    EmbedTextDetails,
    OnDemandServingMode,
)

logger = logging.getLogger(__name__)

OCI_COMPARTMENT_ID = os.environ["OCI_COMPARTMENT_ID"]
OCI_REGION = os.environ.get("OCI_REGION", "us-chicago-1")
EMBED_MODEL_ID = "cohere.embed-multilingual-v3.0"
THRESHOLDS = {
    "vigencia_promo": 0.72,
    "criterio_promo": 0.72,
    "reglas_internas": 0.78,
    "proceso_activacion": 0.75,
    "por_que_cac": 0.75,
    "facturacion": 0.75,
    "info_plan_actual": 0.72,
    "comparar_beneficios": 0.72,
    "planes_mas_baratos": 0.78,
    "planes_mas_caros": 0.75,
    "planes_ultra": 0.76,
    "planes_mas_gb": 0.72,
    "otra_recomendacion": 0.78,
    "confirmacion_activacion": 0.82,
}

INTENCIONES = {
    "vigencia_promo": [
        "hasta cuando dura esta promocion",
        "cuando vence la promocion",
        "por cuanto tiempo aplica la promocion",
        "cuanto dura la promocion",
        "cuando expira esta oferta",
        "hasta que fecha esta disponible",
        "solo puedo activarlo hoy",
        "puedo activarlo mañana",
        "puedo esperar para activarlo",
        "tengo que activarlo hoy",
        "es decir solo hoy puedo activarlo",
        "si no lo activo hoy que pasa",
    ],
    "criterio_promo": [
        "porque a veces tienen promocion",
        "cuando aplica la promocion",
        "por que hay promocion en algunos planes",
        "cuando hay promo",
        "por que unos tienen promocion y otros no",
        "cuales planes tienen promocion",
    ],
    "reglas_internas": [
        "cuales son las reglas para activar",
        "como activas los planes",
        "que criterios usas para recomendar",
        "como funciona el sistema de activacion",
        "como trabajas internamente",
        "que puedes hacer tu",
        "explicame como funciona esto",
    ],
    "proceso_activacion": [
        "cual es el proceso para activar",
        "como es el proceso de cambio de plan",
        "que pasos debo seguir para activar",
        "como se activa el plan",
        "que tengo que hacer para activar",
        "como funciona la activacion del plan",
        "que pasa cuando activo el plan",
        "pasos para activar el plan",
        "como activo mi plan",
    ],
    "por_que_cac": [
        "porque tengo que ir al cac",
        "por que tengo que llamar a soporte",
        "no puedes cambiarlo tu mismo",
        "por que me mandas con soporte",
        "no puedes hacer el cambio tu",
        "porque no puedes activarlo aqui",
        "por que no puedes hacerlo",
    ],
    "facturacion": [
        "cuando me cobran el plan",
        "cual es mi fecha de cobro",
        "cuando tengo que pagar",
        "cuando comienza el cobro del nuevo plan",
        "cuando inicia la facturacion",
        "cuando es el proximo cobro",
        "en que fecha se hace el pago",
    ],
    "info_plan_actual": [
        "cuantos gigas tengo en mi plan",
        "cuanto pago actualmente por mi plan",
        "cual es mi plan actual",
        "que plan tengo contratado",
        "cuantos datos tiene mi plan actual",
        "cuanto es mi renta mensual",
        "que tengo contratado actualmente",
    ],
    "comparar_beneficios": [
        "que gano con el cambio de plan",
        "en que mejora el nuevo plan",
        "que diferencia hay con mi plan actual",
        "que beneficios nuevos obtendria",
        "vale la pena el cambio de plan",
        "que cambia respecto a mi plan actual",
        "quiero evaluar los beneficios del plan",
        "dejame revisar bien los beneficios",
        "quiero analizar los beneficios",
        "explicame todos los beneficios",
        "quiero conocer bien los beneficios",
        "que beneficios nuevos tendria con el cambio",
        "en que es mejor el nuevo plan",
        "que mejora con el cambio de plan",
    ],
    "planes_mas_baratos": [
        "tienes planes mas baratos",
        "algo mas economico disponible",
        "quiero pagar menos por mi plan",
        "planes de menor precio",
        "opciones mas economicas que mi plan actual",
        "menor renta disponible",
        "algo mas accesible en precio",
        "quisiera bajar mi renta",
        "planes con menor costo",
        "se me hace caro el plan",
        "me parece caro",
        "es muy caro para mi",
        "no quiero pagar tanto",
        "hay algo mas barato",
        "planes mas baratos sin apps incluidas",
        "opciones economicas sin cashback",
        "algo mas barato en precio mensual",
    ],
    "planes_mas_caros": [
        "tienes planes mas caros o premium",
        "algo mas premium disponible",
        "plan superior al que tengo",
        "opciones mas caras disponibles",
        "algo de mayor precio y beneficios",
        "planes de mayor categoria",
    ],
    "planes_ultra": [
        "quiero ver planes ultra",
        "que opciones ultra tienen disponibles",
        "planes de la familia telcel ultra",
        "mostrame los planes ultra",
        "quiero un plan ultra sin apps sociales",
        "planes sin redes sociales incluidas",
        "quiero mas gigas sin apps",
        "los planes ultra tienen cashback",
        "el cashback aplica en ultra",
        "los ultra incluyen cashback",
        "sin redes sociales",
        "sin apps ilimitadas",
        "sin aplicaciones sociales",
        "sin facebook ni instagram",
        "sin redes incluidas",
        "prefiero algo sin apps incluidas",
        "sin las apps incluidas",
        "prefiero sin aplicaciones",
        "opciones sin apps ilimitadas",
        "algo sin redes ni apps",
    ],
    "planes_mas_gb": [
        "quiero mas gigas en mi plan",
        "planes con mas datos disponibles",
        "mayor capacidad de datos",
        "opciones con mas gb que mi plan actual",
        "planes con mayor numero de gigas",
        "algo con mas datos disponibles para mi",
        "quisiera un plan con mayor numero de gigas",
        "tienes planes con mas gigas disponibles",
    ],
    "otra_recomendacion": [
        "dame otra recomendacion de plan",
        "recomiendame otro plan diferente",
        "que mas recomiendas para mi perfil",
        "cual me recomiendas tu",
        "hay otra opcion que se adapte a mi",
        "dame una recomendacion diferente",
        "sugiereme otro plan distinto",
        "hay otra opcion que no sea esta",
    ],
    "confirmacion_activacion": [
        "si quiero activarlo",
        "quiero activarlo",
        "dale activalo",
        "si por favor activalo",
        "adelante con el cambio",
        "procede con la activacion",
        "confirmo que quiero activarlo",
    ],
}


def _get_oci_client() -> GenerativeAiInferenceClient:
    config = {
        "user": os.environ["OCI_USER"],
        "fingerprint": os.environ["OCI_FINGERPRINT"],
        "tenancy": os.environ["OCI_TENANCY"],
        "region": OCI_REGION,
        "key_file": os.environ.get("OCI_KEY_FILE", "./.oci/oci_api_key.pem"),
    }
    return GenerativeAiInferenceClient(config)


def _embed(texts: list) -> list:
    client = _get_oci_client()
    details = EmbedTextDetails(
        inputs=texts,
        serving_mode=OnDemandServingMode(model_id=EMBED_MODEL_ID),
        compartment_id=OCI_COMPARTMENT_ID,
        input_type="SEARCH_QUERY",
    )
    response = client.embed_text(details)
    return response.data.embeddings


def _cosine_similarity(a: list, b: list) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# Cache de embeddings de referencia en memoria
_REFERENCE_EMBEDDINGS: dict = {}


def load_reference_embeddings():
    """
    Genera y cachea los embeddings de todas las frases de referencia.
    Llamar una vez al iniciar la aplicación.
    """
    global _REFERENCE_EMBEDDINGS
    logger.info("[ROUTER] Generando embeddings de referencia...")

    for intencion, frases in INTENCIONES.items():
        embeddings = _embed(frases)
        _REFERENCE_EMBEDDINGS[intencion] = embeddings
        logger.info("[ROUTER] '%s': %d frases indexadas", intencion, len(frases))

    logger.info("[ROUTER] Router semántico listo — %d intenciones", len(INTENCIONES))


def classify(message: str, threshold: float = 0.75) -> Optional[str]:
    """
    Clasifica un mensaje en una intención.
    Retorna el nombre de la intención o None si no supera el threshold.
    """
    if not _REFERENCE_EMBEDDINGS:
        logger.warning("[ROUTER] Embeddings no cargados — fallback a matching exacto")
        return None

    try:
        msg_embedding = _embed([message])[0]
    except Exception as e:
        logger.error("[ROUTER] Error generando embedding: %s", e)
        return None

    best_intencion = None
    best_score = 0.0

    for intencion, ref_embeddings in _REFERENCE_EMBEDDINGS.items():
        for ref_emb in ref_embeddings:
            score = _cosine_similarity(msg_embedding, ref_emb)
            if score > best_score:
                best_score = score
                best_intencion = intencion

    logger.info("[ROUTER] '%s' → '%s' (%.3f)", message[:50], best_intencion, best_score)

    intencion_threshold = THRESHOLDS.get(best_intencion, threshold)
    if best_score >= intencion_threshold:
        return best_intencion

    return None
