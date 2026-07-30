# PR8.5 작은 얼굴 blur 차단 원인 분석 및 안전한 개선 결과

작성일: 2026-07-28

## 1. 결론

- 최종 상태: `BLOCKED_BY_MORE_CALIBRATION`
- production-ready: `false`
- 라이브 업로드: 0건
- 배포, App Check, IAM 변경: 없음
- FLUX 실행: 0건

기존 통과 7건은 v1과 v3 shadow에서 모두 통과했다. 기존 blur 차단 3건은 v3가 명확한 통과나 확정 true blur로 분류하지 못해 모두 검토 대상으로 남았다. 따라서 false-positive 수정은 0건이며, 활성 v1의 GPU 이전 차단 3건을 유지한다. 이 10건만으로 운영 임계값을 낮추거나 v3를 활성화하지 않는다.

## 2. Evidence baseline

- worker revision evidence: `seolleyeon-avatar-worker-00047-9qx`
- participant count: 10
- detected: 10/10
- old accepted: 7/10
- old blur blocked: 3/10
- tile fallback: 0/10
- exact UID/photo consent match: 10/10
- Auth UID match: 10/10
- App Check: 기존 live runner 교환에서 403이 있었으며, 이번 작업에서는 우회·토큰 등록·설정 변경을 하지 않았다.

로컬 진단 후보는 `avatar_face_blur_multimetric_v3`, 정책은 `pr85_v3_shadow`, 보정 상태는 `uncalibrated_candidate`다. 활성 판정을 대체하지 않는다.

## 3. 기존 blur 판정 경로

- EXIF 정규화된 원본에서 full-range detection, 필요 시 tile detection, NMS, primary selection을 수행한다.
- blur 점수는 clamped native detector face region에서 계산된다.
- 기존 metric은 grayscale `FIND_EDGES` 평균을 40으로 나눈 뒤 `[0, 1]`로 제한한다.
- native face size와 무관하게 `< 0.12`를 blur로 차단한다.
- 이 판정은 head-and-shoulders crop, resize, landmarker, privacy 처리, GPU 생성보다 먼저 실행된다.

따라서 현재 3건의 차단 원인은 이후 crop·resize·padding·landmarker·FLUX가 아니다. 확인된 일반 결함은 기존 metric이 ROI 크기, 경계 에너지, 휘도와 노이즈에 민감하고 하나의 고정 임계값을 사용한다는 점이다. 이 점은 metric 교체 사유지만, 현재 3건을 강제로 통과시킬 근거는 아니다.

## 4. 익명 사진별 원인

| rowIndex | uidHash | photoHashPrefix | faceSizeBucket | oldReason | rootCause | v3 shadow | 근거 |
| ---: | --- | --- | --- | --- | --- | --- | --- |
| 4 | `uid:b8c1466f0fd6` | `fd6aef797ded` | ge192 | blur | `UNKNOWN_NEEDS_MORE_EVIDENCE` | review | native 해상도와 노출은 충분하지만 native/canonical 선명도 신호가 충돌 |
| 5 | `uid:800c4a4906f0` | `19de73a2087c` | ge192 | blur | `UNKNOWN_NEEDS_MORE_EVIDENCE` | review | native 해상도와 노출은 충분하며 일부 저대비 기여 가능성이 있으나 확정 불가 |
| 9 | `uid:c089fa9e969f` | `b4b2a589f594` | ge192 | blur | `UNKNOWN_NEEDS_MORE_EVIDENCE` | review | native 해상도와 노출은 충분하지만 native/canonical 선명도 신호가 충돌 |

세 건 모두 full-image 단일 얼굴 detection이며 tile fallback이 없었다. 저해상도, 심한 저조도, 차별적인 JPEG 손상, 이후 crop·resize 오염은 주원인으로 지지되지 않는다. 현재 증거로 motion과 defocus를 구분하거나 true optical blur를 확정하면 과도한 주장이다.

