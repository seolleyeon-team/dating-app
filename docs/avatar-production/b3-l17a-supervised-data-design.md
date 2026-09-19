# B3-L17A — SUPERVISED_WATERMARK_LOGO_DATASET_V1: supervised watermark/logo data design (no model, no training)

Marker `SUPERVISED_WATERMARK_LOGO_DATA_DESIGN`. Contract digest
`5d10e2b09248…` (source policy `7335e2378bc1…`, ontology `0f2925f0d492…`,
annotation schema `ad492f8341c5…`, split plan `75522cd03b4f…`, label policy
`ba2c49fd0b43…`), from `avatar_supervised_dataset_contract.contract_digest()`
and checked in CI. Offline data-design work only: no model training,
fine-tuning, linear probe, classifier fit, threshold selection, feature
extraction, production inference, image generation, production data access,
build or deploy.

Immutable authority: B3-L15A `EDGE_SCAN_VERIFIER_FAILED_DEVELOPMENT`; B3-L16A
`DINOV2_VERIFIER_FAILED_DEVELOPMENT` (provenance-only metadata correction
merged as `PROVENANCE_ONLY_METADATA_CORRECTION`);
`FROZEN_VERIFIER_REPRESENTATION_SEARCH_STOP_RULE` — no SigLIP, OpenCLIP,
DINOv2-large, CLIP variant, RBF SVM, MLP, random forest, boosting, new
threshold grid, new crop, new scan or new zero-shot detector in this phase.
`TEXT_POLICY_GAP` unresolved; `NATURAL_POSITIVE_EVIDENCE_MISSING` (data design
alone does not close it).

## 1. Legacy contamination inventory

| Source | Kind | Count | Classification | Future use |
|---|---|---|---|---|
| generated avatars (20, G1–G5; 5 independent groups) | natural generated output | 20 | `LEGACY_DEVELOPMENT_CONTAMINATED` | TRAIN_DEVELOPMENT / VALIDATION augmentation with an explicit flag; regression set; **never SEALED_TEST** |
| source photos (8) | source photo | 8 | `RESTRICTED_SOURCE_NOT_MODEL_DATA` | none |
| B3-L11 constructs (VISUAL_MARK_CHALLENGE_V3 development) | controlled challenge evidence | 180 | `LEGACY_DEVELOPMENT_CONTAMINATED` | augmentation / challenge / regression |
| B3-L14A constructs (EDGE_MARK_GENERALIZATION_V1 dev + consumed holdout) | controlled challenge evidence | 320 | `LEGACY_DEVELOPMENT_CONTAMINATED` | augmentation / challenge / regression |
| B3-L15A proposal crops (CLIP) | controlled challenge evidence | 19,607 | `LEGACY_DEVELOPMENT_CONTAMINATED` | augmentation / challenge / regression |
| B3-L16A proposal crops (DINOv2) | controlled challenge evidence | 19,607 | `LEGACY_DEVELOPMENT_CONTAMINATED` | augmentation / challenge / regression |
| B3-L7/L8/L9/L10 OWLv2 + Florence captures | controlled challenge evidence | 112 | `LEGACY_DEVELOPMENT_CONTAMINATED` | augmentation / challenge / regression |
| human label artifacts (B3-L5/L6 Rater A/B/C) | label artifact | 20 | `LEGACY_DEVELOPMENT_CONTAMINATED` | ontology continuity only; not inherited as truth |

Rule: any image or derivative whose performance was seen in B3 can never be a
future sealed holdout. The 20 avatars carry the owner Rater A reference truth
20/20 no visible graphical mark (18 NO_VISIBLE_RELEVANT_TEXT_OR_MARK, 2
GARMENT_TEXT): **natural positives so far = 0**.

## 2. Source policy (digest `7335e2378bc1…`)

* Runtime target is the generated avatar output; **user-uploaded source
  photos are never model data** (training or evaluation) and are never copied
  into the dataset — no added identity exposure.
* Preferred natural-domain source: owner-authorized, first-party generated
  avatar outputs under explicit QA/data-use authority, generated output only,
  private local storage, stable opaque dataset id, retention and deletion
  policy, provenance record.
* Production user images: prohibited without separate owner/privacy approval.
  No silent production mining: no Firestore bulk export, no production bucket
  crawl, no UID-based corpus, no consent-less production image use; this phase
  read and wrote 0 production user data.
