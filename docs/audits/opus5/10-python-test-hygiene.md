# Python 29 RED test/environment hygiene

검증일: 2026-09-02 (Asia/Seoul)

## Baseline and policy

- latest-main integration baseline: `1222 passed, 29 failed, 6 skipped`
- 실패 이름은 기존 P-01~P-07과 정확히 동일했다.
- production allowlist, fail-closed policy, provider mode를 테스트에 맞춰 약화하지 않았다.
- test 삭제, skip, xfail, mock-only bypass는 추가하지 않았다.

## Cluster results

| Cluster | Before | Root cause / production evidence | Change | Targeted result | Production changed? |
|---|---:|---|---|---|---|
| P-01 Flask runtime | 5 fail | production requirements/Docker에는 Flask/gunicorn이 있으나 local interpreter에 Flask 없음 | 기존 pinned validation venv의 Flask 3.1.3과 직접 runtime deps만 격리 validation path로 사용 | 5 pass | NO |
| P-02 stale buckets | 17 fail | deploy/default contract는 `seolleyeon-final-*`; tests만 legacy bucket 사용 | source/temp/approved/chat fixture를 final bucket으로 교정하고 legacy/wrong bucket DENY를 유지 | 관련 batch 22 pass 후 마지막 exact 1 pass; full GREEN | NO |
| P-03 watermark booleans | 2 fail | raw boolean 하나는 typed/corroborated hard reject 근거가 아님 | 다른 hard reject는 유지하고 raw logo marker 단독 override 불가를 assertion | P-03/P-04 합계 4 pass | NO |
| P-04 eyewear | 2 fail | 현재 계약은 mismatch를 `needs_review`로 fail closed | non-previewable human-review state와 reason을 assertion | P-03/P-04 합계 4 pass | NO |
| P-05 production FLUX | 1 fail | production generation은 Azure이며 legacy FLUX는 진입 전에 거부 | analyzer/generator call 0과 stable rejection code를 assertion | 1 pass | NO |
| P-06 tokenizer artifact | 1 fail | offline cache에 exact tokenizer artifact가 없음 | 고정 repo/revision의 `tokenizer/*` 7개 파일만 temp에 받아 offline path로 검증 | 1 pass | NO |
| P-07 Rules literal | 1 fail | Rules helper가 old inline literal에서 `get()` + `after.diff(before)`로 진화 | brittle literal 대신 helper body/wiring 검사; 실제 emulator DENY 2개 추가 | Python 1 pass; Rules full 199 pass | NO |

## Environment hygiene details

P-01은 새 unpinned install을 하지 않았다. 기존 validation venv에서 아래 pinned runtime만 임시 validation site로 복사했다.

```text
Flask 3.1.3
Werkzeug 3.1.8
Jinja2 3.1.6
itsdangerous 2.2.0
click 8.4.2
blinker 1.9.0
MarkupSafe 3.0.3
```

이 격리는 Flask를 제공하면서 global MediaPipe가 없는 기존 test isolation을 보존했다. 전체 venv site-packages를 우선시한 첫 시도에서 실제 MediaPipe 하위 모듈이 fake root module을 앞질러 1개가 실패했으며, 원인을 확인한 뒤 최소 Flask runtime path로 교정했다. 저장소 코드는 이 환경 문제를 위해 변경하지 않았다.

P-06은 test source가 고정한 다음 artifact만 사용했다.

```text
repo: black-forest-labs/FLUX.2-klein-4B
revision: e7b7dc27f91deacad38e78976d1f2b499d76a294
subfolder: tokenizer
offline verification: enabled
model weights: not downloaded
```

## Full comparison

| Stage | Result |
|---|---|
| original security baseline | `1209 passed, 40 failed, 6 skipped` |
| after initial P1 remediation | `1221 passed, 29 failed, 6 skipped` |
| latest-main integration baseline | `1222 passed, 29 failed, 6 skipped` |
| after P-01~P-07 hygiene | `1258 passed` |
| final after redirect regression tests | `1260 passed in 184.33s` |

최종 run에는 failure, skip, xfail이 없다. 새 regression test 추가로 전체 test 수는 증가했고 기존 실패를 숨긴 항목은 없다.

```text
PYTHON_TEST_HYGIENE = PASS
PYTHON_FULL = PASS
NEW_FAILURE = 0
PRODUCTION_POLICY_WEAKENING = NO
```
> **HISTORICAL / RETIRED — NOT A CURRENT DEPLOYMENT AUTHORITY.** See [the current avatar architecture](../../avatar-production/CURRENT_ARCHITECTURE.md).
>
