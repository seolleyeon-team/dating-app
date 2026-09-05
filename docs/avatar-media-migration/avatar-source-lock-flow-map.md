> **HISTORICAL / RETIRED — NOT A CURRENT DEPLOYMENT AUTHORITY.** The current Azure-only, source-set architecture is defined in [avatar-production/CURRENT_ARCHITECTURE.md](../avatar-production/CURRENT_ARCHITECTURE.md).
>

# Avatar Source Lock Flow Map

```json
{
  "before_generation_change_allowed": true,
  "generation_start_trigger": "Current app uploads the picked image immediately in PhotoUploadScreen._addPhoto via uploadAvatarSourcePhoto; the upload response creates currentAvatarSourcePhotoId/currentAvatarJobId and starts queued avatar generation.",
  "source_lock_fields": [
    "userPrivateMedia.currentAvatarSourcePhotoId",
    "userPrivateMedia.currentAvatarJobId",
    "userPrivateMedia.avatarSourceSelectionVersion",
    "userPrivateMedia.sourcePhotos[].avatarGenerationState=current",
    "users/{uid}.avatar.status",
    "users/{uid}.onboarding.avatarGenerationJobId",
    "users/{uid}.onboarding.avatarSourceSelectionVersion"
  ],
  "backend_upload_guard": "Approved-avatar guard runs first. Source-start lock now rejects existing current source/current job or locked avatar statuses before image parsing/storage and rechecks inside the upload transaction.",
  "flutter_polling_state": "PhotoUploadScreen uses _activeAvatarJobId/_activeAvatarSourcePhotoId from the upload response and polls only _activeAvatarJobId. On reload, it can recover the public-safe onboarding.avatarGenerationJobId and recreate a queued slot token without source refs.",
  "profile_edit_avatar_delete_path": "ProfileEditScreen already blocks add/remove when avatarLockStateFromUserProfile reports approved avatar lock.",
  "retry_same_source_path": "Flutter retry button calls _startAvatarGeneration again against the existing _activeAvatarJobId; no new source bytes are sent.",
  "remaining_supersede_paths": [
    "Legacy/admin reset code paths may still use superseded states, but normal user uploads after source lock are rejected."
  ]
}
```

Policy target: once `uploadAvatarSourcePhoto` starts generation and creates a current source/job, normal user flow must keep that source locked through failed/no-preview states and through approval.
