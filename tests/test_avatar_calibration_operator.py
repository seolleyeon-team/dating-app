import io
import json
import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]
AI_MODEL_DIR = REPO_ROOT / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

from avatar_generation.calibration_operator import (  # noqa: E402
    CalibrationOperatorError,
    GcloudStorageGateway,
    assert_redacted_calibration_report,
    delete_staged_recovery_candidates,
    enrich_manifest_source_generations,
    persist_review_bundle_and_delete_remote,
    stage_local_review_bundle_for_recovery,
)


def _png(color=(80, 100, 120)):
    output = io.BytesIO()
    Image.new("RGB", (256, 256), color).save(output, format="PNG")
    return output.getvalue()


def _manifest():
    return {
        "projectId": "seolleyeon-final",
        "participants": [
            {
                "uid": f"uid-secret-{index}",
                "sourcePhotoRef": (
                    "gs://seolleyeon-final-private-source-photos/"
                    f"users/uid-secret-{index}/source/photo.jpg"
                ),
                "sourceVersion": "g004-source-v1",
            }
            for index in range(1, 6)
        ],
    }


class _FakeStorageGateway:
    def __init__(self):
        self.generations = {}
        self.objects = {}
        self.deleted = []
        self.downloaded = []
        self.uploaded = []
        self.upload_failure_at = None

    def describe_generation(self, uri):
        if uri not in self.generations:
            raise CalibrationOperatorError("operator_object_missing")
        return self.generations[uri]

    def download(self, uri, *, generation):
        if uri not in self.objects:
            raise CalibrationOperatorError("operator_object_missing")
        if self.generations[uri] != generation:
            raise CalibrationOperatorError("operator_object_generation_changed")
        self.downloaded.append((uri, generation))
        return self.objects[uri]

    def delete(self, uri, *, generation):
        if self.generations[uri] != generation:
            raise CalibrationOperatorError("operator_object_generation_changed")
        self.deleted.append(uri)
        self.objects.pop(uri, None)

    def upload_create_only(self, path, uri):
        if uri in self.objects:
            raise CalibrationOperatorError("operator_object_exists")
        if self.upload_failure_at == len(self.uploaded) + 1:
            raise CalibrationOperatorError("operator_upload_failed")
        generation = str(900 + len(self.uploaded) + 1)
        self.objects[uri] = Path(path).read_bytes()
        self.generations[uri] = generation
        self.uploaded.append((Path(path), uri, generation))
        return generation


def test_cloud_run_tag_url_is_discovered_from_captured_gcloud_json(monkeypatch):
    gateway = GcloudStorageGateway(executable="gcloud")
    expected = "https:" + "//g004-live-example.a.run.app"
    payload = {
        "status": {
            "traffic": [
                {"tag": "stable", "url": "https:" + "//stable-example.a.run.app"},
                {"tag": "g004", "url": expected},
            ]
        }
    }
    captured = {}

    def fake_run(arguments, *, text):
        captured["arguments"] = arguments
        captured["text"] = text
        return SimpleNamespace(stdout=json.dumps(payload))

    monkeypatch.setattr(gateway, "_run", fake_run)

    value = gateway.cloud_run_tag_url(
        service="worker",
        region="asia-southeast1",
        project="seolleyeon-final",
        tag="g004",
    )

    assert value == expected
    assert captured["text"] is True
    assert "--format=json(status.traffic)" in captured["arguments"]


def test_identity_token_can_use_process_local_operator_override(monkeypatch):
    gateway = GcloudStorageGateway(executable="gcloud")
    monkeypatch.setenv("AVATAR_CALIBRATION_IDENTITY_TOKEN", "opaque-identity-token")

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("gcloud identity token should not be called")

    monkeypatch.setattr(gateway, "_run", fail_if_called)

    assert gateway.identity_token() == "opaque-identity-token"