## 5. 수정 내용

- `diagnostic_roi.py`: native face-quality ROI, 원본 유효 픽셀 mask, downscale-only canonical ROI를 분리했다. padding은 metric에서 제외한다.
- `diagnostic_metrics.py`: Laplacian variance, mean-squared Sobel Tenengrad, edge density, local contrast, exposure/clipping, compression risk와 보조 방향성 신호를 CPU로 계산한다.
- `blur_assessment.py`: typed/versioned v3 shadow 분류기를 추가했다. 저해상도, 노출, 압축 위험, invalid ROI와 blur 증거를 분리하고 충돌은 검토 대상으로 보낸다.
- `pipeline.py`: 활성 v1 결정을 유지하면서 같은 assessor를 명시적 opt-in shadow로 실행한다. 기본값은 비활성이라 활성 경로에 평가 비용을 추가하지 않는다. opt-in 평가가 실패해도 민감한 예외 내용을 남기지 않고 `unavailable`로 격리해 v1 결과를 바꾸지 않는다.
- `environment.py`, `source_analyzer.py`, `worker.py`, reference privacy·QA 경계: 세 환경 별칭을 공유하고 하나라도 production-like이면 fail-closed로 처리한다. production-like 환경에서는 source analysis와 reference privacy preprocess를 끌 수 없고 legacy detector 주입도 small-face 경계를 우회하지 못한다. QA dev/staging bypass도 거부된다. 모델 부재·분석 실패는 차단하며 blur, low-resolution, low-light, out-of-frame, landmark, compression, uncertain 사유를 분리한다.
- `quality_context.py`와 내부 types: geometry·metric을 repr에서 숨기고 persistence는 재귀 allowlist만 통과시킨다.
- `avatar_blur_diagnostics.py`: 10건 local-only 진단과 익명화된 hash/bucket/aggregate만 출력하며 rowIndex 기반 우회 판정이 없다.

## 6. Blur Assessment v3 shadow

PR8.5에서 요구한 v2 산출물 이름은 호환을 위해 유지했지만 실제 후보 구현 버전은 v3다.

- ROI: 작은 margin을 둔 native primary face-quality ROI
- native-resolution policy: native short side가 최소값보다 작으면 blur가 아니라 low resolution으로 분리
- metrics: Laplacian variance, Tenengrad, edge density, local contrast, exposure/clipping, compression risk, 보조 방향성
- normalization: canonical short side 160px로 downscale만 수행하고 upscale은 금지
- decision: 명확한 다중 신호 합의만 pass 또는 reject 후보, 충돌·압축 불확실성은 borderline/needs_review, invalid ROI는 fail-closed
- version: `avatar_face_blur_multimetric_v3`
- policy: `pr85_v3_shadow`
- activation: `AVATAR_BLUR_SHADOW_ENABLED=true`인 명시적 관찰 실행에서만 pipeline 평가; 기본값 false
- config snapshot SHA-256: `cc11820c5ab0d42595119b88058e36efc01ce9656c97bfe00e3f5d1e50a0cc25`

현재 숫자는 운영 임계값이 아니라 10건 cohort와 합성 회귀로 검증한 초기 shadow 후보값이다.

## 7. 결과 비교

- old pass/reject: 7 / 3
- new pass/reject/review: 7 / 0 / 3
- false-positive corrected: 0
- active-v1 blur rejection retained: 3
- v3-confirmed true blur: 0
- low-resolution reclassified: 0
- low-light reclassified: 0
- unresolved: 3

v3의 review는 pass가 아니다. 활성 v1은 세 건을 계속 GPU 이전에 차단하므로 안전·비용·개인정보 경계를 유지한다.

## 8. 회귀 결과

