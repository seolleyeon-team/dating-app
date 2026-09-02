# Confirmed P0/P1 remediation

검증일: 2026-09-02 (Asia/Seoul)

## Scope decision

- confirmed P0: 0
- confirmed P1: 1
- Rules production changes: none
- Python production changes: one CLIP loader module
- P2/P3/TEST_ONLY Python cleanup: deliberately deferred

## PY-P1-01 — private GCS CLIP loader wiring regression

Severity: P1

Affected boundary: avatar/private-media privacy and normal CLIP embedding job availability.

Root cause: `avatar_media_privacy.py` retained the allowlisted backend GCS loader and signed/private URL classifier, but `seolleyeon_clip_embedder.py` stopped importing and invoking them. The active job handler passes authoritative `gs://` refs from `userPrivateMedia`, so the embedder attempted to open them as local paths. Its HTTPS loader also lacked the pre-download sensitive-reference guard.

### Production evidence

- Functions builds `clip_job_v1` payloads and enables the clip queue unless explicitly disabled.
- `clip_job_service.py` dispatches to `process_clip_job_payload()`.
- `seolleyeon_clip_job_handler.py` reloads authoritative private media, enforces consent and final-bucket allowlisting, then passes up to three `gs://` refs to `SeolleyeonCLIPEmbedder`.
- `docs/avatar-media-migration/pr3-clip-private-gcs.md` defines backend-only GCS loading as the production contract.
- Git history contains the prior loader/guard implementation and the later accidental removal.

### TDD RED

New regression:

```text
tests/test_avatar_media_privacy.py::test_clip_loader_dispatches_private_gcs_to_backend_storage
```

Pre-fix result: FAIL because `seolleyeon_clip_embedder` had no `_load_image_from_gcs` and `load_image_any()` had no GCS dispatch contract.

The existing 11 failures independently covered missing GCS helpers and missing pre-download rejection.

### Minimal fix

Only `lib/ai_recommend_model/seolleyeon_clip_embedder.py` production code changed:

1. reuse `_parse_gcs_uri`, `_load_image_from_gcs`, and `_is_private_or_signed_image_ref` from the existing privacy module;
2. add a final-project GCS bucket allowlist default, overridable by `ALLOWED_GCS_IMAGE_BUCKETS`;
3. route `gs://` and `gcs://` through the backend storage client with the byte limit;
4. reject sensitive/signed/private HTTPS refs before `requests.get()`.

No dependency, schema, public API, queue format, Firestore Rule, or production data change was made.

### Security invariants

- private source images are read only through backend GCS credentials;
- bucket allowlisting is fail closed, including an explicitly empty set;
- byte-size enforcement remains in the shared loader;
- signed/private/temp HTTPS URLs are rejected before network I/O;
- job handler consent, uid/path, authoritative-doc, and source-bucket checks remain unchanged;
- public approved HTTPS image support remains available subject to host and privacy checks.

### GREEN evidence

- exact new regression: 1 pass
- GCS + signed/private HTTPS focused subset: 12 pass, 40 deselected
- full Python suite: P1's 11 old failures removed, no new failures

## Rules TEST_ONLY corrections

The five Rules failures produced no confirmed P0/P1. Three test files were corrected to model the server-minted canonical claims and the server-only direct chat creation contract. `firestore.rules` was not modified. Full result: 197/197.

## Deferred items

Python P-01 through P-07 are ENVIRONMENT_ONLY or TEST_ONLY. Fixing 17+ stale bucket/QA expectations would be broad test cleanup, is not a production P0/P1 remedy, and was intentionally excluded by the requested severity gate.
