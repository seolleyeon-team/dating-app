# Phase 6P-8A — GitHub host ref inventory

## Scope

Read-only snapshot of `https://github.com/seolleyeon-team/dating-app`, captured outside the active repository at:

`C:\tmp\seolleyeon-phase6p8a-20260807-204557`

The active repository working directory remained outside the project (`C:\tmp`). No push, force-push, ref deletion, PR mutation, fork mutation, or support submission was performed.

## Snapshot result

| Surface | Result | Interpretation |
|---|---:|---|
| Ordinary heads | 45 | All visible ordinary heads fetched into the local forensic mirror |
| Ordinary commits inspected | 253 | Metadata/reachability inspection only |
| Ordinary merge commits inspected | 82 | Metadata/reachability inspection only |
| Current ordinary heads with target path reachable | 0 | Ordinary regression gate PASS |
| Current ordinary heads with known blob reachable | 0 | Ordinary regression gate PASS |
| Visible pull heads | 53 | 53/53 fetched; coverage 100% |
| Affected pull heads | 3 | PR 51, PR 52, PR 53 |
| Advertised pull merge refs | 0 | Merge trees were checked through API metadata |
| Tags | 0 | No tag surface observed in the snapshot |
| Other visible internal refs | 0 | No unclassified ref remained |
| Unknown visible refs | 0 | No stop-state condition |

The current default head is `main` at `cdc6951b77f20a76e720199981b866f074f3b1ea`. The five historically affected ordinary branch names are currently clean by target-path and known-blob reachability, but their current tips do not match the prior sanitized-tip map (`0/5` matches). This is recorded as ordinary-tip mapping drift, not as current ordinary recontamination.

The old first-changed commit remains reachable as an ancestor in the ordinary graph. That fact is recorded separately from the target-path/blob gate; it does not change the current ordinary reachability result.

## Evidence locations

- `refs/refs-all.txt`, `refs/refs-pull.txt`, `refs/remote-head.txt`
- `maps/ordinary-ref-audit.tsv`
- `maps/visible-pr-head-audit.tsv`
- `maps/affected-ref-map.tsv`
- `manifests/ordinary-ref-regression-summary.txt`

## Gate

`ORDINARY_REF_REGRESSION = PASS`.