- 기존 통과 7건: v3 shadow 7/7 pass
- 기존 차단 3건: v3 shadow 3/3 review, 활성 v1 차단 유지
- true blur, clear face, small face, exposure, JPEG, invalid ROI, crop/mask, 사유 코드 분리 회귀 테스트 추가
- native/canonical conflict, compression phase, canonical mask erosion, border-contact ROI 회귀 테스트 추가
- CV 검토: shadow-only 범위 `APPROVE`
- 개인정보·보안 검토: `APPROVE`
- 최종 코드 재검토: CRITICAL/HIGH/MEDIUM/LOW 0건, `APPROVE`
- 최종 아키텍처 재검토: `CLEAR`

## 9. 성능

- benchmark: deterministic synthetic 768 x 768 input, synthetic face short side 384px
- 측정 범위: `BlurAssessor.assess`만 포함
- warm-up / measured: 10 / 100
- CPU p50 / p95: 254.869 / 356.387 ms
- min / max: 158.081 / 699.327 ms
- detector, model startup, decode, I/O 제외
- 기본 활성 경로의 v3 평가 비용: 0ms; shadow 기본 비활성
- opt-in shadow 관찰 시 위 microbenchmark 비용이 추가될 수 있음
- source rejection before GPU: 유지
- 신규 모델 및 GPU 비용: 없음

단일 Windows CPU microbenchmark이므로 운영 처리량 수치로 해석하지 않는다.

## 10. 개인정보 및 변경 경계

- raw UID, 원본 파일명·경로·object reference: 미포함
- raw bbox·keypoint·landmark 및 image bytes: 미포함
- credential 및 App Check debug token: 미포함
- 보고서·artifact: rowIndex, 익명 hash prefix, bucket, safe aggregate만 포함
- live/cloud mutation, deployment, App Check·IAM 변경: 없음

process-local assessment metric과 geometry는 persistence allowlist에 포함되지 않는다.

## 11. Tests

- focused blur/reason/security/pipeline: 56 passed
- focused final blur/architecture/worker: 132 passed
- focused environment/privacy/QA: 62 passed
- full Python: 601 passed, 6 skipped
- Python compileall: pass
- Functions TypeScript build: pass
- Functions tests: 126 passed
- Flutter analyze (`--no-pub`): no issues
- Flutter tests (`--no-pub`): 102 passed
- privacy QA (`--dry_run --fail_on_warning`): pass, 238 files scanned, leakage/warning counts 0
- `git diff --check`: pass; 기존 CRLF 정규화 경고만 있음

## 12. Remaining blockers

- 이 cohort와 독립적인 labeled face-quality dataset에 sharp, defocus, motion, low texture, exposure, noise, JPEG 사례가 필요하다.
- native size 및 camera pipeline별 false-pass/false-reject rate를 측정해야 한다.
- canonical scale·blur kernel 안정성, border-contact tolerance, compression의 독립 x/y phase를 검증해야 한다.
- activation threshold, rollback 기준, shadow 관찰 기간과 배포 승인이 필요하다.
- App Check 403은 별도 운영 blocker다. 권한 있는 사용자 또는 관리자가 승인된 token/device flow로 해결해야 하며, 이번 작업은 debug token 등록, enforcement 우회, IAM 변경을 하지 않았다.
- 승인 전 live staging 재실행은 별도 작업이며 이번 범위에서는 수행하지 않았다.

"blur 李⑤떒? ?듦낵?⑥쓣 留욎텛湲??꾪빐 ?꾧퀎媛믪쓣 ??텛??諛⑹떇?쇰줈 ?닿껐?섏? ?딆븯?? primary face??native-resolution ?덉쭏??湲곗??쇰줈 true blur, low resolution, exposure쨌compression 臾몄젣, crop쨌resize ?ㅻ쪟? 遺꾩꽍 遺덊솗?ㅼ꽦??遺꾨━?섍퀬, ?ㅼ젣濡??ъ슜?섍린 ?대젮???ъ쭊? FLUX ?ㅽ뻾 ?꾩뿉 怨꾩냽 ?덉쟾?섍쾶 李⑤떒?쒕떎."
