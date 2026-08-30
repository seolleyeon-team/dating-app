# G004 Watermark Artifact-Only Contract — Offline Report

Report: `out/g004-watermark-contract-offline-20260827-v1.json`

This is an offline, same-20 contribution recomputation. It consumes the
privacy-safe machine evidence extracted from the existing v9 artifact. No
review image was opened or copied, and no remote operation was performed.

## Result

Verdict: `WATERMARK_ARTIFACT_ONLY_CONTRACT_FIXED_OFFLINE`

The decision class remains `ambiguous_text_evidence` for all 20 candidates,
which is expected. The blocking action is separated from that diagnostic class:

| Measure | Before | After |
| --- | ---: | ---: |
| `watermarkDecisionClass=ambiguous_text_evidence` | 20 | 20 |
| `watermarkQaAction=review` | 20 | 0 |
| `watermarkQaAction=allow` | 0 | 20 |
| `textLogoWatermarkRisk=medium` | 20 | 0 |
| `textLogoWatermarkRisk=low` | 0 | 20 |
| `logoTextWatermarkRisk=medium` | 20 | 0 |
| `logoTextWatermarkRisk=low` | 0 | 20 |
| watermark contribution requiring runtime review | 20 | 0 |

The existing selection tier remains `needs_review` for 20 candidates with
`hardPass=0`, `needsReview=20`, and `hardReject=0`. Those full-QA values are
preserved from the redacted v9 outcome because this report does not rerun the
non-watermark gates or fabricate a hard pass.

`visualRiskStatus=needs_review` remains present as diagnostic evidence for all
20 rows; its watermark contribution is non-blocking. `requiredSignalUnavailable`
is `0`, `rubricComplete` is `true`, and `humanSignoff` remains `false`.

## Regression and safety

- Background leakage: medium 20/20 before, low 20/20 after; regression 0.
- Identifiability: low 8/20 and medium 12/20 before and after; regression 0.
- Watermark artifact review after: 0; watermark hard reject after: 0.
- Remaining typed blockers: `BLOCKED_TRAIT_POLICY_CONTRACT` and the
  identifiability review band.
- `humanSignoff=false` remains unchanged.
- The policy version is
  `watermark_policy_v3_generated_artifact_only_v1` and the new QA contract is
  `avatar_qa_v4_watermark_artifact_only_v1`.
- The existing v9 policy and QA versions remain represented as historical
  provenance; the v9 artifact is not overwritten.

## Remote mutation ledger

Azure generation, new images, Cloud Build, Artifact Registry, Cloud Run, Cloud
Tasks, remote recovery, traffic mutation, production mutation, queue resume,
candidate regeneration, and human-signoff mutation are all `0`.

Next action: `TRAIT_POLICY_CONTRACT_RESOLUTION`.
