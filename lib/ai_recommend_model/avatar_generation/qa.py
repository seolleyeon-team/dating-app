from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import io
import math
import os
from pathlib import Path
import re
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
from urllib.parse import unquote, urlparse

from PIL import Image, ImageChops, ImageStat


try:  # Pillow 10+ exposes resampling enums.
    _LANCZOS = Image.Resampling.LANCZOS
except AttributeError:  # pragma: no cover - kept for older local Pillow builds
    _LANCZOS = Image.LANCZOS


AUTO_REJECT_REASONS = {
    "blank_or_monochrome_image",
    "childlike_or_teenager",
    "corrupt_image",
    "too_identifiable",
    "unique_mark_copied",
    "idol_model_influencer_look",
    "too_beautified",
    "crop_expanded_to_unseen_body",
    "image_aspect_invalid",
    "image_dimensions_invalid",
    "logo_text_watermark",
    "not_adult_university_student_tone",
    "signed_url_marker",
    "source_candidate_identical",
    "undecodable_image",
}

SIGNED_URL_MARKERS = (
    "x-goog-signature",
    "x-goog-credential",
    "x-goog-expires",
    "googleaccessid",
    "signature=",
    "signedurl",
    "getsignedurl",
    "x-amz-signature",
    "x-amz-credential",
    "x-amz-expires",
)

TEXT_WATERMARK_MARKERS = (
    "watermark",
    "text overlay",
    "text-overlay",
    "logo overlay",
    "visible logo",
)

MIN_IMAGE_SIDE = 32
MAX_IMAGE_SIDE = 8192
MIN_ASPECT_RATIO = 0.40
MAX_ASPECT_RATIO = 2.50
BLANK_STDDEV_THRESHOLD = 4.0
BLANK_CHANNEL_RANGE_THRESHOLD = 8
COMPARE_SIZE = 64
HASH_SIZE = 16


@dataclass(frozen=True)
class AvatarQAThresholds:
    face_similarity_reject: float = 0.65
    face_similarity_review: float = 0.50
    childlike_reject: float = 0.70
    childlike_review: float = 0.45
    beautification_reject: float = 0.75
    beautification_review: float = 0.50


@dataclass
class AvatarQAResult:
    adultQa: str = "needs_review"
    childlikeRisk: str = "medium"
    privacyQa: str = "needs_review"
    brandQa: str = "needs_review"
    beautificationRisk: str = "medium"
    cropConsistency: str = "needs_review"
    uniqueMarkCopyRisk: str = "medium"
    logoTextWatermarkRisk: str = "medium"
    faceSimilarityScore: Optional[float] = None
    identifiabilityRisk: str = "medium"
    previewAllowed: bool = False
    requiresHumanReview: bool = True
    qaVersion: str = "avatar_qa_v1"
    completedAt: Optional[str] = None
    rejectReasons: List[str] = field(default_factory=list)

    def to_document(self) -> Dict[str, object]:
        return {
            "adultQa": self.adultQa,
            "childlikeRisk": self.childlikeRisk,
            "privacyQa": self.privacyQa,
            "brandQa": self.brandQa,
            "beautificationRisk": self.beautificationRisk,
            "cropConsistency": self.cropConsistency,
            "uniqueMarkCopyRisk": self.uniqueMarkCopyRisk,
            "logoTextWatermarkRisk": self.logoTextWatermarkRisk,
            "faceSimilarityScore": (
                None if self.faceSimilarityScore is None else float(self.faceSimilarityScore)
            ),
            "identifiabilityRisk": self.identifiabilityRisk,
            "previewAllowed": bool(self.previewAllowed),
            "requiresHumanReview": bool(self.requiresHumanReview),
            "rejectReasons": list(self.rejectReasons),
            "qaVersion": self.qaVersion,
            "completedAt": self.completedAt
            or datetime.now(tz=timezone.utc).isoformat(),
        }

    @property
    def is_rejected(self) -> bool:
        return bool(set(self.rejectReasons) & AUTO_REJECT_REASONS)


@dataclass(frozen=True)
class LoadedImage:
    image: Optional[Image.Image]
    unavailable: bool = False
    reject_reason: Optional[str] = None


