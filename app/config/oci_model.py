"""
config/oci_model.py
"""
import os
import litellm
from dotenv import load_dotenv
from strands.models.litellm import LiteLLMModel

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
    key_file = os.environ.get("OCI_KEY_FILE", "./.oci/oci_api_key.pem")

    return LiteLLMModel(
        model_id=f"oci/{model_id}",
        params={
            "oci_region": region,
            "oci_compartment_id": compartment_id,
            "oci_user": os.environ["OCI_USER"],
            "oci_fingerprint": os.environ["OCI_FINGERPRINT"],
            "oci_tenancy": os.environ["OCI_TENANCY"],
            "oci_key": _read_key_file(key_file),
            "temperature": float(os.environ.get("LLM_TEMPERATURE", "0.3")),
            "max_tokens": int(os.environ.get("LLM_MAX_TOKENS", "600")),
            "top_p": 0.9,
        },
    )


# Singleton
oci_model = build_oci_model()