# Avatar canonical source reconciliation — 2026-08-30

Status: CANONICAL_AVATAR_SOURCE_RECONCILED_OFFLINE (source only — no cloud
mutation, no build, no deploy, no push).

Integration branch: `integration/avatar-production-canonical-20260830`
Integration base: `fa67fa8d` (feat/child-safety-standards-page tip, which
contains local `main` 9d3a15c2; chosen over bare `main` because the onboarding
restoration diffs were authored against this lineage and it carries no
avatar-relevant divergence from `main`).

## 1. Source lineage graph

```
b214c930 ──┬─ (main line) … 9d3a15c2(main) … c844ebd1 … fa67fa8d  ← integration base
           └─ codex/phase2-provenance-baseline-20260824
              21004a38 → ef452e81      "PHASE2": Azure transport/limiter,
                                        QA v3 watermark evidence, calibration suite

(standalone snapshot repo, semisemifinal/.tmp_g004_visualrisk_v9_provenance/.git)
6219695 → ff7a687 → 4865ba3e           "4865 LINE": QA v6, watermark v3,
                                        unique-mark v2 applicability, trait
                                        applicability, prompt v1, SAME-20 evidence
                                        (g004-recovery image lineage)

(uncommitted, stage-b worktree)         "APPROVAL LINE": avatarApproval
                                        generation-pin + ifGenerationMatch=0 fix
                                        (+ Phase 3 runtime, excluded)

(uncommitted, semisemifinal-main)       "ONBOARDING LINE": 2-photo requirement,
                                        bypass removal, rules guards
```

Key forensics results:

