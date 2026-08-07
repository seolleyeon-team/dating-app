# Phase 6P-7A local exposure inventory

This is a read-only inventory and classification of local repositories,
mirrors, worktrees, filesystem backups, and Phase 7A replacements. It does not
authorize deletion. The machine-readable companion is
`95-phase6p7a-local-exposure-inventory.csv`.

## Sensitive-artifact handling

The only exact sensitive path in scope is `.tmp/email_tokens_sample.json`.
The known Git blob is `29a6db3aed274bc3ef622c3146795e504da16b03`.
Raw values were never printed, copied into a report, or duplicated into a
replacement. Inventory results record presence/reachability only.

## Key findings

- The original worktree is still contaminated and contains pre-existing dirty
  WIP, six stashes, local backup refs, reflogs, and the sensitive path.
- The linked cleanup worktree and several historical source/inspection mirrors
  retain the sensitive path or object and are not treated as clean.
- The nested `dating-app` repository has unique history and requires owner
  review; it was not copied, rewritten, or deleted.
- The clean local recovery clone has 65 refs, 291 commits, 84 merges, zero
  sensitive-path history, zero reachable known blob, and no physical known
  blob object.
- The clean WIP checkout is reconstructed from that clean recovery clone plus
  non-sensitive WIP deltas. Its target file is physically absent.
- Two Phase 6A remote-verification mirrors retain non-ordinary remote refs;
  those 53 non-ordinary refs are outside this local rehearsal and are tracked
  for Phase 6P-8.

## Classification rule

`SANITIZED` is asserted only after checking path history, reachable blob,
and physical object existence. A name such as `sanitized-canonical` is not
evidence by itself. A copied object that is unreachable is recorded separately
from a clean fresh clone where that object is absent.

No row in this inventory represents a completed deletion.
