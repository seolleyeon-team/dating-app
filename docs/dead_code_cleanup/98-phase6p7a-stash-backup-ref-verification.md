# Phase 6P-7A stash and backup-ref verification

The local ref rewrite preserved the full ref namespace in the isolated
candidate. No original ref was changed and no stash was dropped.

| Ref class | Source | Clean candidate | Result |
|---|---:|---:|---|
| All refs | 65 | 65 | names/types/tips mapped |
| Local branches | 17 | 17 | preserved |
| Remote-tracking refs | 44 | 44 | preserved as mapped local evidence |
| `refs/stash` | 1 ref / 6 entries | 1 ref / 6 mapped entries | preserved |
| `backup/*` heads | 5 | 5 | preserved as sanitized equivalents |
| Other recovery refs | 3 | 3 | preserved; one direct tree ref retained |

The six stash entries retain their ordered parent structure (working-tree,
index, and any additional stash parent) through the one-to-one mapping. The
target path is absent from the clean recovery clone and the known blob is not
reachable there. The intermediate candidate may still hold the old object
unreachable in its object database; it remains evidence only.

No `stash`, `update-ref`, `branch -D`, `rebase`, `reflog expire`, `gc`, or
`prune` command was run against the original repository.
