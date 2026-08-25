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

# -----------------------------------------------------------------------------
# rollout activation
#
# 최종 정책(생활권이 다르면 추천 불가, 값이 없으면 fail-closed)은 고정이다.
# 이 플래그는 "그 정책을 지금 production 추천 경로에서 강제할 것인가"만
# 결정한다. missing 사용자만 허용하거나 cross-zone 을 일부 허용하는 완화
# 모드가 아니다.
#
#   OFF -> 기존 추천 정책 그대로 (생활권 조건 미적용)
#   ON  -> 기존 추천 정책 + 생활권 hard eligibility
#
# authoritative 위치는 Firestore `recommendationConfig/current` 문서다
# (blindMeetingConfig/current 와 같은 관례). 서버 전용 write 이며,
# 문서나 필드가 없으면 OFF 로 본다 — 롤아웃 준비 단계의 안전한 기본값이다.
# -----------------------------------------------------------------------------

RECOMMENDATION_CONFIG_COLLECTION = "recommendationConfig"
RECOMMENDATION_CONFIG_DOC = "current"
CAMPUS_LIFE_ZONE_ENFORCED_FIELD = "campusLifeZoneEnforced"
CAMPUS_LIFE_ZONE_POLICY_VERSION_FIELD = "campusLifeZonePolicyVersion"

# activation 은 3-state 다. "명시적으로 꺼져 있다" 와 "지금 상태를 모른다" 를
# 같은 False 로 뭉개면, 최종 활성화 이후의 일시적 config 조회 실패가 조용히
# cross-zone 추천을 다시 허용한다 (fail-open).
#
#   ACTIVATION_OFF      : 문서를 읽었고 활성화되지 않았다 (문서 없음 포함).
#   ACTIVATION_ENFORCED : 문서를 읽었고 boolean true 였다.
#   ACTIVATION_UNKNOWN  : 조회 자체가 실패했다. 어느 쪽으로도 단정하지 않는다.
ACTIVATION_OFF = "off"
ACTIVATION_ENFORCED = "enforced"
ACTIVATION_UNKNOWN = "unknown"


class CampusLifeZoneActivationUnknown(RuntimeError):
    """activation 상태를 확인하지 못했다.

    배치 파이프라인은 이 상태에서 추천을 새로 쓰지 않는다. 한 번 실패하는
    것이, 활성화된 정책을 모른 채 cross-zone 추천을 저장하는 것보다 안전하다.
    """


def campus_life_zone_activation_from_config(config: Any) -> str:
    """config 문서 내용만으로 activation 상태를 정한다 (읽기는 성공한 상태).

    정확히 boolean ``True`` 일 때만 ENFORCED 다. ``"true"``/``1`` 같은 느슨한
    값으로 정책이 켜지지 않는다. 문서·필드가 없으면 OFF (롤아웃 준비 단계).
    """
    if not isinstance(config, Mapping):
        return ACTIVATION_OFF
    if config.get(CAMPUS_LIFE_ZONE_ENFORCED_FIELD) is True:
        return ACTIVATION_ENFORCED
    return ACTIVATION_OFF


def campus_life_zone_enforced_from_config(config: Any) -> bool:
    """config 문서 내용으로 활성화 여부만 본다 (읽기는 성공한 상태).

    조회 실패와 명시적 OFF 를 구분해야 하는 곳은
    [campus_life_zone_activation_from_config] / [load_campus_life_zone_activation]
    을 쓴다.
    """
    return campus_life_zone_activation_from_config(config) == ACTIVATION_ENFORCED


def campus_life_zone_policy_version_from_config(config: Any) -> int:
    """정책 세대(epoch). 세 런타임이 같은 정책 버전을 쓰는지 확인할 때 쓴다.

    값이 없거나 정수가 아니면 0 (초기 세대).
    """
    if not isinstance(config, Mapping):
        return 0
    raw = config.get(CAMPUS_LIFE_ZONE_POLICY_VERSION_FIELD)
    if isinstance(raw, bool) or not isinstance(raw, int):
        return 0
    return raw if raw > 0 else 0


def load_campus_life_zone_activation_with_version(db: Any) -> Tuple[str, int]:
    """activation 상태와 정책 버전을 한 번의 read 로 읽는다."""
    try:
        snap = (
            db.collection(RECOMMENDATION_CONFIG_COLLECTION)
            .document(RECOMMENDATION_CONFIG_DOC)
            .get()
        )
        data = snap.to_dict() or {}
    except Exception as error:
        raise CampusLifeZoneActivationUnknown(str(error)) from error
    return (
        campus_life_zone_activation_from_config(data),
        campus_life_zone_policy_version_from_config(data),
    )


def load_campus_life_zone_activation(db: Any) -> str:
    """Firestore 에서 activation 상태를 읽는다. 조회 실패는 UNKNOWN.

    문서가 없는 것은 실패가 아니라 "아직 활성화한 적 없음" 이므로 OFF 다.
    """
    state, _version = load_campus_life_zone_activation_with_version(db)
    return state


