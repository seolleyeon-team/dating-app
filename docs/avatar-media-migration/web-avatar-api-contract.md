# festival_web avatar API contract

## Backend source of truth

The exact avatar API contract comes from the `semisemifinal` branch:

- `functions/src/avatarMedia.ts`
- `functions/src/avatarApproval.ts`
- `functions/src/index.ts`
- `lib/services/avatar_source_photo_service.dart`
- `lib/services/avatar_generation_client.dart`

The `festival_web/functions` implementation now adapts these callable modules for the festival web session model.

## Region and callable names

- Region: `asia-northeast3`
- Callable: `uploadAvatarSourcePhoto`
- Callable: `getAvatarJobCandidates`
- Callable: `approveAvatarCandidate`

The web client must use Firebase Functions SDK and the current Firebase Auth session. It must not call external image APIs and must not upload source photos directly to Firebase Storage.

## `uploadAvatarSourcePhoto`

Type: Firebase callable function.

Request payload:

```json
{
  "imageBase64": "<base64 image bytes or data URL>",
  "contentType": "image/jpeg|image/png|image/webp",
  "fileName": "optional client file name",
  "uid": "optional authenticated uid mirror",
  "slotIndex": 0,
  "chatPartnerRealPhotoDisclosure": false
}
```

Accepted image payload keys:

- `imageBase64`
- `base64Image`
- `imageBytesBase64`
- `image`

Default max image bytes: `10 * 1024 * 1024`.

Response shape:

```json
{
  "jobId": "avatar_job_...",
  "photoId": "src_...",
  "avatarStatus": "queued|preview_ready|failed|approved|...",
  "message": "avatar_generation_queued|avatar_source_locked|...",
  "duplicate": false,
  "sourceSelectionVersion": 1,
  "approvedAvatarUrl": "optional safe approved avatar URL"
}
```

Never returned:

- `gcsUri`
- `sourcePhotoRefs`
- private bucket/path metadata
- raw source object paths
- embeddings or landmarks

Important backend lock behavior:

- If `users/{uid}.avatar.status == approved`, upload throws `failed-precondition` with `avatar_already_approved`.
- If `userPrivateMedia/{uid}.currentAvatarSourcePhotoId` and `currentAvatarJobId` are already set, upload throws `failed-precondition` with `avatar_source_locked`.

## `getAvatarJobCandidates`

Type: Firebase callable function.

Request payload:

```json
{
  "jobId": "avatar_job_..."
}
```

Response shape:

```json
{
  "jobId": "avatar_job_...",
  "status": "queued|running|qa_pending|preview_ready|needs_review|no_previewable_candidates|failed|superseded|cancelled|approved",
  "errorCode": "optional safe code",
  "candidates": [
    {
      "candidateId": "cand_...",
      "previewImageBase64": "<runtime preview image>",
      "previewMimeType": "image/jpeg|image/png|image/webp",
      "qaSummary": {
        "status": "pass"
      }
    }
  ]
}
```

Candidates are returned only when:

- the job belongs to the authenticated user,
- the job is the current avatar job according to `userPrivateMedia`,
- job status allows preview,
- candidate QA allows preview.

Hard-reject candidates are filtered out server-side and must not be displayed by the web UI.

## `approveAvatarCandidate`

Type: Firebase callable function.

Request payload:

```json
{
  "candidateId": "cand_..."
}
```

Response shape:

```json
{
  "avatarStatus": "approved",
  "approvedAvatarUrl": "https://...",
  "avatarId": "avatar_...",
  "selectedCandidateId": "cand_...",
  "duplicate": false
}
```

Approval checks:

- candidate belongs to authenticated user,
- candidate is preview-allowed,
- job belongs to authenticated user,
- job still matches the current source/job contract,
- approved avatar lock is respected.

## Client status handling

Continue polling:

- `queued`
- `running`
- `generating`
- `qa_pending`
- `qa_running`

Stop and show candidates:

- `preview_ready` with at least one candidate

Stop with safe error:

- `no_previewable_candidates`
- `needs_review`
- `failed`
- `superseded`
- `cancelled`

Stop as approved:

- `approved`
- `approval_copying`
- `completed`

## Safe Korean messages

- `avatar_already_approved`: `이미 등록된 아바타가 있어요. 프로필 이미지는 삭제하거나 변경할 수 없어요.`
- `avatar_source_locked`: `아바타 생성이 시작되어 사진을 변경할 수 없어요.`
- invalid image: `이미지 파일을 확인해주세요.`
- no previewable candidates with source lock: `안전한 아바타 후보를 만들지 못했어요. 같은 사진으로 다시 시도해주세요.`
- generic generation failure: `아바타 생성에 실패했어요. 다시 시도해주세요.`
- timeout: `아바타 생성이 지연되고 있어요. 잠시 후 다시 확인해주세요.`

## WEB-1 handoff

{
  "subagent": "WEB-1",
  "status": "complete",
  "summary": [
    "Extracted callable contract from semisemifinal backend and Flutter client.",
    "All avatar callables use Firebase callable functions in asia-northeast3.",
    "Upload uses base64 image payload, not direct client Storage upload.",
    "Candidate response exposes runtime preview image payload only, not private refs."
  ],
  "files_inspected": [
    "semisemifinal:functions/src/avatarMedia.ts",
    "semisemifinal:functions/src/avatarApproval.ts",
    "semisemifinal:functions/src/index.ts",
    "semisemifinal:lib/services/avatar_source_photo_service.dart",
    "semisemifinal:lib/services/avatar_generation_client.dart"
  ],
  "files_changed": [
    "docs/avatar-media-migration/web-avatar-api-contract.md"
  ],
  "commands_run": [
    "git show semisemifinal:functions/src/avatarMedia.ts",
    "git show semisemifinal:functions/src/avatarApproval.ts",
    "git grep avatar callable names in semisemifinal"
  ],
  "tests_run": [],
  "test_results": [],
  "api_contracts": [
    "uploadAvatarSourcePhoto: {imageBase64, contentType, fileName?, uid?, slotIndex?, chatPartnerRealPhotoDisclosure?}",
    "getAvatarJobCandidates: {jobId}",
    "approveAvatarCandidate: {candidateId}"
  ],
  "ui_components": [],
  "privacy_findings": [
    "No source GCS refs or private bucket paths are returned by intended API responses.",
    "Preview candidate payload is runtime-safe base64/mime data and candidateId only."
  ],
  "remaining_blockers": [
    "festival branch still needs the backend callable modules wired into Functions."
  ]
}
