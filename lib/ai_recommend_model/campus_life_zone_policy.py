#!/usr/bin/env python3
"""생활권(campus life zone) 추천 eligibility 정책 — 순수 모듈.

1:1 추천, 3:3 블라인드 취향 미팅, 3:3 시즌 미팅이 모두 이 모듈의 semantics를
공유한다. numpy/torch/firestore 같은 무거운 의존성 없이 단독으로 import 되어야
하므로 표준 라이브러리만 사용한다 (recsys/jobs/meeting_verify_policy.py 와 같은
pure-policy 분리 패턴).

핵심 원칙
---------
- 생활권 분류 자체는 클라이언트의 ``CampusLifeZoneResolver``
  (lib/constants/campus_life_zones.dart) 가 유일한 source of truth이고,
  결과는 ``users/{uid}.onboarding.campusLifeZones`` 에 저장된다.
  추천기는 grade/department/RA 로 절대 재계산하지 않고 저장된 값만 읽는다.
- 생활권은 랭킹 점수가 아니라 **hard eligibility** 조건이다.
- 한 사용자가 여러 생활권(신촌+송도)을 가질 수 있으므로 비교는 언제나
  집합 교집합이며, 단일 값 equality 로 구현하지 않는다.
- 값이 없거나 비어 있으면 **fail-closed** (추천 불가). 다른 생활권으로
  대체 추천하지 않는다.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Optional, Sequence, Set, Tuple

CAMPUS_LIFE_ZONE_FIELD = "campusLifeZones"

__all__ = [
    "CAMPUS_LIFE_ZONE_FIELD",
    "campus_life_zone_rejection",
    "campus_zone_compatibility",
    "has_compatible_campus_life_zone",
    "normalize_campus_life_zones",
    "read_campus_life_zones_from_user_doc",
    "shared_campus_life_zones",
]


def normalize_campus_life_zones(value: Any) -> Set[str]:
    """저장된 campusLifeZones 값을 집합으로 읽는다. 알 수 없는 형태는 빈 집합."""
    if isinstance(value, (list, tuple, set, frozenset)):
        items: Iterable[Any] = value
    elif isinstance(value, str):
        items = [value]
    else:
        return set()
    zones: Set[str] = set()
    for item in items:
        text = str(item).strip() if item is not None else ""
        if text:
            zones.add(text)
    return zones


def read_campus_life_zones_from_user_doc(doc: Any) -> Set[str]:
    """raw ``users/{uid}`` 문서에서 생활권을 읽는다.

    canonical 위치는 중첩된 ``onboarding`` 맵이다. 필드를 flatten 하는
    index/projection 도 동작하도록 top level 도 함께 허용한다.
    """
    if not isinstance(doc, Mapping):
        return set()
    onboarding = doc.get("onboarding")
    if isinstance(onboarding, Mapping):
        zones = normalize_campus_life_zones(onboarding.get(CAMPUS_LIFE_ZONE_FIELD))
        if zones:
            return zones
    return normalize_campus_life_zones(doc.get(CAMPUS_LIFE_ZONE_FIELD))


def has_compatible_campus_life_zone(left: Any, right: Any) -> bool:
    """두 사용자는 생활권이 교차할 때만 서로 추천될 수 있다.

    equality 가 아니라 집합 교집합이다. 복수 생활권 사용자
    (``['sinchon', 'songdo']``) 는 양쪽 단일 생활권 모두와 호환된다.
    """
    left_zones = normalize_campus_life_zones(left)
    right_zones = normalize_campus_life_zones(right)
    if not left_zones or not right_zones:
        return False
    return bool(left_zones & right_zones)


def shared_campus_life_zones(zone_values: Iterable[Any]) -> Set[str]:
    """그룹 전원이 공유하는 생활권 (교집합).

    3:3 미팅에서 쓴다. 전원이 실제로 함께 만날 수 있어야 하므로 다수결·
    대표자·첫 멤버 기준은 절대 허용되지 않는다. 한 명이라도 생활권 정보가
    없으면 빈 집합을 돌려준다 (fail-closed).
    """
    shared: Optional[Set[str]] = None
    saw_any = False
    for value in zone_values:
        saw_any = True
        zones = normalize_campus_life_zones(value)
        if not zones:
            return set()
        shared = zones if shared is None else (shared & zones)
        if not shared:
            return set()
    if not saw_any:
        return set()
    return shared or set()


def campus_life_zone_rejection(
    actor_meta: Optional[Mapping[str, Any]],
    candidate_meta: Optional[Mapping[str, Any]],
) -> Optional[str]:
    """1:1 추천 pair 가 거부되면 skip 사유를, 통과하면 None 을 돌려준다.

    boolean predicate 와 분리해 두어 호출부가 생활권 사유를 일반 "policy"
    카운터에 뭉뚱그리지 않고 구분해서 관측할 수 있게 한다.
    """
    actor_zones = normalize_campus_life_zones(
        (actor_meta or {}).get(CAMPUS_LIFE_ZONE_FIELD)
    )
    candidate_zones = normalize_campus_life_zones(
        (candidate_meta or {}).get(CAMPUS_LIFE_ZONE_FIELD)
    )
    if not actor_zones or not candidate_zones:
        return "missing_campus_life_zones"
    if not (actor_zones & candidate_zones):
        return "campus_life_zone_mismatch"
    return None


def campus_zone_compatibility(
    left_zones: Sequence[str],
    right_zones: Sequence[str],
    *,
    allow_missing_campus_zone: bool = False,
) -> Tuple[bool, Optional[str]]:
    """두 그룹의 공통 생활권 판정. ``regionId`` 정책과 완전히 독립이다.

    ``regionId`` 는 대학/파티션 키이고 생활권은 신촌/송도 캠퍼스 생활권으로
    서로 다른 축이다. 두 정책은 각각 독립적으로 적용된다.

    Returns:
        ``(ok, skip_reason)``. 통과하면 ``(True, None)``.
    """
    left = normalize_campus_life_zones(list(left_zones))
    right = normalize_campus_life_zones(list(right_zones))
    if not left or not right:
        # 기본은 fail-closed. 운영 토글은 있지만 켜지 않는 것이 기본값이다.
        if allow_missing_campus_zone:
            return True, None
        return False, "missing_campus_life_zones"
    if left & right:
        return True, None
    return False, "campus_life_zone_mismatch"
