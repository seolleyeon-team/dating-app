"""컨테이너 안에서 생활권 정책 배선을 확인한다.

production 이미지(recsys/Dockerfile)에 필요한 모듈이 실제로 들어갔는지,
config 상태(OFF / ON / UNKNOWN)에 따라 일일 추천 선택이 어떻게 달라지는지,
손상된 생활권 값이 fail-closed 되는지, RRF 품질 게이트 기본값이 2인지를
네트워크 없이 확인한다.

실행:
  docker build -f recsys/Dockerfile -t recs-pipeline-verify .
  docker run --rm --entrypoint python \
    -v "<repo>/scripts/container_campus_life_zone_activation_check.py:/app/check.py" \
    recs-pipeline-verify /app/check.py

읽기 전용이고 외부 통신을 하지 않는다 (Firestore stub 만 쓴다).
"""

import re
import sys

# production 코드(recsys.jobs.daily_job)와 같은 방식으로 모델 디렉터리를 잡는다.
from recsys.jobs.daily_recommender import (  # noqa: E402,F401
    DailySelectionConfig,
    select_daily_items,
)

from campus_life_zone_policy import (  # noqa: E402
    ACTIVATION_ENFORCED,
    ACTIVATION_OFF,
    CampusLifeZoneActivationUnknown,
    campus_life_zone_enforced_from_config,
    has_compatible_campus_life_zone,
    load_campus_life_zone_activation,
    load_campus_life_zone_enforced,
    read_persisted_campus_life_zones,
)


class _Doc:
    def __init__(self, data):
        self._data = data

    def to_dict(self):
        return self._data


class _Ref:
    def __init__(self, data):
        self._data = data

    def get(self):
        return _Doc(self._data)


class _Col:
    def __init__(self, data):
        self._data = data

    def document(self, _doc_id):
        return _Ref(self._data)


class _Db:
    def __init__(self, data):
        self._data = data

    def collection(self, _name):
        return _Col(self._data)


class _BrokenDb:
    def collection(self, _name):
        raise RuntimeError("firestore unavailable")


def _meta(gender, zones):
    return {
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
    }


ITEMS = [{"uid": "other", "score": 0.9}]

failures = []


def check(name, condition, detail=""):
    if condition:
        print("  ok   %s" % name)
    else:
        failures.append(name)
        print("  FAIL %s %s" % (name, detail))


def run(enforced, actor_zones, candidate_zones):
    meta = {
        "actor": _meta("male", actor_zones),
        "other": _meta("female", candidate_zones),
    }
    users = {
        "actor": {"onboarding": {"campusLifeZones": actor_zones}},
        "other": {"onboarding": {"campusLifeZones": candidate_zones}},
    }
    return select_daily_items(
        "actor",
        ITEMS,
        meta,
        date_key="20260826",
        candidate_docs=users,
        config=DailySelectionConfig(campus_life_zone_enforced=enforced),
    )


print("[container] activation 판정")
check("문서 없음 -> OFF", load_campus_life_zone_activation(_Db(None)) == ACTIVATION_OFF)
check("빈 문서 -> OFF", load_campus_life_zone_activation(_Db({})) == ACTIVATION_OFF)
check(
    "boolean true 만 ON",
    load_campus_life_zone_activation(_Db({"campusLifeZoneEnforced": True}))
    == ACTIVATION_ENFORCED
    and campus_life_zone_enforced_from_config({"campusLifeZoneEnforced": "true"})
    is False,
)

unknown_raised = False
try:
    load_campus_life_zone_activation(_BrokenDb())
except CampusLifeZoneActivationUnknown:
    unknown_raised = True
check(
    "조회 실패 -> UNKNOWN (OFF 로 수렴하지 않는다)",
    unknown_raised,
)

batch_aborts = False
try:
    load_campus_life_zone_enforced(_BrokenDb())
except CampusLifeZoneActivationUnknown:
    batch_aborts = True
check("배치 기본 동작은 중단이다", batch_aborts)
check(
    "읽기 전용 도구만 OFF 를 택할 수 있다",
    load_campus_life_zone_enforced(_BrokenDb(), on_unknown="off") is False,
)

