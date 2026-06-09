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
        "max_tokens": int(os.environ.get("LLM_MAX_TOKENS", "600")),
        "top_p": 0.9,
    }

    # Si hay credenciales de API key, úsalas
    oci_user = os.environ.get("OCI_USER")
    if oci_user:
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
    logger.info("[OCI] Modelo listo en %.2fs temperature=%.1f max_tokens=%d",
                time.time() - t0, params["temperature"], params["max_tokens"])
    return model


# Singleton
oci_model = build_oci_model()