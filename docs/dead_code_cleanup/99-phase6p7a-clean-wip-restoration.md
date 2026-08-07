# Phase 6P-7A clean WIP restoration

Clean replacement checkout:

`C:/tmp/seolleyeon-phase6p7a-20260806-172208/clean-wip/checkout`

The checkout uses the sanitized equivalent of the original branch rather than
rebasing the WIP onto `main`. Its mapped HEAD is
`bace49427581e401dc2deafba258e28d2211179d`.

## Reconstruction

1. Checked out the exact sanitized equivalent branch.
2. Reapplied the original staged binary diff with `git apply --index`.
3. Reconstructed unstaged tracked changes, deletions, and renames from the
   original status snapshot.
4. Copied only non-sensitive untracked/working-tree files by the frozen file
   manifest.
5. Excluded the exact target and nested independent repositories.

## Comparison

| Check | Result |
|---|---:|
| Replacement-eligible source paths | 180 |
| Replacement status paths | 180 |
| Status semantic mismatches | 0 |
| Unexpected clean paths | 0 |
| Physical files compared | 179 |
| Equal hashes | 179 |
| Hash mismatches | 0 |
| Missing/unexpected physical files | 0 |
| Both absent (pre-existing staged deletion) | 1 |
| Source target physical | YES |
| Clean target physical | NO |

The clean WIP target path is physically absent. Nested `dating-app/**` and
`.codex-worktrees/**` were excluded because they are separate local copies,
not first-party WIP delta; they remain in the exposure inventory for owner
review. The original worktree was not reset or modified.
