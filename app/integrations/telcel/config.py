"""
integrations/telcel/config.py

Definición de las APIs intermedias Telcel y lectura de su configuración desde el entorno.

Cada API lee sus variables con su propio prefijo:
    <PREFIX>_ENDPOINT, <PREFIX>_API_KEY, <PREFIX>_ENC_KEY, <PREFIX>_ENC_IV, <PREFIX>_USER
    <PREFIX>_MOCK=true  → no se hace la llamada HTTP real (mock por API, no global)
"""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class TelcelApi:
    name: str            # nombre para logs
    env_prefix: str      # prefijo de las variables de entorno
    request_field: str   # campo del body que lleva el payload cifrado
    response_field: str  # campo de la respuesta que trae el payload cifrado


CREATE_PROCESS = TelcelApi(
    "createProcess", "TELCEL_CREATE_PROCESS", "createProcessRequest", "createProcessResponse",
)
COMMUNICATION_MESSAGE = TelcelApi(
    "communicationMessage", "TELCEL_COMM_MSG", "communicationMessageRequest", "communicationMessageResponse",
)
CREATE_PRODUCT_ORDER = TelcelApi(
    "createProductOrder", "TELCEL_CREATE_PRODUCT_ORDER", "createProductOrderRequest", "createProductOrderResponse",
)


@dataclass(frozen=True)
class TelcelApiConfig:
    endpoint: str
    api_key: str
    enc_key: str
    enc_iv: str
    user: str


def is_mock_enabled(api: TelcelApi) -> bool:
    return os.environ.get(f"{api.env_prefix}_MOCK", "false").strip().lower() == "true"


def load_config(api: TelcelApi) -> TelcelApiConfig:
    def get(name: str) -> str:
        value = os.environ.get(f"{api.env_prefix}_{name}")
        if not value:
            raise RuntimeError(
                f"Falta la variable de entorno {api.env_prefix}_{name}. Revisa tu archivo .env "
                f"(usa .env.example como referencia)."
            )
        return value

    return TelcelApiConfig(
        endpoint=get("ENDPOINT"),
        api_key=get("API_KEY"),
        enc_key=get("ENC_KEY"),
        enc_iv=get("ENC_IV"),
        user=get("USER"),
    )
