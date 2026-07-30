import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
AI_MODEL_DIR = REPO_ROOT / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

from avatar_generation.model_adapters.image_similarity import (  # noqa: E402
    CalibrationPolicy,
    ImageSimilarityAdapter,
    SimilarityResult,
    compare_image_similarity,
    cosine_similarity,
)


class DummyEncoder:
    provider = "dummy"
    version = "test-v1"

    def __init__(self, vectors, *, available=True):
        self.vectors = list(vectors)
        self._available = available
        self.calls = 0

    def is_available(self):
        return self._available

    def encode_image(self, image):
        self.calls += 1
        return self.vectors.pop(0)


class FailingEncoder(DummyEncoder):
    def __init__(self, *, fail_at):
        super().__init__([[1.0, 0.0], [1.0, 0.0]])
        self.fail_at = fail_at

    def is_available(self):
        if self.fail_at == "availability":
            raise RuntimeError("local model unavailable with sensitive path")
        return True

    def encode_image(self, image):
        if self.fail_at == "encode":
            raise ValueError("cannot encode private-image-123")
        return super().encode_image(image)


def test_cosine_similarity_math_is_deterministic():
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0
    assert round(cosine_similarity([1.0, 1.0], [1.0, 0.0]), 6) == 0.707107


def test_embeddings_are_process_local_and_absent_from_repr_and_document():
    result = SimilarityResult(
        provider="dummy",
        available=True,
        score=0.9,
        broad_consistency=0.9,
        identity_decision="needs_review",
        identity_reliable=False,
        needs_review=True,
        calibration_version=None,
        threshold=None,
        source_embedding=(1.0, 2.0, 3.0),
        target_embedding=(4.0, 5.0, 6.0),
    )

    rendered = repr(result)
    doc = result.to_document()

    assert "1.0" not in rendered
    assert "4.0" not in rendered
    assert "embedding" not in repr(doc).lower()
    assert "source_embedding" not in doc
    assert doc["score"] == 0.9


def test_uncalibrated_similarity_score_is_not_reliable_identity_evidence():
    encoder = DummyEncoder([[1.0, 0.0], [1.0, 0.0]])

    result = compare_image_similarity("a", "b", encoder=encoder)

    assert result.available is True
    assert result.score == 1.0
    assert result.identity_reliable is False
    assert result.identity_decision == "uncertain"
    assert result.needs_review is True


def test_calibrated_high_similarity_is_privacy_risk_not_pass():
    encoder = DummyEncoder([[1.0, 0.0], [0.8, 0.6]])
    policy = CalibrationPolicy(calibration_version="cal-2026-07", threshold=0.75)

    result = compare_image_similarity("a", "b", encoder=encoder, calibration_policy=policy)

    assert result.score == 0.8
    assert result.identity_reliable is True
    assert result.identity_decision == "high_similarity_risk"
    assert result.needs_review is True
    assert result.to_document()["calibrationVersion"] == "cal-2026-07"


def test_calibrated_near_threshold_similarity_requires_review():
    encoder = DummyEncoder([[1.0, 0.0], [0.7, 0.714142842854285]])
    policy = CalibrationPolicy(
        calibration_version="cal-2026-07",
        threshold=0.75,
        review_margin=0.10,
    )

    result = compare_image_similarity("a", "b", encoder=encoder, calibration_policy=policy)

    assert result.score == 0.7
    assert result.identity_reliable is False
    assert result.identity_decision == "review_similarity"
    assert result.needs_review is True


def test_calibrated_low_similarity_is_reliable_low_risk():
    encoder = DummyEncoder([[1.0, 0.0], [0.2, 0.9797958971132712]])
    policy = CalibrationPolicy(
        calibration_version="cal-2026-07",
        threshold=0.75,
        review_margin=0.10,
    )

    result = compare_image_similarity("a", "b", encoder=encoder, calibration_policy=policy)

    assert result.score == 0.2
    assert result.identity_reliable is True
    assert result.identity_decision == "low_similarity_risk"
    assert result.needs_review is False


def test_unavailable_adapter_fails_closed_to_review_without_encoding():
    encoder = DummyEncoder([[1.0, 0.0], [1.0, 0.0]], available=False)

    result = compare_image_similarity(
        "a",
        "b",
        encoder=encoder,
        calibration_policy=CalibrationPolicy(
            calibration_version="cal-2026-07",
            threshold=0.75,
        ),
    )

    assert result.available is False
    assert result.score is None
    assert result.identity_decision == "needs_review"
    assert result.identity_reliable is False
    assert result.needs_review is True
    assert encoder.calls == 0


def test_encoder_exceptions_fail_closed_with_sanitized_reason():
    result = compare_image_similarity(
        "a",
        "b",
        encoder=FailingEncoder(fail_at="encode"),
        calibration_policy=CalibrationPolicy(
            calibration_version="cal-2026-07",
            threshold=0.75,
        ),
    )

    assert result.available is False
    assert result.score is None
    assert result.identity_decision == "needs_review"
    assert result.identity_reliable is False
    assert result.needs_review is True
    assert result.availability_reason == "ValueError"
    assert "private-image" not in repr(result.to_document())


def test_availability_exceptions_fail_closed_with_sanitized_reason():
    result = compare_image_similarity(
        "a",
        "b",
        encoder=FailingEncoder(fail_at="availability"),
    )

    assert result.available is False
    assert result.identity_decision == "needs_review"
    assert result.availability_reason == "RuntimeError"


def test_default_adapter_construction_does_not_load_model():
    adapter = ImageSimilarityAdapter(provider="clip", model_id="local-clip")

    assert adapter.provider == "clip"
    assert adapter._model is None
    assert adapter._processor is None

