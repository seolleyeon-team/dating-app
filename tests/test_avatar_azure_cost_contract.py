from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
AI_MODEL_DIR = REPO_ROOT / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

from avatar_generation.cost import (  # noqa: E402
    build_batch_cost_document,
    build_job_cost_document,
)


def test_azure_cost_document_does_not_charge_the_legacy_gpu_component():
    document = build_job_cost_document(
        duration_seconds=10.0,
        generation_backend="azure_gpt_image_2",
        provider_usage={
            "requestCount": 2,
            "attemptCount": 2,
            "successCount": 1,
            "failureCount": 0,
            "unknownOutcomeCount": 0,
        },
    )

    assert document["costEstimate"]["generationBackend"] == "azure_gpt_image_2"
    assert document["costEstimate"]["breakdown"]["gpuChargeApplied"] is False
    assert document["costEstimate"]["breakdown"]["gpuUsd"] == 0.0
    assert document["providerUsage"]["requestCount"] == 2
    assert document["providerUsage"]["successCount"] == 1


def test_azure_batch_cost_document_keeps_gpu_charge_zero():
    document = build_batch_cost_document(
        [
            {
                "status": "preview_ready",
                "candidateCount": 1,
                "generationBackend": "azure_gpt_image_2",
                "durationSeconds": 10.0,
            },
            {
                "status": "preview_ready",
                "candidateCount": 1,
                "generationBackend": "azure_gpt_image_2",
                "durationSeconds": 10.0,
            },
        ],
        duration_seconds=10.0,
    )

    assert document["batchCostEstimate"]["totalCost"]["breakdown"]["generationBackend"] == "azure_gpt_image_2"
    assert document["batchCostEstimate"]["totalCost"]["breakdown"]["gpuChargeApplied"] is False
    assert document["batchCostEstimate"]["totalCost"]["breakdown"]["gpuUsd"] == 0.0
