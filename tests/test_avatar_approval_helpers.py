import sys
from pathlib import Path

AI_MODEL_DIR = Path(__file__).resolve().parents[1] / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

from avatar_generation.jobs import build_avatar_approval_updates
from avatar_generation.storage import APPROVED_AVATAR_BUCKET


def test_avatar_approval_updates_public_avatar_fields_only_by_default():
    approved_url = "https://storage.googleapis.com/seolleyeon-approved-avatars/users/u1/avatar/avatar_1.png"

    updates = build_avatar_approval_updates(
        uid="u1",
        job_id="avatar_job_1",
        candidate_id="cand_1",
        avatar_id="avatar_1",
        approved_avatar_url=approved_url,
        server_timestamp="SERVER_TS",
    )

    user_update = updates["users"]
    assert user_update["profileImageMode"] == "avatar"
    assert user_update["avatar"]["status"] == "approved"
    assert user_update["avatar"]["approvedAvatarUrl"] == approved_url
    assert user_update["avatar"]["approvedAvatarStoragePath"] == (
        f"gs://{APPROVED_AVATAR_BUCKET}/users/u1/avatar/avatar_1.png"
    )
    assert user_update["onboarding"]["avatarUrls"] == [approved_url]
    assert "photoUrls" not in user_update["onboarding"]


def test_avatar_approval_legacy_photo_urls_can_only_be_approved_avatar():
    approved_url = "https://cdn.example/approved-avatar.png"

    updates = build_avatar_approval_updates(
        uid="u1",
        job_id="avatar_job_1",
        candidate_id="cand_1",
        avatar_id="avatar_1",
        approved_avatar_url=approved_url,
        server_timestamp="SERVER_TS",
        write_legacy_photo_urls=True,
    )

    assert updates["users"]["onboarding"]["photoUrls"] == [approved_url]
    assert not approved_url.startswith("gs://")
    assert "source" not in approved_url.lower()