@pytest.mark.parametrize(
    "traffic",
    [
        [],
        [{"tag": "other", "url": "https:" + "//other-example.a.run.app"}],
        [{"tag": "g004", "url": "http:" + "//g004-example.a.run.app"}],
        [{"tag": "g004", "url": "https:" + "//g004-example.a.run.app/private"}],
        [{"tag": "g004", "url": "https:" + "//g004-example.a.run.app?token=secret"}],
    ],
)
def test_cloud_run_tag_url_fails_closed_for_missing_or_invalid_target(monkeypatch, traffic):
    gateway = GcloudStorageGateway(executable="gcloud")
    monkeypatch.setattr(
        gateway,
        "_run",
        lambda arguments, *, text: SimpleNamespace(
            stdout=json.dumps({"status": {"traffic": traffic}})
        ),
    )

    with pytest.raises(CalibrationOperatorError):
        gateway.cloud_run_tag_url(
            service="worker",
            region="asia-southeast1",
            project="seolleyeon-final",
            tag="g004",
        )


def test_manifest_generations_are_enriched_in_memory_without_mutating_source():
    manifest = _manifest()
    original = deepcopy(manifest)
    gateway = _FakeStorageGateway()
    for index, participant in enumerate(manifest["participants"], start=1):
        gateway.generations[participant["sourcePhotoRef"]] = str(100 + index)

    enriched = enrich_manifest_source_generations(manifest, gateway)

    assert manifest == original
    assert [row["sourceGeneration"] for row in enriched["participants"]] == [
        "101",
        "102",
        "103",
        "104",
        "105",
    ]


def test_review_bundle_downloads_fully_then_generation_pinned_delete(tmp_path):
    gateway = _FakeStorageGateway()
    run_id = "G004-AZURE-CAL-TEST-001"
    for participant in range(1, 3):
        for candidate in range(1, 3):
            uri = (
                "gs://seolleyeon-final-avatar-temp/calibration/g004/"
                f"{run_id}/P{participant:02d}/C{candidate:02d}.png"
            )
            gateway.generations[uri] = str(participant * 100 + candidate)
            gateway.objects[uri] = _png((participant * 40, candidate * 40, 120))

    summary = persist_review_bundle_and_delete_remote(
        gateway,
        run_id=run_id,
        participant_count=2,
        candidates_per_participant=2,
        review_root=tmp_path,
        temp_bucket="seolleyeon-final-avatar-temp",
    )

    final_dir = tmp_path / run_id
    assert summary == {
        "localArtifactCount": 4,
        "remoteDeletedCount": 4,
        "remoteRemainingCount": 0,
    }
    assert sorted(path.name for path in final_dir.glob("*.png")) == [
        "P01_C01.png",
        "P01_C02.png",
        "P02_C01.png",
        "P02_C02.png",
    ]
    assert len(gateway.deleted) == 4
    assert len(gateway.downloaded) == 4
    assert all(
        generation == gateway.generations[uri]
        for uri, generation in gateway.downloaded
    )


def test_review_bundle_does_not_delete_any_remote_object_when_preflight_fails(tmp_path):
    gateway = _FakeStorageGateway()
    run_id = "G004-AZURE-CAL-TEST-002"
    one_uri = (
        "gs://seolleyeon-final-avatar-temp/calibration/g004/"
        f"{run_id}/P01/C01.png"
    )
    gateway.generations[one_uri] = "101"
    gateway.objects[one_uri] = _png()

    with pytest.raises(CalibrationOperatorError):
        persist_review_bundle_and_delete_remote(
            gateway,
            run_id=run_id,
            participant_count=1,
            candidates_per_participant=2,
            review_root=tmp_path,
            temp_bucket="seolleyeon-final-avatar-temp",
        )

    assert gateway.deleted == []
    assert not (tmp_path / run_id).exists()


def test_review_bundle_fails_closed_if_generation_changes_before_download(tmp_path):
    gateway = _FakeStorageGateway()
    run_id = "G004-AZURE-CAL-TEST-003"
    uri = (
        "gs://seolleyeon-final-avatar-temp/calibration/g004/"
        f"{run_id}/P01/C01.png"
    )
    gateway.generations[uri] = "101"
    gateway.objects[uri] = _png()

    original_describe = gateway.describe_generation

    def describe_then_change(value):
        generation = original_describe(value)
        gateway.generations[value] = "102"
        return generation

    gateway.describe_generation = describe_then_change

    with pytest.raises(CalibrationOperatorError):
        persist_review_bundle_and_delete_remote(
            gateway,
            run_id=run_id,
            participant_count=1,
            candidates_per_participant=1,
            review_root=tmp_path,
            temp_bucket="seolleyeon-final-avatar-temp",
        )

    assert gateway.deleted == []


