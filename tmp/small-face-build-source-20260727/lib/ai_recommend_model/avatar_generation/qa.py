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

from .qa_signals import CandidateQASignalResult


try:  # Pillow 10+ exposes resampling enums.
    _LANCZOS = Image.Resampling.LANCZOS
except AttributeError:  # pragma: no cover - kept for older local Pillow builds
    _LANCZOS = Image.LANCZOS


AUTO_REJECT_REASONS = {
    "background_leakage",
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
    "no_face_generated",
    "logo_text_watermark",
    "multiple_faces_generated",
    "not_adult_university_student_tone",
    "secondary_face_leakage",
    "secondary_person_generated",
    "sexualized_or_nightlife",
    "severe_artifact",
    "hard_trait_contradiction",
    "signed_url_marker",
    "source_candidate_identical",
    "source_candidate_near_duplicate",
    "undecodable_image",
    "eyewear_invented_or_omitted",
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
    "brand logo",
    "campus sign",
    "large text",
    "logo text",
    "watermark",
    "school name",
    "school sign",
    "text overlay",
    "text-overlay",
    "text logo",
    "logo overlay",
    "visible logo",
)

DEBUG_FORBIDDEN_KEYS = {
    "clipembeddings",
    "downloadurl",
    "downloadurls",
    "gcsuri",
    "gcsuris",
    "image_ref",
    "imageref",
    "privatebucket",
    "previewurl",
    "previewurls",
    "signedurl",
    "signedurls",
    "sourcephotogcsuri",
    "sourcephotogcsuris",
    "sourcephotoref",
    "sourcephotorefs",
    "userprivatemedia",
}

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
    perceptual_near_duplicate_reject: float = 0.985
    perceptual_review: float = 0.92
    allow_perceptual_hard_reject_only_near_duplicate: bool = True
    require_reliable_face_similarity_for_too_identifiable: bool = True
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
    cropIsolationQuality: str = "pass"
    uniqueMarkCopyRisk: str = "medium"
    logoTextWatermarkRisk: str = "medium"
    textLogoWatermarkRisk: str = "low"
    backgroundLeakageRisk: str = "low"
    secondaryFaceLeakageRisk: str = "low"
    faceSimilarityScore: Optional[float] = None
    primaryFaceConfidence: Optional[float] = None
    identifiabilityRisk: str = "medium"
    previewAllowed: bool = False
    requiresHumanReview: bool = True
    softPass: bool = False
    qaVersion: str = "avatar_qa_v1"
    completedAt: Optional[str] = None
    rejectReasons: List[str] = field(default_factory=list)
    reviewReasons: List[str] = field(default_factory=list)
    softPassReasons: List[str] = field(default_factory=list)
    candidateTraitConsistency: Dict[str, Any] = field(default_factory=dict)
    debug: Dict[str, Any] = field(default_factory=dict)

    def to_document(self) -> Dict[str, object]:
        return {
            "adultQa": self.adultQa,
            "childlikeRisk": self.childlikeRisk,
            "privacyQa": self.privacyQa,
            "brandQa": self.brandQa,
            "beautificationRisk": self.beautificationRisk,
            "cropConsistency": self.cropConsistency,
            "cropIsolationQuality": self.cropIsolationQuality,
            "uniqueMarkCopyRisk": self.uniqueMarkCopyRisk,
            "logoTextWatermarkRisk": self.logoTextWatermarkRisk,
            "textLogoWatermarkRisk": self.textLogoWatermarkRisk,
            "backgroundLeakageRisk": self.backgroundLeakageRisk,
            "secondaryFaceLeakageRisk": self.secondaryFaceLeakageRisk,
            "faceSimilarityScore": (
                None if self.faceSimilarityScore is None else float(self.faceSimilarityScore)
            ),
            "primaryFaceConfidence": (
                None if self.primaryFaceConfidence is None else float(self.primaryFaceConfidence)
            ),
            "identifiabilityRisk": self.identifiabilityRisk,
            "previewAllowed": bool(self.previewAllowed),
            "requiresHumanReview": bool(self.requiresHumanReview),
            "softPass": bool(self.softPass),
            "rejectReasons": list(self.rejectReasons),
            "reviewReasons": list(self.reviewReasons),
            "softPassReasons": list(self.softPassReasons),
            "candidateTraitConsistency": _sanitize_debug_value(
                dict(self.candidateTraitConsistency or {})
            ),
            "qaVersion": self.qaVersion,
            "completedAt": self.completedAt
            or datetime.now(tz=timezone.utc).isoformat(),
            "debug": _sanitize_debug_value(dict(self.debug or {})),
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
    if (
        result.cropConsistency == "fail" or result.cropIsolationQuality == "fail"
    ) and "severe_artifact" not in reasons:
        reasons.add("crop_expanded_to_unseen_body")
    if _risk_is_high(result.logoTextWatermarkRisk) or _risk_is_high(
        result.textLogoWatermarkRisk
    ):
        reasons.add("logo_text_watermark")
    if _risk_is_high(result.backgroundLeakageRisk):
        reasons.add("background_leakage")
    if _risk_is_high(result.secondaryFaceLeakageRisk):
        reasons.add("secondary_face_leakage")
    if result.brandQa == "fail" and "sexualized_or_nightlife" not in reasons:
        reasons.add("not_adult_university_student_tone")
    result.rejectReasons = sorted(reasons)
    if result.rejectReasons:
        result.previewAllowed = False
        result.requiresHumanReview = False
        result.softPass = False
    elif result.softPass:
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
        and result.cropIsolationQuality == "pass"
        and result.logoTextWatermarkRisk == "low"
        and result.textLogoWatermarkRisk == "low"
        and result.backgroundLeakageRisk == "low"
        and result.secondaryFaceLeakageRisk == "low"
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

    def read_bool(name: str, fallback: bool) -> bool:
        raw = os.environ.get(name)
        if raw is None:
            return fallback
        normalized = raw.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "no", "n", "off"}:
            return False
        return fallback

    return AvatarQAThresholds(
        face_similarity_reject=read_float(
            "AVATAR_QA_FACE_SIMILARITY_REJECT_THRESHOLD", 0.65
        ),
        face_similarity_review=read_float(
            "AVATAR_QA_FACE_SIMILARITY_REVIEW_THRESHOLD", 0.50
        ),
        perceptual_near_duplicate_reject=read_float(
            "AVATAR_QA_PHASH_NEAR_DUPLICATE_REJECT_THRESHOLD", 0.985
        ),
        perceptual_review=read_float(
            "AVATAR_QA_PHASH_REVIEW_THRESHOLD", 0.92
        ),
        allow_perceptual_hard_reject_only_near_duplicate=read_bool(
            "AVATAR_QA_ALLOW_PHASH_HARD_REJECT_ONLY_NEAR_DUPLICATE", True
        ),
        require_reliable_face_similarity_for_too_identifiable=read_bool(
            "AVATAR_QA_REQUIRE_RELIABLE_FACE_SIM_FOR_TOO_IDENTIFIABLE", True
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


def _sanitize_debug_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _sanitize_debug_value(child)
            for key, child in value.items()
            if _normalized_debug_key(str(key)) not in DEBUG_FORBIDDEN_KEYS
        }
    if isinstance(value, list):
        return [_sanitize_debug_value(child) for child in value]
    if isinstance(value, str):
        lowered = value.lower()
        if (
            lowered.startswith(("gs://", "gcs://"))
            or "seolleyeon-private-source-photos" in lowered
            or "seolleyeon-final-private-source-photos" in lowered
            or "seolleyeon-avatar-temp" in lowered
            or "seolleyeon-final-avatar-temp" in lowered
            or "userprivatemedia" in lowered
            or "clipembeddings" in lowered
            or "sourcephotoref" in lowered
            or "sourcephotogcsuri" in lowered
            or any(marker in lowered for marker in SIGNED_URL_MARKERS)
        ):
            return "[redacted-media-ref]"
    return value


def _normalized_debug_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]", "", key.lower())


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


