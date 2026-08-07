# Removal batches

## Batch status

No removal batch has run.

| Batch | Candidate scope | Status | Reason |
|---|---|---|---|
| 0 | Inventory and protection manifest | COMPLETE | Baseline, workflow reconciliation, runtime protection, and candidate groups documented |
| 1 | Any generated/artifact paths | NOT STARTED | More than 30 possible paths; user approval and independent Reviewer B required |
| 2 | Any separate/prototype project paths | NOT STARTED | Ownership and product intent are unproven |
| 3 | Any individual source/test/asset path | NOT STARTED | Twelve checks and two reviewers are incomplete |

## Required procedure for a future approved batch

1. Freeze the exact approved path list; do not expand it during execution.
2. Record pre-removal `git diff --binary`, staged diff, status, untracked manifest, and backup reference.
3. Run all 12 checks and obtain Reviewer A and Reviewer B decisions.
4. Remove only the approved paths on a cleanup branch/worktree. Do not touch the user's dirty WIP branch.
5. Run `flutter analyze`, `flutter test`, web debug/release, APK debug, Functions lint/build/test, and rules emulator tests.
6. Run targeted route, dynamic, native, asset, and operational checks for the batch.
7. Compare pre/post outputs and inspect the deletion diff.
8. If any regression appears, restore the batch from the backup branch or revert the cleanup commit; do not reset or clean the user's WIP.
9. Record the exact removed paths in `08-removed-files-manifest.md` and the rollback instructions in `09-restore-runbook.md`.

The current audit ends before step 4.


## Batch 001 — exact pointer cleanup

| Item | Result |
|---|---|
| Exact scope | Ten pytest_tmp_avatar_qa_escalated/** *current pointer files; frozen in 11-exact-file-review-matrix.md |
| Reviewer gate | Reviewer A + native Codex Reviewer B: APPROVE_SAFE_TO_REMOVE |
| Backup | backup/pre-dead-code-cleanup-20260804-060225 and external WIP snapshot C:/tmp/seolleyeon-dead-code-backup-20260804-060225 |
| Execution | git rm -- exact paths only, in isolated worktree C:/Users/samsung/StudioProjects/semisemifinal/.codex-worktrees/dead-code-cleanup-20260804 |
| Runtime/source scope | No Dart, Functions, rules, migration, workflow, native, asset, or operational source touched |
| Result | Deleted and post-verified; 35 sibling image/report artifacts deferred |
| Commit | chore(cleanup): remove verified temporary artifacts batch 1 after the documented gates |

No later batch is authorized by this Phase 2 execution.