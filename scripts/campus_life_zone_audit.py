#!/usr/bin/env python3
"""생활권(campusLifeZones) 결측률 read-only 감사.

추천은 생활권을 hard eligibility 로 쓰고 값이 없으면 fail-closed 이므로,
배포 전에 "정상 사용자 중 생활권 결측이 얼마나 되는지"를 반드시 확인해야
한다. 결측이 많으면 그 사용자들의 추천이 즉시 0명이 된다.

이 스크립트는 **읽기 전용**이다. Firestore 에 어떤 write 도 하지 않는다.
출력은 집계값만이며 uid/학과/학년 등 개인 식별 정보는 남기지 않는다.

사용 예:
    python scripts/campus_life_zone_audit.py --project seolleyeon-final
    python scripts/campus_life_zone_audit.py --project seolleyeon-final --limit 5000
    python scripts/campus_life_zone_audit.py --project seolleyeon-final \
        --collection publicProfiles

인증: gcloud auth application-default login 또는 서비스 계정.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from typing import Any, Mapping

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_AI_MODEL_DIR = os.environ.get(
    "AI_MODEL_DIR", os.path.join(_PROJECT_ROOT, "lib", "ai_recommend_model")
)
if _AI_MODEL_DIR not in sys.path:
    sys.path.insert(0, _AI_MODEL_DIR)

from campus_life_zone_policy import (  # noqa: E402
    CAMPUS_LIFE_ZONE_FIELD,
    normalize_campus_life_zones,
    read_campus_life_zones_from_user_doc,
)

CANONICAL = {"sinchon", "songdo"}


def _is_map(value: Any) -> bool:
    return isinstance(value, Mapping)


def _raw_zone_value(doc: Mapping[str, Any]) -> Any:
    onboarding = doc.get("onboarding")
    if _is_map(onboarding) and CAMPUS_LIFE_ZONE_FIELD in onboarding:
        return onboarding[CAMPUS_LIFE_ZONE_FIELD]
    return doc.get(CAMPUS_LIFE_ZONE_FIELD)


def _recommendation_eligible(doc: Mapping[str, Any]) -> bool:
    """추천 대상이 될 법한 정상 계정인지 (보수적 근사)."""
    if doc.get("isWithdrawn") is True:
        return False
    if str(doc.get("status") or "").lower() in {"withdrawn", "banned", "suspended"}:
        return False
    if doc.get("profileVisible") is False:
        return False
    verified = doc.get("isStudentVerified", doc.get("isVerified"))
    return verified is True


# 측정 전용: CampusLifeZoneResolver 가 값을 만들 수 있는 "입력이 존재하는지"만
# 본다. 생활권 자체를 계산하지 않는다 (분류 로직 단일 소스 유지).
_DEPT_ONLY_RULES = ("음악대학", "약학과", "첨단융합공학부")


def _resolver_inputs_available(doc: Mapping[str, Any]) -> bool:
    onboarding = doc.get("onboarding")
    onboarding = onboarding if _is_map(onboarding) else {}
    department = str(onboarding.get("department") or "").strip()
    if not department:
        return False
    if any(rule in department for rule in _DEPT_ONLY_RULES):
        return True
    return bool(str(onboarding.get("grade") or "").strip())


def _decode_rest_value(value: Mapping[str, Any]) -> Any:
    """Firestore REST 의 typed value 를 파이썬 값으로 바꾼다."""
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
            _decode_rest_value(v)
            for v in (value["arrayValue"].get("values") or [])
        ]
    if "mapValue" in value:
        return {
            k: _decode_rest_value(v)
            for k, v in (value["mapValue"].get("fields") or {}).items()
        }
    return None


def _iter_docs_rest(project: str, collection: str, limit: int | None, database: str):
    """google-cloud-firestore 2.29 의 database-id 인코딩 버그를 우회한다."""
    import subprocess
    import urllib.parse
    import urllib.request

    token = os.environ.get("GOOGLE_ACCESS_TOKEN", "").strip()
    if not token:
        import shutil

        exe = shutil.which("gcloud") or shutil.which("gcloud.cmd")
        if not exe:
            raise RuntimeError(
                "gcloud 를 찾지 못했다. GOOGLE_ACCESS_TOKEN 환경변수로 "
                "application-default access token 을 넘겨라."
            )
        token = subprocess.run(
            [exe, "auth", "application-default", "print-access-token"],
            capture_output=True, text=True, check=True, shell=False,
        ).stdout.strip()

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
            fields = doc.get("fields") or {}
            yield {k: _decode_rest_value(v) for k, v in fields.items()}
            seen += 1
        page_token = payload.get("nextPageToken")
        if not page_token:
            return


def audit(project: str, collection: str, limit: int | None, database: str | None) -> dict:
    stream = _iter_docs_rest(project, collection, limit, database or "(default)")

    total = 0
    eligible = 0
    repairable = 0
    needs_user_input = 0
    zone_state: Counter[str] = Counter()
    combo: Counter[str] = Counter()
    unknown_values: Counter[str] = Counter()

    for doc in stream:
        total += 1
        if not _recommendation_eligible(doc):
            continue
        eligible += 1

        raw = _raw_zone_value(doc)
        if raw is None:
            zone_state["missing_field"] += 1
            if _resolver_inputs_available(doc):
                repairable += 1
            else:
                needs_user_input += 1
            continue
        if not isinstance(raw, (list, tuple)):
            zone_state["invalid_type"] += 1
            continue
        zones = read_campus_life_zones_from_user_doc(doc)
        if not zones:
            zone_state["empty"] += 1
            if _resolver_inputs_available(doc):
                repairable += 1
            else:
                needs_user_input += 1
            continue

        unknown = zones - CANONICAL
        if unknown:
            zone_state["unknown_value"] += 1
            for value in sorted(unknown):
                # canonical 이 아닌 값의 "종류"만 센다 (개인 식별 아님).
                unknown_values[value] += 1
            continue

        zone_state["present"] += 1
        combo["+".join(sorted(zones))] += 1

    unusable = sum(
        zone_state[k] for k in ("missing_field", "empty", "invalid_type", "unknown_value")
    )
    with_zones = zone_state["present"]
    return {
        "project": project,
        "collection": collection,
        "sampled": total,
        "totalEligibleUsers": eligible,
        "withCampusLifeZones": with_zones,
        "missingCampusLifeZones": zone_state["missing_field"] + zone_state["empty"],
        "invalidCampusLifeZones": zone_state["invalid_type"] + zone_state["unknown_value"],
        "sinchonOnly": combo.get("sinchon", 0),
        "songdoOnly": combo.get("songdo", 0),
        "dual": combo.get("sinchon+songdo", 0),
        "repairableFromExistingData": repairable,
        "requiresUserRepair": needs_user_input,
        "coverageRatio": round(with_zones / eligible, 4) if eligible else None,
        "zoneState": dict(zone_state),
        "unknownZoneValues": dict(unknown_values),
        "readOnly": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--collection", default="users")
    parser.add_argument("--database", default=None)
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="샘플 문서 수 (미지정 시 전체 스캔 — 비용 주의)",
    )
    parser.add_argument(
        "--min-coverage",
        dest="min_coverage",
        type=float,
        default=None,
        help=(
            "생활권 보유 비율이 이 값 미만이면 exit 1 (release gate). "
            "임계값은 제품 판단이므로 기본값을 두지 않는다."
        ),
    )
    args = parser.parse_args()

    summary = audit(args.project, args.collection, args.limit, args.database)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))

    if args.min_coverage is None:
        return 0
    coverage = summary["coverageRatio"]
    if coverage is None:
        return 0
    return 0 if coverage >= args.min_coverage else 1


if __name__ == "__main__":
    raise SystemExit(main())
