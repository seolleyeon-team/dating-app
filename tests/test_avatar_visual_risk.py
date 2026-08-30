import importlib.util
import sys
import types
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
VISUAL_RISK_PATH = (
    REPO_ROOT
    / "lib"
    / "ai_recommend_model"
    / "avatar_generation"
    / "analysis"
    / "visual_risk.py"
)
ADAPTER_PATH = (
    REPO_ROOT
    / "lib"
    / "ai_recommend_model"
    / "avatar_generation"
    / "model_adapters"
    / "florence2_visual.py"
)


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


visual_risk = _load_module("avatar_generation.analysis.visual_risk", VISUAL_RISK_PATH)
sys.modules.setdefault("avatar_generation", types.ModuleType("avatar_generation"))
sys.modules.setdefault("avatar_generation.analysis", types.ModuleType("avatar_generation.analysis"))
setattr(sys.modules["avatar_generation.analysis"], "visual_risk", visual_risk)
florence2_visual = _load_module("florence2_visual_under_test", ADAPTER_PATH)

TASK_MORE_DETAILED_CAPTION = visual_risk.TASK_MORE_DETAILED_CAPTION
TASK_OCR_WITH_REGION = visual_risk.TASK_OCR_WITH_REGION
TASK_OD = visual_risk.TASK_OD
STATUS_NEEDS_REVIEW = visual_risk.STATUS_NEEDS_REVIEW
VisualRiskAnalysis = visual_risk.VisualRiskAnalysis
analyze_florence_visual_risk_outputs = visual_risk.analyze_florence_visual_risk_outputs
Florence2VisualRiskAdapter = florence2_visual.Florence2VisualRiskAdapter


def test_parses_florence_task_shapes_and_preserves_nonzero_origin_xyxy():
    analysis = analyze_florence_visual_risk_outputs(
        {
            TASK_OCR_WITH_REGION: {
                TASK_OCR_WITH_REGION: {
                    "quad_boxes": [[11, 13, 41, 13, 41, 29, 11, 29]],
                    "labels": ["PRIVATE CAFE"],
                    "scores": [0.96],
                }
            },
            TASK_OD: {
                TASK_OD: {
                    "bboxes": [[23, 31, 87, 149], [101, 50, 129, 180]],
                    "labels": ["person", "brand logo"],
                    "scores": [0.91, 0.88],
                }
            },
            TASK_MORE_DETAILED_CAPTION: {
                TASK_MORE_DETAILED_CAPTION: "portrait in a quiet room"
            },
        },
        image_size=(200, 200),
        primary_face_bbox_xyxy=(35, 45, 70, 84),
    )

    kinds = [region.kind for region in analysis.regions]
    assert analysis.provider_available is True
    assert kinds.count("text") == 1
    assert kinds.count("person") == 1
    assert kinds.count("background-person") == 0
    assert kinds.count("logo") == 1
    assert analysis.regions[0].bbox_xyxy == (11.0, 13.0, 41.0, 29.0)
    assert analysis.regions[0].bbox == (11.0, 13.0, 41.0, 29.0)
    assert analysis.regions[0].confidence == 0.96
    assert analysis.regions[0].raw_label == "PRIVATE CAFE"
    assert analysis.regions[2].confidence == 0.88
    assert analysis.regions[2].raw_label == "brand logo"
    assert "PRIVATE" not in repr(analysis.to_document())


def test_primary_person_exclusion_background_count_and_overlap_regression():
    analysis = analyze_florence_visual_risk_outputs(
        {
            TASK_OCR_WITH_REGION: {"quad_boxes": [], "labels": []},
            TASK_OD: {
                "bboxes": [
                    [20, 20, 90, 180],
                    [68, 60, 100, 100],
                    [160, 45, 178, 92],
                ],
                "labels": ["person", "person", "person"],
            },
        },
        image_size=(200, 200),
        primary_face_bbox_xyxy=(42, 44, 72, 78),
    )

    document = analysis.to_document()
    assert document["regionCounts"]["person"] == 1
    assert document["regionCounts"]["background-person"] == 2
    assert "background-complexity" not in document["regionCounts"]
    assert analysis.background_complexity == "high"
    assert analysis.background_complexity_risk_count == 1
    assert analysis.actions_required == (
        "neutralize_background_person",
        "review_background_complexity",
    )


