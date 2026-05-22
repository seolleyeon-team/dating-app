# Build from repository root:
#   docker build -f lib/ai_recommend_model/avatar_generation/Dockerfile -t seolleyeon-avatar-worker .

FROM pytorch/pytorch:2.8.0-cuda12.8-cudnn9-runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PORT=8080 \
    AVATAR_WORKER_MODE=flux \
    MODEL_ID=black-forest-labs/FLUX.2-klein-4B \
    SOURCE_PHOTO_BUCKET=seolleyeon-final-private-source-photos \
    AVATAR_TEMP_BUCKET=seolleyeon-final-avatar-temp \
    MAX_CANDIDATES=4 \
    AVATAR_FLUX_NUM_INFERENCE_STEPS=4 \
    AVATAR_FLUX_GUIDANCE_SCALE=1.0 \
    AVATAR_REFERENCE_PRIVACY_PREPROCESS=true \
    AVATAR_REFERENCE_FACE_EQUIVALENT_SIZE=32 \
    AVATAR_REFERENCE_FACE_BLUR_RADIUS=4.0 \
    AVATAR_REFERENCE_NONFACE_EQUIVALENT_SIZE=96 \
    AVATAR_REFERENCE_NONFACE_BLUR_RADIUS=1.5 \
    AVATAR_FACE_MIN_RELATIVE_SIZE=0.08 \
    AVATAR_INITIAL_CANDIDATE_COUNT=4 \
    AVATAR_EXTRA_CANDIDATE_COUNT=4 \
    AVATAR_MAX_TOTAL_CANDIDATES=8 \
    AVATAR_PREVIEW_COUNT=4 \
    AVATAR_PREVIEW_REQUIRE_FOUR=true \
    AVATAR_PREVIEW_FILL_WITH_SOFT_PASS=true \
    AVATAR_PREVIEW_FILL_HARD_REJECT=false \
    AVATAR_RERANK_PROVIDER=deterministic_qa_tier

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libegl1 \
        libgles2 \
        libglib2.0-0 \
        libgl1 \
        libsm6 \
        libxext6 \
        libxrender1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements_avatar_worker.txt /app/requirements_avatar_worker.txt
RUN pip install --no-cache-dir -r /app/requirements_avatar_worker.txt

COPY lib/ai_recommend_model /app

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "1", "--timeout", "3600", "avatar_generation.worker_service:app"]
