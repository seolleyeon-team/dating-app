from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
AI_MODEL_DIR = REPO_ROOT / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

from avatar_generation.jobs import AvatarJobSpec, build_avatar_job_doc  # noqa: E402


def test_python_job_builder_emits_canonical_azure_model_and_provenance():
    document = build_avatar_job_doc(
        AvatarJobSpec(
            job_id="job-1",
            uid="user-1",
            source_photo_ids=["photo-1"],
            source_photo_refs=["gs://private/source.jpg"],
        )
    )

    assert document["model"] == {
        "provider": "azure",
        "modelId": "azure_gpt_image_2",
        "version": "gpt-image-2",
    }
    assert document["generationBackend"] == "azure_gpt_image_2"
    assert document["provenance"] == {
        "sourceInputMode": "storage_normalized_original_direct",
        "uploadNormalization": "existing_avatar_media_ingestion",
        "preGenerationTransform": "none",
        "promptVersion": "avatar_general_prompt_v1",
        "legacyTraitExtraction": False,
        "legacyReferencePreprocessing": False,
        "legacyFlux": False,
        # avatar_qa_v6 unique-mark applicability: the canonical Azure pipeline
        # has no unique-mark producer, so provenance declares the server-owned
        # disabled_by_pipeline mode instead of leaving it ambiguous.
        "uniqueMarkQaAuthority": "server",
        "uniqueMarkQaMode": "disabled_by_pipeline",
    }
