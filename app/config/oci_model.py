"""
config/oci_model.py
"""
import logging
import os
import time
import litellm
from dotenv import load_dotenv
from strands.models.litellm import LiteLLMModel

logger = logging.getLogger(__name__)

load_dotenv()

# Parche temporal: fuerza drop_params=True para OCI hasta que LiteLLM lo corrija
from litellm.llms.oci.chat.transformation import OCIChatConfig
_original_map = OCIChatConfig.map_openai_params

def _patched_map(self, non_default_params, optional_params, model, drop_params):
    return _original_map(self, non_default_params, optional_params, model, drop_params=True)

OCIChatConfig.map_openai_params = _patched_map


def _read_key_file(path: str) -> str:
    abs_path = os.path.expanduser(path)
    with open(abs_path, "r") as f:
        return f.read()


def build_oci_model() -> LiteLLMModel:
    model_id = os.environ["OCI_MODEL_ID"]
    compartment_id = os.environ["OCI_COMPARTMENT_ID"]
    region = os.environ["OCI_REGION"]

    t0 = time.time()
    logger.info("[OCI] Iniciando modelo model_id=%s region=%s", model_id, region)

    params = {
        "oci_region": region,
        "oci_compartment_id": compartment_id,
        "temperature": float(os.environ.get("LLM_TEMPERATURE", "0.3")),
        # 1024: con el catálogo en modo datos, el LLM redacta listas de hasta ~16 planes
        # (clientes de renta baja) y 600 las cortaba. Sin razonamiento es solo un tope.
        "max_tokens": int(os.environ.get("LLM_MAX_TOKENS", "1024")),
        "top_p": 0.9,
    }

    # Razonamiento interno de modelos como Gemini 2.5: sus tokens se descuentan del
    # mismo max_tokens y, con 600, dejaban respuestas cortadas o vacías (OCI además
    # reporta finish_reason="stop", así que no se detecta como truncado). "none" lo
    # desactiva. Valores: none | low | medium | high; vacío = no enviar el parámetro.
    # Nota: en Gemini vía OCI, "low"/"medium" no reducen el razonamiento (medido).
    reasoning_effort = os.environ.get("LLM_REASONING_EFFORT", "none").strip()
    if reasoning_effort:
        params["reasoning_effort"] = reasoning_effort

    # Si hay credenciales de API key, úsalas
    oci_user = os.environ.get("OCI_USER")
    auth_mode = "instance_principal"
    try:
        if oci_user:
            auth_mode = "api_key"
            key_file = os.environ.get("OCI_KEY_FILE", "./.oci/oci_api_key.pem")
            params["oci_user"] = oci_user
            params["oci_fingerprint"] = os.environ["OCI_FINGERPRINT"]
            params["oci_tenancy"] = os.environ["OCI_TENANCY"]
            params["oci_key"] = _read_key_file(key_file)
            logger.info("[OCI] Auth: API key user=%s", oci_user[:30])
        # Si no, usa Instance Principal (autenticación automática en OKE)
        else:
            params["oci_auth"] = "instance_principal"
            logger.info("[OCI] Auth: instance_principal")

        model = LiteLLMModel(
            model_id=f"oci/{model_id}",
            params=params,
        )
    except Exception:
        logger.error(
            "[OCI] Fallo al construir el modelo model_id=%s region=%s auth=%s",
            model_id, region, auth_mode, exc_info=True,
        )
        raise
    logger.info(
        "[OCI] Modelo listo en %.2fs model_id=%s region=%s auth=%s "
        "temperature=%.1f max_tokens=%d top_p=%.2f reasoning_effort=%s",
        time.time() - t0, model_id, region, auth_mode,
        params["temperature"], params["max_tokens"], params["top_p"],
        params.get("reasoning_effort", "(no enviado)"),
    )
    return model


# Singleton
oci_model = build_oci_model()