import importlib.util
import math
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
AI_MODEL_DIR = REPO_ROOT / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

CLIP_RISK_PATH = (
    AI_MODEL_DIR
    / "avatar_generation"
    / "model_adapters"
    / "clip_risk.py"
)


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


clip_risk = _load_module("clip_risk_under_test", CLIP_RISK_PATH)
ClipRiskCalibrationPolicy = clip_risk.ClipRiskCalibrationPolicy
LocalClipRiskScorer = clip_risk.LocalClipRiskScorer
classify_clip_risk = clip_risk.classify_clip_risk


class DummyScorer:
    provider = "dummy"
    version = "test-v1"

    def __init__(self, scores=None, *, available=True):
        self.scores = scores or _low_risk_scores()
        self._available = available
        self.calls = []

    def is_available(self):
        self.calls.append("is_available")
        return self._available

    def score_prompt_groups(self, image, prompt_groups):
        self.calls.append(("score", tuple(prompt_groups)))
        return self.scores


class FailingScorer(DummyScorer):
    def __init__(self, *, fail_at):
        super().__init__()
        self.fail_at = fail_at

    def is_available(self):
        if self.fail_at == "availability":
            raise RuntimeError("sensitive local path C:/private/image.png")
        return True

    def score_prompt_groups(self, image, prompt_groups):
        if self.fail_at == "score":
            raise ValueError("raw prompt or image bytes should not leak")
        return super().score_prompt_groups(image, prompt_groups)


class FakeInputs(dict):
    def to(self, device):
        self["device"] = device
        return self


class FakeProcessor:
    def __call__(self, *, text, images, return_tensors, padding):
        return FakeInputs(input_ids=list(text), pixel_values=[[1.0, 0.0]])


class FakeModel:
    logit_scale = math.log(2.0)

    def get_image_features(self, *, pixel_values):
        return [[1.0, 0.0]]

    def get_text_features(self, **kwargs):
        return [[1.0, 0.0], [0.0, 1.0]]


class FakeNoScaleModel(FakeModel):
    logit_scale = None


def _explicit_policy():
    return ClipRiskCalibrationPolicy(
        calibration_version="avatar_clip_risk_calibration_test_v1",
        risk_thresholds={
            "childlike": 0.35,
            "sexualized": 0.35,
            "beautification": 0.55,
            "brand_mismatch": 0.45,
            "severe_artifact": 0.35,
        },
        minimum_scores={
            "adult_like": 0.55,
            "brand_fit": 0.55,
        },
    )


def _low_risk_scores():
    return {
        "adult_childlike": {"adult_like": 0.92, "childlike": 0.08},
        "sexualized_safe": {"safe": 0.96, "sexualized": 0.04},
        "natural_beautified": {"natural": 0.80, "beautified": 0.20},
        "brand_fit_mismatch": {"brand_fit": 0.88, "brand_mismatch": 0.12},
        "clean_artifact": {"clean": 0.94, "severe_artifact": 0.06},
    }


def _high_risk_scores():
    return {
        "adult_childlike": {"adult_like": 0.40, "childlike": 0.60},
        "sexualized_safe": {"safe": 0.20, "sexualized": 0.80},
        "natural_beautified": {"natural": 0.30, "beautified": 0.70},
        "brand_fit_mismatch": {"brand_fit": 0.25, "brand_mismatch": 0.75},
        "clean_artifact": {"clean": 0.35, "severe_artifact": 0.65},
    }


def test_default_no_policy_is_available_uncalibrated_and_needs_review():
    result = classify_clip_risk("image", scorer=DummyScorer(_low_risk_scores()))

    assert result.available is True
    assert result.availability == "available"
    assert result.calibrated is False
    assert result.calibration_version is None
    assert result.needs_review is True
    assert result.decision == "review"


def test_calibrated_high_risk_scores_map_to_review():
    result = classify_clip_risk(
        "image",
        scorer=DummyScorer(_high_risk_scores()),
        calibration_policy=_explicit_policy(),
    )

    assert result.available is True
    assert result.calibrated is True
    assert result.childlike_score == 0.60
    assert result.sexualized_score == 0.80
    assert result.beautification_score == 0.70
    assert result.brand_mismatch_score == 0.75
    assert result.severe_artifact_score == 0.65
    assert result.adult_like_score == 0.40
    assert result.brand_fit_score == 0.25
    assert result.needs_review is True
    assert result.decision == "review"


def test_calibrated_low_risk_scores_map_to_pass():
    result = classify_clip_risk(
        "image",
        scorer=DummyScorer(_low_risk_scores()),
        calibration_policy=_explicit_policy(),
    )

    assert result.available is True
    assert result.calibrated is True
    assert result.needs_review is False
    assert result.decision == "pass"
    assert result.to_document()["calibrationVersion"] == "avatar_clip_risk_calibration_test_v1"