def apply_avatar_qa_rejection_logic(result: AvatarQAResult) -> AvatarQAResult:
    reasons = set(result.rejectReasons)
    if result.adultQa == "fail" or result.childlikeRisk == "high":
        reasons.add("childlike_or_teenager")
    if result.privacyQa == "fail" or result.identifiabilityRisk == "high":
        reasons.add("too_identifiable")
    if result.uniqueMarkCopyRisk == "high":
        reasons.add("unique_mark_copied")
    if result.beautificationRisk == "high":
        reasons.add("too_beautified")
    if result.cropConsistency == "fail":
        reasons.add("crop_expanded_to_unseen_body")
    if result.logoTextWatermarkRisk == "high":
        reasons.add("logo_text_watermark")
    if result.brandQa == "fail":
        reasons.add("not_adult_university_student_tone")
    result.rejectReasons = sorted(reasons)
    if result.rejectReasons:
        result.previewAllowed = False
        result.requiresHumanReview = False
    elif (
        result.adultQa == "pass"
        and result.privacyQa == "pass"
        and result.brandQa == "pass"
        and result.childlikeRisk == "low"
        and result.beautificationRisk == "low"
        and result.identifiabilityRisk == "low"
        and result.cropConsistency == "pass"
        and result.logoTextWatermarkRisk == "low"
    ):
        result.previewAllowed = True
        result.requiresHumanReview = False
    else:
        result.previewAllowed = False
        result.requiresHumanReview = True
    return result


def qa_thresholds_from_env() -> AvatarQAThresholds:
    def read_float(name: str, fallback: float) -> float:
        raw = os.environ.get(name)
        if raw is None:
            return fallback
        try:
            return float(raw)
        except ValueError:
            return fallback

    return AvatarQAThresholds(
        face_similarity_reject=read_float(
            "AVATAR_QA_FACE_SIMILARITY_REJECT_THRESHOLD", 0.65
        ),
        face_similarity_review=read_float(
            "AVATAR_QA_FACE_SIMILARITY_REVIEW_THRESHOLD", 0.50
        ),
        childlike_reject=read_float("AVATAR_QA_CHILDLIKE_REJECT_THRESHOLD", 0.70),
        childlike_review=read_float("AVATAR_QA_CHILDLIKE_REVIEW_THRESHOLD", 0.45),
        beautification_reject=read_float(
            "AVATAR_QA_BEAUTIFICATION_REJECT_THRESHOLD", 0.75
        ),
        beautification_review=read_float(
            "AVATAR_QA_BEAUTIFICATION_REVIEW_THRESHOLD", 0.50
        ),
    )


def _score(value: Any) -> Optional[float]:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _risk_from_score(
    score: Optional[float],
    *,
    review_threshold: float,
    reject_threshold: float,
) -> str:
    if score is None:
        return "medium"
    if score >= reject_threshold:
        return "high"
    if score >= review_threshold:
        return "medium"
    return "low"


def _qa_status_from_bool(pass_value: Any, fail_value: Any = None) -> str:
    if fail_value is True:
        return "fail"
    if pass_value is True:
        return "pass"
    if pass_value is False:
        return "needs_review"
    return "needs_review"


def _truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _is_production_environment() -> bool:
    return os.environ.get("ENVIRONMENT", "").strip().lower() in {"prod", "production"}


def _dev_bypass_allowed() -> bool:
    return _truthy_env("AVATAR_QA_ALLOW_DEV_BYPASS") and not _is_production_environment()


def _staging_heuristic_preview_allowed() -> bool:
    return (
        _truthy_env("AVATAR_QA_ALLOW_STAGING_HEURISTIC_PREVIEW")
        and not _is_production_environment()
    )


def _iter_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for key, child in value.items():
            if isinstance(key, str):
                yield key
            yield from _iter_strings(child)
    elif isinstance(value, (list, tuple, set)):
        for child in value:
            yield from _iter_strings(child)


def _contains_signed_url_marker(*values: Any) -> bool:
    for text in _iter_strings(values):
        lowered = text.lower()
        if any(marker in lowered for marker in SIGNED_URL_MARKERS):
            return True
    return False


