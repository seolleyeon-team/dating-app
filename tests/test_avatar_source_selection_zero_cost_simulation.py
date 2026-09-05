import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
AI_MODEL_DIR = REPO_ROOT / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

from avatar_generation.zero_cost_simulation import (  # noqa: E402
    run_zero_cost_avatar_simulation,
)


def test_six_photo_zero_cost_simulation_selects_one_source_for_both_rounds():
    report = run_zero_cost_avatar_simulation()

    assert report.selected_photo_id == "P3"
    assert report.runner_up_photo_id == "P2"
    assert report.top1_score > report.top2_score
    assert report.score_margin == round(report.top1_score - report.top2_score, 6)
    assert report.selection_confidence in {"high", "medium", "low"}

    assert report.initial_success.provider_calls == 2
    assert report.initial_success.source_photo_ids == ("P3", "P3")
    assert report.extra_required.provider_calls == 4
    assert report.extra_required.source_photo_ids == ("P3", "P3", "P3", "P3")
    assert report.real_azure_calls == 0
