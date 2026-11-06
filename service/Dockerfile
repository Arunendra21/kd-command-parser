# Inference service image. No model weights inside: they are downloaded from
# object storage (MODEL_URI) at start-up. CPU-only PyTorch keeps it small.
FROM python:3.11.10-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 SCHEMA_PATH=/app/schema.json
WORKDIR /app

COPY service/requirements.txt .
RUN pip install --no-deps --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.txt

COPY service/core.py service/app.py ./
COPY data/schema.json ./schema.json

RUN useradd -r -u 10001 app && mkdir -p /tmp/model && chown app /tmp/model
USER 10001
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