print("[container] OFF 상태의 일일 추천")
off = run(False, ["sinchon"], ["songdo"])
check("OFF 면 다른 생활권 후보가 남는다", off["topN"] == 1, off["selection"])
check(
    "OFF 여도 관측 카운터는 기록된다",
    off["selection"]["campusLifeZoneObserved"].get("campus_life_zone_mismatch") == 1,
    off["selection"]["campusLifeZoneObserved"],
)
check("OFF 는 enforced=False 로 보고된다", off["selection"]["campusLifeZoneEnforced"] is False)

print("[container] ON 상태의 일일 추천")
on = run(True, ["sinchon"], ["songdo"])
check("ON 이면 다른 생활권 후보가 제외된다", on["topN"] == 0, on["selection"])
check(
    "ON 이면 제외 사유가 rejected 에 남는다",
    on["selection"]["rejected"].get("campus_life_zone_mismatch") == 1,
    on["selection"]["rejected"],
)
check("ON 은 enforced=True 로 보고된다", on["selection"]["campusLifeZoneEnforced"] is True)
same = run(True, ["songdo"], ["sinchon", "songdo"])
check("ON 이어도 같은 생활권(이중 포함)은 통과한다", same["topN"] == 1, same["selection"])

print("[container] 손상된 생활권 값")
for label, value in (
    ("garbage 토큰", ["garbage"]),
    ("canonical + garbage", ["sinchon", "garbage"]),
    ("raw string", "sinchon"),
    ("숫자", 123),
    ("null", None),
    ("빈 배열", []),
):
    check("%s -> 무효" % label, read_persisted_campus_life_zones(value) == set())
check(
    "같은 손상 값끼리도 호환되지 않는다",
    has_compatible_campus_life_zone(["garbage"], ["garbage"]) is False,
)
malformed = run(True, ["sinchon"], ["garbage"])
check(
    "ON 에서 손상된 후보는 제외된다",
    malformed["topN"] == 0,
    malformed["selection"],
)

print("[container] 미팅(3:3) 추천 모듈도 이미지에 포함됐는지")
for module_name in (
    "seolleyeon_meeting_common_v1",
    "seolleyeon_meeting_recommend_export_v1",
    "seolleyeon_meeting_daily_recs_export_v1",
    "seolleyeon_rec_common_v3",
    "seolleyeon_rrf_export",
):
    try:
        __import__(module_name)
        print("  ok   import %s" % module_name)
    except Exception as error:  # noqa: BLE001 - 이미지 누락을 그대로 보고한다
        failures.append("import %s" % module_name)
        print("  FAIL import %s (%s)" % (module_name, error))

import seolleyeon_meeting_common_v1 as meeting_common  # noqa: E402

meeting_unknown = False
try:
    meeting_common.load_campus_life_zone_enforced(_BrokenDb())
except CampusLifeZoneActivationUnknown:
    meeting_unknown = True
check("미팅 모듈도 같은 activation 판정을 쓴다", meeting_unknown)

print("[container] RRF 소스 품질 게이트")
import seolleyeon_rrf_export as rrf  # noqa: E402

parser_src = open(rrf.__file__, encoding="utf-8").read()
match = re.search(r'"--min_sources_per_user", type=int, default=(\d+)', parser_src)
check(
    "이미지 안의 기본값이 2 다",
    match is not None and match.group(1) == "2",
    match.group(1) if match else "not found",
)
check(
    "단일 소스는 게이트를 통과하지 못한다",
    rrf.passes_source_quality_gate({"usedSources": ["svd"]}, 2) is False
    and rrf.passes_source_quality_gate({"usedSources": ["clip"]}, 2) is False,
)
check(
    "두 소스 이상이면 통과한다",
    rrf.passes_source_quality_gate({"usedSources": ["clip", "svd"]}, 2) is True,
)

main_src = open("/app/recsys/main.py", encoding="utf-8").read()
check(
    "Cloud Run entrypoint 기본값도 2 다",
    "DEFAULT_RRF_MIN_SOURCES_PER_USER = 2" in main_src,
)

print("")
if failures:
    print("CONTAINER CHECK FAILED: %d" % len(failures))
    sys.exit(1)
print("CONTAINER CHECK PASSED")
