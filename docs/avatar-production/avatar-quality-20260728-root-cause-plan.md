# Avatar quality 2026-07-28 root-cause plan

Status: root-cause investigation complete; implementation awaits explicit approval.

This record covers the seven-user staging calibration that produced 56 private
candidates, all with public status `needs_review` and no preview-ready result.
It intentionally contains no raw user identifier, media reference, signed URL,
token, source filename, geometry, landmark, embedding, or private image.

## Decision summary

The run has multiple independent causes. The reported universal childlike and
beautification risks were a reporting defect, but the zero-preview result was
real. It came from a staging heuristic/absolute-policy contract mismatch while
critical QA models were unavailable. Independent visual review also found real
generation-quality problems, so the remediation must not promote the existing
candidates merely by correcting the report or lowering safety thresholds.

The calibration does not pass its acceptance gate:

- jobs completed: 7
- generated candidates: 56
- initial candidates: 28
- extra candidates: 28
- preview-ready candidates: 0
- approvals: 0
- hard-reject exposure: 0
- source-retention terminal updates: 0 of 7
- public user states reconciled from `queued`: 0 of 7

No deployment, source cleanup, approval, rerun, or new GPU generation is
authorized by this document.

## Existing candidate QA distribution

Direct aggregate inspection of the 56 candidate documents established:

| Field | Distribution |
| --- | --- |
| candidate status | `needs_review`: 56 |
| rerank tier | `needs_review`: 56 |
| QA debug decision | `soft_pass`: 56 |
| `softPass` | `true`: 56 |
| `previewAllowed` | `false`: 56 |
| `requiresHumanReview` | `false`: 56 |
| `childlikeRisk` | `low`: 56 |
| `beautificationRisk` | `low`: 56 |
| childlike score | unavailable/null: 56 |
| beautification score | unavailable/null: 56 |
| crop consistency | `pass`: 56 |
| crop isolation | `needs_review`: 56 |
| background leakage risk | `medium`: 56 |
| secondary-face leakage risk | `medium`: 56 |
| text/logo/watermark risk | `medium`: 56 |
| review reason | `qa_signal_uncertain`: 56 |
| advanced QA model availability | unavailable: 56 |

The low childlike and beautification enums were synthetic heuristic values, not
measurements from the configured candidate-quality models. They therefore
cannot be used as evidence that the candidates are safe.

## Per-candidate evidence availability

All 56 private candidate objects were still available during the investigation.
Each candidate had enough sanitized trace metadata to correlate an anonymous
ordinal with its seed, generation metadata, prompt/trait hashes, preprocessing
metadata, QA version, debug decision, threshold snapshot, and model-availability
map.

Important trace gaps:

- generation round is inferred from ordinal, not explicitly persisted
- exact QA policy and calibrated risk versions are not persisted
- worker revision and immutable image digest are not persisted per job
- actual and recorded generator parameter/seed equality is not guaranteed
- QA asset version/checksum and score polarity are not persisted
- source-to-candidate identity fidelity was not reviewed because source images
  were deliberately excluded from the private contact sheet

The contact sheet and candidate objects remain private evidence and must not be
copied into this repository or public documentation.

## Actual image-quality assessment

Two independent reviewers inspected all 56 candidates using anonymous row and
candidate ordinals. They agreed on the following robust findings:

- all candidates are strongly smoothed, idealized, and stylistically homogeneous
- a meaningful subset has youthful, doll-like, or age-ambiguous proportions
- additional sampling did not systematically improve quality
- two to three candidates retain clear non-neutral environment content
- one candidate contains visible background people and must never be exposed
- approximately eight contain visible or likely garment logos/graphics
- no catastrophic missing or grossly malformed face was observed
- source identity, actual-age fidelity, and accessory correctness remain unknown

The reviewers differed in how conservatively they labeled childlike appearance.
One classified 12 as clearly childlike/doll-like and 8 as age-ambiguous; the
other found no unequivocal child but approximately one-third with moderate
underage ambiguity. The defensible conclusion is a confirmed youthful/doll-like
style bias with an uncertain exact count, not a universal 56-of-56 childlike
failure.

One strict visual rubric produced:

| Round | Accept | Borderline | Reject |
| --- | ---: | ---: | ---: |
| Initial 28 | 8 | 11 | 9 |
| Extra 28 | 8 | 6 | 14 |

