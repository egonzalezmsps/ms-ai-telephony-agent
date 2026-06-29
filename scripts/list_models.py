import os
from dotenv import load_dotenv
load_dotenv()

import oci

config = {
    "user": os.environ["OCI_USER"],
    "fingerprint": os.environ["OCI_FINGERPRINT"],
    "tenancy": os.environ["OCI_TENANCY"],
    "region": os.environ["OCI_REGION"],
    "key_file": os.environ.get("OCI_KEY_FILE", "./.oci/oci_api_key.pem"),
}

client = oci.generative_ai.GenerativeAiClient(config)
compartment_id = os.environ["OCI_COMPARTMENT_ID"]

models = client.list_models(compartment_id=compartment_id)
print(type(models.data))
print(dir(models.data))

# Intentar diferentes formas de acceder
if hasattr(models.data, 'items'):
    for m in models.data.items:
        print(f"{m.display_name} | {m.id}")
elif hasattr(models.data, 'models'):
    for m in models.data.models:
        print(f"{m.display_name} | {m.id}")
else:
    print(models.data)
