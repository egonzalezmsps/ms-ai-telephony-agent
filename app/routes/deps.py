"""
routes/deps.py

Dependencies de FastAPI compartidas entre routers.
"""

import os
from typing import Optional

from fastapi import Header, HTTPException


def require_api_key(x_api_key: Optional[str] = Header(default=None)) -> None:
    expected_key = os.getenv("API_KEY", "")
    if expected_key and x_api_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