def _contains_text_watermark_marker(metadata: Mapping[str, Any], refs: Sequence[str]) -> bool:
    for ref in refs:
        lowered_ref = str(ref).lower()
        if any(marker in lowered_ref for marker in TEXT_WATERMARK_MARKERS):
            return True

    def walk(value: Any) -> bool:
        if isinstance(value, Mapping):
            for key, child in value.items():
                lowered_key = str(key).lower()
                if (
                    any(marker in lowered_key for marker in TEXT_WATERMARK_MARKERS)
                    and child is True
                ):
                    return True
                if walk(child):
                    return True
            return False
        if isinstance(value, str):
            lowered_value = value.lower()
            return any(marker in lowered_value for marker in TEXT_WATERMARK_MARKERS)
        if isinstance(value, (list, tuple, set)):
            return any(walk(child) for child in value)
        return False

    return walk(metadata)


def _parse_gcs_ref(ref: str) -> Optional[Tuple[str, str]]:
    match = re.match(r"^(?:gs|gcs)://([^/]+)/(.+)$", ref.strip())
    if not match:
        return None
    bucket = match.group(1).strip()
    path = match.group(2).strip()
    if not bucket or not path or path.startswith("/") or ".." in path.split("/"):
        return None
    return bucket, path


def _local_path_from_ref(ref: str) -> Optional[Path]:
    if re.match(r"^[A-Za-z]:[\\/]", ref):
        return Path(ref)
    parsed = urlparse(ref)
    if parsed.scheme == "file":
        path = unquote(parsed.path)
        if re.match(r"^/[A-Za-z]:", path):
            path = path[1:]
        return Path(path)
    if parsed.scheme and parsed.scheme not in {"", "file"}:
        return None
    return Path(ref)


def _read_gcs_bytes(ref: str, metadata: Mapping[str, Any]) -> Optional[bytes]:
    parsed = _parse_gcs_ref(ref)
    if parsed is None:
        return None
    bucket_name, object_path = parsed
    storage_client = metadata.get("storageClient") or metadata.get("_storage_client")
    if storage_client is None:
        try:
            from google.cloud import storage

            storage_client = storage.Client()
        except Exception:
            return None
    try:
        blob = storage_client.bucket(bucket_name).blob(object_path)
        if hasattr(blob, "exists") and not blob.exists():
            return None
        return blob.download_as_bytes()
    except Exception:
        return None


def _read_local_bytes(ref: str) -> Optional[bytes]:
    path = _local_path_from_ref(ref)
    if path is None or not path.is_file():
        return None
    try:
        return path.read_bytes()
    except OSError:
        return None


def _read_image_bytes(ref: str, metadata: Mapping[str, Any]) -> Optional[bytes]:
    if _parse_gcs_ref(ref) is not None:
        return _read_gcs_bytes(ref, metadata)
    return _read_local_bytes(ref)


def _load_image(ref: str, metadata: Mapping[str, Any]) -> LoadedImage:
    data = _read_image_bytes(ref, metadata)
    if data is None:
        return LoadedImage(image=None, unavailable=True)
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            return LoadedImage(image=image.convert("RGB"))
    except Exception:
        return LoadedImage(image=None, reject_reason="undecodable_image")


def _is_blank_or_monochrome(image: Image.Image) -> bool:
    sample = image.convert("RGB").resize((COMPARE_SIZE, COMPARE_SIZE), _LANCZOS)
    stat = ImageStat.Stat(sample)
    mean_stddev = sum(float(value) for value in stat.stddev[:3]) / 3.0
    max_channel_range = max(int(high - low) for low, high in stat.extrema[:3])
    return (
        mean_stddev < BLANK_STDDEV_THRESHOLD
        or max_channel_range < BLANK_CHANNEL_RANGE_THRESHOLD
    )


