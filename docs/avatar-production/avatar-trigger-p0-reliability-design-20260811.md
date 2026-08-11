# 설레연 Avatar Trigger P0 Reliability Design

작성일: 2026-08-11 (KST)
상태: 로컬 설계 초안 — 운영 배포/재활성화 전용 승인 필요

## 1. 범위와 운영 안전선

이번 작업의 목적은 2026-07-29 이후 발생한 Firestore/Eventarc/Pub/Sub 증폭 사고의
재발을 코드, 회귀 테스트, Emulator, trigger graph 검증으로 차단하는 것이다.

이번 작업에서는 다음을 하지 않는다.

- Firebase Functions 운영 배포
- Eventarc trigger 재활성화
- production Firestore/Storage/Pub/Sub/Cloud Tasks mutation
- live avatar generation 또는 비용 발생형 검증

2026-08-10 20:03 KST에 분리한 `onavatargenerationstatesync-334616` 및
`onavatarjobsourceretention-371023` Eventarc 연결은 계속 비활성 상태로 유지한다.
함수 코드만 고쳐도 운영 trigger가 자동으로 복구되지 않으며, 재배포/재활성화는 별도
승인과 아래 gate를 모두 통과한 뒤에만 가능하다.

## 2. 확인된 사고 원인

현재 `functions/src/avatarGenerationStateSync.ts`는
`onDocumentWritten("avatarJobs/{jobId}")`로 모든 job write를 받고, terminal 상태를
반영한 뒤 같은 `avatarJobs` 문서에 `publicStateSyncedAt`와 `updatedAt`을
`serverTimestamp()`로 다시 쓴다. 따라서 timestamp가 매번 달라지는 직접 self-cycle이
생긴다.

현재 `functions/src/avatarSourceRetention.ts`도 같은 `avatarJobs`를
`onDocumentWritten`으로 감시한다. Retention은 정상 처리 시에도 job/private/clip 및
retention state를 갱신하므로 StateSync와 별도의 fan-out을 만들 수 있다.

`functions/src/index.ts`의 `onUserPublicProfileSync`는 `users/{uid}`의 모든 write를
받아 `publicProfiles/{uid}`를 무조건 재작성한다. StateSync와 Retention의 user write가
이 경로를 증폭시킨다. 현재 public profile destination을 다시 감시하는 trigger는
발견되지 않았지만, destination이 동일해도 write하는 비용 증폭 결함은 별도 수정 대상이다.

주요 증거:

- Firestore writes: 2026-07-29 990,527건, 2026-08-04 4,708,435건
- Firestore reads: 2026-08-05 10,506,615건
- 2026-08-01~10 Eventarc delivery: StateSync 약 11.27M, Retention 약 11.27M,
  PublicProfile 약 8.12M
- StateSync 구현과 관련 테스트는 `dd3dad982` (2026-07-29 21:31:44 KST)에 추가됨
- StateSync live function 생성 시각은 2026-07-29 18:31:15 KST이며, 정확한 배포
  commit과 live 생성 시각은 동일하다고 단정하지 않는다.

## 3. 불변식

아래 불변식은 순수 planner unit test, mutation regression, Emulator chain test에서
동시에 검증한다.

1. **Watched-document self-write 금지**: trigger가 감시하는 `avatarJobs`에
   bookkeeping timestamp를 다시 쓰지 않는다.
2. **Semantic no-op**: 현재 user/public/retention business state가 목표와 같으면
   Firestore write는 0건이다. `updatedAt`만 갱신하지 않는다.
3. **Transition only**: `before`와 `after`의 business state가 바뀐 경우에만 sync한다.
   `completed -> completed`, timestamp-only, unrelated metadata-only event는 no-op이다.
4. **Redelivery safe**: 같은 event를 2/10/100회 재전달해도 첫 유효 반영 이후
   추가 business write는 0건이다.
5. **Concurrency safe**: 동일 terminal transition의 동시 20회 처리 결과는 한 번의
   semantic mutation으로 수렴하고 stale overwrite가 없다.