@pytest.mark.parametrize(
    "leaky",
    [
        {"ref": "gs://private-bucket/object"},
        {"url": "https://private.example/path"},
        {"note": "uid-secret-1"},
        {"candidateHash": "a" * 64},
        {"sha256": "b" * 64},
        {"imageDigest": "c" * 64},
    ],
)
def test_report_privacy_scan_rejects_private_references(leaky):
    with pytest.raises(CalibrationOperatorError, match="operator_report_privacy_failed"):
        assert_redacted_calibration_report(
            leaky,
            private_values=("uid-secret-1",),
        )


def test_report_privacy_scan_accepts_redacted_scalar_evidence():
    report = {
        "status": "completed",
        "participantOrdinals": ["P01", "P02"],
        "reviewArtifacts": {"count": 4, "referencesExposed": False},
    }

    assert_redacted_calibration_report(report, private_values=("uid-secret-1",))
    assert json.dumps(report)


def _local_review_bundle(root, run_id, *, participants=2, candidates=2):
    directory = root / run_id
    directory.mkdir(parents=True)
    for participant in range(1, participants + 1):
        for candidate in range(1, candidates + 1):
            (directory / f"P{participant:02d}_C{candidate:02d}.png").write_bytes(
                _png((participant * 30, candidate * 30, 120))
            )
    return directory


def test_local_review_bundle_is_create_only_staged_then_generation_pinned_deleted(tmp_path):
    gateway = _FakeStorageGateway()
    run_id = "G004-AZURE-CAL-RECOVERY-001"
    directory = _local_review_bundle(tmp_path, run_id)

    bundle = stage_local_review_bundle_for_recovery(
        gateway,
        run_id=run_id,
        participant_count=2,
        candidates_per_participant=2,
        review_root=tmp_path,
        temp_bucket="seolleyeon-final-avatar-temp",
    )

    assert bundle.count == 4
    assert len(gateway.uploaded) == 4
    assert all(path.parent == directory for path, _uri, _generation in gateway.uploaded)
    assert "gs://" not in repr(bundle)

    summary = delete_staged_recovery_candidates(gateway, bundle)

    assert summary == {
        "remoteUploadedCount": 4,
        "remoteDeletedCount": 4,
        "remoteRemainingCount": 0,
    }
    assert len(gateway.deleted) == 4
    assert gateway.objects == {}


def test_local_review_stage_validates_complete_exact_bundle_before_upload(tmp_path):
    gateway = _FakeStorageGateway()
    run_id = "G004-AZURE-CAL-RECOVERY-002"
    directory = _local_review_bundle(tmp_path, run_id)
    (directory / "P02_C02.png").unlink()

    with pytest.raises(CalibrationOperatorError, match="operator_review_bundle_invalid"):
        stage_local_review_bundle_for_recovery(
            gateway,
            run_id=run_id,
            participant_count=2,
            candidates_per_participant=2,
            review_root=tmp_path,
            temp_bucket="seolleyeon-final-avatar-temp",
        )

    assert gateway.uploaded == []


def test_local_review_stage_rolls_back_only_new_objects_on_partial_failure(tmp_path):
    gateway = _FakeStorageGateway()
    gateway.upload_failure_at = 3
    run_id = "G004-AZURE-CAL-RECOVERY-003"
    _local_review_bundle(tmp_path, run_id)

    with pytest.raises(CalibrationOperatorError, match="operator_recovery_stage_failed"):
        stage_local_review_bundle_for_recovery(
            gateway,
            run_id=run_id,
            participant_count=2,
            candidates_per_participant=2,
            review_root=tmp_path,
            temp_bucket="seolleyeon-final-avatar-temp",
        )

    assert len(gateway.uploaded) == 2
    assert len(gateway.deleted) == 2
    assert gateway.objects == {}