def _image_validation_reasons(image: Image.Image) -> List[str]:
    width, height = image.size
    reasons: List[str] = []
    if (
        width < MIN_IMAGE_SIDE
        or height < MIN_IMAGE_SIDE
        or width > MAX_IMAGE_SIDE
        or height > MAX_IMAGE_SIDE
    ):
        reasons.append("image_dimensions_invalid")
    else:
        aspect = width / float(height)
        if aspect < MIN_ASPECT_RATIO or aspect > MAX_ASPECT_RATIO:
            reasons.append("image_aspect_invalid")
    if _is_blank_or_monochrome(image):
        reasons.append("blank_or_monochrome_image")
    return reasons


def _images_exactly_equal(source: Image.Image, candidate: Image.Image) -> bool:
    if source.size != candidate.size:
        return False
    return ImageChops.difference(source.convert("RGB"), candidate.convert("RGB")).getbbox() is None


def _average_hash(image: Image.Image) -> List[bool]:
    sample = image.convert("L").resize((HASH_SIZE, HASH_SIZE), _LANCZOS)
    if hasattr(sample, "get_flattened_data"):
        pixels = list(sample.get_flattened_data())
    else:  # pragma: no cover - older Pillow compatibility
        pixels = list(sample.getdata())
    average = sum(pixels) / float(len(pixels))
    return [pixel >= average for pixel in pixels]


def _hash_similarity(source: Image.Image, candidate: Image.Image) -> float:
    source_hash = _average_hash(source)
    candidate_hash = _average_hash(candidate)
    hamming = sum(1 for left, right in zip(source_hash, candidate_hash) if left != right)
    return 1.0 - (hamming / float(len(source_hash)))


def _image_similarity_score(source: Image.Image, candidate: Image.Image) -> float:
    source_cmp = source.convert("RGB").resize((COMPARE_SIZE, COMPARE_SIZE), _LANCZOS)
    candidate_cmp = candidate.convert("RGB").resize((COMPARE_SIZE, COMPARE_SIZE), _LANCZOS)
    diff = ImageChops.difference(source_cmp, candidate_cmp)
    stat = ImageStat.Stat(diff)
    channel_rms = math.sqrt(sum(float(value) ** 2 for value in stat.rms[:3]) / 3.0)
    difference_similarity = max(0.0, min(1.0, 1.0 - (channel_rms / 255.0)))
    perceptual_similarity = _hash_similarity(source_cmp, candidate_cmp)
    score = (difference_similarity * 0.75) + (perceptual_similarity * 0.25)
    return round(max(0.0, min(1.0, score)), 4)


def _hard_reject_result(
    reasons: Iterable[str],
    *,
    face_similarity_score: Optional[float] = None,
) -> AvatarQAResult:
    reason_set = set(reasons)
    identifiable = bool({"too_identifiable", "source_candidate_identical"} & reason_set)
    result = AvatarQAResult(
        adultQa="needs_review",
        childlikeRisk="medium",
        privacyQa="fail" if identifiable else "needs_review",
        brandQa="needs_review",
        beautificationRisk="medium",
        cropConsistency="needs_review",
        uniqueMarkCopyRisk="unknown",
        logoTextWatermarkRisk=(
            "high" if "logo_text_watermark" in reason_set else "medium"
        ),
        faceSimilarityScore=face_similarity_score,
        identifiabilityRisk="high" if identifiable else "medium",
        previewAllowed=False,
        requiresHumanReview=False,
        qaVersion="avatar_qa_v1",
        rejectReasons=sorted(reason_set),
    )
    return apply_avatar_qa_rejection_logic(result)


def _dev_bypass_result() -> AvatarQAResult:
    result = build_avatar_qa_from_signals(
        {
            "adultLike": True,
            "brandFit": True,
            "cropConsistent": True,
            "logoTextWatermarkDetected": False,
            "uniqueMarkCopied": False,
            "faceSimilarityScore": 0.0,
            "childlikeScore": 0.0,
            "beautificationScore": 0.0,
        }
    )
    result.qaVersion = "avatar_qa_v1_dev_bypass"
    return result


def _staging_heuristic_preview_result(
    *,
    face_similarity_score: Optional[float],
    text_watermark_detected: bool,
    thresholds: AvatarQAThresholds,
) -> AvatarQAResult:
    result = build_avatar_qa_from_signals(
        {
            "adultLike": True,
            "brandFit": True,
            "cropConsistent": True,
            "logoTextWatermarkDetected": text_watermark_detected,
            "uniqueMarkCopied": False,
            "faceSimilarityScore": face_similarity_score,
            "childlikeScore": 0.05,
            "beautificationScore": 0.05,
        },
        thresholds=thresholds,
    )
    result.qaVersion = "avatar_qa_v1_staging_heuristic_preview"
    return result


