# Avatar generation: current architecture

This file is the current repository authority as of 2026-09-05. Older dated,
PR-numbered, migration, audit, and incident documents are historical evidence;
they are not deployment instructions when they conflict with this file.

## Retired

- Local-model avatar image generation and every provider fallback to it
- Local-model worker/deployment modes and model downloads
- Single-photo avatar-generation admission

Unsupported worker/provider configuration fails closed. It is never silently
translated to the canonical provider.

## Canonical flow

Flutter uploads 2–6 onboarding photos individually and receives opaque,
server-issued source references. Pressing Next calls only
`beginAvatarGenerationFromOnboardingPhotos`. The server validates the complete
set and creates one logical selection job. The worker hard-gates each normalized
original for exactly one primary face, ranks eligible originals
deterministically, transactionally locks the best original-direct source, and
only then calls Azure GPT Image 2. Candidate QA and preview selection follow.

Generation policy is `initial=2`, `extra=2`, `max=4`, with
`minSafeBeforeExtra=2`, `minPreview=1`, `previewCount=2`, and
`requireFour=false`. Every candidate uses the same selected source. Azure input
is the selected normalized original, not a face crop.

CLIP recommendation is a separate consent-controlled pipeline and is not a
generation fallback. Torch, Transformers, Hugging Face model access, Florence,
CLIP, and MediaPipe remain because QA, recommendation, similarity, and face
detection consume them. The retired image-generation runtime dependency is not
installed.

## Dependency ownership

| Dependency/runtime | Legacy generation only | Current consumer | Decision |
| --- | --- | --- | --- |
| Diffusers image pipeline | yes | none | removed |
| Local image checkpoint/tokenizer | yes | none | removed |
| Torch/CUDA runtime | no | QA, CLIP, similarity | preserved |
| Transformers/Hugging Face Hub | no | pinned Florence and CLIP QA assets | preserved |
| MediaPipe and OpenCV | no | source selector and face-quality gates | preserved |
| HTTP client and Pillow | no | Azure transport and response normalization | preserved |

The retired single-photo callable is not registered. Its old factory remains
only as a side-effect-free tombstone that immediately returns
`avatar_single_photo_generation_retired`; it cannot be enabled by configuration
and cannot write Storage, Firestore, Tasks, or call Azure.

## Release safety

Run `scripts/staging_avatar_live_preflight.py` before any deployment. It checks
the canonical source-set export, Azure-only worker mode, 2/2/4 policy, selector
files, detector assets declared in the container, Azure quota/provider modules,
and absence of the retired generation dependency. Cloud changes require a
separate explicit approval.