def test_from_env_policy_requires_version_and_numeric_thresholds(monkeypatch):
    monkeypatch.setenv("AVATAR_CLIP_RISK_CALIBRATION_VERSION", "avatar_clip_risk_env_v1")
    monkeypatch.setenv("AVATAR_CLIP_RISK_CHILDLIKE_THRESHOLD", "0.35")
    monkeypatch.setenv("AVATAR_CLIP_RISK_SEXUALIZED_THRESHOLD", "0.35")
    monkeypatch.setenv("AVATAR_CLIP_RISK_BEAUTIFICATION_THRESHOLD", "0.55")
    monkeypatch.setenv("AVATAR_CLIP_RISK_BRAND_MISMATCH_THRESHOLD", "0.45")
    monkeypatch.setenv("AVATAR_CLIP_RISK_SEVERE_ARTIFACT_THRESHOLD", "0.35")
    monkeypatch.setenv("AVATAR_CLIP_RISK_ADULT_LIKE_MINIMUM", "0.55")
    monkeypatch.setenv("AVATAR_CLIP_RISK_BRAND_FIT_MINIMUM", "0.55")

    result = classify_clip_risk(
        "image",
        scorer=DummyScorer(_low_risk_scores()),
        calibration_policy=ClipRiskCalibrationPolicy.from_env(),
    )

    assert result.calibrated is True
    assert result.needs_review is False
    assert result.decision == "pass"
    assert result.calibration_version == "avatar_clip_risk_env_v1"


def test_document_and_signals_exclude_prompt_text_embeddings_paths_and_gender():
    result = classify_clip_risk("gs://private/path.png", scorer=DummyScorer(_high_risk_scores()))

    document = result.to_document()
    signals = result.to_signals()
    serialized = repr({"document": document, "signals": signals}).lower()

    for fragment in [
        "privacy preserving",
        "sexualized nightlife",
        "prompt",
        "caption",
        "label",
        "gs://",
        "private/path",
        "pixel",
        "embedding",
        "gender",
    ]:
        assert fragment not in serialized
    assert document == signals
    assert set(document) == {
        "provider",
        "version",
        "availability",
        "available",
        "availabilityReason",
        "childlikeScore",
        "sexualizedScore",
        "beautificationScore",
        "brandMismatchScore",
        "severeArtifactScore",
        "adultLikeScore",
        "brandFitScore",
        "calibrated",
        "calibrationVersion",
        "needsReview",
        "decision",
    }


def test_uncalibrated_score_fails_closed_to_review():
    policy = ClipRiskCalibrationPolicy(calibration_version="")

    result = classify_clip_risk("image", scorer=DummyScorer(_low_risk_scores()), calibration_policy=policy)

    assert result.available is True
    assert result.calibrated is False
    assert result.calibration_version == ""
    assert result.needs_review is True
    assert result.decision == "review"


def test_policy_with_version_but_missing_thresholds_fails_closed_to_review():
    policy = ClipRiskCalibrationPolicy(calibration_version="not_enough")

    result = classify_clip_risk("image", scorer=DummyScorer(_low_risk_scores()), calibration_policy=policy)

    assert result.available is True
    assert result.calibrated is False
    assert result.needs_review is True
    assert result.decision == "review"


def test_unavailable_adapter_fails_closed_without_scoring():
    scorer = DummyScorer(available=False)

    result = classify_clip_risk("image", scorer=scorer)

    assert result.available is False
    assert result.availability == "unavailable"
    assert result.calibrated is False
    assert result.needs_review is True
    assert result.decision == "unavailable"
    assert result.childlike_score is None
    assert scorer.calls == ["is_available"]


def test_exceptions_fail_closed_with_sanitized_reason():
    result = classify_clip_risk("image", scorer=FailingScorer(fail_at="score"))

    assert result.available is False
    assert result.needs_review is True
    assert result.availability_reason == "ValueError"
    assert "raw prompt" not in repr(result.to_document())
    assert "image bytes" not in repr(result.to_document())


def test_availability_exceptions_fail_closed_with_sanitized_reason():
    result = classify_clip_risk("image", scorer=FailingScorer(fail_at="availability"))

    assert result.available is False
    assert result.needs_review is True
    assert result.availability_reason == "RuntimeError"
    assert "private" not in repr(result.to_document()).lower()


def test_local_scorer_applies_clip_logit_scale_before_softmax():
    scorer = LocalClipRiskScorer(processor=FakeProcessor(), model=FakeModel())

    scores = scorer.score_prompt_groups(
        "image",
        {"group": {"aligned": ("aligned",), "other": ("other",)}},
    )

    assert round(scores["group"]["aligned"], 6) == 0.880797
    assert round(scores["group"]["other"], 6) == 0.119203


def test_local_scorer_uses_injected_temperature_without_model_logit_scale():
    scorer = LocalClipRiskScorer(
        processor=FakeProcessor(),
        model=FakeNoScaleModel(),
        temperature=0.5,
    )

    scores = scorer.score_prompt_groups(
        "image",
        {"group": {"aligned": ("aligned",), "other": ("other",)}},
    )

    assert round(scores["group"]["aligned"], 6) == 0.880797


def test_default_local_scorer_is_lazy_and_local_files_only(monkeypatch):
    calls = {"processor": [], "model": []}

    def processor_factory(model_id, **kwargs):
        calls["processor"].append((model_id, kwargs))
        return object()

    def model_factory(model_id, **kwargs):
        calls["model"].append((model_id, kwargs))
        return object()

    monkeypatch.setenv("AVATAR_CLIP_RISK_MODEL_ID", "local-compatible-clip")
    scorer = LocalClipRiskScorer(
        processor_factory=processor_factory,
        model_factory=model_factory,
    )

    assert scorer.provider == "clip"
    assert scorer.version == "local-compatible-clip"
    assert scorer.local_files_only is True
    assert scorer._processor is None
    assert scorer._model is None
    assert calls == {"processor": [], "model": []}

    assert scorer.is_available() is True
    assert calls == {
        "processor": [("local-compatible-clip", {"local_files_only": True})],
        "model": [("local-compatible-clip", {"local_files_only": True})],
    }
