# festival_web avatar pipeline map

## WEB-0 status

- Branch/worktree: `C:\Users\samsung\StudioProjects\festival_worktree`
- Current branch: `festival`
- Upstream: `origin/festival`
- Web app folder: `festival_web`
- Web app stack: Flutter Web, not React/Next/Vite
- Root app stack: Flutter mobile/desktop plus Firebase Functions
- Current `festival` branch does not contain the `semisemifinal` avatar callable files:
  - `functions/src/avatarMedia.ts`
  - `functions/src/avatarApproval.ts`
  - `lib/services/avatar_source_photo_service.dart`
  - `lib/shared/utils/profile_display_image_resolver.dart`

## Existing festival_web structure

`festival_web` is a compact Flutter Web app. Most app code currently lives in:

- `festival_web/lib/main.dart`
- `festival_web/lib/firebase_options.dart`
- `festival_web/lib/festival_push_service.dart`
- `festival_web/lib/recommendation/*`
- `festival_web/functions/src/index.ts`
- `festival_web/functions/src/festival_embeddings.ts`

The current festival profile flow uses:

- `FestivalBackend.uploadProfilePhoto(XFile photo)`
- direct Firebase Storage upload to `festivalProfiles/{ticketId}/{uid}/profile.{ext}`
- Firestore profile draft fields:
  - `photoUrl`
  - `photoStoragePath`
  - `photoContentType`
  - `photoOriginalName`
  - `photoSizeBytes`
  - `photoMode: firebase_storage`

This direct public photo flow does not satisfy the avatar privacy policy.

## Flutter source flow map

The `semisemifinal` branch is the source of truth for the avatar implementation.
Relevant source files:

- `lib/features/onboarding/screens/photo_upload_screen.dart`
- `lib/services/avatar_source_photo_service.dart`
- `lib/services/avatar_generation_client.dart`
- `lib/shared/utils/avatar_lock_policy.dart`
- `lib/shared/utils/profile_display_image_resolver.dart`
- `functions/src/avatarMedia.ts`
- `functions/src/avatarApproval.ts`
- `functions/src/index.ts`

The Flutter flow is:

1. User picks a source image locally.
2. Client sends image bytes/base64 to backend callable, not directly to Storage.
3. Backend writes the private source photo and creates or reuses an avatar job.
4. UI locks source mutation once generation starts.
5. Client polls `getAvatarJobCandidates(jobId)`.
6. Backend returns only preview-safe candidate data.
7. UI displays previewable candidates only.
8. User selects a candidate and calls `approveAvatarCandidate`.
9. Backend copies the approved avatar to the approved bucket and writes approved avatar fields.
10. UI proceeds and locks approved avatar mutation.

## Backend API contract map

The intended backend callables from `semisemifinal` are:

- `uploadAvatarSourcePhoto`
- `getAvatarJobCandidates`
- `approveAvatarCandidate`

All callables use Firebase Auth and region `asia-northeast3`.

The web app must call these backend APIs through Firebase Functions, using the current Firebase user session. It must not upload source photos directly to Firebase Storage and must not write source photo URLs or private paths to Firestore.

The `festival` branch root Functions currently lack these callable modules, so implementation must bring over or adapt the backend callable modules from `semisemifinal`.

## Planned web implementation files

Prefer new focused Flutter files instead of adding all code to `festival_web/lib/main.dart`:

- `festival_web/lib/avatar/avatar_generation_client.dart`
- `festival_web/lib/avatar/avatar_generation_models.dart`
- `festival_web/lib/avatar/avatar_generation_messages.dart`
- `festival_web/lib/avatar/avatar_display_resolver.dart`
- `festival_web/lib/avatar/avatar_candidate_dialog.dart`
- `festival_web/lib/avatar/avatar_generating_overlay.dart`
- `festival_web/lib/avatar/avatar_photo_input.dart`

Likely `main.dart` edits:

