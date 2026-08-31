# Avatar QA Contract

## Watermark policy

Contract version: `watermark_policy_v4_runtime_evidence_parity_v1`
Evidence schema: `watermark_evidence_v2_token_quality_derived_v1`
(2026-08-31 REVIEW_WITH_REDACTED_EVIDENCE_PARITY — supersedes
`watermark_policy_v3_generated_artifact_only_v1`; see
`g004-watermark-runtime-evidence-authority-20260831-v1.md`.)

The watermark classifier separates three layers:

1. Observed evidence: typed text/logo/sign regions and redacted counts,
   confidence bands, area bands, location bands, token-quality bands,
   repetition, source consistency, and the typed per-region evidence list.
   Raw OCR text is process-local only: every raw-text-dependent semantic
   (`tokenQuality`, `artifactHint`) is derived once before redaction, and
   classification — runtime, recovery, and offline — consumes only the
   serialized categorical evidence (`classify_watermark_evidence_document`).
   Legacy evidence without the typed schema is never re-classified and never
   gains a stronger rejection from field absence.
2. Artifact classification: whether the evidence is ordinary/integrated
   content, an unresolved artifact, or a corroborated generated overlay.
3. QA action: the only layer allowed to change preview or rejection state.

Text or logo presence by itself is not a blocker. Source inconsistency,
corner/edge placement, small area, or unknown confidence is also evidence only.

| Action | Risk fields | QA effect |
| --- | --- | --- |
| `allow` | `low` | no watermark review or reject |
| `review` | `medium` | no preview; human review required |
| `reject` | `high` | hard reject; no preview |

### Allowed

- ordinary text;
- clothing text;
- benign logo or sign;
- source-consistent text/logo/sign;
- candidate-only integrated logo;
- ambiguous text-like evidence without artifact corroboration.

### Review

- probable generated or broken text artifact without strong overlay
  corroboration;
- a SINGLE, non-repeated `implausible` token below high confidence — even
  with `sourceConsistency` `inconsistent` or `not_available` (v4: this was
  wrongly a hard reject at runtime under v3);
- unresolved artifact evidence when the visual provider is available.

### Reject

- clear overlay watermark (strong corroboration required: repetition, or
  high-confidence implausible/artifact-hint overlay evidence);
- repeated generated overlay;
- strong generated text artifact with overlay corroboration;
- generated overlay logo/sign with corroboration.

`identifiable_brand_logo` is not a hard reject on its own. A logo requires
generated/overlay corroboration before it can produce `reject`.

## Fail-closed conditions

Visual model outage, critical visual unavailability, or another required QA
signal that is unavailable remains `review` and cannot produce a hard pass.
An outage is recorded separately from available-provider ambiguity.

## Trait applicability policy

Policy version: `trait_policy_v2_applicability_v1`
QA contract version: `avatar_qa_v7_watermark_evidence_parity_v1`

Trait applicability is resolved from server-authoritative pipeline provenance.
The client cannot declare a trait result, and an empty `{}` trait object never
means `allow` by itself.

| Pipeline/evidence | Applicability | Action | QA effect |
| --- | --- | --- | --- |
| canonical Azure GPT-Image-2; no card by design | `not_applicable` | `allow` | non-blocking |
| trait-enabled; complete matching evidence | `available` | `allow` | non-blocking |
| trait-enabled; mismatch or uncertain comparison | `available` | `review` | review; never hard reject |
| trait-enabled; missing or incomplete evidence | `unavailable` | `review` | fail-closed review |
| unknown pipeline provenance | `unavailable` | `review` | fail-closed review |

Canonical Azure metadata records `traitQaMode=disabled_by_pipeline` and
`traitQaAuthority=server`. The worker does not run source or candidate trait
extraction on that path. Trait-enabled legacy/test paths retain comparison
QA; meaningful mismatch and unknown values remain review decisions.

## Unique-mark applicability policy

Policy version: `unique_mark_policy_v2_applicability_v1`
QA contract version: `avatar_qa_v7_watermark_evidence_parity_v1`

The server resolves unique-mark applicability from the pipeline provenance
before interpreting `uniqueMarkCopyRisk`. The client cannot declare the state.
The canonical Azure GPT-Image-2 path has no unique-mark producer by design, so
absence is `not_applicable`/`allow`; it is not equivalent to `low`, and no
`uniqueMarkCopied=false` or `uniqueMarkCopyRisk=low` value is fabricated.

| Pipeline/evidence | Applicability | Action | QA/preview effect |
| --- | --- | --- | --- |
| canonical Azure GPT-Image-2; producer disabled by design | `not_applicable` | `allow` | non-blocking; preview eligible from unique-mark perspective |
| unique-mark-enabled; valid low evidence | `available` | `allow` | non-blocking |
| unique-mark-enabled; valid high evidence | `available` | `reject` | hard reject `unique_mark_copied` |
| unique-mark-enabled; missing/failed evidence | `unavailable` | `review` | fail-closed review; no preview |
| unknown pipeline provenance | `unavailable` | `review` | fail-closed review; no preview |

`uniqueMarkCopyRisk=high` remains a hard reject. `unavailable` remains review;
it is never treated as `not_applicable`. QA, preview, worker, and offline
evaluation consume the same typed applicability/action state. No raw physical
mark descriptions, locations, coordinates, boxes, landmarks, or embeddings
are persisted.

## Persisted observability

Persisted/debug-safe fields are limited to `watermarkQaAction`,
`watermarkPolicyVersion`, `watermarkDecisionClass`, `watermarkEvidenceClasses`,
and redacted scalar evidence. Raw OCR/token text, labels, brands, exact boxes or
coordinates, image paths/URLs, participant identifiers, and embeddings are not
persisted.

The QA contract version for new runtime evidence is
`avatar_qa_v7_watermark_evidence_parity_v1`. Earlier evidence (v9 and the
v6-era artifacts) retains its
original contract and is never overwritten. Offline recomputation may consume
that evidence and writes only a separate report.

## Scope invariants

This contract does not change Florence model selection, thresholds, prompt
construction, identity precedence, background policy, human signoff, Azure
generation, or remote deployment behavior.
