# ============================================================
# Seolleyeon Recommendation Pipeline - Cloud Run Job Image
# Build context: project root
# Usage:  docker build -f recsys/Dockerfile -t recs-pipeline .
# ============================================================

# --- Stage 1: install deps + pre-download CLIP model ---------
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc g++ && \
    rm -rf /var/lib/apt/lists/*

COPY recsys/requirements.txt /build/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

RUN python -c "\
from transformers import AutoModel, AutoProcessor; \
AutoModel.from_pretrained('openai/clip-vit-base-patch32'); \
AutoProcessor.from_pretrained('openai/clip-vit-base-patch32')"

# --- Stage 2: runtime image ----------------------------------
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/lib/python3.11/site-packages \
                    /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /root/.cache/huggingface /root/.cache/huggingface

COPY lib/ai_recommend_model/*.py /app/ai_recommend_model/
COPY recsys/ /app/recsys/

ENV AI_MODEL_DIR=/app/ai_recommend_model \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    CLIP_MODEL_ID=openai/clip-vit-base-patch32 \
    ALLOWED_IMAGE_HOSTS=firebasestorage.googleapis.com,storage.googleapis.com

ENTRYPOINT ["python", "-m", "recsys.main"]