- Replace direct profile photo upload with avatar source upload flow.
- Persist approved avatar URL only in the existing festival profile fields needed by the festival recommendation/profile UI.
- Keep source photo refs out of client state and Firestore profile documents.
- Route to taste onboarding after approval, preserving the existing route behavior.

## Known blockers and risks

- `festival_web` currently stores and displays `photoUrl`; migration must ensure this becomes an approved avatar URL, not a source photo URL.
- `festival_web/functions` currently focuses on embeddings and may not include the avatar callable contract. Root `functions` may need the `semisemifinal` avatar modules.
- Current festival recommendation/profile card code reads `FestivalProfile.photoUrl`. That field must be populated only from approved avatar data.
- Existing direct Storage upload path must be removed or bypassed for the normal onboarding profile image flow.
- Live generation requires Cloud Run worker/task/pubsub configuration; this task must not deploy or mutate production.

## Implementation update

Implemented in `festival_web`:

- Backend avatar callable modules were added under `festival_web/functions/src/avatarMedia.ts` and `festival_web/functions/src/avatarApproval.ts`, then wired from `festival_web/functions/src/index.ts`.
- Web avatar client and models were added under `festival_web/lib/avatar/`.
- Signup profile photo flow now selects a local source image, uploads it via `uploadAvatarSourcePhoto`, locks source mutation, polls `getAvatarJobCandidates`, shows preview-safe candidates, approves through `approveAvatarCandidate`, saves only approved avatar display metadata, and routes to `AppRoutes.taste`.
- Profile and chat display now use `FestivalAvatarDisplayResolver`, which returns only `avatar.status == approved` with a safe `avatar.approvedAvatarUrl`.
- The old normal onboarding path no longer calls direct profile-photo Storage upload from the signup screen.

Current non-production limitations:

- No production deployment or live Cloud Run worker smoke test was run.
- If the browser refreshes during active generation before approval, this web UI does not yet recover the in-flight job from backend state.
- `flutter analyze` still reports unrelated pre-existing warnings outside the avatar implementation.

## WEB-0 handoff

{
  "subagent": "WEB-0",
  "status": "complete",
  "summary": [
    "festival_web is Flutter Web and currently uses direct Firebase Storage profile photo upload.",
    "festival branch lacks the semisemifinal avatar callable modules.",
    "Implementation should port backend avatar API contracts and add focused web avatar client/UI/state modules."
  ],
  "files_inspected": [
    "festival_web/pubspec.yaml",
    "festival_web/lib/main.dart",
    "festival_web/functions/src/index.ts",
    "festival_web/functions/src/festival_embeddings.ts",
    "functions/src/index.ts",
    "semisemifinal:functions/src/avatarMedia.ts",
    "semisemifinal:functions/src/avatarApproval.ts"
  ],
  "files_changed": [
    "docs/avatar-media-migration/web-avatar-pipeline-map.md"
  ],
  "commands_run": [
    "git status --short --branch",
    "git branch --show-current",
    "git branch --all",
    "rg ... avatar/function/web mapping searches",
    "git show semisemifinal:functions/src/avatarMedia.ts",
    "git show semisemifinal:functions/src/avatarApproval.ts"
  ],
  "tests_run": [],
  "test_results": [],
  "api_contracts": [
    "uploadAvatarSourcePhoto callable in asia-northeast3",
    "getAvatarJobCandidates callable in asia-northeast3",
    "approveAvatarCandidate callable in asia-northeast3"
  ],
  "ui_components": [
    "festival_web/lib/main.dart profile creation screen",
    "planned festival_web/lib/avatar/* widgets and client"
  ],
  "privacy_findings": [
    "Current festival_web direct Storage upload exposes profile photo URL semantics.",
    "New flow must expose only approved avatar URL and runtime-safe preview candidate bytes."
  ],
  "remaining_blockers": [
    "Need exact contract extraction from semisemifinal backend and Flutter client.",
    "Need festival_web state-machine tests before implementation."
  ]
}
