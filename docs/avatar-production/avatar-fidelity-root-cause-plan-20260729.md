# Avatar Fidelity Corridor root-cause plan

Date: 2026-07-29  
Status: `BLOCKED_BY_CALIBRATION_DATA` for activation; local implementation
awaits explicit approval.

This document is the implementation decision record for the seven-user,
56-candidate staging run. It contains no raw user identifier, source or
candidate path, storage reference, signed URL, token, prompt containing
identifying traits, source/candidate hash, seed, bounding box, landmark,
embedding, or private image.

## Executive decision

The incident has multiple causes:

1. The generation input loses too much broad facial information before FLUX.
2. The trait card fails to restore the lost information.
3. Prompt ordering and length put sparse fidelity traits at material truncation
   risk while repeating privacy and idealization constraints.
4. The deployed FLUX call has no explicit reference-strength control and runs a
   minimal four-step configuration against a strong generic style prior.
5. QA has a privacy upper bound but no broad-resemblance lower bound.
6. The live QA route also had an aggregation defect, unavailable models, an
   impossible-pass heuristic contract, and ineffective systemic-failure
   suppression.

The repair must introduce a two-sided Fidelity Corridor:

- candidates below a calibrated broad-resemblance lower bound are excluded
- candidates above the exact-identity/privacy upper bound are excluded
- only candidates between both bounds and passing every safety veto are ranked

The current seven users and 56 candidates are forensic evidence only. They
must not be used both to calibrate and validate activation thresholds.

No generation, deployment, cleanup, approval, preview mutation, or production
change is authorized by this record.

## Current repository and deployment baseline

- repository branch: `audit/opus5-production-hardening`
- staging project: `seolleyeon-final`
- production/source project mutation: prohibited
- worker service: `seolleyeon-avatar-worker`
- worker revision: `seolleyeon-avatar-worker-00047-9qx`
- traffic: 100 percent to the revision above
- immutable worker image digest:
  `sha256:4cef2b72c96c01be65f9e9f0f45b87d4de07ca0a211a9c78eae2f38343eb4f27`
- runtime environment: `staging`
- generation mode: `flux`
- generation model: `black-forest-labs/FLUX.2-klein-4B`
- persisted model version: `flux2_klein_4b_v1`
- prompt version: `seolleyeon_avatar_v3_flux2_klein`
- prompt builder: `seolleyeon_avatar_prompt_builder_v4`
- generation size: 1024 by 1024
- inference steps: 4
- guidance: 1.0
- analysis/reference profile: `region_privacy_v1`
- face abstraction: longest side 64px, blur radius 2.0
- style abstraction: longest side 96px, blur radius 1.5
- SAM segmentation: disabled
- live QA route: `avatar_qa_v1_staging_heuristic_preview`
- contract document target: `avatar_qa_v2`

The repository is heavily dirty with pre-existing user work. All local
implementation must preserve unrelated edits and avoid reset/clean operations.

## Existing 56-candidate state

| Metric | Result |
| --- | ---: |
| eligible jobs | 7 |
| job errors | 0 |
| response safety violations | 0 |
| initial candidates | 28 |
| extra candidates | 28 |
| total candidates | 56 |
| preview-ready candidates | 0 |
| approved candidates | 0 |
| public hard pass | 0 |
| public soft pass | 0 |
| public needs review | 56 |
| hard reject | 0 |
| too identifiable | 0 |
| terminal no-preview jobs | 7 |

The runner's `childlikeRisk=56` and `beautificationRisk=56` counters are
invalid. Direct candidate inspection found `low` for both enums on all 56,
with the underlying model scores unavailable. The script counted schema key
names in serialized JSON rather than typed risk values.

All 56 used the staging heuristic route. Five advanced QA model families were
recorded unavailable, while the heuristic recorded `softPass=true` but omitted
absolute crop/leakage fields. Their defaults made all candidates
non-previewable.

## Private human review

An independent reviewer compared all 56 candidates against the seven
exact-consent sources in a private local environment. Only anonymous row and
candidate ordinals were used.

### Broad resemblance

| Human resemblance score | Candidates |
| --- | ---: |
| 1 / 5 | 14 |
| 2 / 5 | 31 |
| 3 / 5 | 9 |
| 4 / 5 | 2 |
| 5 / 5 | 0 |

- clear or likely different-person impression: 54 of 56
- borderline same-person broad impression: 2 of 56
- borderline preview-safe inside a future corridor: 2 of 56
- needs additional human review: 7 of 56
- not preview-safe under fidelity requirements: 47 of 56
- exact biometric-copy appearance: 0 of 56

