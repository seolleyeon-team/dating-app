"""Single canonical source for the Azure QA pipeline-provenance contract.

`trait_policy._is_canonical_azure_contract` and
`unique_mark_policy.resolve_unique_mark_qa_state` decide applicability from
these server-side authority keys. Before this module existed, the worker,
the calibration/recovery service, and the persisted job provenance each
duplicated the dict by hand and drifted (G004 runtime attempt #3,
PIPELINE_PROVENANCE_DRIFT: `provider`/`pipelineMode`/`traitQaMode`/
`traitQaAuthority` missing on the recovery path, `provider` missing on the
worker candidate-QA path). Every QA metadata producer must build from here.
"""

from __future__ import annotations

from typing import Any, Dict

from .model_adapters.azure_contracts import AZURE_GPT_IMAGE_2_MODEL_ID

TRAIT_QA_MODE_DISABLED_BY_PIPELINE = "disabled_by_pipeline"
UNIQUE_MARK_QA_MODE_DISABLED_BY_PIPELINE = "disabled_by_pipeline"
QA_PROVENANCE_AUTHORITY_SERVER = "server"


def canonical_azure_qa_pipeline_contract() -> Dict[str, Any]:
    """Authority keys the v6 applicability policies require, exactly once."""

    return {
        "provider": "azure",
        "generationBackend": AZURE_GPT_IMAGE_2_MODEL_ID,
        "sourceInputMode": "storage_normalized_original_direct",
        "uploadNormalization": "existing_avatar_media_ingestion",
        "preGenerationTransform": "none",
        "pipelineMode": AZURE_GPT_IMAGE_2_MODEL_ID,
        "legacyTraitExtraction": False,
        "legacyReferencePreprocessing": False,
        "legacyFlux": False,
        "traitQaMode": TRAIT_QA_MODE_DISABLED_BY_PIPELINE,
        "traitQaAuthority": QA_PROVENANCE_AUTHORITY_SERVER,
        "uniqueMarkQaMode": UNIQUE_MARK_QA_MODE_DISABLED_BY_PIPELINE,
        "uniqueMarkQaAuthority": QA_PROVENANCE_AUTHORITY_SERVER,
    }
