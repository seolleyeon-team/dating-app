from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from avatar_generation.avatar_prompt_contract import AVATAR_GENERAL_PROMPT_VERSION
from avatar_generation.model_adapters.azure_contracts import (
    AZURE_GPT_IMAGE_2_MODEL_ID,
    AZURE_GPT_IMAGE_2_VERSION,
)
from avatar_generation.preview_policy import is_preview_eligible, passes_absolute_preview_checks
from avatar_generation.qa import AvatarQAResult
from avatar_generation.storage import build_approved_avatar_ref


def _timestamp(server_timestamp: Any = None) -> Any:
    return server_timestamp if server_timestamp is not None else datetime.now(tz=timezone.utc)


@dataclass(frozen=True)
class AvatarJobSpec:
    job_id: str
    uid: str
    source_photo_ids: List[str]
    source_photo_refs: List[str]
    candidate_count: int = 4


def build_avatar_job_doc(spec: AvatarJobSpec, *, server_timestamp: Any = None) -> Dict[str, Any]:
    now = _timestamp(server_timestamp)
    return {
        "jobId": spec.job_id,
        "uid": spec.uid,
        "model": {
            "provider": "azure",
            "modelId": AZURE_GPT_IMAGE_2_MODEL_ID,
            "version": AZURE_GPT_IMAGE_2_VERSION,
        },
        "generationBackend": AZURE_GPT_IMAGE_2_MODEL_ID,
        "provenance": {
            "sourceInputMode": "storage_normalized_original_direct",
            "uploadNormalization": "existing_avatar_media_ingestion",
            "preGenerationTransform": "none",
            "promptVersion": AVATAR_GENERAL_PROMPT_VERSION,
            "legacyTraitExtraction": False,
            "legacyReferencePreprocessing": False,
            "legacyFlux": False,
            "uniqueMarkQaMode": "disabled_by_pipeline",
            "uniqueMarkQaAuthority": "server",
        },
        "sourcePhotoIds": list(spec.source_photo_ids),
        "sourcePhotoRefs": list(spec.source_photo_refs),
        "candidateCount": int(spec.candidate_count),
        "status": "queued",
        "createdAt": now,
        "updatedAt": now,
        "privacyMode": {
            "preserveBroadCues": True,
            "preserveExactIdentity": False,
            "beautification": 0.0,
            "target": "medium_resemblance_not_biometric_copy",
        },
    }


def build_candidate_doc(
    *,
    candidate_id: str,
    job_id: str,
    uid: str,
    image_ref: str,
    qa: Optional[AvatarQAResult] = None,
    preview_url: str = "",
    server_timestamp: Any = None,
) -> Dict[str, Any]:
    qa_doc = (qa or AvatarQAResult()).to_document()
    if qa_doc.get("rejectReasons"):
        status = "rejected"
    elif qa_doc.get("requiresHumanReview") is True:
        status = "needs_review"
    elif qa_doc.get("previewAllowed") is True and is_preview_eligible(
        {"status": "preview_ready", "qa": qa_doc}
    ):
        status = "preview_ready"
    elif (
        qa_doc.get("softPass") is True
        and passes_absolute_preview_checks({"status": "soft_pass", "qa": qa_doc})
    ):
        status = "soft_pass"
    else:
        status = "needs_review"
    return {
        "candidateId": candidate_id,
        "jobId": job_id,
        "uid": uid,
        "imageRef": image_ref,
        "previewUrl": preview_url,
        "qa": qa_doc,
        "status": status,
        "createdAt": _timestamp(server_timestamp),
    }


def build_avatar_approval_updates(
    *,
    uid: str,
    job_id: str,
    candidate_id: str,
    avatar_id: str,
    approved_avatar_url: str,
    server_timestamp: Any = None,
    write_legacy_photo_urls: bool = False,
) -> Dict[str, Dict[str, Any]]:
    now = _timestamp(server_timestamp)
    approved_ref = build_approved_avatar_ref(uid=uid, avatar_id=avatar_id)
    onboarding: Dict[str, Any] = {"avatarUrls": [approved_avatar_url]}
    if write_legacy_photo_urls:
        onboarding["photoUrls"] = [approved_avatar_url]
    return {
        "users": {
            "profileImageMode": "avatar",
            "avatar": {
                "status": "approved",
                "approvedAvatarUrl": approved_avatar_url,
                "approvedAvatarStoragePath": approved_ref,
                "avatarId": avatar_id,
                "selectedCandidateId": candidate_id,
                "sourceJobId": job_id,
                "updatedAt": now,
            },
            "onboarding": onboarding,
        },
        "avatarJobs": {
            "status": "approved",
            "updatedAt": now,
        },
        "avatarCandidates": {
            "status": "approved",
        },
    }


def build_rejected_candidate_cleanup_refs(candidates: Iterable[Dict[str, Any]]) -> List[str]:
    return [
        str(candidate.get("imageRef"))
        for candidate in candidates
        if candidate.get("status") == "rejected" and candidate.get("imageRef")
    ]
