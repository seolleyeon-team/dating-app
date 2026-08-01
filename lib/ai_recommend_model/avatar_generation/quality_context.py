from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from PIL import Image

_LEAF = object()
_DROP = object()

_REFERENCE_PREPROCESS_METADATA_ALLOWLIST: Mapping[str, Any] = {
    "schemaVersion": _LEAF,
    "sourceSize": {"width": _LEAF, "height": _LEAF},
    "outputSize": {"width": _LEAF, "height": _LEAF},
    "profile": {
        "name": _LEAF,
        "version": _LEAF,
        "primaryFaceScalePx": _LEAF,
        "faceEquivalentPx": _LEAF,
        "styleEquivalentPx": _LEAF,
        "protectedStyleEquivalentPx": _LEAF,
        "requiresLaterUpperBoundGate": _LEAF,
    },
    "regions": {
        "face": {
            "downsamplePx": _LEAF,
            "blurRadius": _LEAF,
            "maskCoverage": _LEAF,
        },
        "style": {
            "downsamplePx": _LEAF,
            "blurRadius": _LEAF,
            "maskCoverage": _LEAF,
        },
    },
    "segmentation": {
        "provider": _LEAF,
        "faceCount": _LEAF,
        "maskCoverage": _LEAF,
        "samError": _LEAF,
    },
    "sam": {"enabled": _LEAF, "provider": _LEAF},
    "primaryCropApplied": _LEAF,
    "cropType": _LEAF,
    "cropRisk": _LEAF,
    "cropIsolationQuality": _LEAF,
    "backgroundNeutralized": _LEAF,
    "textLogoDetected": _LEAF,
    "textLogoNeutralized": _LEAF,
    "secondaryFacesNeutralized": _LEAF,
    "backgroundNeutralization": {
        "enabled": _LEAF,
        "mode": _LEAF,
        "neutralColor": _LEAF,
        "backgroundBlurRadius": _LEAF,
        "backgroundDesaturate": _LEAF,
        "secondaryFaceBlurRadius": _LEAF,
        "secondaryFaceCount": _LEAF,
        "secondaryFaceAction": _LEAF,
        "textLogoBlurEnabled": _LEAF,
        "textLogoRiskDetected": _LEAF,
        "textLogoRegionCount": _LEAF,
        "textLogoAction": _LEAF,
        "backgroundPersonRegionCount": _LEAF,
        "backgroundRegionCount": _LEAF,
        "foregroundMaskCoverage": _LEAF,
    },
    "referencePreprocessVersion": _LEAF,
    "enabled": _LEAF,
    "faceEquivalentSize": _LEAF,
    "nonFaceEquivalentSize": _LEAF,
    "hardPrivacyMode": _LEAF,
    "smallFaceAnalysisReferenceUsed": _LEAF,
}


@dataclass(frozen=True)
class AvatarQualityContext:
    """Process-local source/reference artifacts that must not be persisted."""

    generation_image: Image.Image | None = field(default=None, repr=False, compare=False)
    analysis_image: Image.Image | None = field(default=None, repr=False, compare=False)
    foreground_mask: Image.Image | None = field(default=None, repr=False, compare=False)
    face_hints: Sequence[Any] = field(default_factory=tuple, repr=False, compare=False)
    metadata: Mapping[str, Any] = field(
        default_factory=dict,
        repr=False,
        compare=False,
    )

    def persisted_metadata(self) -> dict[str, Any]:
        sanitized = _allowlisted_value(
            self.metadata,
            _REFERENCE_PREPROCESS_METADATA_ALLOWLIST,
        )
        return sanitized if isinstance(sanitized, dict) else {}


def _allowlisted_value(value: Any, schema: Any) -> Any:
    if schema is _LEAF:
        if value is None or isinstance(value, (bool, int, float, str)):
            return value
        return _DROP
    if not isinstance(schema, Mapping) or not isinstance(value, Mapping):
        return _DROP

    result: dict[str, Any] = {}
    for key, child_schema in schema.items():
        if key not in value:
            continue
        child = _allowlisted_value(value[key], child_schema)
        if child is not _DROP:
            result[key] = child
    return result


__all__ = ["AvatarQualityContext"]
