#!/usr/bin/env python3
"""생성된 추천 결과의 생활권 위반 read-only 감사.

커버리지 감사(누가 생활권을 갖고 있나)와 다른 질문에 답한다:
**이미 만들어져 서빙되는 추천 안에 실제로 만날 수 없는 상대가 들어 있는가.**

활성화(`campusLifeZoneEnforced=true`) 직후에 이 값이 0 이 아니면, 정책은 켜졌는데
결과가 따라오지 않은 것이다. 준비 단계(OFF)에서는 위반이 아니라 "켰다면 걸렸을
수" 로만 집계한다.

검사 대상:

    1:1     modelRecs/{uid}/daily/{dateKey}/sources/{svd,knn,clip,rrf}
            dailyRecs/{uid}/days/{dateKey}
    시즌    meetingModelRecs/{groupId}/daily/{dateKey}/sources/group_ranker
            meetingDailyRecs/{groupId}/days/{dateKey}
    블라인드 blindMeetings (생성된 미팅의 6인 교집합)

이 스크립트는 **읽기 전용**이다. Firestore 에 어떤 write 도 하지 않는다
(get/list 만 쓴다). 출력은 집계값만이며 uid·닉네임·학과 등 개인 식별 정보를
남기지 않는다.

사용 예:
    python scripts/campus_life_zone_recommendation_audit.py \\
        --project seolleyeon-final --date-key 20260826 --expected-policy off

    python scripts/campus_life_zone_recommendation_audit.py \\
        --project seolleyeon-final --date-key 20260826 \\
        --expected-policy enforced --max-cross-zone 0 --max-malformed 0

인증: gcloud auth application-default login 또는 GOOGLE_ACCESS_TOKEN.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from typing import Any, Iterator, Mapping

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_AI_MODEL_DIR = os.environ.get(
    "AI_MODEL_DIR", os.path.join(_PROJECT_ROOT, "lib", "ai_recommend_model")
)
if _AI_MODEL_DIR not in sys.path:
    sys.path.insert(0, _AI_MODEL_DIR)

from campus_life_zone_policy import (  # noqa: E402
    CAMPUS_LIFE_ZONE_FIELD,
    CANONICAL_CAMPUS_LIFE_ZONES,
    read_persisted_campus_life_zones,
)

ONE_TO_ONE_SOURCES = ("clip", "svd", "knn", "rrf")


# ---------------------------------------------------------------------------
# 순수 판정 (production 접근 없이 테스트 가능)
# ---------------------------------------------------------------------------


def zone_value_state(raw: Any) -> str:
    """저장된 생활권 값의 상태. malformed 종류를 구분해서 센다."""
    if raw is None:
        return "missing"
    if not isinstance(raw, (list, tuple)):
        return "invalid_type"
    if len(raw) == 0:
        return "missing"
    if any(not isinstance(item, str) for item in raw):
        return "invalid_item_type"
    tokens = {item.strip() for item in raw}
    unknown = tokens - CANONICAL_CAMPUS_LIFE_ZONES
    if unknown and tokens & CANONICAL_CAMPUS_LIFE_ZONES:
        return "mixed_unknown_token"
    if unknown:
        return "unknown_token"
    return "valid"


def zones_of_user(doc: Mapping[str, Any] | None) -> set:
    if not isinstance(doc, Mapping):
        return set()
    onboarding = doc.get("onboarding")
    if isinstance(onboarding, Mapping) and CAMPUS_LIFE_ZONE_FIELD in onboarding:
        return read_persisted_campus_life_zones(onboarding[CAMPUS_LIFE_ZONE_FIELD])
    return read_persisted_campus_life_zones(doc.get(CAMPUS_LIFE_ZONE_FIELD))


def raw_zone_value(doc: Mapping[str, Any] | None) -> Any:
    if not isinstance(doc, Mapping):
        return None
    onboarding = doc.get("onboarding")
    if isinstance(onboarding, Mapping) and CAMPUS_LIFE_ZONE_FIELD in onboarding:
        return onboarding[CAMPUS_LIFE_ZONE_FIELD]
    return doc.get(CAMPUS_LIFE_ZONE_FIELD)


def document_policy_state(doc: Mapping[str, Any] | None) -> str:
    """문서에 기록된 생활권 정책 상태. 없으면 ``missing`` (legacy)."""
    if not isinstance(doc, Mapping):
        return "missing"
    policy = doc.get("policy")
    if not isinstance(policy, Mapping):
        return "missing"
    state = policy.get("campusLifeZone")
    return state if isinstance(state, str) and state else "missing"


def audit_pairs(
    pairs: list[tuple[Any, Any]],
) -> dict:
    """(actor zones raw, candidate zones raw) 목록의 위반을 센다.

    Returns 집계값만. 어떤 pair 였는지는 남기지 않는다.
    """
    counts: Counter[str] = Counter()
    for actor_raw, candidate_raw in pairs:
        counts["pairs"] += 1
        actor_state = zone_value_state(actor_raw)
        candidate_state = zone_value_state(candidate_raw)

        if actor_state in {"invalid_type", "invalid_item_type", "unknown_token", "mixed_unknown_token"}:
            counts["actorMalformedZone"] += 1
        if candidate_state in {"invalid_type", "invalid_item_type", "unknown_token", "mixed_unknown_token"}:
            counts["candidateMalformedZone"] += 1

        actor_zones = read_persisted_campus_life_zones(actor_raw)
        candidate_zones = read_persisted_campus_life_zones(candidate_raw)

        if not actor_zones:
            counts["actorMissingZone"] += 1
            continue
        if not candidate_zones:
            counts["candidateMissingZone"] += 1
            continue
        if not (actor_zones & candidate_zones):
            counts["crossZoneMismatch"] += 1
        else:
            counts["compatible"] += 1
    return dict(counts)


def audit_group_pairs(pairs: list[tuple[Any, Any]]) -> dict:
    """그룹 pair(공통 생활권끼리)의 위반을 센다."""
    counts: Counter[str] = Counter()
    for actor_raw, candidate_raw in pairs:
        counts["groupPairs"] += 1
        actor_zones = read_persisted_campus_life_zones(actor_raw)
        candidate_zones = read_persisted_campus_life_zones(candidate_raw)
        if not actor_zones:
            counts["actorGroupMissingSharedZone"] += 1
            continue
        if not candidate_zones:
            counts["candidateGroupMissingSharedZone"] += 1
            continue
        if not (actor_zones & candidate_zones):
            counts["crossZoneGroupRecommendation"] += 1
        else:
            counts["compatibleGroupPairs"] += 1
    return dict(counts)


def audit_group_index_consistency(
    stored_shared: Any, member_zone_values: list[Any]
) -> str:
    """파생 필드(sharedCampusLifeZones)가 멤버 값과 일치하는지.

    파생 필드만 믿으면, 멤버가 바뀐 뒤 갱신되지 않은 값으로 매칭될 수 있다.
    """
    stored = read_persisted_campus_life_zones(stored_shared)
    derived: set | None = None
    for value in member_zone_values:
        zones = read_persisted_campus_life_zones(value)
        if not zones:
            derived = set()
            break
        derived = zones if derived is None else (derived & zones)
        if not derived:
            break
    derived = derived or set()
    if stored == derived:
        return "consistent"
    if not stored and derived:
        return "stored_missing"
    if stored and not derived:
        return "stored_stale"
    return "mismatch"


def evaluate(report: Mapping[str, Any], expected_policy: str) -> list[str]:
    """release gate 판정. OFF 에서는 cross-zone 자체를 실패로 보지 않는다."""
    failures: list[str] = []

    provenance = report.get("policyProvenance", {}) or {}
    for output_name, states in provenance.items():
        for state, count in (states or {}).items():
            if int(count or 0) <= 0 or state == expected_policy:
                continue
            if state == "missing" and expected_policy != "enforced":
                continue
            failures.append(f"{output_name}:policy_{state}")

    if expected_policy != "enforced":
        return failures

    one_to_one = report.get("oneToOne", {}) or {}
    season = report.get("season", {}) or {}
    blind = report.get("blind", {}) or {}

    for name, counts in (("oneToOne", one_to_one), ("season", season)):
        for key in (
            "crossZoneMismatch",
            "crossZoneGroupRecommendation",
            "actorMissingZone",
            "candidateMissingZone",
            "actorGroupMissingSharedZone",
            "candidateGroupMissingSharedZone",
            "actorMalformedZone",
            "candidateMalformedZone",
        ):
            if int(counts.get(key, 0) or 0) > 0:
                failures.append(f"{name}:{key}")

    if int(blind.get("crossZoneMeetings", 0) or 0) > 0:
        failures.append("blind:crossZoneMeetings")
    return failures


# ---------------------------------------------------------------------------
# Firestore REST 읽기 (read-only)
# ---------------------------------------------------------------------------


def _decode(value: Mapping[str, Any]) -> Any:
    if "nullValue" in value:
        return None
    for key in ("stringValue", "booleanValue", "timestampValue"):
        if key in value:
            return value[key]
    if "integerValue" in value:
        return int(value["integerValue"])
    if "doubleValue" in value:
        return float(value["doubleValue"])
    if "arrayValue" in value:
        return [_decode(v) for v in (value["arrayValue"].get("values") or [])]
    if "mapValue" in value:
        return {
            k: _decode(v) for k, v in (value["mapValue"].get("fields") or {}).items()
        }
    return None


def _access_token() -> str:
    token = os.environ.get("GOOGLE_ACCESS_TOKEN", "").strip()
    if token:
        return token
    import shutil
    import subprocess

    exe = shutil.which("gcloud") or shutil.which("gcloud.cmd")
    if not exe:
        raise RuntimeError(
            "gcloud 를 찾지 못했다. GOOGLE_ACCESS_TOKEN 환경변수로 "
            "application-default access token 을 넘겨라."
        )
    return subprocess.run(
        [exe, "auth", "application-default", "print-access-token"],
        capture_output=True,
        text=True,
        check=True,
        shell=False,
    ).stdout.strip()


class Reader:
    """읽기 전용 Firestore REST 클라이언트 (get/list 만)."""

    def __init__(self, project: str, database: str, token: str):
        self._base = (
            f"https://firestore.googleapis.com/v1/projects/{project}"
            f"/databases/{database}/documents"
        )
        self._token = token

    def _request(self, url: str) -> dict | None:
        import urllib.error
        import urllib.request

        req = urllib.request.Request(
            url, headers={"Authorization": f"Bearer {self._token}"}
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return None
            raise

    def get(self, path: str) -> dict | None:
        payload = self._request(f"{self._base}/{path}")
        if payload is None:
            return None
        return {k: _decode(v) for k, v in (payload.get("fields") or {}).items()}

    def list(self, collection: str, limit: int | None = None) -> Iterator[tuple[str, dict]]:
        import urllib.parse

        page_token = None
        seen = 0
        while True:
            page_size = 300
            if limit is not None:
                page_size = min(page_size, limit - seen)
                if page_size <= 0:
                    return
            params = {"pageSize": str(page_size)}
            if page_token:
                params["pageToken"] = page_token
            payload = self._request(
                f"{self._base}/{collection}?{urllib.parse.urlencode(params)}"
            )
            if payload is None:
                return
            for doc in payload.get("documents", []) or []:
                doc_id = str(doc.get("name", "")).rsplit("/", 1)[-1]
                fields = {k: _decode(v) for k, v in (doc.get("fields") or {}).items()}
                yield doc_id, fields
                seen += 1
            page_token = payload.get("nextPageToken")
            if not page_token:
                return


def run_audit(
    reader: Reader, date_key: str, limit: int | None, expected_policy: str
) -> dict:
    users = {uid: doc for uid, doc in reader.list("users", limit)}
    user_zone_raw = {uid: raw_zone_value(doc) for uid, doc in users.items()}

    provenance: dict[str, Counter] = {
        "modelRecs": Counter(),
        "dailyRecs": Counter(),
        "meetingModelRecs": Counter(),
        "meetingDailyRecs": Counter(),
    }

    # ---------------------------------------------------------------- 1:1
    one_to_one_pairs: list[tuple[Any, Any]] = []
    checked_sources: Counter[str] = Counter()
    for uid in users:
        for source in ONE_TO_ONE_SOURCES:
            doc = reader.get(f"modelRecs/{uid}/daily/{date_key}/sources/{source}")
            if doc is None:
                continue
            checked_sources[source] += 1
            provenance["modelRecs"][document_policy_state(doc)] += 1
            for item in doc.get("items") or []:
                if not isinstance(item, Mapping):
                    continue
                candidate_uid = str(item.get("uid") or "")
                if not candidate_uid:
                    continue
                one_to_one_pairs.append(
                    (user_zone_raw.get(uid), user_zone_raw.get(candidate_uid))
                )
        daily = reader.get(f"dailyRecs/{uid}/days/{date_key}")
        if daily is not None:
            provenance["dailyRecs"][document_policy_state(daily)] += 1
            for item in daily.get("items") or []:
                if not isinstance(item, Mapping):
                    continue
                candidate_uid = str(item.get("uid") or "")
                if not candidate_uid:
                    continue
                one_to_one_pairs.append(
                    (user_zone_raw.get(uid), user_zone_raw.get(candidate_uid))
                )

    one_to_one = audit_pairs(one_to_one_pairs)
    one_to_one["sourceDocuments"] = dict(checked_sources)

    # ------------------------------------------------------------- 시즌 3:3
    groups = {gid: doc for gid, doc in reader.list("meetingGroups", limit)}
    group_shared_raw = {
        gid: doc.get("sharedCampusLifeZones") for gid, doc in groups.items()
    }
    index_consistency: Counter[str] = Counter()
    for gid, doc in groups.items():
        members = doc.get("membersSnapshot")
        if not isinstance(members, list):
            continue
        member_values = [
            m.get("campusLifeZones") if isinstance(m, Mapping) else None
            for m in members
        ]
        index_consistency[
            audit_group_index_consistency(group_shared_raw.get(gid), member_values)
        ] += 1

    group_pairs: list[tuple[Any, Any]] = []
    for gid in groups:
        ranker = reader.get(
            f"meetingModelRecs/{gid}/daily/{date_key}/sources/group_ranker"
        )
        if ranker is not None:
            provenance["meetingModelRecs"][document_policy_state(ranker)] += 1
            for item in ranker.get("items") or []:
                if not isinstance(item, Mapping):
                    continue
                other = str(item.get("groupId") or "")
                if other:
                    group_pairs.append(
                        (group_shared_raw.get(gid), group_shared_raw.get(other))
                    )
        daily = reader.get(f"meetingDailyRecs/{gid}/days/{date_key}")
        if daily is not None:
            provenance["meetingDailyRecs"][document_policy_state(daily)] += 1
            for item in daily.get("candidates") or []:
                if not isinstance(item, Mapping):
                    continue
                other = str(item.get("groupId") or "")
                if other:
                    group_pairs.append(
                        (group_shared_raw.get(gid), group_shared_raw.get(other))
                    )

    season = audit_group_pairs(group_pairs)
    season["groupIndexConsistency"] = dict(index_consistency)
    season["groupIndexZoneMismatch"] = int(
        index_consistency.get("mismatch", 0) + index_consistency.get("stored_stale", 0)
    )

    # ---------------------------------------------------------- 블라인드 3:3
    blind_counts: Counter[str] = Counter()
    for _meeting_id, doc in reader.list("blindMeetings", limit):
        participant_ids = doc.get("participantIds")
        if not isinstance(participant_ids, list) or not participant_ids:
            continue
        blind_counts["meetings"] += 1
        shared: set | None = None
        for uid in participant_ids:
            zones = read_persisted_campus_life_zones(user_zone_raw.get(str(uid)))
            if not zones:
                shared = set()
                break
            shared = zones if shared is None else (shared & zones)
            if not shared:
                break
        if not (shared or set()):
            blind_counts["crossZoneMeetings"] += 1
        else:
            blind_counts["compatibleMeetings"] += 1

    report = {
        "dateKey": date_key,
        "expectedPolicy": expected_policy,
        "totalUsers": len(users),
        "totalGroups": len(groups),
        "oneToOne": one_to_one,
        "season": season,
        "blind": dict(blind_counts),
        "policyProvenance": {k: dict(v) for k, v in provenance.items()},
    }
    report["failures"] = evaluate(report, expected_policy)
    report["healthy"] = not report["failures"]
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="생성된 추천의 생활권 위반 감사 (read-only)"
    )
    parser.add_argument("--project", required=True)
    parser.add_argument("--database", default="(default)")
    parser.add_argument("--date-key", dest="date_key", required=True)
    parser.add_argument(
        "--expected-policy",
        dest="expected_policy",
        choices=["off", "enforced"],
        default="off",
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--max-cross-zone",
        dest="max_cross_zone",
        type=int,
        default=None,
        help="cross-zone 위반 허용치. 초과하면 non-zero 로 끝난다.",
    )
    parser.add_argument(
        "--max-malformed",
        dest="max_malformed",
        type=int,
        default=None,
        help="malformed 생활권 값 허용치. 초과하면 non-zero 로 끝난다.",
    )
    args = parser.parse_args()

    import urllib.parse

    reader = Reader(
        args.project,
        urllib.parse.quote(args.database, safe=""),
        _access_token(),
    )
    report = run_audit(reader, args.date_key, args.limit, args.expected_policy)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))

    failures = list(report["failures"])
    cross_zone = int(report["oneToOne"].get("crossZoneMismatch", 0)) + int(
        report["season"].get("crossZoneGroupRecommendation", 0)
    ) + int(report["blind"].get("crossZoneMeetings", 0))
    if args.max_cross_zone is not None and cross_zone > args.max_cross_zone:
        failures.append(f"crossZone {cross_zone} > {args.max_cross_zone}")
    malformed = int(report["oneToOne"].get("actorMalformedZone", 0)) + int(
        report["oneToOne"].get("candidateMalformedZone", 0)
    )
    if args.max_malformed is not None and malformed > args.max_malformed:
        failures.append(f"malformed {malformed} > {args.max_malformed}")

    if failures:
        print("AUDIT GATE FAILED: " + "; ".join(failures), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