def _risk_is_high(value: Any) -> bool:
    return str(value or "").strip().lower() in {"high", "critical", "fail", "failed"}


def _normalized_risk(value: Any, *, fallback: str = "medium") -> str:
    if isinstance(value, bool):
        return "high" if value else "low"
    normalized = str(value or "").strip().lower()
    if normalized in {"high", "critical", "fail", "failed", "reject", "rejected"}:
        return "high"
    if normalized in {"medium", "review", "needs_review", "unknown", "uncertain"}:
        return "medium"
    if normalized in {"low", "none", "pass", "passed", "ok", "clear"}:
        return "low"
    return fallback


def _normalized_crop_isolation(value: Any, *, fallback: str = "needs_review") -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"fail", "failed", "bad", "high", "reject", "rejected"}:
        return "fail"
    if normalized in {"pass", "passed", "ok", "good", "low", "clear"}:
        return "pass"
    if normalized in {"review", "needs_review", "medium", "unknown", "uncertain"}:
        return "needs_review"
    return fallback


def _qa_status_from_bool(pass_value: Any, fail_value: Any = None) -> str:
    if fail_value is True:
        return "fail"
    if pass_value is True:
        return "pass"
    if pass_value is False:
        return "needs_review"
    return "needs_review"


def _boolish(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "present", "detected"}:
            return True
        if normalized in {"false", "0", "no", "none", "absent", "not_detected"}:
            return False
    return None


