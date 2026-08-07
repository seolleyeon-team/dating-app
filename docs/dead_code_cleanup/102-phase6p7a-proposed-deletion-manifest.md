# Phase 6P-7A proposed deletion/replacement manifest

This is a proposal for Phase 6P-7B only. It is not an execution log. The CSV
uses the required action vocabulary and intentionally contains no raw sensitive
values.

## Action summary

- `KEEP_ACTIVE_SANITIZED`: clean recovery and clean WIP replacements.
- `KEEP_SECURITY_EVIDENCE`: attested Method B source/candidate and Phase 6A
  verification copies pending evidence-retention review.
- `REPLACE_WITH_SANITIZED_COPY`: original active repository, linked worktree,
  and plain WIP backup after owner cutover approval.
- `SAFE_TO_DELETE_CONTAMINATED_COPY`: one grouped entry covering the old failed
  candidate mirrors; exact paths must be revalidated immediately before 7B.
- `NEEDS_OWNER_REVIEW`: nested `dating-app` and owner-uncertain plain dirs.

No path in this manifest was deleted, overwritten, dropped, expired, pruned,
or sanitized in place during Phase 7A. Physical deletion count is 0.
