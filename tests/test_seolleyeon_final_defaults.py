from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

EXPECTED_DEFAULTS = {
    "lib/ai_recommend_model/avatar_media_upload.py": [
        'PRIVATE_SOURCE_BUCKET = "seolleyeon-final-private-" "source-photos"',
        'APPROVED_AVATAR_BUCKET = "seolleyeon-final-approved-" "avatars"',
        'AVATAR_TEMP_BUCKET = "seolleyeon-final-avatar-temp"',
    ],
    "lib/ai_recommend_model/avatar_generation/cleanup.py": [
        'PRIVATE_SOURCE_BUCKET = "seolleyeon-final-private-source-photos"',
        'AVATAR_TEMP_BUCKET = "seolleyeon-final-avatar-temp"',
        'APPROVED_AVATAR_BUCKET = "seolleyeon-final-approved-avatars"',
        'CHAT_PROFILE_PHOTO_BUCKET = "seolleyeon-final-chat-profile-photos"',
    ],
    "lib/ai_recommend_model/avatar_generation/storage.py": [
        'PRIVATE_SOURCE_BUCKET = "seolleyeon-final-private-" "source-photos"',
        'AVATAR_TEMP_BUCKET = "seolleyeon-final-avatar-temp"',
        'APPROVED_AVATAR_BUCKET = "seolleyeon-final-approved-" "avatars"',
    ],
    "lib/ai_recommend_model/avatar_generation/job_lease.py": [
        'DEFAULT_SOURCE_PHOTO_BUCKET = "seolleyeon-final-private-source-photos"',
    ],
    "lib/ai_recommend_model/avatar_generation/worker.py": [
        'DEFAULT_SOURCE_PHOTO_BUCKET = "seolleyeon-final-private-source-photos"',
        'DEFAULT_AVATAR_TEMP_BUCKET = "seolleyeon-final-avatar-temp"',
    ],
    "lib/ai_recommend_model/seolleyeon_clip_job_handler.py": [
        'DEFAULT_PRIVATE_SOURCE_PHOTO_BUCKET = "seolleyeon-final-private-" "source-photos"',
    ],
    "lib/ai_recommend_model/seolleyeon_clip_train_export.py": [
        '"seolleyeon-final.firebasestorage.app"',
    ],
    "lib/ai_recommend_model/seolleyeon_clip_train_export_v3.py": [
        '"seolleyeon-final.firebasestorage.app"',
    ],
    "recsys/main.py": [
        'os.environ.get("GCP_PROJECT", "seolleyeon-final")',
    ],
    "infra/deploy.sh": [
        'PROJECT_ID="${GCP_PROJECT:-seolleyeon-final}"',
    ],
}


def test_active_python_defaults_target_seolleyeon_final():
    for relative_path, expected_fragments in EXPECTED_DEFAULTS.items():
        source = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        for fragment in expected_fragments:
            assert fragment in source, f"missing final default in {relative_path}"


def test_active_security_rules_allow_final_approved_bucket_only():
    storage_rules = (REPO_ROOT / "storage.rules").read_text(encoding="utf-8")
    firestore_rules = (REPO_ROOT / "firestore.rules").read_text(encoding="utf-8")

    assert 'bucket == "seolleyeon-final-approved-avatars"' in storage_rules
    assert 'bucket == "seolleyeon-approved-avatars"' not in storage_rules
    assert "seolleyeon-final-approved-avatars/users" in firestore_rules
    assert "seolleyeon-approved-avatars/users" not in firestore_rules