def _eyewear_contract_from_trait_card(value: Any) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    nested = value.get("eyewear")
    if isinstance(nested, Mapping):
        present = _boolish(nested.get("present"))
        return {
            "present": present,
            "confidence": str(nested.get("confidence") or "unclear").strip().lower(),
            "style": str(
                nested.get("generalStyle", nested.get("general_style", "unclear"))
                or "unclear"
            ).strip().lower(),
            "source": str(nested.get("source") or "unclear").strip().lower(),
        }
    raw_present = value.get("eyewear_present")
    present = _boolish(raw_present)
    return {
        "present": present,
        "confidence": str(value.get("eyewear_confidence") or "unclear").strip().lower(),
        "style": str(value.get("eyewear_style") or "unclear").strip().lower(),
        "source": str(value.get("eyewear_source") or "unclear").strip().lower(),
    }


def _candidate_eyewear_consistency(metadata: Mapping[str, Any]) -> Dict[str, Any]:
    source_trait = (
        metadata.get("sourceTraitCard")
        or metadata.get("traitCard")
        or _mapping_child(metadata, "promptMeta").get("trait_card")
    )
    candidate_trait = metadata.get("candidateTraitCard")
    raw_signals = metadata.get("qaSignals") or metadata.get("signals")
    signals = raw_signals if isinstance(raw_signals, Mapping) else {}

    source = _eyewear_contract_from_trait_card(source_trait)
    candidate = _eyewear_contract_from_trait_card(candidate_trait)
    candidate_present = candidate.get("present")
    if candidate_present is None:
        candidate_present = _boolish(
            signals.get("candidateEyewearPresent", signals.get("candidateEyewearDetected"))
        )

    source_present = source.get("present")
    source_confidence = str(source.get("confidence") or "unclear").lower()
    reliable_source = source_confidence in {"medium", "high"}
    if source_present is None or not reliable_source:
        return {
            "eyewearMatch": "uncertain",
            "eyewearReason": "source_eyewear_unclear",
            "sourcePresent": source_present,
            "candidatePresent": candidate_present,
            "sourceConfidence": source_confidence,
        }
    if candidate_present is None:
        return {
            "eyewearMatch": "uncertain",
            "eyewearReason": "candidate_eyewear_unavailable",
            "sourcePresent": source_present,
            "candidatePresent": None,
            "sourceConfidence": source_confidence,
        }
    if bool(source_present) == bool(candidate_present):
        return {
            "eyewearMatch": "pass",
            "eyewearReason": "eyewear_presence_matches",
            "sourcePresent": bool(source_present),
            "candidatePresent": bool(candidate_present),
            "sourceConfidence": source_confidence,
        }
    reason = (
        "invented_eyewear_from_no_glasses_source"
        if source_present is False and candidate_present is True
        else "omitted_eyewear_from_glasses_source"
    )
    return {
        "eyewearMatch": "fail",
        "eyewearReason": reason,
        "sourcePresent": bool(source_present),
        "candidatePresent": bool(candidate_present),
        "sourceConfidence": source_confidence,
    }


def _apply_candidate_trait_consistency(
    result: AvatarQAResult,
    consistency: Mapping[str, Any],
) -> AvatarQAResult:
    result.candidateTraitConsistency = dict(consistency or {})
    result.debug = dict(result.debug or {})
    result.debug["candidateTraitConsistency"] = dict(consistency or {})
    if consistency.get("eyewearMatch") == "fail":
        reasons = set(result.rejectReasons)
        reasons.add("eyewear_invented_or_omitted")
        result.rejectReasons = sorted(reasons)
        result.reviewReasons = sorted(
            set(result.reviewReasons + [str(consistency.get("eyewearReason") or "eyewear_mismatch")])
        )
        result = apply_avatar_qa_rejection_logic(result)
    return result


def _truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _is_production_environment() -> bool:
    return os.environ.get("ENVIRONMENT", "").strip().lower() in {"prod", "production", "production_bridge"}


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


