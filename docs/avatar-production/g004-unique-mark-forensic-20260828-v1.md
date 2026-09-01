# G004 Unique-Mark Runtime Contract Forensic

- Primary verdict: `UNIQUE_MARK_RUNTIME_POLICY_CONTRACT_MISMATCH`
- H1: `H1_REJECTED`
- Overall G004: `BLOCKED_QA_CALIBRATION_DATA`

## Answer

- Effective production answer: `yes_as_effective_preview_blocker_but_no_as_hard_reject`
- Preview blocker: `True`
- QA-layer unknown force-review: `False`
- Worker unknown force-review: `True`
- Unknown force-reject: `False`

## Actual replay

| uniqueMarkCopyRisk | QA layer | preview gate | worker status |
| --- | --- | --- | --- |
| `low` | previewAllowed=True / reject=[] | eligible=True | `hard_pass` |
| `unknown` | previewAllowed=True / reject=[] | eligible=False | `needs_review` |
| `unavailable` | previewAllowed=True / reject=[] | eligible=False | `needs_review` |
| `high` | previewAllowed=False / reject=['unique_mark_copied'] | eligible=False | `rejected` |

## Offline result

- Same-20: 5 participants / 20 candidates
- Hard pass / needs review / hard reject: 0 / 20 / 0
- `unique_mark_evidence_unavailable`: {'candidateCount': 20, 'participantCount': 5}
- Offline parity: `pass`; the offline reason explains the effective preview gate and is not a production hard-reject reason.

## Decision

No production or offline policy fix was applied because H1 was rejected. The QA layer and preview layer require a separate authority decision for the absent canonical Azure producer.

Next action: `UNIQUE_MARK_POLICY_AUTHORITY_RESOLUTION`

All remote mutations and Azure generation calls: `0`.
