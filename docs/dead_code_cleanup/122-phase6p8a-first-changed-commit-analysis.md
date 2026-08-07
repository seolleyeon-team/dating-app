# Phase 6P-8A — first changed commit analysis

## Proven mapping

| Item | SHA / date |
|---|---|
| Historical target | `.tmp/email_tokens_sample.json` |
| Known blob | `29a6db3aed274bc3ef622c3146795e504da16b03` |
| Historical file SHA-256 | `439d7fd903c1bdd4c6ddb28634f982e02ebb4e91d966a6a21159ef0f2e1caf7b` |
| Old first-changed commit | `a1293410abb553a530f8be031158c79a97e90e16` |
| Sanitized equivalent | `478279958bbea20a7b5a9314df7f191ae04ca89b` |
| First-changed date | `2026-01-14T20:40:29+09:00` |
| Historical introducing commit observed on affected PR heads | `c4fe98dda8741e00f3a5a390b494b4758e0a06de` |
| Introducing-commit date | `2026-07-29T21:31:44+09:00` |

The first-changed mapping is proven from the existing topology-preserving rewrite map and an independent path-history comparison across the affected PR heads. It is not inferred from a filter-repo-generated report, and no commit subject or sensitive blob content is reproduced.

The old first-changed commit is reachable as an ordinary-graph ancestor, while the target path and known blob are not reachable from any current ordinary head. Those are separate gate facts and are both retained in the machine-readable summary.

## Gate

`FIRST_CHANGED_COMMIT = PROVEN`.