def _mapping_child(parent: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    child = parent.get(key)
    return child if isinstance(child, Mapping) else {}


def _metadata_qa_signals(metadata: Mapping[str, Any]) -> Dict[str, Any]:
    source_analysis = _mapping_child(metadata, "sourceAnalysis")
    reference_preprocess = _mapping_child(metadata, "referencePreprocess")

    signals: Dict[str, Any] = {}
    primary_face_confidence = _score(source_analysis.get("primaryFaceConfidence"))
    if primary_face_confidence is not None:
        signals["primaryFaceConfidence"] = primary_face_confidence

    # Source preprocessing metadata may elevate risk, but must not synthesize
    # candidate low-risk/pass signals. Candidate safety must come from actual
    # candidate QA signals.
    if (
        source_analysis.get("backgroundNeutralizationRequired") is True
        and reference_preprocess.get("backgroundNeutralized") is not True
    ):
        signals["backgroundLeakageRisk"] = "high"

    if source_analysis.get("secondaryFaceCount") not in (None, 0, "0"):
        signals.setdefault("secondaryFaceLeakageRisk", "medium")

    if reference_preprocess.get("cropRisk") == "needs_review":
        signals["cropIsolationQuality"] = "needs_review"

    return signals


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


def _process_local_image(metadata: Mapping[str, Any], key: str) -> Optional[Image.Image]:
    value = metadata.get(key)
    if isinstance(value, Image.Image):
        return value.convert("RGB")
    return None


def _load_image_or_process_local(ref: str, metadata: Mapping[str, Any], key: str) -> LoadedImage:
    image = _process_local_image(metadata, key)
    if image is not None:
        return LoadedImage(image=image)
    return _load_image(ref, metadata)


def _analysis_reference_image(metadata: Mapping[str, Any]) -> Optional[Image.Image]:
    return _process_local_image(metadata, "_analysis_reference_image")


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
    debug: Optional[Mapping[str, Any]] = None,
) -> AvatarQAResult:
    reason_set = set(reasons)
    identifiable = bool(
        {"too_identifiable", "source_candidate_identical", "source_candidate_near_duplicate"}
        & reason_set
    )
    result = AvatarQAResult(
        adultQa="needs_review",
        childlikeRisk="medium",
        privacyQa="fail" if identifiable else "needs_review",
        brandQa="needs_review",
        beautificationRisk="medium",
        cropConsistency=(
            "fail" if "crop_expanded_to_unseen_body" in reason_set else "needs_review"
        ),
        cropIsolationQuality=(
            "fail"
            if "crop_expanded_to_unseen_body" in reason_set
            else "needs_review"
        ),
        uniqueMarkCopyRisk="unknown",
        logoTextWatermarkRisk=(
            "high" if "logo_text_watermark" in reason_set else "medium"
        ),
        textLogoWatermarkRisk=(
            "high" if "logo_text_watermark" in reason_set else "medium"
        ),
        backgroundLeakageRisk=(
            "high" if "background_leakage" in reason_set else "medium"
        ),
        secondaryFaceLeakageRisk=(
            "high"
            if {
                "multiple_faces_generated",
                "secondary_face_leakage",
                "secondary_person_generated",
            }
            & reason_set
            else "medium"
        ),
        faceSimilarityScore=face_similarity_score,
        identifiabilityRisk="high" if identifiable else "medium",
        previewAllowed=False,
        requiresHumanReview=False,
        qaVersion="avatar_qa_v1",
        rejectReasons=sorted(reason_set),
        debug=dict(debug or {}),
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
    perceptual_similarity_score: Optional[float],
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
            "faceSimilarityScore": None,
            "childlikeScore": 0.05,
            "beautificationScore": 0.05,
        },
        thresholds=thresholds,
    )
    result.qaVersion = "avatar_qa_v1_staging_heuristic_preview"
    result.privacyQa = "pass"
    result.identifiabilityRisk = "low"
    result.previewAllowed = False
    result.requiresHumanReview = False
    result.softPass = True
    result.softPassReasons = ["staging_heuristic_absolute_checks_passed"]
    if perceptual_similarity_score is not None:
        result.debug = _qa_debug_document(
            thresholds=thresholds,
            face_similarity_score=None,
            perceptual_similarity_score=perceptual_similarity_score,
            model_availability={"faceSimilarity": "unavailable", "clip": "unavailable", "dino": "unavailable"},
            decision_tier="soft_pass",
            hard_reject_reasons=[],
            needs_review_reasons=[],
            soft_pass_reasons=result.softPassReasons,
        )
    return result