- `4865ba3e8bd8eea9e730349c6d08226aa13bed7a` does NOT exist in the primary
  repository. It is HEAD of a standalone provenance snapshot repo at
  `semisemifinal/.tmp_g004_visualrisk_v9_provenance/` ("fix(avatar-qa): align
  production QA contracts for G004 recovery"). It is not a descendant of
  phase2 in git terms; semantically it is phase2's Azure infrastructure plus
  the later QA corrections (Azure adapter files are byte-identical across
  phase2 / snapshot / the semisemifinal working tree).
- Phase2 commits (21004a38, ef452e81) are NOT clean cherry-pick candidates:
  they bundle unrelated recsys provenance work (`seolleyeon_rec_common_v3.py`,
  `seolleyeon_policy_state.py`, `avatar_media_privacy.py`) and an unwanted
  UTF-8 re-encoding of `functions/src/avatarMedia.ts`. Selective transplant was
  used instead; no phase2 commit was cherry-picked wholesale.
- The approval fix has NO commit; it exists only as an uncommitted diff in the
  stage-b worktree. Scoped patch extracted (avatarApproval.ts + test),
  SHA256 `99b2e6eaef91890d1ba0be93beb8600e4e84b01d32b3641e83b67ba8262e80aa`.
- The onboarding restoration has NO commit; its exact 16-file set was ported
  from the `semisemifinal-main` worktree, excluding that worktree's unrelated
  concurrent changes (festival_web deletion, festival retirement edits,
  MEMORY.md, recommendation-refresh work).

## 2. Authority matrix (winners)

| Capability | Winner | Why |
| --- | --- | --- |
| Generation provider | 4865 (= phase2 Azure, unchanged bytes) | serving revision + latest lineage |
| Azure transport / limiter / retry | 4865 = phase2 (identical) + outer azure tests | Retry-After + single-limiter locked by tests |
| Prompt | 4865 `avatar_general_prompt_v1` (detailed Live2D contract) | supersedes one-line `v0_temp`; see §5 |
| Source normalization | 4865 `storage_normalized_original_direct` | no crop/segmentation/trait injection, provenance-declared |
| Candidate persistence / worker / preview | 4865 | includes Azure claim ledger (idempotency), QA readiness preflight |
| Face/identifiability QA | 4865 (calibrated precedence, review band) | v6 lineage |
| Background QA | 4865 (text/logo complexity ≠ background leakage) | v6 lineage |
| Watermark QA | 4865 `watermark_policy_v3_generated_artifact_only_v1` | supersedes phase2 v2_source_consistency |
| Trait QA | 4865 trait_policy applicability (Azure N/A → allow) | v6 lineage |
| Unique-mark QA | 4865 `unique_mark_policy_v2_applicability_v1` | v6 lineage |
| QA contract version | `avatar_qa_v6_unique_mark_applicability_v1` | 4865 |
| Approval copy | Stage-B uncommitted fix | source generation pin, dest `ifGenerationMatch: 0`, provenance-checked 412 |
| functions avatarMedia | base UTF-16 + semisemifinal 19-line Azure block + onboarding photo gate | avoids whole-file re-encoding |
| 2-photo onboarding client/server | Onboarding line | newest product contract |
| Firestore rules | base + onboarding guards | server-only photo-evidence fields |
| Routing/resume | Onboarding line (approved-avatar gate) | replaces forgeable counter |
| Everything else | fa67fa8d base | must not regress |

Rejected/superseded pieces: phase2 QA v3 files (superseded by 4865), phase2
avatarMedia re-encoding, phase2 recsys provenance bundle, stage-b Phase 3
runtime (orchestrator/GPU-QA split, trigger manifest importing
`avatarPhase3Contracts`) — Phase 3 remains an independently gated line (§33),
and the ported approval fix keeps its legacy path fully functional without any
Phase 3 module.

## 3. Provider contract

- Canonical worker mode: `azure_gpt_image_2`; production refuses `flux`
  (`legacy_flux_is_not_a_production_generation_backend`) and `dry_run`.
- functions payload: `DEFAULT_AVATAR_MODEL_ID="azure_gpt_image_2"`,
  `AVATAR_MODEL_VERSION="gpt-image-2"`, provenance block with
  `promptVersion=avatar_general_prompt_v1`, `legacyFlux:false`,
  `uniqueMarkQaMode=disabled_by_pipeline` (worker-side jobs.py).
- The old "gpt-image string must never appear" test encoded the retired
  FLUX-only policy; the 4865 lineage already removed that token, and
  `tests/test_avatar_canonical_provider_contract.py` now locks the replacement
  contract (Azure canonical, no production FLUX, no client Azure credential).
- FLUX code remains as local-legacy/offline research only
  (`resolve_worker_mode` blocks it in production).

## 4. Approval contract (ported fix)

- Phase 3-provenance candidates: source pinned by object generation,
  destination copy `preconditionOpts.ifGenerationMatch=0`, 412 with matching
  provenance → idempotent reuse, mismatched provenance →
  `avatar_canonical_destination_conflict`.
- Legacy temp-bucket candidates: unchanged verified behavior (no stored source
  generation exists for them); Firestore reservation remains the duplicate
  guard. Residual gap (destination precondition for the legacy path) is
  documented, not silently invented.

## 5. Prompt evolution report (§9 obligation)

The expected one-line prompt "위 사진과 동일한 얼굴의 2d 아바타를 생성해줘"
was the `v0_temp` contract (phase2, 2026-08-23). The 4865 lineage replaced it
with a detailed identity-preserving Live2D-style contract versioned
`avatar_general_prompt_v1` (same constant name). The newer explicit contract is
adopted unchanged; no prompt edits were made in this reconciliation.

## 6. G004 authority

- CURRENT: 5+ fresh exact-consent cohort (see updated
  `g004-calibration-plan.md`, `avatar-release-gates.md`), cohort policy
  `g004-5plus-v1`; SUPERSEDED: mandatory 10-20 → 50-100 sequence.
- Offline SAME-20 (5 participants / 20 candidates), verified from
  `out/g004-full-qa-offline-20260828-v2.json` in the snapshot: hardPass 8,
  needsReview 12, hardReject 0, requiredSignalUnavailable 0, zero-blocker 8.
- Private manifest: FOUND on this host (SHA256
  `8BAF32B9AB5D247660344A6B9A7F988C8659EE99CC5BB91028F7BC14FBF760D7`,
  participantCount 5, no identifiers recorded here). Review root exists
  (`G004-AZURE-CAL-20260824-001`, 20 candidate images).
- humanSignoff remains FALSE. Runtime parity from a rebuilt canonical image
  remains open. This reconciliation does not close G004.

## 7. Project topology authority

- Mobile Firebase project / cloud avatar project / deploy target:
  `seolleyeon-final` (.firebaserc, firebase.json, google-services.json,
  cloudbuild.avatar-worker.yaml). Forbidden: `seolleyeon`, `default`, "";
  `seolleyeon-festival` retired (ops configs). No contradiction found; no
  project IDs were changed.
- Cloud (read-only, 2026-08-30): worker traffic 100% on
  `…azure-foundry-v1-rpm2-20260823`; latest ready `…g004-recovery-v10-20260828`
  (0%); queue `avatar-generation` PAUSED, depth 0; g004-recovery v8–v10 images
  have no committed source — this snapshot adoption closes that provenance gap
  at HEAD.

## 8. Known exclusions (deliberate)

- Phase 3 runtime + trigger manifest + phase3 tests (stage-b) — separate gate.
- Festival retirement uncommitted edits (config/avatar-ops, worker topology
  guard, storage.rules, index.ts festival trigger removal) — separate line,
  will merge on its own; expected small conflict in `worker.py`
  (`validate_bridge_runtime_config` → `validate_runtime_project_topology`).
- festival_web deletion, MEMORY.md, recommendation-refresh work — unrelated.
- `tmp/small-face-build-source-20260727/` retained (labeled canary backup);
  `.g002narrow/`, g002 patches, and stray shell-accident files removed.

## 9. Next rollout sequence

1. G004_CANONICAL_RUNTIME_RECOVERY_AND_HUMAN_SIGNOFF_GATE — build the
   canonical image from this HEAD, exact-image preflight, 0%-traffic recovery
   revision, SAME-20 runtime parity (Azure generation 0), then human signoff.
2. Staging live onboarding E2E (2 photos → Azure → QA → preview → approval).
3. Production preflight → PRODUCTION_AVATAR_MUTATION_READY checkpoint →
   canary → activation (per avatar-production-rollout-20260830.md).
