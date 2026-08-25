#!/usr/bin/env python3
"""생활권 커버리지 + publicProfiles 투영 정합성 read-only 감사.

최종 활성화(`campusLifeZoneEnforced=true`) 전에는 원본 커버리지만으로 부족하다.
1:1 클라이언트는 상대 프로필을 `publicProfiles/{uid}` 로만 읽으므로, `users` 에
생활권이 있어도 투영이 빠지면 그 후보는 serving 단계에서 fail-closed 로 사라진다.

그래서 두 커버리지를 따로 잰다.

    A. users/{uid}.onboarding.campusLifeZones
    B. publicProfiles/{uid}.campusLifeZones

그리고 A 에는 있는데 B 에는 없는 사용자를 ``sourceProjectionMismatch`` 로 센다.

이 스크립트는 **읽기 전용**이다. Firestore 에 어떤 write 도 하지 않는다.
출력은 집계값만이며 uid·학과·학년 등 개인 식별 정보를 남기지 않는다
(문서 id 는 집합 연산에만 쓰고 출력하지 않는다).

사용 예:
    python scripts/campus_life_zone_projection_audit.py --project seolleyeon-final
    python scripts/campus_life_zone_projection_audit.py --project seolleyeon-final \
        --max-mismatch 0 --min-projection-coverage 0.95

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


def _is_map(value: Any) -> bool:
    return isinstance(value, Mapping)


def raw_zone_value(doc: Mapping[str, Any]) -> Any:
    """문서에서 생활권 원본 값을 꺼낸다 (검증 전)."""
    onboarding = doc.get("onboarding")
    if _is_map(onboarding) and CAMPUS_LIFE_ZONE_FIELD in onboarding:
        return onboarding[CAMPUS_LIFE_ZONE_FIELD]
    return doc.get(CAMPUS_LIFE_ZONE_FIELD)


def zone_state(raw: Any) -> str:
    """저장된 값의 상태를 분류한다 (§27 malformed 집계용).

    canonical 검증과 같은 규칙을 쓰되, "왜 무효인지"를 구분해서 센다.
    """
    if raw is None:
        return "missing_field"
    if not isinstance(raw, (list, tuple)):
        return "invalid_type"
    if len(raw) == 0:
        return "empty"
    if any(not isinstance(item, str) for item in raw):
        return "invalid_item_type"
    tokens = {item.strip() for item in raw}
    unknown = tokens - CANONICAL_CAMPUS_LIFE_ZONES
    if unknown and tokens & CANONICAL_CAMPUS_LIFE_ZONES:
        return "mixed_unknown_token"
    if unknown:
        return "unknown_token"
    return "valid"


def recommendation_eligible(doc: Mapping[str, Any]) -> bool:
    """추천 후보가 될 법한 정상 계정인지 (보수적 근사).

    scripts/campus_life_zone_audit.py 와 같은 기준을 쓴다.
    """
    if doc.get("isWithdrawn") is True:
        return False
    if str(doc.get("status") or "").lower() in {"withdrawn", "banned", "suspended"}:
        return False
    if doc.get("profileVisible") is False:
        return False
    verified = doc.get("isStudentVerified", doc.get("isVerified"))
    return verified is True


def summarize(
    users: Mapping[str, Mapping[str, Any]],
    public_profiles: Mapping[str, Mapping[str, Any]],
) -> dict:
    """§15 지표를 계산한다. 순수 함수라 production 접근 없이 테스트할 수 있다.

    Args:
        users: uid -> users/{uid} 문서
        public_profiles: uid -> publicProfiles/{uid} 문서
    """
    eligible_ids = [uid for uid, doc in users.items() if recommendation_eligible(doc)]

    source_states: Counter[str] = Counter()
    projection_states: Counter[str] = Counter()

    eligible_with_zone = 0
    eligible_missing_zone = 0
    eligible_with_public_profile = 0
    eligible_with_projection_zone = 0
    eligible_missing_projection_zone = 0
    projection_mismatch = 0
    projection_zone_value_mismatch = 0
    dual_zone_users = 0
    dual_zone_projected = 0

    for uid in eligible_ids:
        user_doc = users[uid]
        source_raw = raw_zone_value(user_doc)
        source_state = zone_state(source_raw)
        source_states[source_state] += 1

        source_zones = read_persisted_campus_life_zones(source_raw)
        has_source = bool(source_zones)
        if has_source:
            eligible_with_zone += 1
            if len(source_zones) > 1:
                dual_zone_users += 1
        else:
            eligible_missing_zone += 1

        public_doc = public_profiles.get(uid)
        if public_doc is None:
            projection_states["no_public_profile"] += 1
            if has_source:
                # 원본에는 있는데 클라이언트가 읽을 문서 자체가 없다.
                projection_mismatch += 1
                eligible_missing_projection_zone += 1
            continue

        eligible_with_public_profile += 1
        projection_raw = raw_zone_value(public_doc)
        projection_states[zone_state(projection_raw)] += 1
        projection_zones = read_persisted_campus_life_zones(projection_raw)

        if projection_zones:
            eligible_with_projection_zone += 1
            if len(projection_zones) > 1:
                dual_zone_projected += 1
        else:
            eligible_missing_projection_zone += 1

        if has_source and not projection_zones:
            projection_mismatch += 1
        elif has_source and projection_zones != source_zones:
            # 값 자체가 어긋난 경우 (예: 이중 생활권이 잘려서 투영됨)
            projection_zone_value_mismatch += 1

    eligible_total = len(eligible_ids)

    def ratio(numerator: int) -> float:
        return round(numerator / eligible_total, 4) if eligible_total else 0.0

    malformed_source = sum(
        count
        for state, count in source_states.items()
        if state in {"invalid_type", "invalid_item_type", "unknown_token", "mixed_unknown_token"}
    )
    malformed_projection = sum(
        count
        for state, count in projection_states.items()
        if state in {"invalid_type", "invalid_item_type", "unknown_token", "mixed_unknown_token"}
    )

    return {
        "totalUsers": len(users),
        "totalPublicProfiles": len(public_profiles),
        "eligibleUsers": eligible_total,
        # A. 원본 커버리지
        "eligibleUsersWithZone": eligible_with_zone,
        "eligibleUsersMissingZone": eligible_missing_zone,
        "sourceCoverageRatio": ratio(eligible_with_zone),
        # B. 투영 커버리지
        "eligibleUsersWithPublicProfile": eligible_with_public_profile,
        "eligibleUsersWithPublicProfileZone": eligible_with_projection_zone,
        "eligibleUsersMissingPublicProfileZone": eligible_missing_projection_zone,
        "projectionCoverageRatio": ratio(eligible_with_projection_zone),
        # 정합성
        "sourceProjectionMismatch": projection_mismatch,
        "projectionZoneValueMismatch": projection_zone_value_mismatch,
        "dualZoneUsers": dual_zone_users,
        "dualZoneProjected": dual_zone_projected,
        # malformed (§27)
        "sourceZoneStates": dict(source_states),
        "projectionZoneStates": dict(projection_states),
        "malformedSourceZones": malformed_source,
        "malformedProjectionZones": malformed_projection,
    }


# ---------------------------------------------------------------------------
# Firestore REST 읽기 (google-cloud-firestore 2.29 의 database-id 인코딩 버그 우회)
# ---------------------------------------------------------------------------


def _decode_rest_value(value: Mapping[str, Any]) -> Any:
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
        return [
            _decode_rest_value(v) for v in (value["arrayValue"].get("values") or [])
        ]
    if "mapValue" in value:
        return {
            k: _decode_rest_value(v)
            for k, v in (value["mapValue"].get("fields") or {}).items()
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


def iter_docs(
    project: str, collection: str, limit: int | None, database: str, token: str
) -> Iterator[tuple[str, dict]]:
    """(doc_id, fields) 를 흘려보낸다. doc_id 는 집합 연산 용도로만 쓴다."""
    import urllib.parse
    import urllib.request

    base = (
        f"https://firestore.googleapis.com/v1/projects/{project}"
        f"/databases/{urllib.parse.quote(database, safe='')}/documents/{collection}"
    )
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
        req = urllib.request.Request(
            f"{base}?{urllib.parse.urlencode(params)}",
            headers={"Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        for doc in payload.get("documents", []) or []:
            doc_id = str(doc.get("name", "")).rsplit("/", 1)[-1]
            fields = doc.get("fields") or {}
            yield doc_id, {k: _decode_rest_value(v) for k, v in fields.items()}
            seen += 1
        page_token = payload.get("nextPageToken")
        if not page_token:
            return


def main() -> int:
    parser = argparse.ArgumentParser(
        description="생활권 커버리지 + publicProfiles 투영 정합성 감사 (read-only)"
    )
    parser.add_argument("--project", required=True)
    parser.add_argument("--database", default="(default)")
    parser.add_argument("--users-collection", default="users")
    parser.add_argument("--public-collection", default="publicProfiles")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--min-source-coverage",
        type=float,
        default=None,
        help="원본 커버리지가 이 값 미만이면 non-zero 로 끝난다 (활성화 게이트).",
    )
    parser.add_argument(
        "--min-projection-coverage",
        type=float,
        default=None,
        help="투영 커버리지가 이 값 미만이면 non-zero 로 끝난다.",
    )
    parser.add_argument(
        "--max-mismatch",
        type=int,
        default=None,
        help="sourceProjectionMismatch 가 이 값을 넘으면 non-zero 로 끝난다.",
    )
    parser.add_argument(
        "--max-malformed",
        type=int,
        default=None,
        help="malformed 생활권 값이 이 값을 넘으면 non-zero 로 끝난다.",
    )
    args = parser.parse_args()

    token = _access_token()
    users = {
        doc_id: doc
        for doc_id, doc in iter_docs(
            args.project, args.users_collection, args.limit, args.database, token
        )
    }
    public_profiles = {
        doc_id: doc
        for doc_id, doc in iter_docs(
            args.project, args.public_collection, args.limit, args.database, token
        )
    }

    report = summarize(users, public_profiles)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))

    failures = []
    if args.min_source_coverage is not None and (
        report["sourceCoverageRatio"] < args.min_source_coverage
    ):
        failures.append(
            "sourceCoverageRatio %.4f < %.4f"
            % (report["sourceCoverageRatio"], args.min_source_coverage)
        )
    if args.min_projection_coverage is not None and (
        report["projectionCoverageRatio"] < args.min_projection_coverage
    ):
        failures.append(
            "projectionCoverageRatio %.4f < %.4f"
            % (report["projectionCoverageRatio"], args.min_projection_coverage)
        )
    if args.max_mismatch is not None and (
        report["sourceProjectionMismatch"] > args.max_mismatch
    ):
        failures.append(
            "sourceProjectionMismatch %d > %d"
            % (report["sourceProjectionMismatch"], args.max_mismatch)
        )
    if args.max_malformed is not None:
        malformed = report["malformedSourceZones"] + report["malformedProjectionZones"]
        if malformed > args.max_malformed:
            failures.append("malformed zones %d > %d" % (malformed, args.max_malformed))

    if failures:
        print("GATE FAILED: " + "; ".join(failures), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