This is human/CV evidence only. It must not replace calibrated QA or authorize
automatic preview.

## QA implementation findings

### Confirmed aggregation defect

The calibration runner serializes the QA/rerank objects and searches their text
for words such as `childlike` and `beautification`. Always-present schema keys
therefore increment both counters regardless of whether their values are low,
false, null, unknown, unavailable, or review-only.

The reported `childlikeRiskCount=56` and
`beautificationRiskCount=56` are invalid and must be withdrawn.

### Confirmed impossible-pass contract

The staging heuristic returns `softPass=true` before actual QA inference. It
does not populate crop-isolation and leakage fields required by the absolute
preview policy. Their defaults are non-passing, so all 56 candidates are
converted to `needs_review`.

The same result simultaneously records `requiresHumanReview=false`,
`previewAllowed=false`, a debug `soft_pass` tier, and a public
`needs_review` tier. This is an internally inconsistent contract.

The safe repair is to make unavailable/unmeasured signals explicit and
fail-closed, then run the real calibrated QA path. The heuristic must not
fabricate a previewable soft pass. Absolute safety requirements and calibrated
thresholds will not be weakened.

### Confirmed systemic-failure detection defect

The extra-generation guard checks top-level model-availability data, while this
route stores it under the QA debug object. It therefore missed the common model
outage and generated four extra candidates for every job.

Systemic infrastructure, serialization, calibration, and policy blockers must
stop the extra round and produce an explicit retryable/operator-visible reason.
Candidate-specific visual defects may still request a bounded extra round.

### Disproved hypotheses

- Score polarity did not cause the universal report counts.
- A face crop did not cause those report counts; the relevant risk scorer uses
  the full candidate image.
- The evidence does not justify lowering childlike, beautification, privacy, or
  identity-similarity thresholds.

## Generation findings

The prompts already contain adult, ordinary-feature, and anti-beautification
instructions, but the final prompt is long enough that trailing constraints may
be truncated by the model tokenizer. The current runtime does not prove the
effective tokenized prompt or record which constraints survived.

Additional credible contributors:

- the style prior strongly favors smooth Korean-animation/idol geometry
- anti-chibi and adult head/body proportion constraints are not reliably binding
- garment logo/text and neutral-background suppression are insufficient
- trait-card proxies can introduce weak `soft` or `round` geometry cues
- privacy-reference defaults can over-blur adult structure and eyewear if the
  safer staging overrides are absent
- generator weights are not pinned by immutable revision
- runtime generator settings and recorded audit settings can diverge
- actual generator seed and persisted seed metadata can diverge

Generation reference and analysis reference are separate in the checked path,
and the privacy-reduced generation reference—not the raw source—is passed to
the generator. No evidence supports a raw-source privacy bypass.

## Model availability and readiness

The live candidates did not exercise real advanced QA inference. Face detector,
face similarity, CLIP, DINO, and MediaPipe availability were recorded as
unavailable for all 56 candidates.

The container image bakes only limited assets. FLUX, Florence, CLIP, and
similarity models are otherwise lazy-loaded or depend on runtime cache state.
The readiness endpoint and startup probe demonstrate process/port readiness,
not complete model readiness. Manual warmup covers FLUX but not every trait and
QA model.

The remediation must:

- distinguish process-ready from model-ready
- verify required model assets and calibration at startup/warmup
- keep safety fail-closed when a model is unavailable
- persist non-secret model/calibration versions and availability
- measure each model's cold-load cost separately

## Retention and public-state findings

Seven retention invocations failed because `FieldValue.serverTimestamp()` was
embedded inside an element of the `sourcePhotos` array. The same invalid pattern
exists in three paths: claim, successful deletion/redaction, and retryable
failure.

Current aggregate staging state remains:

- terminal `no_previewable_candidates` jobs: 7
- public user avatar states still `queued`: 7
- active retained sources: 7
- approved avatars: 0

The queued state is structural: upload/retry writes the public state, the worker
terminalizes only the job, and no compare-and-set synchronizer repairs the
current user's avatar state.

Further retention contract defects must be addressed together:

- a crash after claim can strand `deleting` because there is no lease recovery
- a retryable storage failure is acknowledged without a deterministic re-driver
- deletion-terminal retention policy conflicts with same-source retry policy
- current-job/source and consent can change between claim and storage deletion