The two borderline candidates are not authorized for automatic preview. They
are evidence that a usable corridor may exist after calibrated QA and safety
verification.

### Shared visual defects

- generic, attractive, highly smoothed avatar face prior
- enlarged eyes and softened jaw/cheek structure
- source skin-tone and adult maturity drift
- source hair is often broadly preserved, but face geometry is not
- invented eyewear in multiple no/unclear-eyewear rows
- facial-hair loss where present
- school/idol styling and invented garment emblems
- two clear background failures and one additional contextual leak
- one candidate with visible background people

### Initial versus extra round

The extra round did not materially improve resemblance. It repeated the same
generic beautified/juvenile style and added more logo/background or childlike
failures in several rows.

The existing 56 should be re-evaluated by shadow QA, but no old candidate may
be automatically promoted.

## Root-cause decision matrix

| Hypothesis | Decision | Confidence | Evidence |
| --- | --- | --- | --- |
| `SOURCE_QUALITY_BLUR` | not primary | high | Clear frontal sources also produced different-person candidates; the three admission-blur rows were excluded before this seven-user run |
| `PRIVACY_REFERENCE_OVER_BLUR` | primary cause | high | Working image is reduced to a 64px longest side for the face variant and then blurred; three live rows had no primary crop |
| `WRONG_PRIMARY_CROP` | wrong person not supported; insufficient face scale supported | medium-high | Hair/clothing/hat consistently refer to the intended subject, but full/large working crops leave too few face pixels |
| `PRIVACY_MASK_WRONG_REGION` | confirmed secondary cause | high | Live metadata reported zero background/person/text regions for all rows despite complex sources and later candidate leakage |
| `TRAIT_EXTRACTION_LOSS` | primary cause | high | Broad facial and structural hair traits were almost entirely `unclear` in all seven live trait cards |
| `TRAIT_PROMPT_UNDERSPECIFIED` | confirmed secondary cause | high | The prompt receives a sparse trait card with no useful face-shape/geometry lower-bound content |
| `TRAIT_PROMPT_CONTRADICTORY` | limited tension, no literal contradiction proven | medium | Broad preservation and de-identification coexist, but no explicit "different person" instruction was found |
| `PROMPT_EXCESSIVE_DEIDENTIFICATION` | probable contributor | medium-high | Long prompts repeat privacy/generalization language and several variants are deliberately more private |
| `GENERATION_REFERENCE_STRENGTH_TOO_LOW` | no direct runtime knob exists | high | The executed FLUX call exposes no conditioning/reference-strength argument |
| `FLUX_CONFIG_LOW_FIDELITY` | probable contributor, requires A/B | medium | Four steps and guidance 1.0 provide little correction against the generic prior |
| `QA_FIDELITY_SIGNAL_MISSING` | confirmed architecture defect | high | Existing QA measures too-identifiable risk but has no source-resemblance lower bound |
| `QA_FIDELITY_THRESHOLD_DEFECT` | uncalibrated/not yet decidable | high | No independent labeled corridor calibration or holdout exists |
| `QA_SCORE_POLARITY_OR_AGGREGATION_DEFECT` | aggregation confirmed; polarity disproved | high | Key-name counting is wrong; high face similarity correctly means higher identity risk |
| `QA_MODEL_UNAVAILABLE_OR_CONFLICT` | confirmed live cause | high | Advanced QA models were unavailable and the heuristic/default contract conflicted |
| `MULTIPLE_CAUSES` | overall classification | high | Generation, QA, observability, state, and cost defects are independent and compounding |

## Source optical quality and crop findings

The seven generated rows are not a source-blur cohort. Several sources have
complex background, partial pose, small face, hood, glasses, or limited lower
face context, but clean close/frontal sources fail in the same generic direction.
This disproves source optical blur as the shared cause.

Primary selection appears to target the intended subject because candidates
retain subject-specific hair, hat, hood, glasses, or clothing cues. The
problem is face scale, not evidence of selecting another person.

Live reference metadata:

- primary crop applied: 4 of 7
- primary crop not applied: 3 of 7
- segmentation provider: source-analysis fallback for 7 of 7
- SAM: unavailable/disabled for 7 of 7
- reported background regions: zero for 7 of 7
- reported background-person regions: zero for 7 of 7
- reported text/logo regions: zero for 7 of 7
- background neutralized flag: true for 7 of 7

The zero-region values conflict with visible source content and generated
leakage. A metadata flag therefore does not prove actual neutralization.