* Third-party public datasets: optional training augmentation only. Each needs
  a per-dataset audit of name, source URL, exact version, license,
  commercial/product-use compatibility, redistribution restrictions, image
  copyright status, annotation license and download terms; anything missing or
  ambiguous → `LICENSE_REVIEW_REQUIRED` and excluded. No web scraping. A
  third-party set never replaces the first-party natural holdout.

## 3. Natural-positive definition

`NATURAL_POSITIVE` = a visible text/logo/watermark/mark region that appears in
the canonical avatar generation output itself, without any post-hoc synthetic
overlay. Not counted: B3 injected overlays, programmatic synthetic marks,
manually pasted logo/text, challenge derivatives, synthetic constructs — these
are `CONTROLLED_SYNTHETIC_AUGMENTATION` / `CONTROLLED_CHALLENGE_EVIDENCE` only
(training augmentation, challenge set, regression set; excluded from natural
validation and sealed-holdout statistics and from natural counts).

## 4. Label ontology (digest `0f2925f0d492…`; B3 authority `avatar_watermark_label_schema_v2`)

`NO_VISIBLE_RELEVANT_TEXT_OR_MARK` · `GARMENT_TEXT` · `BACKGROUND_SIGNAGE` ·
`BRAND_TEXT_OR_MARK` · `OVERLAY_TEXT` · `OVERLAY_WATERMARK` · `GRAPHICAL_LOGO`
· `GENERATIVE_TEXT_ARTIFACT` · `UNCERTAIN`. Frozen; a versioned extension may
only be frozen before labeling starts. **No positive/negative collapse**: the
dataset labels observations; the action mapping is a separate future contract
(detector target ≠ product reject policy while `TEXT_POLICY_GAP` is open).
`UNCERTAIN` → `EXCLUDED_FROM_PRIMARY_TRAINING`, reported as an uncertainty
rate, usable for a separate robustness evaluation.

## 5. Region annotation schema (digest `ad492f8341c5…`)

Per visible relevant region: `regionId`, `class` (ontology), `bboxNormalized`
[xmin, ymin, xmax, ymax] in [0, 1], `visibility` clear/faint, `sceneRelation`
overlay/garment/background/integrated/unknown, `legibility`
legible/partial/illegible/not_applicable, `raterConfidence` high/medium/low,
`annotationStatus` agreed/adjudicated/uncertain. Transcription is **not
stored by default**; storing OCR text needs a new pre-registered hypothesis.
Image-level record fields: `hasRelevantRegion`, `regionCount`, `classSet`,
`uncertainPresent`, `sourceProvenanceClass`, `splitGroupId` only. Forbidden
anywhere: UID, user id, email, source-photo path, path, filename,
user-facing filename, display name, phone, identity. Repo holds schema,
validator, a fake-id example and aggregate counts only; the private manifest
(opaqueImageId, groupId, provenanceClass, originKind, collectionBatch,
annotationVersion, sha256, perceptualHash, width, height, regions, split)
stays local.

## 6. Label authority, blinding, agreement (digest `ba2c49fd0b43…`)

Rater A + independent Rater B label the raw generated image only; the new
dataset does not inherit the B3 Rater A pilot truth. Disagreement →
owner-designated adjudicator or pre-registered third rater; with no
adjudicator the region becomes `UNCERTAIN`. One rater only →
`SINGLE_RATER_DATASET_LIMITATION`, never promotable to production validation
evidence. Raters never see CLIP/DINOv2 scores, Grounding DINO boxes, Florence
or OWLv2 results, model predictions, threshold results or prior B3 pass/fail
metadata; the label template has no field for them. Agreement metrics frozen
before labeling: image-level agreement, region class agreement, region
localization agreement (IoU ≥ 0.5); Cohen's kappa is descriptive only, never
proof of label correctness.

## 7. Leakage unit, duplicates, split, sealed test (digest `75522cd03b4f…`)

* Leakage unit = group: same underlying identity/source lineage
  (regenerations, variants, near duplicates) share one opaque `groupId`; no
  identity or source-photo identifier is stored.
* Duplicates (local only, before the split): SHA-256 exact + 64-bit DCT pHash
  (32 × 32 grayscale, top-left 8 × 8 DCT, median), Hamming ≤ 10 → collapsed
  into one group; the threshold was fixed before any data; no model score
  enters dedup (the function has no score input).