The fix will keep timestamps authoritative in a dedicated retention event/state
document, use only literal values inside compatibility arrays, add lease/retry
recovery, revalidate current job/source/consent before external deletion, and
add an idempotent terminal job-to-user state synchronizer. Approval locks and
approval-in-progress states remain protected.

## Cost and latency findings

| Metric | Result |
| --- | ---: |
| total estimated cost | USD 0.633190 |
| total worker time | 1604.232 s |
| total wall time | 1694.435 s |
| generated-candidate unit cost | USD 0.011307 |
| cost per preview-ready | unavailable; denominator is zero |
| cold job worker time | 618.432 s |
| cold model-load time | 273.789 s |
| warm worker p50 | 121.812 s |
| warm worker p95 | 251.697 s |
| extra-generation rate | 7 of 7 |
| extra-candidate share | 28 of 56 |

QA latency was bimodal. Four jobs took about 8.6–8.8 seconds, while three took
about 121.9–155.1 seconds. The most supported cause is candidate-trait Florence
inference running sequentially per candidate for an eyewear-preservation
condition. This is a strong code/configuration inference, not yet a directly
instrumented causal measurement.

The exact avoidable cost of the extra round cannot be calculated because stage
timings are not split by generation round.

## Root-cause classification and priority

1. `MULTIPLE_CAUSES` — confirmed overall classification.
2. `QA_AGGREGATION_DEFECT` — confirmed; explains both false 56-of-56 counters.
3. `QA_POLICY_IMPOSSIBLE_PASS` — confirmed; explains zero preview on the
   staging heuristic route.
4. `QA_DEFAULT_VALUE_DEFECT` — confirmed; heuristic/default state is
   internally inconsistent.
5. `QA_MODEL_UNAVAILABLE` — confirmed for all 56 candidate traces.
6. `GENERATION_BEAUTIFICATION_BIAS` — confirmed by two independent visual
   reviews; exact severity count is rubric-dependent.
7. `GENERATION_CHILDLIKE_BIAS` — confirmed as a non-universal
   youthful/doll-like bias; exact count is uncertain.
8. `GENERATION_PROMPT_DEFECT` / `GENERATION_CONFIG_DEFECT` — probable
   contributors requiring tokenizer/config regression evidence.
9. `GENERATION_REFERENCE_OVERPRIVATIZED` — plausible configuration risk, not
   proven as the live-run cause.
10. `QA_THRESHOLD_MISCALIBRATION`, `QA_SCORE_POLARITY_DEFECT`, and
    `QA_CROP_DEFECT` — not supported as causes of the false universal counters.

Separate confirmed operational causes:

- Firestore transform inside an array broke source retention.
- Missing terminal job-to-user synchronization left public state queued.
- Missing common-mode classification caused wasteful extra generation.
- Incomplete model readiness shifted cold load into user jobs.

## Proposed local implementation scope

The implementation is intentionally modular. Exact edits will be limited to the
following areas unless new evidence requires another approval request.

### QA, reporting, and adaptive generation

- `scripts/run_canary_from_validated_map.py`
- new focused aggregation tests under `tests/`
- `lib/ai_recommend_model/avatar_generation/qa.py`
- `lib/ai_recommend_model/avatar_generation/preview_policy.py`
- `lib/ai_recommend_model/avatar_generation/worker.py`
- `lib/ai_recommend_model/avatar_generation/adaptive_generation.py`
- existing focused QA/worker integration tests

### Generation and reproducibility

- `lib/ai_recommend_model/seolleyeon_avatar_prompt_builder_v4.py`
- `lib/ai_recommend_model/avatar_generation/trait_card/prompt.py`
- `lib/ai_recommend_model/avatar_generation/preprocessing/reference.py`
- `lib/ai_recommend_model/avatar_generation/model_adapters/flux2_klein.py`
- focused prompt, reference, seed, parameter, and generation-worker tests

Changes will shorten and prioritize adult-proportion, natural-feature,
neutral-background, third-party, and text/logo constraints; preserve source
traits without raw-source exposure; and make executed configuration traceable.

### Retention and public-state recovery

- `functions/src/avatarSourceRetention.ts`
- one new retention-state helper module
- one new terminal avatar-state synchronization module
- `functions/src/index.ts`
- focused retention and state-synchronization tests