## Analysis reference to generation privacy reference

The analysis reference keeps the working crop and neutralizes background. The
generation reference then creates:

- a face variant by reducing the entire working image to a 64px longest side,
  resizing it back, and applying Gaussian blur radius 2.0
- a style variant by reducing the entire working image to a 96px longest side,
  resizing it back, and applying blur radius 1.5
- a composite controlled by fallback face/style masks

For an uncropped or upper-body working image, the actual face occupies only a
fraction of those 64 pixels. Broad eye shape, nose prominence, cheek/jaw balance,
skin-tone nuance, and adult maturity are therefore materially weakened before
FLUX.

A private local reproduction using the checked code and live profile confirmed:

- analysis references retained broad source appearance
- generation references blurred internal facial balance into low-information
  blobs, especially for small/full-body and hooded sources
- fallback foreground masks retained source background, text, and people in
  several complex scenes

The diagnostic used locally inferred primary hints because deployed raw boxes
are correctly non-persistent. It supports the mechanism and matches live
metadata/candidate leakage, but it is not presented as byte-identical deployed
reference reconstruction.

## Trait extraction findings

The live trait card did not compensate for reference abstraction.

For all seven rows, these fields were `unclear`:

- face-shape category
- facial-feature balance
- jaw impression
- cheek fullness
- brow shape/thickness
- eye size/shape/tilt
- nose prominence/bridge impression
- mouth fullness
- hair length/volume/direction/bangs
- skin-tone range
- expression mood
- visible crop

Eyewear was explicit for only three of seven rows. Four rows were `unclear`.
Hair color and clothing color/category were the main consistently populated
traits, and one hair-color result visibly disagreed with its source.

Candidate trait-consistency scores were:

- 0.00: 32 candidates
- 0.25: 24 candidates
- above 0.25: 0 candidates

These scores did not act as a fidelity lower bound. Invented eyewear and missing
facial hair were not stopped by the live heuristic route.

## Prompt findings

The builder includes adult, natural-feature, anti-childlike,
anti-beautification, neutral-background, and exact-identity suppression text.
The issue is not complete absence of these instructions.

Confirmed risks:

- worst-case safe prompts are approximately 618–623 whitespace words
- metadata advertises `max_sequence_length=512`
- the executed worker call does not pass that value to the FLUX pipeline
- compact trait JSON and several important constraints occur late
- repeated avoidance/privacy text competes with sparse resemblance instructions
- no explicit measurable FidelityLowerBound is encoded

Exact tokenizer truncation is not proven because the deployed tokenizer cache
was not invoked. A tokenizer-level test is mandatory before prompt changes are
accepted.

## FLUX configuration findings

The executed pipeline receives only:

- prompt
- privacy-reduced image
- width and height
- inference steps
- guidance scale
- seeded generator

It does not expose scheduler, explicit reference conditioning strength,
denoising/transform strength, VAE choice, or negative prompt in this path.
Unsupported arguments must not be invented.

Additional reproducibility defects:

- model weights are loaded by model ID without an immutable model revision
- executed steps/guidance use one environment family while audit metadata can
  read another
- prompt candidate "identity strength" is descriptive metadata, not a model knob
- persisted seed metadata is not proven equal to the actual generator seed

The four-step/guidance-1.0 configuration is a credible quality contributor, but
must be tested after reference/prompt repair and one variable at a time.

## QA Fidelity Corridor finding

Current QA has no real corridor.

### Existing SafetyGate

Keep as veto:

- childlike or sexualized content
- multiple faces or background people
- readable text/logo/school leakage
- malformed face/body or severe artifact
- severe beautification
- unsafe crop
- unavailable critical safety signal

### Existing PrivacyUpperBound behavior

Reliable face similarity is interpreted only as too-identifiable risk:

- high reliable similarity can fail privacy
- raw embeddings are process-local
- pHash/crop similarity alone is not biometric identity

This behavior must not be reversed or reused as a positive ranking score.

### Missing FidelityLowerBound

There is no active source-resemblance field or gate. DINO configuration exists,
but real DINO broad-resemblance inference is not wired into the preview
decision. Trait comparison covers only a narrow subset and no geometry or
composition lower-bound score is produced.

The new gate should begin shadow-only and combine:

- background-minimized broad visual resemblance
- coarse normalized facial geometry derived process-locally
- hair, eyewear, facial-hair, skin-tone, face-shape and expression consistency
- head/shoulder composition and adult naturalness

