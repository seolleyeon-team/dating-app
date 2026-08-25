"""Daily Firestore-job orchestration contracts without a live Firestore client."""

from recsys.jobs.daily_job import build_daily_documents


def user(
    uid: str,
    gender: str,
    *,
    approved: bool = True,
    campus_life_zones: list[str] | None = None,
) -> tuple[str, dict, dict]:
    zones = ["sinchon"] if campus_life_zones is None else campus_life_zones
    return (
        uid,
        {
            "onboarding": {
                "gender": gender,
                "interests": [uid],
                "campusLifeZones": zones,
            },
            "avatar": {
                "status": "approved" if approved else "queued",
                "approvedAvatarUrl": f"https://cdn.example/{uid}.jpg" if approved else "",
            },
        },
        {
            "universityId": "yonsei",
            "isVerified": True,
            "isActive": True,
            "isProfileComplete": True,
            "gender": gender,
            "birthYear": 2002,
            "prefGender": [],
            "prefAgeMin": None,
            "prefAgeMax": None,
            "mannerScore": 36.5,
            "lastActiveAt": None,
            "campusLifeZones": zones,
        },
    )


def test_build_daily_documents_writes_ready_and_explicit_coverage_states():
    actor, actor_doc, actor_meta = user("actor", "male")
    candidate, candidate_doc, candidate_meta = user("candidate", "female")
    users = dict([("actor", actor_doc), ("candidate", candidate_doc)])
    meta = dict([("actor", actor_meta), ("candidate", candidate_meta)])
    display_status = {
        "actor": {"displayReady": True, "approvedAvatarUrl": "https://cdn.example/actor.jpg"},
        "candidate": {"displayReady": True, "approvedAvatarUrl": "https://cdn.example/candidate.jpg"},
    }

    docs, coverage = build_daily_documents(
        users,
        meta,
        display_status,
        {"actor": {"status": "ready", "items": [{"uid": "candidate", "rank": 1, "score": 1.0}]}},
        date_key="20260824",
    )

    assert docs["actor"]["status"] == "ready"
    assert docs["actor"]["items"][0]["uid"] == "candidate"
    assert docs["actor"]["dateKey"] == "20260824"
    assert coverage == {
        "eligibleActors": 2,
        "ready": 1,
        "empty": 0,
        "skipped": 1,
        "missing": 0,
        "compatiblePairs": 1,
        "candidatePool": 2,
    }
    assert docs["candidate"]["status"] == "skipped"
    assert docs["candidate"]["reason"] == "missing_rrf_source"


def test_build_daily_documents_marks_empty_when_rrf_is_ready_but_policy_leaves_no_item():
    actor, actor_doc, actor_meta = user("actor", "male")
    same_gender, candidate_doc, candidate_meta = user("same", "male")
    users = {"actor": actor_doc, "same": candidate_doc}
    meta = {"actor": actor_meta, "same": candidate_meta}
    display_status = {
        "actor": {"displayReady": True},
        "same": {"displayReady": True},
    }

    docs, coverage = build_daily_documents(
        users,
        meta,
        display_status,
        {"actor": {"status": "ready", "items": [{"uid": "same", "rank": 1, "score": 1.0}]}},
        date_key="20260824",
    )

    assert docs["actor"]["status"] == "empty"
    assert docs["actor"]["items"] == []
    assert docs["actor"]["selection"]["rejected"]["gender"] == 1
    assert coverage["empty"] == 1
    assert coverage["compatiblePairs"] == 0


def test_actor_with_signal_but_without_avatar_is_still_eligible():
    actor, actor_doc, actor_meta = user("actor", "male", approved=False)
    candidate, candidate_doc, candidate_meta = user("candidate", "female")
    users = {"actor": actor_doc, "candidate": candidate_doc}
    meta = {"actor": actor_meta, "candidate": candidate_meta}
    display_status = {
        "actor": {"displayReady": False},
        "candidate": {"displayReady": True},
    }

    docs, coverage = build_daily_documents(
        users,
        meta,
        display_status,
        {"actor": {"status": "ready", "items": [{"uid": "candidate", "rank": 1, "score": 1.0}]}},
        date_key="20260824",
        signal_actor_ids={"actor"},
    )

    assert docs["actor"]["status"] == "ready"
    assert coverage["eligibleActors"] == 2
    assert coverage["ready"] == 1
    assert coverage["skipped"] == 1