def _merge_local_signals(
    signals: Optional[Mapping[str, Any]],
    *,
    text_watermark_detected: bool,
    metadata: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    merged: Dict[str, Any] = dict(_metadata_qa_signals(metadata or {}))
    merged.update(dict(signals or {}))
    if text_watermark_detected:
        merged["logoTextWatermarkDetected"] = True
        merged["textLogoWatermarkDetected"] = True
    return merged


def _qa_debug_document(
    *,
    thresholds: AvatarQAThresholds,
    face_similarity_score: Optional[float],
    perceptual_similarity_score: Optional[float],
    model_availability: Mapping[str, str],
    decision_tier: str,
    hard_reject_reasons: Sequence[str],
    needs_review_reasons: Sequence[str],
    soft_pass_reasons: Sequence[str],
) -> Dict[str, Any]:
    perceptual_distance = (
        None
        if perceptual_similarity_score is None
        else round(1.0 - float(perceptual_similarity_score), 6)
    )
    return {
        "qaVersion": "avatar_qa_v1",
        "thresholdSnapshot": {
            "faceSimilarityReject": thresholds.face_similarity_reject,
            "faceSimilarityReview": thresholds.face_similarity_review,
            "perceptualReject": thresholds.perceptual_near_duplicate_reject,
            "perceptualReview": thresholds.perceptual_review,
            "brandReject": None,
            "requireReliableFaceSimilarityForTooIdentifiable": (
                thresholds.require_reliable_face_similarity_for_too_identifiable
            ),
        },
        "modelAvailability": {
            "faceDetector": model_availability.get("faceDetector", "unavailable"),
            "faceSimilarity": model_availability.get("faceSimilarity", "unavailable"),
            "clip": model_availability.get("clip", "unavailable"),
            "dino": model_availability.get("dino", "unavailable"),
            "mediapipe": model_availability.get("mediapipe", "unavailable"),
        },
        "scores": {
            "faceSimilarityScore": face_similarity_score,
            "perceptualHashDistance": perceptual_distance,
            "perceptualSimilarityScore": perceptual_similarity_score,
            "ssimScore": None,
            "clipSimilarityScore": None,
            "dinoStyleScore": None,
            "traitConsistencyScore": None,
            "brandFitScore": None,
            "beautificationRiskScore": None,
            "childlikeRiskScore": None,
            "privacyPenalty": None,
        },
        "decision": {
            "selectionTier": decision_tier,
            "previewAllowed": decision_tier == "hard_pass",
            "requiresHumanReview": decision_tier == "needs_review",
            "hardRejectReasons": list(hard_reject_reasons),
            "needsReviewReasons": list(needs_review_reasons),
            "softPassReasons": list(soft_pass_reasons),
        },
    }


def _model_unavailable_with_local_similarity(
    face_similarity_score: Optional[float],
    *,
    perceptual_similarity_score: Optional[float] = None,
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
    result.reviewReasons = ["model_unavailable"]
    result.debug = _qa_debug_document(
        thresholds=thresholds,
        face_similarity_score=face_similarity_score,
        perceptual_similarity_score=perceptual_similarity_score,
        model_availability={"faceSimilarity": "unavailable", "clip": "unavailable", "dino": "unavailable"},
        decision_tier="needs_review",
        hard_reject_reasons=[],
        needs_review_reasons=result.reviewReasons,
        soft_pass_reasons=[],
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
    face_similarity_reliable = signals.get("faceSimilarityReliable") is True
    face_similarity = (
        _score(signals.get("faceSimilarityScore")) if face_similarity_reliable else None
    )
    childlike_score = _score(signals.get("childlikeScore"))
    beautification_score = _score(signals.get("beautificationScore"))
    primary_face_confidence = _score(signals.get("primaryFaceConfidence"))

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
    multiple_faces_generated = any(
        signals.get(key) is True
        for key in (
            "multipleFacesDetected",
            "multipleFacesGenerated",
            "generatedMultipleFaces",
        )
    )
    secondary_person_generated = any(
        signals.get(key) is True
        for key in (
            "secondaryPersonDetected",
            "secondaryPersonGenerated",
            "extraPeopleInvented",
        )
    )
    background_leakage_detected = any(
        signals.get(key) is True
        for key in (
            "backgroundLeakageDetected",
            "originalBackgroundReproduced",
            "identifiableLocationBackground",
        )
    )
    text_logo_detected = any(
        signals.get(key) is True
        for key in (
            "logoTextWatermarkDetected",
            "textLogoWatermarkDetected",
            "backgroundTextLogoDetected",
            "schoolSignDetected",
            "campusSignDetected",
            "brandLogoDetected",
        )
    )
    crop_expanded = any(
        signals.get(key) is True
        for key in (
            "cropExpandedToUnseenBody",
            "fullBodyInvented",
            "extraPeopleInvented",
        )
    )

    background_leakage_risk = (
        "high"
        if background_leakage_detected
        else _normalized_risk(signals.get("backgroundLeakageRisk"), fallback="medium")
    )
    secondary_face_leakage_risk = (
        "high"
        if multiple_faces_generated or secondary_person_generated
        else _normalized_risk(signals.get("secondaryFaceLeakageRisk"), fallback="medium")
    )
    text_logo_watermark_risk = (
        "high"
        if text_logo_detected
        else _normalized_risk(
            signals.get("textLogoWatermarkRisk", signals.get("logoTextWatermarkRisk")),
            fallback="medium",
        )
    )
    crop_isolation_quality = (
        "fail"
        if crop_expanded
        else _normalized_crop_isolation(
            signals.get("cropIsolationQuality"),
            fallback=("pass" if signals.get("cropConsistent") is True and signals.get("cropIsolationQuality") == "pass" else "needs_review"),
        )
    )

    reject_reasons: List[str] = []
    if signals.get("noFaceDetected") is True:
        reject_reasons.append("no_face_generated")
    if signals.get("uniqueMarkCopied") is True:
        reject_reasons.append("unique_mark_copied")
    if signals.get("idolModelInfluencerLook") is True:
        reject_reasons.append("idol_model_influencer_look")
    if crop_expanded:
        reject_reasons.append("crop_expanded_to_unseen_body")
    if text_logo_watermark_risk == "high":
        reject_reasons.append("logo_text_watermark")
    if background_leakage_risk == "high":
        reject_reasons.append("background_leakage")
    if multiple_faces_generated:
        reject_reasons.append("multiple_faces_generated")
    if secondary_person_generated:
        reject_reasons.append("secondary_person_generated")
    if (
        secondary_face_leakage_risk == "high"
        and not multiple_faces_generated
        and not secondary_person_generated
    ):
        reject_reasons.append("secondary_face_leakage")
    if signals.get("notAdultUniversityStudentTone") is True:
        reject_reasons.append("not_adult_university_student_tone")
    if signals.get("sexualizedOrNightlife") is True:
        reject_reasons.append("sexualized_or_nightlife")
    if signals.get("severeArtifactDetected") is True:
        reject_reasons.append("severe_artifact")
    if signals.get("hardTraitContradiction") is True:
        reject_reasons.append("hard_trait_contradiction")

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

    logo_risk = text_logo_watermark_risk
    unique_mark_risk = "high" if signals.get("uniqueMarkCopied") is True else (
        "low" if signals.get("uniqueMarkCopied") is False else "unknown"
    )
    crop_consistency = "fail" if crop_expanded else (
        "pass" if signals.get("cropConsistent") is True else "needs_review"
    )

    result = AvatarQAResult(
        adultQa=adult_qa,
        childlikeRisk=childlike_risk,
        privacyQa=privacy_qa,
        brandQa=brand_qa,
        beautificationRisk=beautification_risk,
        cropConsistency=crop_consistency,
        cropIsolationQuality=crop_isolation_quality,
        uniqueMarkCopyRisk=unique_mark_risk,
        logoTextWatermarkRisk=logo_risk,
        textLogoWatermarkRisk=text_logo_watermark_risk,
        backgroundLeakageRisk=background_leakage_risk,
        secondaryFaceLeakageRisk=secondary_face_leakage_risk,
        faceSimilarityScore=face_similarity,
        primaryFaceConfidence=primary_face_confidence,
        identifiabilityRisk=identifiability_risk,
        qaVersion="avatar_qa_v1",
        rejectReasons=reject_reasons,
    )
    result = apply_avatar_qa_rejection_logic(result)
    if result.rejectReasons:
        decision_tier = "hard_reject"
    elif result.previewAllowed:
        decision_tier = "hard_pass"
    elif result.softPass:
        decision_tier = "soft_pass"
    else:
        decision_tier = "needs_review"
    if not result.rejectReasons and not result.previewAllowed and not result.softPass:
        result.reviewReasons = ["qa_signal_uncertain"]
    result.debug = _qa_debug_document(
        thresholds=t,
        face_similarity_score=face_similarity,
        perceptual_similarity_score=_score(signals.get("perceptualSimilarityScore")),
        model_availability={
            "faceSimilarity": (
                "available" if face_similarity is not None else ("uncalibrated" if signals.get("faceSimilarityScore") is not None or signals.get("faceSimilarityNeedsReview") is True else "unavailable")
            ),
            "clip": str(signals.get("localSafetyRiskAvailability") or "unavailable"),
            "dino": "unavailable",
        },
        decision_tier=decision_tier,
        hard_reject_reasons=result.rejectReasons,
        needs_review_reasons=result.reviewReasons,
        soft_pass_reasons=result.softPassReasons,
    )
    return result


def needs_review_model_unavailable_result() -> AvatarQAResult:
    return AvatarQAResult(
        adultQa="needs_review",
        childlikeRisk="medium",
        privacyQa="needs_review",
        brandQa="needs_review",
        beautificationRisk="medium",
        cropConsistency="needs_review",
        cropIsolationQuality="needs_review",
        uniqueMarkCopyRisk="unknown",
        logoTextWatermarkRisk="medium",
        textLogoWatermarkRisk="medium",
        backgroundLeakageRisk="medium",
        secondaryFaceLeakageRisk="medium",
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

    source = _load_image_or_process_local(source_image_ref, qa_metadata, "_source_image")
    candidate = _load_image_or_process_local(candidate_image_ref, qa_metadata, "_candidate_image")
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

    reliable_face_similarity_score: Optional[float] = None
    perceptual_similarity_score: Optional[float] = None
    review_reasons: List[str] = []
    reference_image = _analysis_reference_image(qa_metadata)
    if not hard_reasons and reference_image is None and _is_production_environment():
        result = needs_review_model_unavailable_result()
        result.reviewReasons = ["analysis_reference_image_unavailable"]
        result.debug = _qa_debug_document(
            thresholds=thresholds,
            face_similarity_score=None,
            perceptual_similarity_score=None,
            model_availability={
                "faceSimilarity": "unavailable",
                "clip": "unavailable",
                "dino": "unavailable",
            },
            decision_tier="needs_review",
            hard_reject_reasons=[],
            needs_review_reasons=result.reviewReasons,
            soft_pass_reasons=[],
        )
        return _apply_candidate_trait_consistency(
            result,
            _candidate_eyewear_consistency(qa_metadata),
        )

    if not hard_reasons:
        comparison_source = reference_image or source.image
        if _images_exactly_equal(comparison_source, candidate.image):
            perceptual_similarity_score = 1.0
            hard_reasons.update(
                {"source_candidate_identical", "source_candidate_near_duplicate", "too_identifiable"}
            )
        else:
            perceptual_similarity_score = _image_similarity_score(
                comparison_source,
                candidate.image,
            )
            if perceptual_similarity_score >= thresholds.perceptual_review:
                review_reasons.append("perceptual_similarity_review")

    text_watermark_detected = _contains_text_watermark_marker(
        qa_metadata,
        [source_image_ref, candidate_image_ref],
    )
    if text_watermark_detected:
        hard_reasons.add("logo_text_watermark")
    eyewear_consistency = _candidate_eyewear_consistency(qa_metadata)
    if eyewear_consistency.get("eyewearMatch") == "fail":
        hard_reasons.add("eyewear_invented_or_omitted")

    if hard_reasons:
        debug = _qa_debug_document(
            thresholds=thresholds,
            face_similarity_score=reliable_face_similarity_score,
            perceptual_similarity_score=perceptual_similarity_score,
            model_availability={
                "faceSimilarity": "unavailable",
                "clip": "unavailable",
                "dino": "unavailable",
            },
            decision_tier="hard_reject",
            hard_reject_reasons=sorted(hard_reasons),
            needs_review_reasons=[],
            soft_pass_reasons=[],
        )
        return _apply_candidate_trait_consistency(
            _hard_reject_result(
                hard_reasons,
                face_similarity_score=reliable_face_similarity_score,
                debug=debug,
            ),
            eyewear_consistency,
        )

    raw_signals = qa_metadata.get("qaSignals") or qa_metadata.get("signals")
    production_environment = _is_production_environment()
    signals = (
        None
        if production_environment
        else raw_signals if isinstance(raw_signals, Mapping) else None
    )
    runtime_signal_result: Optional[CandidateQASignalResult] = None
    if signals is None and _staging_heuristic_preview_allowed():
        return _apply_candidate_trait_consistency(
            _staging_heuristic_preview_result(
                perceptual_similarity_score=perceptual_similarity_score,
                text_watermark_detected=text_watermark_detected,
                thresholds=thresholds,
            ),
            eyewear_consistency,
        )
    if signals is None:
        actual_source = reference_image or source.image
        try:
            from .qa_runtime import build_actual_candidate_qa_signals

            runtime_signal_result = build_actual_candidate_qa_signals(
                source_image=actual_source,
                candidate_image=candidate.image,
                metadata=qa_metadata,
                runtime=qa_metadata.get("_qa_runtime"),
            )
            signals = dict(runtime_signal_result.signals)
        except Exception:
            return _apply_candidate_trait_consistency(
                _model_unavailable_with_local_similarity(
                    reliable_face_similarity_score,
                    perceptual_similarity_score=perceptual_similarity_score,
                    thresholds=thresholds,
                ),
                eyewear_consistency,
            )

    merged_signals = _merge_local_signals(
        signals,
        text_watermark_detected=text_watermark_detected,
        metadata=qa_metadata,
    )
    if perceptual_similarity_score is not None:
        merged_signals["perceptualSimilarityScore"] = perceptual_similarity_score
    result = build_avatar_qa_from_signals(merged_signals, thresholds=thresholds)
    model_availability = (
        dict(runtime_signal_result.model_availability)
        if runtime_signal_result is not None
        else dict(_mapping_child(qa_metadata, "modelAvailability"))
    )
    if runtime_signal_result is not None:
        result.qaVersion = "avatar_qa_v2"
        result.debug = _qa_debug_document(
            thresholds=thresholds,
            face_similarity_score=result.faceSimilarityScore,
            perceptual_similarity_score=perceptual_similarity_score,
            model_availability=model_availability,
            decision_tier=_decision_tier(result),
            hard_reject_reasons=result.rejectReasons,
            needs_review_reasons=result.reviewReasons,
            soft_pass_reasons=result.softPassReasons,
        )
        result.debug["qaVersion"] = "avatar_qa_v2"
    needs_review_from_models = _runtime_result_needs_review(runtime_signal_result, model_availability)
    if qa_metadata.get("modelsUnavailable") is True:
        needs_review_from_models = True
        review_reasons.append("model_unavailable")
    if runtime_signal_result is not None and runtime_signal_result.models_unavailable:
        review_reasons.extend(
            f"{key}_unavailable" for key in runtime_signal_result.models_unavailable
        )
    if runtime_signal_result is not None and runtime_signal_result.needs_review:
        review_reasons.append("actual_qa_signal_review")
    if needs_review_from_models and not result.rejectReasons:
        result.previewAllowed = False
        result.requiresHumanReview = True
        result.softPass = False
        review_reasons.append("qa_model_signal_review")
    if review_reasons and not result.rejectReasons:
        result.reviewReasons = sorted(set(result.reviewReasons + review_reasons))
        result.debug = _qa_debug_document(
            thresholds=thresholds,
            face_similarity_score=result.faceSimilarityScore,
            perceptual_similarity_score=perceptual_similarity_score,
            model_availability=model_availability or {
                "faceSimilarity": (
                    "available" if result.faceSimilarityScore is not None else "unavailable"
                ),
                "clip": "unavailable",
                "dino": "unavailable",
            },
            decision_tier="needs_review",
            hard_reject_reasons=result.rejectReasons,
            needs_review_reasons=result.reviewReasons,
            soft_pass_reasons=result.softPassReasons,
        )
        if runtime_signal_result is not None:
            result.debug["qaVersion"] = "avatar_qa_v2"
    return _apply_candidate_trait_consistency(result, eyewear_consistency)


def _decision_tier(result: AvatarQAResult) -> str:
    if result.rejectReasons:
        return "hard_reject"
    if result.previewAllowed:
        return "hard_pass"
    if result.softPass:
        return "soft_pass"
    return "needs_review"


def _runtime_result_needs_review(
    signal_result: Optional[CandidateQASignalResult],
    model_availability: Mapping[str, str],
) -> bool:
    if signal_result is not None and signal_result.needs_review:
        return True
    unavailable_statuses = {"unavailable", "critical_unavailable", "uncalibrated"}
    for key, value in model_availability.items():
        lowered_key = str(key).lower()
        if lowered_key.endswith(".error") or lowered_key.endswith(".calibrationversion"):
            continue
        if str(value).strip().lower() in unavailable_statuses:
            return True
    return False
