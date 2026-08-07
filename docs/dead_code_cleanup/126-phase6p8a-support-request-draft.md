# Phase 6P-8A — GitHub Support request draft

## Submission status

`NOT SUBMITTED`. This is a sanitized draft for Phase 6P-8B approval. No GitHub issue, PR comment, email, or support ticket was created.

## Draft request

Repository: `seolleyeon-team/dating-app` (public)

We request GitHub Support review of historical host retention for a repository object classified as presumed real-user PII/account-linkage data at `.tmp/email_tokens_sample.json`. The known blob SHA is `29a6db3aed274bc3ef622c3146795e504da16b03`; the historical file SHA-256 is recorded in the private machine-readable evidence, not the file contents.

Read-only evidence found three affected closed/merged PRs: 51, 52, and 53. Their visible head refs and API-confirmed merge trees remain affected, while all 45 current ordinary heads pass the target-path and known-blob reachability gate. No open affected PR was observed. LFS is not involved. One public fork was inventoried and its two visible heads were clean by the same reachability checks.

The old blob and old first-changed commit remain directly addressable through API metadata in this probe. The web commit view was reachable, while the old sensitive blob view and raw URL returned 404. This is partial host-retention evidence; physical purge is not confirmed.

Requested actions:

1. Confirm GitHub-side retention scope for affected PR head refs, merge trees/objects, direct old-SHA/API views, cached views, backups, and replicas.
2. Invalidate or purge retained objects and caches that GitHub can remove under policy.
3. Confirm whether closed/merged PR refs and merge trees require provider-side remediation.
4. Confirm residual access paths and retention/GC status after remediation.

Please do not publish or reproduce the underlying PII in a public issue, PR, or reply. The evidence packet intentionally contains only paths, hashes, counts, statuses, and metadata.