def _merge_local_signals(
    signals: Optional[Mapping[str, Any]],
    *,
    face_similarity_score: Optional[float],
    text_watermark_detected: bool,
) -> Dict[str, Any]:
    merged: Dict[str, Any] = dict(signals or {})
    if face_similarity_score is not None:
        existing_score = _score(merged.get("faceSimilarityScore"))
        merged["faceSimilarityScore"] = max(
            face_similarity_score,
            existing_score if existing_score is not None else 0.0,
        )
    if text_watermark_detected:
        merged["logoTextWatermarkDetected"] = True
    return merged


def _model_unavailable_with_local_similarity(
    face_similarity_score: Optional[float],
    *,
    thresholds: AvatarQAThresholds,
) -> AvatarQAResult:
    result = needs_review_model_unavailable_result()
    result.faceSimilarityScore = face_similarity_score
    if face_similarity_score is not None:
        result.identifiabilityRisk = _risk_from_score(
            face_similarity_score,
            review_threshold=thresholds.face_similarity_review,
            reject_threshold=thresholds.face_similarity_reject,
        )
    return result


def build_avatar_qa_from_signals(
    signals: Mapping[str, Any],
    *,
    thresholds: Optional[AvatarQAThresholds] = None,
) -> AvatarQAResult:
    """Convert local model/heuristic signals into the persisted QA contract.

    `signals` is deliberately generic so PR6 can accept outputs from local CLIP,
    OCR, face/crop detectors, or deterministic tests without storing raw
    embeddings. Scores are decision inputs only; raw embeddings must not be
    included in the returned document.
    """
    t = thresholds or qa_thresholds_from_env()
    face_similarity = _score(signals.get("faceSimilarityScore"))
    childlike_score = _score(signals.get("childlikeScore"))
    beautification_score = _score(signals.get("beautificationScore"))

    childlike_risk = _risk_from_score(
        childlike_score,
        review_threshold=t.childlike_review,
        reject_threshold=t.childlike_reject,
    )
    identifiability_risk = _risk_from_score(
        face_similarity,
        review_threshold=t.face_similarity_review,
        reject_threshold=t.face_similarity_reject,
    )
    beautification_risk = _risk_from_score(
        beautification_score,
        review_threshold=t.beautification_review,
        reject_threshold=t.beautification_reject,
    )

    reject_reasons: List[str] = []
    if signals.get("uniqueMarkCopied") is True:
        reject_reasons.append("unique_mark_copied")
    if signals.get("idolModelInfluencerLook") is True:
        reject_reasons.append("idol_model_influencer_look")
    if signals.get("cropExpandedToUnseenBody") is True:
        reject_reasons.append("crop_expanded_to_unseen_body")
    if signals.get("logoTextWatermarkDetected") is True:
        reject_reasons.append("logo_text_watermark")
    if signals.get("notAdultUniversityStudentTone") is True:
        reject_reasons.append("not_adult_university_student_tone")

    adult_qa = _qa_status_from_bool(
        signals.get("adultLike"),
        signals.get("childlikeOrTeenager") is True or childlike_risk == "high",
    )
    privacy_qa = "fail" if identifiability_risk == "high" else (
        "needs_review" if identifiability_risk == "medium" else "pass"
    )
    brand_qa = "fail" if (
        signals.get("idolModelInfluencerLook") is True
        or signals.get("notAdultUniversityStudentTone") is True
        or signals.get("sexualizedOrNightlife") is True
    ) else _qa_status_from_bool(signals.get("brandFit"))

    logo_risk = "high" if signals.get("logoTextWatermarkDetected") is True else (
        "low" if signals.get("logoTextWatermarkDetected") is False else "medium"
    )
    unique_mark_risk = "high" if signals.get("uniqueMarkCopied") is True else (
        "low" if signals.get("uniqueMarkCopied") is False else "unknown"
    )
    crop_consistency = "fail" if signals.get("cropExpandedToUnseenBody") is True else (
        "pass" if signals.get("cropConsistent") is True else "needs_review"
    )

    result = AvatarQAResult(
        adultQa=adult_qa,
        childlikeRisk=childlike_risk,
        privacyQa=privacy_qa,
        brandQa=brand_qa,
        beautificationRisk=beautification_risk,
        cropConsistency=crop_consistency,
        uniqueMarkCopyRisk=unique_mark_risk,
        logoTextWatermarkRisk=logo_risk,
        faceSimilarityScore=face_similarity,
        identifiabilityRisk=identifiability_risk,
        qaVersion="avatar_qa_v1",
        rejectReasons=reject_reasons,
    )
    return apply_avatar_qa_rejection_logic(result)


