# Avatar Data Contract

Version: `avatar_data_v2`

## Public user document

Only these avatar display fields are public-safe:

- `avatar.status`
- `avatar.approvedAvatarUrl`
- `avatar.sourceJobId`
- `onboarding.avatarUrls`, only as a backend-written approved mirror

Display requires `avatar.status == approved`, a nonempty approved URL, and URL
safety validation. `onboarding.avatarUrls` is never an independent fallback.
`onboarding.photoUrls` and root `photoUrls` are forbidden display fields.

The backend may publish a sanitized generation summary for recovery, but the
client cannot write it. The authoritative source/job IDs remain private.

## Private media document

`userPrivateMedia/{uid}` is backend-only and owns:

- `currentAvatarSourcePhotoId`
- `currentAvatarJobId`
- `avatarSourceSelectionVersion`
- private source entries and lifecycle state
- versioned source retention and recommendation consent
- cleanup state and timestamps

The source array may preserve legacy records, but exactly one entry may be
active/current. Secondary face boxes may exist only in worker memory; they are
not stored in this document.

## Avatar jobs

`avatarJobs/{jobId}` is backend-only. It stores safe IDs, state, model and
contract versions, source analysis decisions, privacy preprocessing actions,
trait card enums, QA decisions, timing, cost, retries, and terminal reason.

Allowed geometry is a coarse backend-only primary crop box needed for processing.
Raw landmarks, blendshapes, face vectors, CLIP/DINO vectors, unique biometric
descriptions, and exact identity descriptors are forbidden.

## Avatar candidates

`avatarCandidates/{candidateId}` is backend-only. It stores current job/user
ownership, temporary candidate reference, model seed/version, QA signals and
decision, preview eligibility, TTL, and approval state. Public responses do not
serialize its storage reference.

## Storage roles

- private source role: backend read/write only, retained by versioned consent
- temporary candidate role: backend only, bounded TTL
- approved avatar role: public read, backend write only
- chat real-photo role: backend-authorized separate feature only

No private bucket name, object location, signed query, or source reference may
enter Flutter, festival web, public Firestore, logs, reports, or analytics.

## Consent and deletion

Source retention and recommendation use are independent versioned consent
purposes. Neither is inferred solely from pressing Generate. Account deletion,
consent withdrawal, admin deletion, and policy deletion must invoke idempotent
backend cleanup and record only sanitized completion evidence.

## Rules requirements

Clients cannot read or write private media, embeddings, jobs, candidates,
server-owned avatar fields, or authoritative recovery fields. Rules must also
remove unrelated broad public grants before the application is considered
production-secure, because those grants can expose identity and relationship data.