6. **No indirect cycle**: `X -> Y -> X` strongly connected component가 없어야 한다.
7. **Bounded fan-out**: 하나의 terminal transition은 사전에 설명 가능한 유한한
   invocation/write 수만 만든다.
8. **Bounded retries**: task/worker/model/retention/recovery/client retry에는 max
   attempts, backoff, deadline, terminal state가 있어야 한다.

## 4. 제안 구조

### 4.1 StateSync

- `onDocumentUpdated("avatarJobs/{jobId}")` 또는 동일한 before/after를 제공하는
  wrapper로 전환한다.
- `shouldSyncAvatarGenerationTransition(before, after)` pure classifier를 둔다.
- terminal transition이 아니면 handler에서 즉시 종료한다.
- `tx.set(jobRef, { publicStateSyncedAt, updatedAt })` self-write는 제거한다.
- 실제 user semantic field를 읽어 목표값과 비교한 뒤 changed-only update를 만든다.
- 동일 상태면 `already_synchronized` no-op을 반환하고 user/job/updatedAt을 쓰지 않는다.
- approval-protected, stale, source mismatch, superseded 상태는 기존 보호 규칙을
  유지하며 no-op으로 검증한다.

`publicStateSyncedAt`의 consumer를 전체 repository에서 확인한다. business contract가
없으면 삭제한다. audit marker가 정말 필요할 때만 trigger가 감시하지 않는 별도
internal state document을 검토하며, marker collection을 자동으로 추가하지 않는다.

### 4.2 Source Retention

- 같은 `avatarJobs`의 timestamp-only/self-write가 retention을 재실행하지 않도록
  before/after transition 또는 retention-relevant semantic diff를 사용한다.
- `avatarSourceRetentionStates/{stateId}`를 claim/lease/retry의 소유 상태로 유지한다.
- 이미 `deleted` 또는 terminal failure인 상태는 read-only no-op이어야 한다.
- job 문서에 source redaction을 기록해야 하는 기존 contract는 실제 field 변화가
  있을 때만 changed-only로 수행한다.
- `clipEmbeddings` trigger와 recovery scheduler도 duplicate/concurrent/lease recovery
  시 추가 self-amplification이 없는지 별도 검증한다.

### 4.3 Public Profile

- `users/{uid}` trigger에서 before/after의 public projection을 비교한다.
- projection이 같으면 `publicProfiles/{uid}` write를 0건으로 한다.
- 실제 projection 변화가 있을 때만 full replace를 수행한다.
- private source reference, raw URL, token, UID 외 민감한 내부 필드를 projection에
  포함하지 않는 현재 allowlist를 유지한다.

### 4.4 Trigger graph guard

현재 코드베이스에 가장 유지하기 쉬운 명시적 manifest를 선택한다. 각 Firestore
trigger에 대해 `watches`, `writes`, `transitionGuard`, `semanticNoOp`, `retry`,
`test`를 기록하고, architecture test가 다음을 실패시킨다.

- manifest에 없는 새 trigger
- watched collection에 대한 unreviewed self-write
- unreviewed A→B→A cycle
- transition/no-op 계약이 없는 trigger

불가피한 cycle allowlist는 이유, owner, bound, 전용 regression test가 함께 있어야 한다.

## 5. 테스트 설계

### 5.1 StateSync/Retention/PublicProfile unit

순수 planner와 mutation plan을 분리해 다음을 검증한다.

- processing/running → terminal: legitimate sync 1회
- terminal 동일 상태, timestamp-only, metadata-only: writes 0
- already synchronized user: writes 0
- duplicate 2/10/100회: 첫 반영 후 추가 write 0
- concurrent 20회: semantic update 1회 이하, stale overwrite 0
- approval-protected/stale/source mismatch/superseded/missing UID: writes 0
- retention already-deleted, retry, lease recovery, duplicate, concurrent: no amplification
- public profile unrelated field, updatedAt-only, same projection: destination write 0

### 5.2 Historical mutation regression

