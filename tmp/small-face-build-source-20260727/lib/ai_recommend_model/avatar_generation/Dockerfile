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
    AVATAR_FACE_DETECTOR_PROVIDER=mediapipe \
    AVATAR_MEDIAPIPE_ENABLED=true \
    AVATAR_MEDIAPIPE_FACE_LANDMARKER_MODEL_PATH=/app/models/face_landmarker.task \
    AVATAR_FACE_DETECT_MODEL_PATH=/app/models/blaze_face_full_range.tflite \
    AVATAR_SMALL_FACE_PIPELINE_ENABLED=true \
    AVATAR_FACE_FULL_RANGE_ENABLED=true \
    AVATAR_FACE_TILE_FALLBACK_ENABLED=true \
    AVATAR_MEDIAPIPE_OUTPUT_BLENDSHAPES=true \
    AVATAR_MEDIAPIPE_NUM_FACES=2 \
    AVATAR_MEDIAPIPE_MIN_DETECTION_CONFIDENCE=0.6 \
    AVATAR_MEDIAPIPE_MIN_PRESENCE_CONFIDENCE=0.6 \
    AVATAR_INITIAL_CANDIDATE_COUNT=4 \
    AVATAR_EXTRA_CANDIDATE_COUNT=4 \
    AVATAR_MAX_TOTAL_CANDIDATES=8 \
    AVATAR_PREVIEW_COUNT=4 \
    AVATAR_MIN_PREVIEW_CANDIDATES=1 \
    AVATAR_PREVIEW_REQUIRE_FOUR=false \
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

RUN mkdir -p /app/models \
    && python -c "from pathlib import Path; import urllib.request; url='https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task'; target=Path('/app/models/face_landmarker.task'); urllib.request.urlretrieve(url, target); assert target.stat().st_size >= 1024 * 1024, 'Downloaded Face Landmarker asset is unexpectedly small.'" \
    && python -c "from pathlib import Path; import urllib.request; url='https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_full_range/float16/latest/blaze_face_full_range.tflite'; target=Path('/app/models/blaze_face_full_range.tflite'); urllib.request.urlretrieve(url, target); assert target.stat().st_size >= 100 * 1024, 'Downloaded full-range FaceDetector asset is unexpectedly small.'"

COPY lib/ai_recommend_model /app

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "1", "--timeout", "3600", "avatar_generation.worker_service:app"]
