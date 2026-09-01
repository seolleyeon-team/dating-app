# G004 Unique-Mark Policy Authority Resolution (offline)

## A. VERDICT

- Primary: `UNIQUE_MARK_POLICY_AUTHORITY_RESOLVED_OFFLINE`
- Secondary: `OFFLINE_QA_CONTRACT_READY_FOR_PROVENANCE_RECOVERY`
- Overall G004: `BLOCKED_QA_CALIBRATION_DATA`

## B. OLD EFFECTIVE CONTRACT

| risk | QA | preview | worker |
| --- | --- | --- | --- |
| `low` | reject=[] / review=False | `True` | `hard_pass` |
| `unknown` | reject=[] / review=False | `False` | `needs_review` |
| `unavailable` | reject=[] / review=False | `False` | `needs_review` |
| `high` | reject=['unique_mark_copied'] / review=False | `False` | `rejected` |

## C. NEW APPLICABILITY CONTRACT

| pipeline | producer | evidence | applicability | action | preview | worker |
| --- | --- | --- | --- | --- | --- | --- |
| `disabled_by_design` | `none_by_design` | `none` | `not_applicable` | `allow` | `True` | `hard_pass` |
| `enabled` | `server_expected` | `valid_low` | `available` | `allow` | `True` | `hard_pass` |
| `enabled` | `server_expected` | `valid_high` | `available` | `reject` | `False` | `rejected` |
| `enabled` | `server_expected` | `missing_or_unavailable` | `unavailable` | `review` | `False` | `needs_review` |
| `unknown` | `unknown` | `unknown` | `unavailable` | `review` | `False` | `needs_review` |

## D. AUTHORITY

- Canonical Azure source: `server-created worker provenance from _azure_provenance_document and _candidate_qa_metadata`
- Canonical decision: `not_applicable_allow`
- Enabled decision: `evidence_driven_available_allow_or_reject; missing_is_unavailable_review`
- Unknown decision: `unavailable_review_fail_closed`
- Client applicability/action claims are not authoritative.

## E. RED / GREEN

- RED: 10 failed / 1 passed before implementation; failures were the missing typed applicability and propagation contract.
- GREEN: unique-mark + forensic focused tests `{'focusedUniqueMarkAndForensicPassed': 27, 'relatedQaRegressionPassed': 271, 'newRelatedFailures': 0, 'suites': ['unique-mark applicability', 'unique-mark forensic regression', 'QA core/runtime/preflight/diagnostics', 'worker and candidate signal integration', 'offline evaluator', 'trait applicability', 'watermark v3', 'background and identifiability', 'calibration evaluator/service/recovery']}`.

## F. IMPLEMENTATION

- Central resolver: `unique_mark_policy.py`.
- Wired QA, preview, worker metadata, signal propagation, and offline evaluator.
- No unique-mark producer, biometric extraction, or raw evidence persistence was added.

## G. QA / PREVIEW / WORKER PARITY

- Shared predicate: `unique_mark_qa_satisfied`; all rows consistent: `True`.

## H. SAME-20 UNIQUE MARK

- Before effective unknown/unavailable blocker: `20`.
- After: N/A `20`, available `0`, unavailable `0`, review `0`, reject `0`.

## I. FULL SAME-20 QA

- Participants/candidates: `5` / `20`
- Hard pass / needs review / hard reject: `8` / `12` / `0`
- Preview eligible: `8`; requiredSignalUnavailable: `0`
- rubricComplete: `True`; humanSignoff: `False`

## J. BLOCKER FREQUENCY

- `{"adult_age_uncertain": {"candidateCount": 4, "participantCount": 1}, "childlike_risk_review_band": {"candidateCount": 4, "participantCount": 1}, "face_similarity_review_band": {"candidateCount": 12, "participantCount": 3}}`

## K. BLOCKER INTERSECTIONS

- `{"adultOnlyCount": 0, "childlikeOnlyCount": 0, "faceOnlyCount": 8, "multiBlockerCombinations": {"adult_age_uncertain+childlike_risk_review_band+face_similarity_review_band": 4, "face_similarity_review_band": 8, "none": 8}, "uniqueMarkUnavailableCandidateCount": 0, "zeroBlockerCandidateCount": 8}`

## L. HARDPASS REACHABILITY

- `{"consistent": true, "hardPassCandidateCount": 8, "status": "consistent", "unexplainedZeroBlockerDifference": [], "zeroBlockerCandidateCount": 8}`

## M. REGRESSIONS

- `{"adult": {"after": {"needs_review": 4, "pass": 16}, "before": {"needs_review": 4, "pass": 16}}, "background": {"after": {"low": 20}, "before": {"medium": 20}, "correctedContext": {"after": {"low": 20}, "before": {"medium": 20}, "regressionCount": 0}}, "childlike": {"after": {"low": 16, "medium": 4}, "before": {"low": 16, "medium": 4}}, "highUniqueMarkRejectPreserved": true, "identifiability": {"after": {"low": 8, "medium": 12}, "before": {"medium": 20}}, "producerUnavailableFailClosed": true, "safetyRegression": false, "trait": {"after": {"false": 20}, "before": {"true": 20}}, "unexpectedDriftCount": 0, "watermark": {"after": {"allow": 20}, "before": {"review": 20}}}`

## N. REQUIRED SIGNALS

- Unique-mark N/A does not add required-signal failure: `False`; current count `0`.

## O. PRIVACY

- All raw physical-mark, OCR, location, geometry, embedding, URL, and identity audit counts are `0`; visualRisk serializer: `pass`.

## P. TESTS

- `{"broad": {"failed": 66, "knownBaselineFailures": 66, "newRelatedFailures": 0, "passed": 350}, "compile": "pass", "determinism": {"firstSemanticSha256": "76469eecf038aa078414db706badcdcf86c879b4194d5d72950280ca3e45d3d2", "identical": true, "nondeterministicDecisionCount": 0, "repeatSemanticSha256": "76469eecf038aa078414db706badcdcf86c879b4194d5d72950280ca3e45d3d2"}, "diffCheck": "pass", "focused": 27, "privacy": "pass", "relatedRegression": 271, "reportDeterminism": {"firstSemanticSha256": "0ae8a00a5f70b5a00dbe6d5f9ae82c716f9823162c30d56e971d4527cb517d5d", "identical": true, "repeatSemanticSha256": "0ae8a00a5f70b5a00dbe6d5f9ae82c716f9823162c30d56e971d4527cb517d5d"}}`

## Q. VERSIONING

- `{"offlineEvaluatorVersion": "g004_full_qa_offline_v2", "oldQaContractVersion": "avatar_qa_v5_trait_applicability_v1", "qaContractVersion": "avatar_qa_v6_unique_mark_applicability_v1", "traitPolicyVersion": "trait_policy_v2_applicability_v1", "uniqueMarkPolicyVersion": "unique_mark_policy_v2_applicability_v1", "watermarkPolicyVersion": "watermark_policy_v3_generated_artifact_only_v1"}`

## R. MUTATIONS

- Main worktree, commit, Cloud Build, Artifact Registry, Cloud Run, Cloud Tasks, Azure, candidate generation/regeneration, traffic, production, Firebase, and human signoff mutations: `0`.

## S. NEXT ACTION

`COMBINED_PROVENANCE_SAFE_RECOVERY_BUILD`
