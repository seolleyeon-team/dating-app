# Avatar State Machine Contract

Version: `avatar_state_v2`

## States

| State | Meaning | Source mutable by normal user |
| --- | --- | --- |
| `local_selecting` | One local primary photo is selected only on-device | yes |
| `upload_pending` | Generate was pressed; request outcome is not authoritative yet | no |
| `source_locked` | Complete current source/job pair exists | no |
| `queued` | Current job is queued | no |
| `running` | Worker owns the current job | no |
| `qa_pending` | Candidate QA is running | no |
| `preview_ready` | One to four preview-safe candidates exist | no |
| `needs_review` | Human review is required; no candidate is shown | no |
| `no_previewable_candidates` | No safe candidate exists | no |
| `retryable_failed` | Same locked source may be retried | no |
| `terminal_failed` | Support/admin action is required | no |
| `approving` | A current preview-safe candidate is being approved | no |
| `approved` | Approved avatar is public-display eligible and permanently locked | no |
| `cancelled_admin_only` | Administrative cancellation | no |
| `superseded_legacy_or_retry_only` | Legacy cleanup or atomic same-source retry handoff | no |

## Normal transitions

```text
local_selecting -> upload_pending -> source_locked -> queued -> running
running -> qa_pending -> preview_ready -> approving -> approved
running|qa_pending -> needs_review|no_previewable_candidates
queued|running|qa_pending -> retryable_failed -> queued
retryable_failed -> terminal_failed
```

Normal users cannot transition a locked source back to `local_selecting` and
cannot create `superseded_legacy_or_retry_only` by choosing another photo.

## Source cardinality decision

An avatar generation submission has exactly one primary source photo. The
legacy mobile requirement for two photos is not part of `avatar_state_v2`.
The same consented private source may also feed recommendation extraction.
Additional recommendation photos require a separate future consent and upload
contract and are not accepted by the avatar flow.

## Current-source invariant

Valid unlocked state:

- `currentAvatarSourcePhotoId` absent
- `currentAvatarJobId` absent

Valid locked state:

- both IDs present
- source entry exists and is active/current
- job belongs to the same user and source
- source selection version matches

Invalid partial state:

- exactly one current ID exists
- upload, retry, preview, and approval fail closed with `avatar_state_inconsistent`
- no object, job, task, candidate, or public field is created

## Upload uncertainty

After Generate is pressed, the client remains locked until the authoritative
status API proves that no source and no job were created. A timeout or network
disconnect never silently unlocks local selection.

## Retry invariant

Same-source retry accepts no image bytes. It validates current source/job,
retryable status, retry count, kill switch, and budget. If a new retry job is
created, `currentAvatarJobId` is atomically updated and the prior failed job is
marked `retry_superseded`; the source ID never changes.

## Approval invariant

Only a preview-safe candidate from the current job may be approved. Approval is
idempotent for the same candidate and rejects a competing candidate after the
first successful approval. Approved status plus a safe nonempty approved URL is
required for public display.