Only rounded scores/bands, model version, policy version, availability,
decision, safe reason codes, and timings may persist.

### SafeCandidateRanking

Ranking eligibility requires all of:

- SafetyGate pass
- critical signals available
- IdentityRiskScore at or below the privacy upper bound
- FidelityScore at or above the calibrated fidelity lower bound
- no unresolved critical conflict

An unsafe candidate is excluded even if its fidelity score is highest.

## Shadow contract

Initial contract:

```json
{
  "schemaVersion": "avatar_fidelity_corridor_shadow_v1",
  "mode": "shadow",
  "policyVersion": "avatar_corridor_policy_v1",
  "calibrationVersion": null,
  "criticalSignalsAvailable": false,
  "gates": {
    "safety": "pass|review|reject",
    "privacyUpperBound": "pass|review|reject",
    "fidelityLowerBound": "pass|review|reject"
  },
  "bands": {
    "fidelity": "low|medium|high|unavailable",
    "identityRisk": "low|medium|high|unavailable",
    "traitConsistency": "low|medium|high|unavailable",
    "composition": "low|medium|high|unavailable"
  },
  "reasonCodes": [],
  "modelAvailability": {},
  "timingMs": {}
}
```

Required reason codes:

- `candidate_not_resembling_source`
- `candidate_trait_mismatch`
- `candidate_generation_generic`
- `candidate_too_identifiable`
- `candidate_childlike`
- `candidate_severe_beautification`
- `candidate_privacy_leak`
- `candidate_multiple_people`
- `fidelity_signal_unavailable`
- `privacy_signal_unavailable`
- `conflicting_fidelity_signals`
- `model_unavailable_systemic`
- `unsafe_candidate_excluded_from_ranking`

Unknown/unavailable must not be serialized as risk `true`, and must not pass.

## Calibration plan

Threshold activation requires separate source-group splits:

1. same-person source/source
2. same-person source/avatar
3. different-person source/avatar
4. near-copy source/avatar
5. over-abstracted source/avatar
6. human-labeled safe resemblance

Allowed data:

- exact-consent private cohort
- public/licensed fixtures
- synthetic regression fixtures

The same person's transformations cannot appear in both calibration and
holdout. The current seven-user cohort may be used for debugging only.

Until independent labels exist:

- corridor mode remains `shadow`
- fidelity threshold remains unactivated
- preview policy remains fail-closed
- overall activation status remains `BLOCKED_BY_CALIBRATION_DATA`

## Proposed local implementation scope

This is a multi-module change and requires explicit approval.

### Reference and source fidelity

- `lib/ai_recommend_model/avatar_generation/preprocessing/reference.py`
- `lib/ai_recommend_model/avatar_generation/analysis/segmentation.py`
- focused reference, crop, background, person, and logo tests

Planned behavior:

- versioned `privacy_strict`, `fidelity_balanced`, and
  `fidelity_high_bounded` profiles
- face-region abstraction based on actual face scale, not only full working
  image longest side
- high retention for hair/eyewear/facial hair
- bounded retention for broad outer face geometry/internal layout
- strong suppression of skin detail, unique marks, exact geometry, background,
  other people, school/logo/text, and photo-specific context
- every higher-fidelity profile still requires the identity upper-bound gate

### Trait extraction and prompt

- `lib/ai_recommend_model/avatar_generation/model_adapters/florence2.py`
- `lib/ai_recommend_model/avatar_generation/trait_card/schema.py`
- `lib/ai_recommend_model/avatar_generation/trait_card/prompt.py`
- `lib/ai_recommend_model/seolleyeon_avatar_prompt_builder_v4.py`
- focused trait coverage, contradiction, privacy, and tokenizer tests

Planned behavior:

- populate privacy-safe broad face/hair/expression enums from analysis reference
- block or review generation when critical broad-trait coverage is insufficient
- compact and move fidelity/adult/privacy invariants before the tokenizer budget
- preserve broad resemblance while explicitly suppressing exact identity
- record only token count/budget status, builder/model versions, and safe reason
  codes; never raw prompt text, prompt hashes, or image-derived hash/hash prefix

### Fidelity Corridor and QA

New modular files:

- `lib/ai_recommend_model/avatar_generation/fidelity_signals.py`
- `lib/ai_recommend_model/avatar_generation/fidelity_corridor.py`

Integration files:

