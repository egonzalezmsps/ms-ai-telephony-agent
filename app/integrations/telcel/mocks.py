"""
integrations/telcel/mocks.py

Respuestas simuladas (ya descifradas) para cuando <PREFIX>_MOCK=true.
"""

import uuid

from app.integrations.telcel.config import (
    COMMUNICATION_MESSAGE,
    CREATE_PROCESS,
    CREATE_PRODUCT_ORDER,
    TelcelApi,
)


def mock_response(api: TelcelApi) -> dict:
    if api == CREATE_PROCESS:
        return {"processId": f"MOCK-{uuid.uuid4().hex[:10].upper()}"}
    if api == COMMUNICATION_MESSAGE:
        return {"status": "SENT"}
    if api == CREATE_PRODUCT_ORDER:
        return {"orderId": f"MOCK-ORDER-{uuid.uuid4().hex[:8].upper()}"}
    raise ValueError(f"Sin mock definido para {api.name}")
