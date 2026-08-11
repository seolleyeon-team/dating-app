import ast
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import quote

import pytest


ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "lib" / "ai_recommend_model"


def _load_helpers(filename: str):
    path = MODEL_DIR / filename
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    helper_names = {"ai_profile_to_storage_urls", "add_ai_profiles_to_uid_urls"}
    if filename.endswith("_train_export.py"):
        helper_names.add("is_ai_profile")
    definitions = [
        node
        for node in tree.body
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name in helper_names
        )
        or (
            isinstance(node, (ast.Assign, ast.AnnAssign))
            and any(
                isinstance(target, ast.Name)
                and target.id == "_AI_PROFILE_SHOT_FILES"
                for target in (
                    node.targets
                    if isinstance(node, ast.Assign)
                    else [node.target]
                )
            )
        )
    ]
    namespace: Dict[str, Any] = {
        "Any": Any,
        "Dict": Dict,
        "List": List,
        "Optional": Optional,
        "Sequence": Sequence,
        "Tuple": Tuple,
        "quote": quote,
        "re": re,
    }
    function_names = {
        node.name
        for node in definitions
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    if "is_ai_profile" not in function_names:
        namespace["is_ai_profile"] = lambda value: bool(
            isinstance(value, str) and re.fullmatch(r"(?:female|male)_\d+", value)
        )
    ast_module = ast.Module(body=definitions, type_ignores=[])
    ast.fix_missing_locations(ast_module)
    exec(compile(ast_module, str(path), "exec"), namespace)
    return namespace


@pytest.fixture(scope="module")
def exporters():
    return (
        _load_helpers("seolleyeon_clip_train_export_v3.py"),
        _load_helpers("seolleyeon_clip_train_export.py"),
    )


def _expected_urls(identity_id: str, bucket: str):
    gender, profile_id = identity_id.split("_", 1)
    names = ("face_card.png", "vibe_card.png", "silhouette_card.png")
    return [
        "https://firebasestorage.googleapis.com/v0/b/"
        f"{bucket}/o/"
        f"{quote(f'ai_profiles/{gender}/{profile_id}/{name}', safe='')}"
        "?alt=media"
        for name in names
    ]


def test_active_and_legacy_helpers_return_three_nested_urls(exporters):
    for module in exporters:
        urls = module["ai_profile_to_storage_urls"](
            "male_007", bucket="test-bucket"
        )

        assert urls == _expected_urls("male_007", "test-bucket")
        assert len(urls) == 3
        assert len(set(urls)) == 3
        assert all("ai_profiles%2Fmale%2F007%2F" in url for url in urls)


def test_helpers_keep_identity_keys_and_store_three_urls(exporters):
    v3, legacy = exporters

    v3_urls = {"male_007": ["legacy-single-image-url"]}
    v3["add_ai_profiles_to_uid_urls"](
        v3_urls,
        ["male_007", "male_007", "female_123", "not-an-ai-target"],
        bucket="test-bucket",
    )
    assert set(v3_urls) == {"male_007", "female_123"}
    assert all(len(urls) == 3 for urls in v3_urls.values())

    legacy_urls = {}
    legacy["add_ai_profiles_to_uid_urls"](
        legacy_urls,
        {"user-a": ["male_007"]},
        {"user-a": ["male_007", "female_123"]},
        bucket="test-bucket",
    )
    assert set(legacy_urls) == {"male_007", "female_123"}
    assert all(len(urls) == 3 for urls in legacy_urls.values())


def test_helpers_preserve_zero_padding_and_reject_malformed_ids(exporters):
    for module in exporters:
        helper = module["ai_profile_to_storage_urls"]
        assert "%2F007%2F" in helper("male_007")[0]
        with pytest.raises(ValueError):
            helper("male_7_extra")
        with pytest.raises(ValueError):
            helper("male_")


def test_active_pipeline_uses_three_urls_for_mean_embedding():
    active_path = MODEL_DIR / "seolleyeon_clip_train_export_v3.py"
    source = active_path.read_text(encoding="utf-8")
    legacy_source = (
        MODEL_DIR / "seolleyeon_clip_train_export.py"
    ).read_text(encoding="utf-8")

    assert "def ai_profile_to_storage_urls(" in source
    assert "def ai_profile_to_storage_url(" not in source
    assert "ai_profiles/{folder}/{pid}.png" not in source
    assert "embedder.embed_profile_mean(urls[:3], normalize=True)" in source
    assert "seolleyeon.firebasestorage.app" not in source
    assert "seolleyeon.firebasestorage.app" not in legacy_source
