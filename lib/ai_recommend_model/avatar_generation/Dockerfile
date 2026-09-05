# Build from repository root:
#   docker build -f lib/ai_recommend_model/avatar_generation/Dockerfile -t seolleyeon-avatar-worker .

FROM pytorch/pytorch:2.8.0-cuda12.8-cudnn9-runtime@sha256:417bd75df6365104c283ea4c1651fb3530d9eb5a4c2fafa51943cff2a94e6385

ARG QA_FLORENCE_REVISION=26b734a54fdfbf9c398351eedfabb7f27fc470b7
ARG QA_CLIP_LARGE_REVISION=32bd64288804d66eefd0ccbe215aa642df71cc41
ARG QA_CLIP_BASE_REVISION=3d74acf9a28c67741b2f4f2ea7635f0aaf6f0268

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PORT=8080 \
    AVATAR_WORKER_MODE=azure_gpt_image_2 \
    MODEL_ID=azure_gpt_image_2 \
    SOURCE_PHOTO_BUCKET=seolleyeon-final-private-source-photos \
    AVATAR_TEMP_BUCKET=seolleyeon-final-avatar-temp \
    APPROVED_AVATAR_BUCKET=seolleyeon-final-approved-avatars \
    MAX_CANDIDATES=4 \
    AVATAR_FIDELITY_CORRIDOR_MODE=shadow \
    AVATAR_FIDELITY_CORRIDOR_CALIBRATION_VERSION=uncalibrated \
    AVATAR_PUBLIC_ROLLOUT_ENABLED=false \
    AZURE_OPENAI_MAX_ATTEMPTS=3 \
    AZURE_OPENAI_MAX_CONCURRENCY=1 \
    AZURE_OPENAI_REQUESTS_PER_MINUTE=2 \
    AZURE_OPENAI_API_STYLE=foundry_v1 \
    AZURE_OPENAI_API_VERSION=preview \
    AVATAR_FACE_MIN_RELATIVE_SIZE=0.08 \
    AVATAR_FACE_DETECTOR_PROVIDER=mediapipe \
    AVATAR_MEDIAPIPE_ENABLED=true \
    AVATAR_MEDIAPIPE_FACE_LANDMARKER_MODEL_PATH=/app/models/face_landmarker.task \
    AVATAR_FACE_DETECT_MODEL_PATH=/app/models/blaze_face_full_range.tflite \
    AVATAR_FACE_FULL_RANGE_ENABLED=true \
    AVATAR_FACE_TILE_FALLBACK_ENABLED=true \
    AVATAR_MEDIAPIPE_OUTPUT_BLENDSHAPES=true \
    AVATAR_MEDIAPIPE_NUM_FACES=2 \
    AVATAR_MEDIAPIPE_MIN_DETECTION_CONFIDENCE=0.6 \
    AVATAR_MEDIAPIPE_MIN_PRESENCE_CONFIDENCE=0.6 \
    AVATAR_INITIAL_CANDIDATE_COUNT=2 \
    AVATAR_EXTRA_CANDIDATE_COUNT=2 \
    AVATAR_MAX_TOTAL_CANDIDATES=4 \
    AVATAR_MIN_SAFE_CANDIDATES_BEFORE_EXTRA=2 \
    AVATAR_PREVIEW_COUNT=2 \
    AVATAR_MIN_PREVIEW_CANDIDATES=1 \
    AVATAR_PREVIEW_REQUIRE_FOUR=false \
    AVATAR_PREVIEW_FILL_WITH_SOFT_PASS=true \
    AVATAR_PREVIEW_FILL_HARD_REJECT=false \
    AVATAR_RERANK_PROVIDER=deterministic_qa_tier \
    AVATAR_QA_VISUAL_RISK_MODEL_ID=/app/models/qa/florence2 \
    AVATAR_CLIP_RISK_MODEL_ID=/app/models/qa/clip-large \
    AVATAR_QA_SIMILARITY_MODEL_ID=/app/models/qa/clip-base \
    AVATAR_REFERENCE_PROFILE=privacy_strict \
    AVATAR_QA_CALIBRATION_ARTIFACT_PATH=/app/avatar_generation/artifacts/avatar_qa_calibration_v1.json \
    AVATAR_QA_CALIBRATION_ARTIFACT_SHA256=6e949a49e90a6a843b01c601489b55411ed87df42675d3fbb4684c6ae428dee1 \
    AVATAR_QA_CALIBRATION_EXPECTED_MODELS_JSON="{\"clipSafety\":\"openai/clip-vit-large-patch14@32bd64288804d66eefd0ccbe215aa642df71cc41\",\"faceSimilarity\":\"openai/clip-vit-base-patch32@3d74acf9a28c67741b2f4f2ea7635f0aaf6f0268\"}" \
    AVATAR_QA_CALIBRATION_EXPECTED_PREPROCESSING_JSON="{\"qa\":\"avatar_qa_v2:transformers-4.57.6:pillow-11.3.0\",\"reference\":\"avatar_reference_preprocess_metadata_v1:privacy_strict_v1\"}"

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
    && python -c "from pathlib import Path; import urllib.request; url='https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_full_range/float16/latest/blaze_face_full_range.tflite'; target=Path('/app/models/blaze_face_full_range.tflite'); urllib.request.urlretrieve(url, target); assert target.stat().st_size >= 100 * 1024, 'Downloaded full-range FaceDetector asset is unexpectedly small.'" \
    && python -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='florence-community/Florence-2-large-ft', revision='${QA_FLORENCE_REVISION}', local_dir='/app/models/qa/florence2')" \
    && python -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='openai/clip-vit-large-patch14', revision='${QA_CLIP_LARGE_REVISION}', local_dir='/app/models/qa/clip-large')" \
    && python -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='openai/clip-vit-base-patch32', revision='${QA_CLIP_BASE_REVISION}', local_dir='/app/models/qa/clip-base')" \
    && python -c "from pathlib import Path; roots=[Path('/app/models/qa/florence2'), Path('/app/models/qa/clip-large'), Path('/app/models/qa/clip-base')]; assert all(root.is_dir() and any(root.iterdir()) for root in roots), 'Pinned QA model artifact is missing.'" \
    && printf '%s\n' "florence2=${QA_FLORENCE_REVISION}" "clip-large=${QA_CLIP_LARGE_REVISION}" "clip-base=${QA_CLIP_BASE_REVISION}" > /app/models/qa/ARTIFACT_REVISIONS.txt

ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

COPY lib/ai_recommend_model /app

RUN python -c "from avatar_generation.calibration_artifact import load_configured_calibration_artifact; artifact = load_configured_calibration_artifact(required=True); assert artifact.calibration_version == 'g004-staging-20260823-v1', 'Pinned QA calibration version mismatch.'"

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "1", "--timeout", "3600", "avatar_generation.worker_service:app"]