테스트 전용 fake handler에 과거의
`avatarJobs/{jobId} -> same doc updatedAt: serverTimestamp()` mutation을 주입한다.
해당 fixture는 recursion/fan-out assertion에서 의도적으로 실패해야 한다. 수정된
구현에서는 같은 fixture의 fixed path가 통과해야 한다. production source에는 broken
handler를 남기지 않는다.

### 5.3 Emulator

StateSync, Retention, PublicProfile 및 관련 trigger를 실제 Firestore Emulator에서
연결한다.

- terminal transition 1회 후 60초 quiet window
- metadata/timestamp-only event
- 동일 event 100회
- 동시 terminal event 20회
- cross-trigger chain
- historical broken fixture
- synthetic jobs N=1/10/100 선형성

각 시나리오에서 invocation, collection mutation, final state, quiet-period mutation을
카운트한다. quiet period에 관련 mutation이 0이고 chain이 유한하게 종료되어야 한다.

## 6. 전체 pipeline audit 범위

다음 경로를 별도 evidence와 severity로 기록한다.

- Flutter photo upload, double tap, rebuild, resume, timeout retry, duplicate submit
- Auth/App Check/UID/source owner gate와 side-effect ordering
- avatar job creation, deterministic Cloud Tasks name, 409 AlreadyExists
- queue retry status, worker timeout/deadline/max attempts/backoff/DLQ
- worker lease/progress/heartbeat write frequency
- adaptive candidate/QA retry upper bound 및 model unavailable 처리
- approval/preview/cleanup race와 source retention/recovery state machine
- Storage input/output prefix, deletion idempotency, object trigger cycle
- logging payload와 no-op sampling/privacy
- per-user 및 1/10/100/1,000 user 비용/write budget

P0/P1은 원인 확인 후 최소 안전 수정과 전용 regression까지 수행한다. P2는 안전한
국소 수정이 아니면 문서화하고 이번 P0 gate를 흐리지 않는다.

## 7. 재배포/재활성화 gate

아래를 모두 latest command output으로 확인하기 전에는 `safe to deploy`와
`safe to re-enable`을 false로 유지한다.

- StateSync watched-document self-write 0
- duplicate 100x additional business write 0
- concurrent 20 bounded
- retention/public profile cycle 0
- direct cycle 0, unreviewed indirect cycle 0
- historical mutation test FAIL 및 fixed implementation PASS
- Emulator quiet-period mutation 0
- 100-job fan-out O(N)
- Functions full suite PASS
- Python avatar suite PASS
- Flutter analyze/test 결과 확보
- privacy/UTF-8/diff checks PASS, 신규 skip 0
- production mutation 0, deploy 0, Eventarc disabled 유지

재활성화 시에는 5분 단위 StateSync/Retention invocation, Firestore avatarJobs write,
Eventarc delivery, user/job ratio, error/retry spike alert와 즉시 kill switch
(Eventarc disable → traffic stop → Tasks pause → read-only incident check → rollback)를
먼저 준비한다.

## 8. 현재 baseline blocker

- Functions `tsc` build는 통과했다.
- Functions 전체 test는 현재 sandbox에서 child process `spawn EPERM`으로 35개가
  시작되지 않았다. 이는 assertion 결과가 아니라 실행 환경 blocker다.
- Python 전체 collection은 현재 runtime에 `pandas`, `PIL`, `numpy`, `torch`가 없어
  막혔고, 별도로 `recsys.main`의 기존 import mismatch가 보고됐다.
- Flutter analyze/test는 bounded window를 초과해 종료했으며 결과를 PASS로 간주하지
  않는다.
- worktree에는 본 작업과 무관할 수 있는 광범위한 기존 변경이 있으므로 reset/clean 및
  unrelated 파일 덮어쓰기를 하지 않는다.

다음 단계는 이 설계를 기준으로 trigger graph와 pipeline mutation inventory를 확정한
뒤, 여러 소스/테스트 파일에 대한 최소 안전 patch 범위를 승인받아 구현하는 것이다.