- `lib/ai_recommend_model/avatar_generation/qa_runtime.py`
- `lib/ai_recommend_model/avatar_generation/qa_signals.py`
- `lib/ai_recommend_model/avatar_generation/qa.py`
- `lib/ai_recommend_model/avatar_generation/preview_policy.py`
- `lib/ai_recommend_model/avatar_generation/rerank.py`
- `lib/ai_recommend_model/avatar_generation/worker.py`
- `lib/ai_recommend_model/avatar_generation/adaptive_generation.py`
- focused QA, corridor, ranking, cache, outage, and adaptive tests

### FLUX execution and trace

- `lib/ai_recommend_model/avatar_generation/worker.py`
- `lib/ai_recommend_model/avatar_generation/model_adapters/flux2_klein.py`
- focused model revision, supported-argument, seed, audit, and prompt-budget tests

Only supported FLUX arguments will be used.

The existing `sourceImageSha256Prefix` and
`privacyReferenceSha256Prefix` generation/audit fields are explicitly in
scope for removal. New corridor, generation, QA, report, log, cache, and
Firestore records must not contain a source, candidate, analysis-reference,
or generation-reference image hash or hash prefix. Image bytes may be hashed
process-locally only for ephemeral computation where required; that value must
not cross the process boundary or become a cache key, log field, report field,
or persisted audit value.

### Reporting and cost

- `scripts/run_canary_from_validated_map.py`
- `scripts/avatar_generation_cost_report.py`
- new shadow comparison/report helpers under `scripts/`
- focused exact-aggregation, cold/warm, per-round, and zero-denominator tests

### Retention/state prerequisite

The known retention array-transform and terminal user-state synchronization
defects must be repaired and verified before any live rerun. This prerequisite
is limited to:

- `functions/src/avatarSourceRetention.ts`
- `functions/src/avatarSourceRetention.test.ts`
- new `functions/src/avatarGenerationStateSync.ts`
- new `functions/src/avatarGenerationStateSync.test.ts`
- `functions/src/index.ts` trigger registration

The executable invariants are:

1. No `FieldValue.serverTimestamp()` or other Firestore transform is embedded
   inside a `sourcePhotos` array element. Array compatibility records contain
   literal values only; authoritative claim, lease, retry, and completion
   timestamps live in a dedicated retention state/event document.
2. A deletion claim has a unique token, bounded lease expiry, attempt count,
   and deterministic retry time. Expired `deleting` claims are recoverable and
   retryable failures have an actual re-driver.
3. Immediately before object deletion, a transaction revalidates UID, current
   job, source photo, source-selection version, retention consent, clip
   terminality, and approval/approval-in-progress protection. Any mismatch
   cancels the claim without deleting bytes.
4. Successful deletion/redaction is idempotent across private media, avatar
   job, and clip records. Replayed triggers do not repeat destructive work.
5. Terminal job-to-user synchronization uses compare-and-set semantics: it
   updates `users/{uid}.avatar` only when the private current job/source and
   public job/source/version still match the terminal job. It never overwrites
   `approved` or approval-in-progress state.
6. `no_previewable_candidates`, terminal non-retryable failure, retryable
   failure, and preview-ready outcomes map deterministically to the documented
   safe public status/reason; a stale or superseded job cannot change public
   state.

Required tests cover nested-transform rejection, claim/lease recovery,
retry scheduling, consent/current-source/current-job races, clip waiting,
approval protection, idempotent deletion/redaction, stale terminal events,
all terminal status mappings, and public/private/job version mismatch. The
gate is `npm --prefix functions test` plus the Functions TypeScript build.
Passing this gate authorizes neither live cleanup nor staging deployment.

## Explicitly unchanged

- no production/public project or production config
- no safety threshold reduction
- no face-identity embedding used as a positive ranking score
- no raw source passed to FLUX
- no raw embedding, landmark, box, keypoint, prompt, or private image persisted
- no source/candidate/reference image hash or hash prefix in corridor,
  generation, QA, report, log, cache key, or Firestore shadow records
- no App Check/Auth/approval/lock weakening
- no current seven-user exception or candidate-specific override
- no automatic promotion of the existing 56
- no Flutter/public API change in the initial shadow implementation
- no staging deployment, cleanup, or live generation without later approval

## Test plan

### Reference

- clean close face, small face, full body, hood, hat, glasses, facial hair
- complex background, other person, readable text/logo/school context
- primary face is never masked
- other people/background/text are neutralized in pixels, not metadata only
- broad trait retention bands for every privacy profile
- exact-detail/unique-mark suppression

### Trait and prompt

- expected broad enums on safe fixtures
- `unclear` coverage gate
- no image-based gender inference or attractiveness rating
- actual tokenizer proves fidelity, adult, safety, privacy, background, people,
  and logo constraints survive