* Partitions `TRAIN_DEVELOPMENT` / `VALIDATION` / `SEALED_TEST` (0.6 / 0.2 /
  0.2), group-disjoint; a group in two partitions fails validation. Split
  algorithm: per (stratum, provenance pool) order groups by
  sha256(seed + groupId) with seed = dataset version, assign the i-th of n to
  the partition whose cumulative fraction covers (i + 0.5)/n; the legacy pool
  excludes SEALED_TEST with renormalised fractions; no manual override
  parameter exists; input order does not change the result.
* Sealed test: manifest frozen, then no evaluation until the model
  architecture, training recipe and threshold are frozen (four prerequisite
  markers); one evaluation behind
  `supervised_dataset_v1_sealed_test.lock`; a second evaluation fails closed;
  browsing minimised; legacy data never.

## 8. Statistical sufficiency (evaluation, not training)

Unit = independent image/group, never crop or region count (20 regions on one
image are one unit). One-sided 95 % exact binomial (Clopper-Pearson) via beta
quantiles (scipy pinned by version in the aggregate):

| Question | Result |
|---|---|
| Clean gate false review ≤ 10 %: 0 false reviews → upper bound < 0.10 | **29** independent clean groups (bound 0.098) |
| 1 false review allowed | 46 |
| Aspirational 5 %: 0 false reviews → upper bound < 0.05 | **59** (bound 0.0495) |
| Critical family recall ≥ 0.90: 0 misses → lower bound ≥ 0.90 | **29** independent positives (bound 0.902) |
| 1 miss allowed | **46**; 2 misses: 61 |

A point estimate alone never certifies sufficiency. These are
evaluation-confidence numbers; **`TRAINING_SIZE_NOT_YET_JUSTIFIED`** — training
corpus size is decided by the future supervised phase's learning-curve
contract, never inferred from evaluation n.

## 9. Coverage plan, hard negatives, retention

* Natural-positive strata to collect: `BRAND_TEXT_OR_MARK`,
  `OVERLAY_WATERMARK`, `GRAPHICAL_LOGO`, `GENERATIVE_TEXT_ARTIFACT`; per
  stratum ≥ 29 independent groups for a 0-miss evaluation (46 with one miss);
  `OVERLAY_TEXT` held separately (`TEXT_POLICY_GAP`). Synthetic samples are
  never added to natural counts.
* Clean/negative corpus: ≥ 29 independent uncontaminated clean groups (59 for
  the 5 % aspiration), designed to include benign hard negatives —
  GARMENT_TEXT, BACKGROUND_SIGNAGE, decorative graphics, face/skin/hair
  texture, jewelry/accessory detail, clothing seams/patterns — collected
  without cherry-picking on any existing model score. Hard-negative mining with
  model predictions is a separate post-training round.
* Retention/deletion per source class (first-party generated, legacy, third
  party, source photo) is recorded in the aggregate; production user images
  are not used.

## 10. Readiness and data availability

All thirteen readiness items are complete (source policy, natural-positive
definition, ontology, region schema, blinded workflow, leakage group, split
algorithm, sealed holdout contract, duplicate handling, privacy contract,
license handling, statistical helper, legacy classification) →
**`SUPERVISED_DATA_COLLECTION_CONTRACT_READY`**.

Actual inventory: natural-positive independent groups **0** in every stratum;
uncontaminated clean groups **0** (the 5 legacy groups are contaminated) →
**`NATURAL_POSITIVE_CORPUS_INSUFFICIENT`** and
**`CLEAN_NEGATIVE_CORPUS_INSUFFICIENT`**. Collection gap: 29 independent groups
per positive stratum and 29 independent clean groups (59 aspirational).
Prospective collection needs new owner-authorized first-party generated
outputs, i.e. **paid generation is required and was not executed**; production
user data is **not** required unless separately approved. Whether natural
positives occur often enough in first-party generation to fill the strata is
itself unknown — the plan yields counts, cost and privacy terms for an owner
decision, and stops.

## 11. Safety

Model training 0 · classifier fits 0 · inference 0 · Azure / OpenAI image
generation 0 · Firestore scans, storage bulk listing, user data mutation,
user corpus export 0 · builds/deploys 0 · production writes 0 · external raw
image transmission 0 · originals 28/28 untouched (no image was opened in this
phase). Repository artifacts aggregate only.
