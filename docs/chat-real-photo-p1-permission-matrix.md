# Chat Real Photo P1 Permission Matrix

## Access Model

Real uploaded photos remain private. Chat participants may receive only a runtime short-lived URL for a chat-profile copy after backend authorization.

Flutter must not directly read:

- `userPrivateMedia`
- `clipEmbeddings`
- `seolleyeon-private-source-photos`
- `seolleyeon-chat-profile-photos`

## Resources And Roles

| Principal | Resource | Role | Level | Reason | Rollback |
|---|---|---|---|---|---|
| Functions runtime service account | `gs://$CHAT_PROFILE_PHOTO_BUCKET` | `roles/storage.objectAdmin` | Bucket | Upload callable writes chat-profile copy; callable reads/signs; cleanup may delete | `gcloud storage buckets remove-iam-policy-binding gs://$CHAT_PROFILE_PHOTO_BUCKET --member=serviceAccount:$FUNCTIONS_RUNTIME_SERVICE_ACCOUNT --role=roles/storage.objectAdmin` |
| Functions runtime service account | `gs://$SOURCE_PHOTO_BUCKET` | Existing narrow read/write role | Bucket | Upload callable writes cleaned source image. No client read. | Do not change unless staging upload fails. |
| Functions runtime service account | `$FUNCTIONS_RUNTIME_SERVICE_ACCOUNT` service account resource | `roles/iam.serviceAccountTokenCreator` | Service-account-level | Only if Cloud Functions signed URL generation requires IAM `signBlob` | `gcloud iam service-accounts remove-iam-policy-binding $FUNCTIONS_RUNTIME_SERVICE_ACCOUNT --member=serviceAccount:$FUNCTIONS_RUNTIME_SERVICE_ACCOUNT --role=roles/iam.serviceAccountTokenCreator` |
| Client users | `gs://$CHAT_PROFILE_PHOTO_BUCKET` | none | none | Direct read/write denied; backend authorization required | N/A |
| `allUsers`, `allAuthenticatedUsers` | any private/chat/temp bucket | none | none | No public access to real or temp media | Remove any binding immediately. |

## Bucket Requirements

- Uniform bucket-level access: enabled
- Public access prevention: enforced
- Bucket `projectNumber` must match `GCP_PROJECT` before update/IAM mutation
- No object ACL dependency
- No public download URL creation
- Signed URL TTL: max 300 seconds
- Signed URL persistence: forbidden

## Over-grant Risks

- Project-level Storage Admin can affect unrelated buckets. Prefer bucket-level object roles.
- Project-level Token Creator can sign more identities than needed. Prefer service-account-level binding.
- Public IAM members on chat-profile bucket expose real photos and block canary.

## Verification Requirements

- `FUNCTIONS_RUNTIME_SERVICE_ACCOUNT` must appear to belong to `GCP_PROJECT`.
- Runtime service account must have the expected bucket-level object role for staging bring-up.
- Runtime service account must not have a direct project-level `roles/storage.admin`, `roles/owner`, or `roles/editor` binding.
- Public members `allUsers` and `allAuthenticatedUsers` must be absent.
- Project-level deploy mismatch `GCP_PROJECT != FIREBASE_PROJECT` is refused.
