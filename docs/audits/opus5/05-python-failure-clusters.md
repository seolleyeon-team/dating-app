# Python 40개 실패 root-cause clustering

검증일: 2026-09-02 (Asia/Seoul)

## 기준선과 격리 재현

Canonical command:

```text
C:/Users/samsung/AppData/Local/Programs/Python/Python311/python.exe -m pytest -q tests recsys/tests
```

- 수정 전 fresh result: 1209 pass, 40 fail, 6 skip
- 모든 실패군을 단독/관련 subset으로 재현했다.
- 단독에서는 통과하고 full suite에서만 실패하는 항목이 없었다.
- environment, module global, mock, import order에 의한 state contamination 증거는 없었다.

## Cluster summary

| Cluster | Count | Primary root cause | Severity | Action |
|---|---:|---|---|---|
| P-01 Flask local test runtime absent | 5 | 현재 interpreter에 Flask가 없어 `worker_service.app is None`; 배포 requirements와 Docker image에는 Flask/gunicorn이 명시됨 | ENVIRONMENT_ONLY | production 변경 없음 |
| P-02 pre-`seolleyeon-final` bucket fixtures | 17 | 테스트가 legacy source/temp/approved/chat bucket을 사용하지만 현재 job/cleanup/QA 기본값과 배포 설정은 `seolleyeon-final-*`만 허용 | TEST_ONLY | 이번 P0/P1 scope에서 미수정 |
| P-03 legacy raw watermark boolean expectations | 2 | 이전 테스트가 raw logo/text boolean을 hard reject로 기대; 현 계약은 typed/redacted corroborated evidence만 hard reject | TEST_ONLY | 미수정 |
| P-04 legacy eyewear hard-reject expectations | 2 | 현재 trait policy는 eyewear mismatch를 `needs_review`로 fail closed하며 hard reject하지 않음 | TEST_ONLY | 미수정 |
| P-05 prohibited production FLUX expectation | 1 | 테스트가 production FLUX 경로 진입을 기대하지만 canonical Azure migration 이후 legacy FLUX는 즉시 거부됨 | TEST_ONLY | 미수정 |
| P-06 offline Hugging Face artifact absent | 1 | local cache에 tokenizer가 없고 offline env가 활성화됨; production image는 build 중 pinned model을 다운로드함 | ENVIRONMENT_ONLY | dependency/network 변경 없음 |
| P-07 stale Rules source-string assertion | 1 | 테스트는 이전 inline expression을 검색; 현재 Rules는 `get()`과 `after.diff(before)` helper로 동일/강화 계약을 구현 | TEST_ONLY | 미수정 |
| P-08 CLIP private-media loader regression | 11 | private GCS loader와 sensitive URL guard가 공통 모듈에 존재하지만 CLIP embedder wiring에서 제거됨 | P1 | TDD 최소 수정 완료 |

합계: 40. P0: 0, P1: 1 cluster, UNKNOWN: 0.

## P-01 — Flask local test runtime absent (5)

Affected tests:

- `test_worker_service_exposes_authenticated_recovery_route`
- `test_worker_service_paid_calibration_endpoint_is_disabled_by_default`
- `test_worker_service_exposes_authenticated_internal_calibration_route`
- `test_worker_service_returns_only_stable_calibration_error`
- `test_authenticated_qa_diagnostics_route_is_flag_gated`

Common boundary: `worker_service.app.test_client()` on `None`. `requirements_avatar_worker.txt` and the production Dockerfile install Flask and run gunicorn, so this local interpreter gap is not evidence of a production runtime defect.

## P-02 — stale bucket fixtures (17)

Downstream groups:

- job lease/state: 7 tests in `test_avatar_job_lease.py`
- load/cost canary: 2 tests in `test_avatar_pr7_load_canary.py`
- cleanup/TTL: 5 tests in `test_avatar_qa_cleanup.py`
- private chat copy fixture: 1 test in `test_avatar_media_privacy.py`
- CLIP job handler fixtures: 2 tests in `test_clip_job_handler.py`

Primary failure: source refs are rejected as `invalid_source_refs` or no deletion/claim is planned because the bucket does not equal the current final-project allowlist. Current Dockerfile, deploy scripts, new default-contract tests, and commit history agree on:

```text
seolleyeon-final-private-source-photos
seolleyeon-final-avatar-temp
seolleyeon-final-approved-avatars
seolleyeon-final-chat-profile-photos
```

No production allowlist was weakened to accept stale fixtures.

## P-03/P-04 — current QA policy versus legacy assertions (4)

- Watermark failures: `test_qa_rejects_childlike_high_similarity_and_watermark`, `test_qa_rejects_generated_multi_face_background_text_and_bad_crop`.
- Eyewear failures: `test_run_avatar_candidate_qa_rejects_invented_eyewear_signal`, `test_run_avatar_candidate_qa_rejects_omitted_eyewear_trait_card`.

`docs/avatar-production/avatar-qa-contract.md`, current policy source, and newer passing product-contract tests agree: uncorroborated watermark/logo markers and eyewear mismatch do not become automatic hard rejects; ambiguous cases remain non-previewable human review. This is fail closed, not a QA bypass.

## P-05/P-06/P-07 — isolated contract/environment failures (3)

- P-05: `test_production_flux_cannot_disable_source_analysis_or_reach_generation` reaches an earlier intentional `legacy_flux_is_not_a_production_generation_backend` rejection.
- P-06: `test_deployed_flux_tokenizer_keeps_core_clauses_and_traits_inside_budget` cannot resolve an uncached model in offline local mode.
- P-07: `test_firestore_rules_protect_client_written_avatar_display_fields` searches for an obsolete literal. Commit history shows the production helper now uses `request.resource.data.get('onboarding', {})`, `resource.data.get(...)`, and `after.diff(before)`.

## P-08 — confirmed CLIP P1 (11)

Affected pre-fix failures:

- 3 helper/loader tests: GCS URI parsing (2) and allowed-bucket/size loading (1)
- 8 parameterized cases requiring signed/private/temp HTTPS rejection before any download

Production reachability:

```text
Functions upload callable
  -> clip_embedding Cloud Task (enabled by default unless explicitly disabled)
  -> clip_job_service
  -> seolleyeon_clip_job_handler
  -> authoritative userPrivateMedia gs:// refs
  -> SeolleyeonCLIPEmbedder.embed_profile_mean()
  -> load_image_any()
```

Before the fix, `load_image_any()` treated `gs://...` as a local filesystem path, so the normal private-media CLIP path failed. `_load_image_from_url()` also downloaded allowlisted-host signed/private URLs without first applying the repository privacy classifier. History shows both capabilities were part of the private GCS contract and were accidentally disconnected during a broad merge.

## After-remediation failure set

Fresh result: 1221 pass, 29 fail, 6 skip. One new focused regression test was added; no test was deleted.

The 29 remaining failures are exactly P-01 through P-07:

```text
5 + 17 + 2 + 2 + 1 + 1 + 1 = 29
```

No P-08 test remains failing and no new test name appeared.