def test_document_excludes_labels_text_coordinates_paths_embeddings_and_gender():
    analysis = analyze_florence_visual_risk_outputs(
        {
            TASK_OCR_WITH_REGION: {
                "quad_boxes": [[11, 13, 41, 13, 41, 29, 11, 29]],
                "labels": ["Jane 010-1234 School"],
            },
            TASK_OD: {"bboxes": [[101, 50, 129, 180]], "labels": ["Acme logo"]},
        },
        image_size=(200, 200),
    )

    serialized = repr(analysis.to_document())
    for fragment in [
        "Jane",
        "010",
        "School",
        "Acme",
        "11",
        "13",
        "41",
        "101",
        "129",
        "path",
        "embedding",
        "gender",
    ]:
        assert fragment not in serialized
    assert analysis.actions_required == ("neutralize_text_logo",)


def test_malformed_output_fails_closed_needs_review():
    analysis = analyze_florence_visual_risk_outputs(
        {
            TASK_OCR_WITH_REGION: {"quad_boxes": [[1, 2, 3]], "labels": ["bad"]},
            TASK_OD: {"bboxes": [], "labels": []},
        },
        image_size=(200, 200),
    )

    assert analysis.provider_available is False
    assert analysis.status == STATUS_NEEDS_REVIEW
    assert analysis.risk == "block"
    assert analysis.actions_required == ("manual_review", "needs_review")
    assert analysis.to_document()["errorCode"] == "malformed_florence_output"


def test_injectable_adapter_protocol_without_model_load():
    class FakeVisualAdapter:
        provider = "fake"

        def analyze(self, image, *, primary_face_bbox_xyxy=None):
            return VisualRiskAnalysis(
                provider=self.provider,
                provider_available=True,
                risk="pass",
            )

    adapter = FakeVisualAdapter()
    assert adapter.analyze(object()).to_document()["provider"] == "fake"


def test_adapter_lazy_local_only_injection_and_post_process_task_calls():
    calls = {"processor_factory": [], "model_factory": [], "processor_tasks": [], "post_process": []}

    class FakeInputs(dict):
        def to(self, device):
            self["device"] = device
            return self

    class FakeProcessor:
        def __call__(self, *, text, images, return_tensors):
            calls["processor_tasks"].append((text, return_tensors))
            return FakeInputs(input_ids=[text], pixel_values=["pixels"])

        def batch_decode(self, generated_ids, *, skip_special_tokens):
            return [f"decoded:{generated_ids[0]}"]

        def post_process_generation(self, generated_text, *, task, image_size):
            calls["post_process"].append((generated_text, task, image_size))
            if task == TASK_OCR_WITH_REGION:
                return {task: {"quad_boxes": [[10, 12, 30, 12, 30, 22, 10, 22]], "labels": ["sign"]}}
            if task == TASK_OD:
                return {task: {"bboxes": [[20, 20, 90, 180]], "labels": ["person"]}}
            return {task: "quiet portrait"}

    class FakeModel:
        def generate(self, *, input_ids, pixel_values, max_new_tokens, num_beams):
            return [input_ids[0]]

        def to(self, device):
            calls["model_device"] = device
            return self

    def processor_factory(model_id, **kwargs):
        calls["processor_factory"].append((model_id, kwargs))
        return FakeProcessor()

    def model_factory(model_id, **kwargs):
        calls["model_factory"].append((model_id, kwargs))
        return FakeModel()

    image = types.SimpleNamespace(size=(200, 240), width=200, height=240)
    adapter = Florence2VisualRiskAdapter(
        device="cpu",
        include_detailed_caption=True,
        processor_factory=processor_factory,
        model_factory=model_factory,
    )

    assert calls["processor_factory"] == []
    assert adapter.model_id == "microsoft/Florence-2-large-ft"
    assert adapter.local_files_only is True

    analysis = adapter.analyze(image, primary_face_bbox_xyxy=(40, 40, 70, 70))

    assert calls["processor_factory"] == [
        ("microsoft/Florence-2-large-ft", {"local_files_only": True})
    ]
    assert calls["model_factory"] == [
        ("microsoft/Florence-2-large-ft", {"local_files_only": True})
    ]
    assert [task for task, _ in calls["processor_tasks"]] == [
        TASK_OCR_WITH_REGION,
        TASK_OD,
        TASK_MORE_DETAILED_CAPTION,
    ]
    assert [task for _, task, _ in calls["post_process"]] == [
        TASK_OCR_WITH_REGION,
        TASK_OD,
        TASK_MORE_DETAILED_CAPTION,
    ]
    assert {image_size for _, _, image_size in calls["post_process"]} == {(200, 240)}
    assert analysis.to_document()["provider"] == "florence2"
    assert analysis.actions_required == ("neutralize_text_logo",)
