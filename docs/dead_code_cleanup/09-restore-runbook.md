# Restore runbook

## Current backup references

- Pre-cleanup HEAD branch: `backup/pre-dead-code-cleanup-20260804-060225`
- External WIP snapshot: `C:/tmp/seolleyeon-dead-code-backup-20260804-060225`
- The user's active branch and dirty WIP were not reset, cleaned, stashed, rebased, or force-pushed.

## Restore an individual approved deletion

After a future approved cleanup batch, restore an individual path from the backup branch with an explicit path:

```powershell
git restore --source=backup/pre-dead-code-cleanup-20260804-060225 -- path/to/file
```

Resolve and verify the exact path before running the command. Do not use a broad directory, wildcard, `git clean`, or a reset.

## Restore a cleanup commit

If a future cleanup branch contains a committed deletion batch, use an explicit revert:

```powershell
git revert <cleanup-commit>
```

Then rerun the full test/build/rules gate and targeted checks. Preserve unrelated WIP.

## Recover uncommitted WIP

Use the external snapshot files as patch inputs only after inspecting them:

```powershell
git apply --check C:/tmp/seolleyeon-dead-code-backup-20260804-060225/working-tree.diff
git apply --check C:/tmp/seolleyeon-dead-code-backup-20260804-060225/staged.diff
```

Apply only the exact required patch and verify the status/diff. The snapshot is a safety artifact; it is not an instruction to overwrite the current worktree.

## Current audit

Because no files were removed, no restoration action is required now.


## Batch 001 restore

The “no files” statement above is the pre-Phase-2 audit state. Batch 001 is now committed only on the isolated cleanup branch. To restore one exact pointer before or after commit, run the explicit path command from the cleanup worktree:

git restore --source=backup/pre-dead-code-cleanup-20260804-060225 -- pytest_tmp_avatar_qa_escalated/test_run_avatar_candidate_qa_bcurrent

Replace the path only with one of the ten manifest entries. To undo the whole cleanup commit, use an explicit revert:

git revert <batch-001-commit>

Then rerun the full post-removal gates. Do not restore the user's dirty WIP wholesale, reset the branch, clean a directory, or use a wildcard.