- forbidden "different person/generic person/avoid resemblance" semantics
- raw prompt persistence remains zero

### Corridor

- low fidelity / safe identity
- adequate fidelity / safe identity
- adequate fidelity / high identity risk
- high fidelity / unavailable privacy signal
- conflicting fidelity signals
- threshold boundaries, NaN, Infinity, missing, unavailable
- unsafe highest-fidelity candidate excluded
- deterministic safe ranking and diversity tie-break
- raw embedding and raw geometry persistence zero
- source/candidate/reference image hash and hash-prefix persistence zero

### Adaptive generation

- all candidates too dissimilar
- all candidates too identifiable
- systemic QA unavailable
- mixed candidate-specific failures
- bounded one-time fidelity-adjusted retry
- candidate, deadline, and USD caps

### Regression

- source privacy, EXIF, small-face/tile path, current source/job, approval lock,
  App Check/Auth, private preview, cost guard, and max-candidate cap
- Python focused and full suites
- Functions build/tests for retention/state prerequisite
- Flutter analyze/tests
- privacy scanner and diff check

## Cost-bounded A/B plan

No A/B generation occurs before local implementation/review and separate
staging/live authorization.

### Stage A

- 2 exact-consent debugging sources
- 4 configurations
- 1 candidate per configuration
- 8 candidates total
- same source/prompt/seed where a single variable is compared

Configurations:

- A0: current reference + current prompt
- A1: fidelity-balanced reference only
- A2: compact improved fidelity prompt only
- A3: fidelity-balanced reference + improved prompt

Expected cost:

- warm marginal estimate: approximately USD 0.09
- cold/load-aware planning range: USD 0.25–0.50
- hard Stage A stop: USD 0.50

### Stage B

- top two configurations only
- 3 sources not reused as final holdout
- 2 candidates per configuration
- 12 candidates total

Expected cost:

- warm marginal estimate: approximately USD 0.14
- planning range: USD 0.15–0.30
- combined Stage A+B hard stop: USD 0.80

Stop immediately on:

- any safety/privacy violation
- any exact-copy or high identity-risk candidate
- critical model unavailable
- no fidelity improvement after Stage A
- budget/deadline guard
- background-person or sensitive text leakage

FLUX steps/guidance experiments occur only after reference and prompt effects
are isolated. One runtime variable changes at a time.

## Privacy plan

- source and candidate images remain in approved private/local storage
- review packages use anonymous row/candidate ordinals only
- raw identity/broad-visual embeddings exist only in process memory
- raw landmarks and boxes are process-local and short-lived
- Firestore/reporting stores rounded scores, bands, versions, availability,
  decisions, timings, and safe reason codes only
- source, candidate, analysis-reference, and generation-reference image hashes
  or hash prefixes are not stored in Firestore, reports, logs, shadow records,
  or cache keys; the current worker prefix fields are removed
- current cohort is not copied into repository fixtures
- repository image fixtures are synthetic or separately approved

## Rollback plan

- introduce `off|shadow|enforced` corridor mode; default `shadow`
- new reference and prompt profiles are versioned and opt-in
- retain current profile/version for immediate staging rollback
- shadow fields cannot change `previewAllowed`, approval, or public state
- deploy only an immutable image digest after later approval
- on model outage, disagreement, cost regression, or privacy anomaly, disable
  the new profile/corridor and retain fail-closed existing safety behavior
- never roll back by disabling App Check, privacy preprocessing, or safety vetoes

## Approval gates

### Local implementation

The file set above is broad. No implementation begins until the user explicitly
approves the bounded local scope.

### Staging deployment

Local approval does not authorize deployment. A later request must identify the
exact worker/QA/function files, config delta, immutable image digest, rollback
revision, expected cost, canary count, retention state, and cleanup posture.

### Live canary

A deployment does not authorize a live run. The first live run is one
exact-consent user with a clean current source/job state and verified retention.
Failure stops the cohort.

### Cleanup

No deployment or canary approval authorizes source cleanup. Exact lineage
cleanup requires a sanitized dry-run and separate explicit approval.

## Completion rule

The work is not complete until a calibrated, independent holdout shows that
safe candidates retain broad source impression without becoming exact identity
copies; childlike, severe beautification, background-person, text/logo,
malformed, and too-identifiable candidates remain blocked; unavailable signals
fail closed; and one-user staging evidence reaches preview, approval, lock,
retention, and terminal user-state consistency.

