import os
from dotenv import load_dotenv
load_dotenv()

import oci
from oci.generative_ai_inference import GenerativeAiInferenceClient
from oci.generative_ai_inference.models import (
    EmbedTextDetails,
    OnDemandServingMode,
)

config = {
    "user": os.environ["OCI_USER"],
    "fingerprint": os.environ["OCI_FINGERPRINT"],
    "tenancy": os.environ["OCI_TENANCY"],
    "region": os.environ.get("OCI_REGION", "us-chicago-1"),
    "key_file": os.environ.get("OCI_KEY_FILE", "./.oci/oci_api_key.pem"),
}

client = GenerativeAiInferenceClient(config)

details = EmbedTextDetails(
    inputs=["hola como estas", "tienes planes mas baratos"],
    serving_mode=OnDemandServingMode(
        model_id="cohere.embed-multilingual-v3.0"
    ),
    compartment_id=os.environ["OCI_COMPARTMENT_ID"],
    input_type="SEARCH_QUERY",
)

response = client.embed_text(details)
embeddings = response.data.embeddings

print(f"✅ Embeddings generados correctamente")
print(f"Número de embeddings: {len(embeddings)}")
print(f"Dimensiones: {len(embeddings[0])}")
print(f"Primeros 5 valores del primer embedding: {embeddings[0][:5]}")