def needs_review_model_unavailable_result() -> AvatarQAResult:
    return AvatarQAResult(
        adultQa="needs_review",
        childlikeRisk="medium",
        privacyQa="needs_review",
        brandQa="needs_review",
        beautificationRisk="medium",
        cropConsistency="needs_review",
        uniqueMarkCopyRisk="unknown",
        logoTextWatermarkRisk="medium",
        identifiabilityRisk="medium",
        previewAllowed=False,
        requiresHumanReview=True,
        qaVersion="avatar_qa_v1_model_unavailable",
        rejectReasons=[],
    )


def run_avatar_candidate_qa(
    source_image_ref: str,
    candidate_image_ref: str,
    metadata: Dict[str, Any],
) -> AvatarQAResult:
    """Run best-effort local QA and return the persisted safety contract."""
    qa_metadata: Mapping[str, Any] = metadata if isinstance(metadata, Mapping) else {}
    thresholds = qa_thresholds_from_env()
    if _contains_signed_url_marker(source_image_ref, candidate_image_ref, qa_metadata):
        return _hard_reject_result(["signed_url_marker"])

    source = _load_image(source_image_ref, qa_metadata)
    candidate = _load_image(candidate_image_ref, qa_metadata)
    decode_reasons = {
        reason
        for reason in (source.reject_reason, candidate.reject_reason)
        if reason is not None
    }
    if decode_reasons:
        return _hard_reject_result(decode_reasons)
    if source.image is None or candidate.image is None:
        if _dev_bypass_allowed():
            return _dev_bypass_result()
        return needs_review_model_unavailable_result()

    hard_reasons = set(_image_validation_reasons(source.image))
    hard_reasons.update(_image_validation_reasons(candidate.image))

    face_similarity_score: Optional[float] = None
    if not hard_reasons:
        if _images_exactly_equal(source.image, candidate.image):
            face_similarity_score = 1.0
            hard_reasons.update({"source_candidate_identical", "too_identifiable"})
        else:
            face_similarity_score = _image_similarity_score(source.image, candidate.image)
            if face_similarity_score >= thresholds.face_similarity_reject:
                hard_reasons.add("too_identifiable")

    text_watermark_detected = _contains_text_watermark_marker(
        qa_metadata,
        [source_image_ref, candidate_image_ref],
    )
    if text_watermark_detected:
        hard_reasons.add("logo_text_watermark")

    if hard_reasons:
        return _hard_reject_result(
            hard_reasons,
            face_similarity_score=face_similarity_score,
        )

    raw_signals = qa_metadata.get("qaSignals") or qa_metadata.get("signals")
    signals = raw_signals if isinstance(raw_signals, Mapping) else None
    if signals is None and _staging_heuristic_preview_allowed():
        return _staging_heuristic_preview_result(
            face_similarity_score=face_similarity_score,
            text_watermark_detected=text_watermark_detected,
            thresholds=thresholds,
        )
    merged_signals = _merge_local_signals(
        signals,
        face_similarity_score=face_similarity_score,
        text_watermark_detected=text_watermark_detected,
    )
    if qa_metadata.get("modelsUnavailable") is True:
        return _model_unavailable_with_local_similarity(
            face_similarity_score,
            thresholds=thresholds,
        )
    return build_avatar_qa_from_signals(merged_signals, thresholds=thresholds)