def load_campus_life_zone_enforced(db: Any, *, on_unknown: str = "raise") -> bool:
    """activation 상태를 boolean 으로 읽는다.

    Args:
        on_unknown: 조회 실패 시 동작.
            ``"raise"`` (기본) — [CampusLifeZoneActivationUnknown] 을 올린다.
            결과를 저장하는 경로(배치)는 반드시 이 기본값을 쓴다.
            ``"off"`` — OFF 로 간주한다. 결과를 쓰지 않는 진단 도구 전용.
    """
    try:
        state = load_campus_life_zone_activation(db)
    except CampusLifeZoneActivationUnknown:
        if on_unknown == "off":
            return False
        raise
    return state == ACTIVATION_ENFORCED

__all__ = [
    "ACTIVATION_ENFORCED",
    "ACTIVATION_OFF",
    "ACTIVATION_UNKNOWN",
    "CAMPUS_LIFE_ZONE_ENFORCED_FIELD",
    "CAMPUS_LIFE_ZONE_FIELD",
    "CAMPUS_LIFE_ZONE_POLICY_VERSION_FIELD",
    "CANONICAL_CAMPUS_LIFE_ZONES",
    "CampusLifeZoneActivationUnknown",
    "RECOMMENDATION_CONFIG_COLLECTION",
    "RECOMMENDATION_CONFIG_DOC",
    "campus_life_zone_activation_from_config",
    "campus_life_zone_enforced_from_config",
    "campus_life_zone_policy_version_from_config",
    "load_campus_life_zone_activation",
    "load_campus_life_zone_activation_with_version",
    "read_persisted_campus_life_zones",
    "campus_life_zone_rejection",
    "campus_zone_compatibility",
    "has_compatible_campus_life_zone",
    "load_campus_life_zone_enforced",
    "normalize_campus_life_zones",
    "read_campus_life_zones_from_user_doc",
    "shared_campus_life_zones",
]


# canonical 생활권 값은 온보딩 resolver(lib/constants/campus_life_zones.dart)가
# 만드는 두 개뿐이다. 그 밖의 토큰은 손상된 값이며 생활권으로 인정하지 않는다.
CAMPUS_LIFE_ZONE_SINCHON = "sinchon"
CAMPUS_LIFE_ZONE_SONGDO = "songdo"
CANONICAL_CAMPUS_LIFE_ZONES = frozenset(
    {CAMPUS_LIFE_ZONE_SINCHON, CAMPUS_LIFE_ZONE_SONGDO}
)


def normalize_campus_life_zones(value: Any) -> Set[str]:
    """생활권 값을 canonical 집합으로 읽는다. 손상된 값은 전부 빈 집합.

    - canonical 이 아닌 토큰이 하나라도 있으면 **값 전체를 무효**로 본다
      (``["sinchon", "garbage"]`` 도 무효). 손상된 문서를 부분적으로 신뢰해
      실제로 만날 수 없는 상대를 추천하는 것보다 보충을 요구하는 편이 안전하다.
    - 빈 집합은 곧 fail-closed 이므로 호출부가 따로 분기할 필요가 없다.

    이 함수는 in-memory 값(집합/리스트/튜플)도 편의상 받는다. Firestore 에
    저장된 문서를 읽을 때는 타입까지 검증하는
    [read_persisted_campus_life_zones] 를 쓴다.
    """
    if isinstance(value, (list, tuple, set, frozenset)):
        items: Iterable[Any] = value
    elif isinstance(value, str):
        items = [value]
    else:
        return set()
    zones: Set[str] = set()
    for item in items:
        if not isinstance(item, str):
            return set()
        text = item.strip()
        if text not in CANONICAL_CAMPUS_LIFE_ZONES:
            return set()
        zones.add(text)
    return zones


def read_persisted_campus_life_zones(value: Any) -> Set[str]:
    """Firestore 에 저장된 ``campusLifeZones`` 필드를 읽는다 (스키마 검증 포함).

    canonical 스키마는 ``List<String>`` 이다. raw string ``"sinchon"`` 처럼
    타입이 다른 값은 손상으로 보고 빈 집합을 돌려준다 (fail-closed).
    """
    if not isinstance(value, (list, tuple)):
        return set()
    return normalize_campus_life_zones(value)


def read_campus_life_zones_from_user_doc(doc: Any) -> Set[str]:
    """raw ``users/{uid}`` 문서에서 생활권을 읽는다.

    canonical 위치는 중첩된 ``onboarding`` 맵이다. 필드를 flatten 하는
    index/projection 도 동작하도록 top level 도 함께 허용한다.
    """
    if not isinstance(doc, Mapping):
        return set()
    onboarding = doc.get("onboarding")
    if isinstance(onboarding, Mapping):
        zones = read_persisted_campus_life_zones(
            onboarding.get(CAMPUS_LIFE_ZONE_FIELD)
        )
        if zones:
            return zones
    return read_persisted_campus_life_zones(doc.get(CAMPUS_LIFE_ZONE_FIELD))


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