### Cost, latency, and readiness reporting

- `scripts/avatar_generation_cost_report.py`
- `lib/ai_recommend_model/avatar_generation/worker_service.py`
- relevant cost/readiness tests

### Required result artifacts

- `docs/avatar-production/avatar-quality-20260728-remediation-result.md`
- `docs/avatar-production/avatar-quality-20260728-retention-recovery.md`
- `docs/avatar-production/avatar-quality-20260728-staging-revalidation.md`
- sanitized JSON artifacts under `out/` as defined by the task

## Explicitly unchanged without later approval

- no production/public project or production configuration
- no safety-threshold reduction or review bypass
- no candidate approval, public preview, or lock mutation
- no staging deployment
- no source or candidate cleanup
- no exact-consent rerun or GPU generation
- no broad user-media reset or migration
- no raw source/candidate image copied into repository artifacts
- no approval authorization or consent semantics weakened

## Test plan

### QA and report unit tests

- exact typed aggregation for low/medium/high, true/false, null, unknown,
  unavailable, missing, NaN, and Infinity
- score polarity and threshold-edge behavior
- model missing and adapter exception behavior
- hard-pass, soft-pass, review, and reject transitions
- required-signal and policy-version enforcement
- staging heuristic cannot claim a contradictory previewable soft pass
- persisted debug/public/rerank tiers remain consistent

### QA synthetic image fixtures

- ordinary adult portrait
- childlike/chibi negative
- oversized head/body proportion
- beautified/idol-like and excessive-smoothing negatives
- natural unretouched portrait
- malformed, multiple-face, no-face, and too-identifiable negatives
- safe stylized adult avatar
- neutral background versus environment/person leakage
- garment text/logo leakage

Only synthetic or explicitly approved non-user fixtures may enter the repository.

### Adaptive generation and observability

- a common systemic reason across the first round produces zero extra calls
- mixed candidate-specific defects may request a bounded extra round
- one unavailable candidate does not over-block unrelated candidates
- explicit retryable/operator-visible terminal state
- generation deadline, candidate-count, and USD-budget boundaries
- per-round stage timing and candidate-trait call counts
- cold/warm, extra-generation rate, and zero-denominator cost reporting

### Generation

- tokenizer-level proof that critical adult, proportion, natural-feature,
  background, third-party, and logo constraints survive
- source-reference structure/hair/eyewear preservation on safe fixtures
- actual generator seed equals persisted seed
- executed generator parameters equal audit metadata
- pinned model revision and safe missing-revision behavior

### Retention and state

- Firestore/emulator execution proves no transform is nested in an array
- duplicate trigger, missing object, partial write, and storage failure
- stale claim lease and deterministic retry recovery
- current job/source and consent changes before deletion
- retry-eligible terminal source is not deleted prematurely
- approval and approval-in-progress protection
- idempotent current-job terminal synchronization to public user state
- dry-run/apply reconciliation parity

### Verification sequence

1. focused Python and Functions tests
2. complete relevant local suites
3. privacy/log-redaction review
4. code review and root-cause-to-test trace
5. explicit staging selective-deploy approval request
6. after approval, one-user canary
7. after a successful canary, remaining approved staging cohort
8. exact cleanup dry-run
9. separate exact seven-source cleanup approval request

## Approval gates

### Local implementation gate

This plan spans multiple modules. Repository implementation must not start until
the user explicitly approves the bounded local scope above.

### Staging selective-deploy gate

Local implementation approval does not authorize deployment. A later request
will identify the exact functions, worker image digest, configuration delta,
tests, rollback point, and expected effect.

### Exact cleanup gate

Deployment approval does not authorize cleanup. After staging validation, a
sanitized exact dry-run will be presented separately. Cleanup requires another
explicit approval and will be limited to the exact calibration lineage.

### Exact-consent rerun gate

No user-source rerun is implied. Any canary or cohort rerun must have an
independent exact-consent authorization and valid private source.

## Completion rule

The work is not complete until real calibrated QA runs fail-closed, safe adult
candidates can reach preview/approval/lock on staging, unsafe childlike,
over-beautified, identifiable, background-person, and logo-risk candidates
remain blocked, retention is idempotent and recoverable, and the public user
state agrees with the authoritative terminal job.

