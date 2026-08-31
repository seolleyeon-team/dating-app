import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
AI_MODEL_DIR = REPO_ROOT / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

from avatar_generation.qa_contract import required_signal_failure_codes  # noqa: E402


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({}, ()),
        ({"faceDetector": "unavailable"}, ("face_detector_unavailable",)),
        ({"visualRisk": "unavailable"}, ("visual_risk_unavailable",)),
        ({"clipSafety": "unavailable"}, ("clip_safety_unavailable",)),
        ({"faceSimilarity": "unavailable"}, ("face_similarity_unavailable",)),
        ({"dino": "unavailable"}, ()),
    ],
)
def test_required_signal_failure_matrix_is_fail_closed_and_dino_optional(overrides, expected):
    availability = {
        "faceDetector": "available",
        "visualRisk": "available",
        "clipSafety": "available",
        "faceSimilarity": "available",
        "dino": "available",
    }
    availability.update(overrides)

    assert required_signal_failure_codes(availability) == expected


def test_clip_safety_accepts_backward_compatible_local_safety_alias():
    availability = {
        "faceDetector": "available",
        "visualRisk": "available",
        "localSafetyRisk": "available",
        "faceSimilarity": "available",
        "dino": "not_required",
    }

    assert required_signal_failure_codes(availability) == ()
