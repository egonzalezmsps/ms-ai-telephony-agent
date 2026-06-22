FROM python:3.11-slim

WORKDIR /app

# Dependencias del sistema (necesarias para el SDK de OCI / cryptography)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    libssl-dev \
 && rm -rf /var/lib/apt/lists/*

# Instalar dependencias Python primero (capa cacheada)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código fuente
COPY main.py .
COPY app/ ./app/
COPY docs/ ./docs/
COPY campaign_app/ ./campaign_app/

EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
