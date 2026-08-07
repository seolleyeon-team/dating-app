# SEOLLEYEON — Phase 6P-6A fresh remote verification

Verification mirror:

`C:\tmp\seolleyeon-phase6p6a-remote-verify-final-20260806-150000`

The mirror was fetched from the canonical repository after the final push. The transfer wrapper timed out after the bare mirror had been populated; the resulting mirror contained all expected ordinary heads and passed full connectivity verification.

## Ordinary-head verification

- Ordinary heads: `45/45`.
- Candidate SHA mismatches: `0`.
- Ref-name differences: `0`.
- Tags: `0`.
- Default HEAD: `refs/heads/main`.
- Reachable commits: `253`.
- Reachable merges: `82`.
- Target path history count: `0`.
- Target path reachable count: `0`.
- Known sensitive blob reachable count: `0`.
- Full mirror `git fsck --full --connectivity-only` errors: `0`.
- Candidate-to-remote parent graph difference: `0`.
- Candidate-to-remote ordinary-head object/tree inventory difference: `0`.

Target path checked:

`.tmp/email_tokens_sample.json`

Known target blob checked:

`29a6db3aed274bc3ef622c3146795e504da16b03`

## Scope note

The mirror contains `53` non-ordinary visible refs, including PR/internal refs. Those refs were explicitly outside Phase 6P-6A scope and were not mutated. The `0` reachability result above is therefore specifically for all `refs/heads/*` ordinary heads.

