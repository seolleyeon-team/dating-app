# B3-L17A.1 — SUPERVISED_WATERMARK_LOGO_DATASET_V1_1: evaluation-quota vs collection-quota consistency correction (no model, no training, no generation)

Versioned correction of B3-L17A `SUPERVISED_WATERMARK_LOGO_DATASET_V1`.
V1 is preserved as a historical frozen record: `b3-l17a-supervised-data-design.md`,
`b3-l17a-supervised-data-design-aggregate-v1.json` and
`b3-l17a-supervised-manifest-example.json` are pinned by SHA-256 in CI and are
not edited. V1 digests (`5d10e2b09248…` contract, `75522cd03b4f…` split plan)
are recorded as constants in the module and never recomputed.

Current contract digest `c1b80fea5509…` (source policy `7335e2378bc1…`
unchanged, ontology `0f2925f0d492…` unchanged, label policy `ba2c49fd0b43…`
unchanged, annotation schema `ca4152f3b513…`, split plan `2e7e1bb8f31a…`),
from `avatar_supervised_dataset_contract.contract_digest()` and checked in CI.

Verdict marker: **`SUPERVISED_DATA_COLLECTION_CONTRACT_READY_AFTER_QUOTA_CORRECTION`**.
Corpus status unchanged: `NATURAL_POSITIVE_CORPUS_INSUFFICIENT`,
`CLEAN_NEGATIVE_CORPUS_INSUFFICIENT`, `TRAINING_SIZE_NOT_YET_JUSTIFIED`,
`NATURAL_POSITIVE_EVIDENCE_MISSING`, `TEXT_POLICY_GAP` unresolved.

Immutable and untouched: B3-L16A `DINOV2_VERIFIER_FAILED_DEVELOPMENT`,
`FROZEN_VERIFIER_REPRESENTATION_SEARCH_STOP_RULE`, the Phase 0 provenance-only
correction, the B3-L17A verdict `SUPERVISED_DATA_COLLECTION_CONTRACT_READY`
(kept as `priorVerdictV1`). This phase performs no image generation
(Azure 0, OpenAI image 0), no model training or inference, no production data
access, no build or deploy.

## 1. The mismatch — `EVALUATION_QUOTA_VS_COLLECTION_QUOTA_MISMATCH`

Confirmed in fresh V1 source (main `764c0a68`):

* Partitions `TRAIN_DEVELOPMENT` 0.6 / `VALIDATION` 0.2 / `SEALED_TEST` 0.2
  (group-level).
* Statistical targets: clean 0 false reviews in 29 independent groups → one-sided
  95 % upper bound < 0.10 (59 for < 0.05); critical family 29/29 → lower bound
  ≥ 0.90 (46 with one miss).
* V1 wording (design §10): "Collection gap: 29 independent groups per positive
  stratum and 29 independent clean groups (59 aspirational)", and
  `corpus_status.collectionGapByClass = 29 − current`. That presents the
  **sealed evaluation quota** as a **total collection target**. With the 0.2
  sealed fraction, 29 collected groups would leave about 6 in `SEALED_TEST`,
  far below the 29 needed for the bound.

Nothing about the target itself changes: 29 / 46 / 59, 95 % one-sided
Clopper-Pearson, unit = independent group. Not done: lowering 29, lowering
confidence to 90 %, merging `SEALED_TEST` into development, counting
`VALIDATION` as sealed evidence, counting crops or regions as independent
samples.

## 2. Three counts that are never confused

| Count kind | Meaning |
|---|---|
| `COLLECTED_GROUPS` | independent groups (source lineages) actually collected and labelled |
| `PARTITIONED_GROUPS` | groups assigned by the frozen splitter (one partition each) |
| `EVALUATION_ELIGIBLE_SEALED_GROUPS` | groups that land in `SEALED_TEST` and are eligible for the statistical bound |

29 / 46 / 59 are targets for `EVALUATION_ELIGIBLE_SEALED_GROUPS` only.
`VALIDATION` serves model selection, training-recipe selection and threshold
selection; `sealed_evidence_groups()` refuses any partition other than
`SEALED_TEST`, and the sealed test stays one-shot behind the lock.

## 3. Minimum collection — derived by simulating the frozen splitter

`avatar_supervised_sample_size.minimum_collected_groups(targetSealedGroups,
sealedFraction, stratum, provenancePool)` builds n synthetic opaque groups,
runs the actual planner, and returns the smallest n whose `SEALED_TEST` count
reaches the target. ceil(target / 0.2) is reported as `naiveCeil` only and is
never the authority. The sealed fraction is not a free parameter: it must equal
the frozen fraction of the pool (0.2 for future-eligible pools; a `LEGACY` pool
raises because it can never reach `SEALED_TEST`; a `SEALED_RESERVED` lineage
pool has fraction 1.0, so its minimum equals the target).

| Sealed target (`EVALUATION_ELIGIBLE_SEALED_GROUPS`) | naive ceil | **minimum `COLLECTED_GROUPS` (code authority)** | sealed at minimum / one below |
|---|---|---|---|
| 29 per critical positive stratum (0 misses) | 145 | **142** | 29 / 28 |
| 46 per critical positive stratum (1 miss) | 230 | **227** | 46 / 45 |
| 29 `NATURAL_CLEAN_REPRESENTATIVE` (0 false reviews, < 0.10) | 145 | **142** | 29 / 28 |
| 59 `NATURAL_CLEAN_REPRESENTATIVE` (aspirational < 0.05) | 295 | **292** | 59 / 58 |

The minimum is a single-label, single-pool statement. For a real multi-label
corpus the sealed quota validator (§6) is the authority at manifest freeze.
These numbers are split/evaluation-quota arithmetic; they are **not** a training
size (`TRAINING_SIZE_NOT_YET_JUSTIFIED`; `training_size_from_collection_n`
raises).

## 4. Multi-label group split contract (frozen, digest `2e7e1bb8f31a…`)

A group may carry several classes (`classSet` such as `GRAPHICAL_LOGO` +
`OVERLAY_WATERMARK`). The V1 per-stratum splitter would have needed the same
group in two rows. V1_1 split algorithm:

1. reject duplicate `groupId` rows and unknown strata; a group is one
   statistical unit and appears exactly once;
2. pool = allowed partitions from the provenance class narrowed by an optional
   prospective `lineageReservation` (`SEALED_RESERVED` → `SEALED_TEST` only,
   `DEVELOPMENT_ONLY` → never `SEALED_TEST`; legacy pool never `SEALED_TEST`);
3. per (label, pool, partition): integer quotas by largest remainder on the
   renormalised frozen fractions, remainder ties `SEALED_TEST` > `VALIDATION`
   > `TRAIN_DEVELOPMENT`;
4. visit groups in sha256(SEED + groupId) order (input-order invariant);
5. assign each group once to the allowed partition with the largest total
   remaining deficit over all its labels, ties by sha256(SEED + groupId +
   partition); every label of the group is credited in that partition.

No manual override and no model score exist as inputs (`overrides=` / `scores=`
raise `TypeError`). A multi-label group counts once in the overall independent
group count and once in each family's conditional recall denominator.
`groups_from_manifest()` derives the group rows (evaluation strata = union of
policy classes / clean category over the group's images) so the same group can
never be split into two rows by hand.

## 5. Two clean concepts

| Category | Definition | Enrichment | Metric name | Production-prevalence claim |
|---|---|---|---|---|
| `NATURAL_CLEAN_REPRESENTATIVE` | natural clean output from the canonical generation distribution, no policy mark, never selected by a model score | no | `REPRESENTATIVE_CLEAN_FALSE_REVIEW_RATE` | only with ≥ 29 representative sealed groups |
| `BENIGN_HARD_NEGATIVE_STRESS` | garment text, background signage, decorative graphics, skin/hair texture, jewelry/accessory, seams/patterns; may be deliberately enriched | yes | `HARD_NEGATIVE_STRESS_FALSE_REVIEW_RATE` | never |

Policy positives are `BRAND_TEXT_OR_MARK`, `OVERLAY_WATERMARK`,
`GRAPHICAL_LOGO`, `GENERATIVE_TEXT_ARTIFACT` (critical strata) plus
`OVERLAY_TEXT` (held separately, `TEXT_POLICY_GAP`). `GARMENT_TEXT` and
`BACKGROUND_SIGNAGE` are benign classes: an image whose only regions are benign
is clean and a hard-negative-stress candidate. The ontology (nine classes,
`avatar_watermark_label_schema_v2`) is unchanged. A clean image without a
declared `cleanCategory` is `UNCATEGORIZED_CLEAN` and contributes to no gate.
`metric_label()` refuses to attach a production-style clean rate name to a
stress set; `production_clean_rate_claim_allowed()` is false for stress sets
and for representative sets below the sealed quota.

## 6. Sealed quota validator (blocks the lock)

`sealed_quota_check(records)` counts `EVALUATION_ELIGIBLE_SEALED_GROUPS` per
critical positive class (required 29 each) and `NATURAL_CLEAN_REPRESENTATIVE`
sealed groups (required 29; aspirational 59 reported separately). Hard-negative
stress groups are reported but never count toward the representative quota.
Result `SEALED_TEST_STATISTICAL_QUOTA_MET` or
**`SEALED_TEST_STATISTICAL_QUOTA_NOT_MET`**. The check is written to
`supervised_dataset_v1_1_sealed_quota_check.json`, which is now the fifth
sealed-test prerequisite; `sealed_test_guard()` raises `SealedQuotaNotMet` and
creates no lock unless the status is MET for this dataset version. The
one-shot lock (`supervised_dataset_v1_1_sealed_test.lock`) is unchanged.

## 7. Corpus status after correction

| Item | Value |
|---|---|
| natural-positive independent groups (collected) | 0 in every stratum |
| uncontaminated clean groups (collected) | 0 (5 legacy groups contaminated) |
| sealed evaluation gap per critical stratum | 29 |
| minimum collection per critical stratum | 142 (227 for the one-miss target) |
| minimum collection for representative clean | 142 (292 aspirational) |
| verdict | `SUPERVISED_DATA_COLLECTION_CONTRACT_READY_AFTER_QUOTA_CORRECTION` |
| corpus | `NATURAL_POSITIVE_CORPUS_INSUFFICIENT`, `CLEAN_NEGATIVE_CORPUS_INSUFFICIENT` |
| training size | `TRAINING_SIZE_NOT_YET_JUSTIFIED` |

Whether natural positives occur often enough in first-party generation to fill
these minimums is unknown and is not estimated here; that is the subject of the
separate B3-L17B0 feasibility plan. Paid generation is still required for any
collection and was not executed; production user data is not required.

## 8. Readiness

The thirteen V1 items plus four correction items (evaluation-vs-collection
quota separation, multi-label group split, clean category separation, sealed
quota validator) are complete →
`SUPERVISED_DATA_COLLECTION_CONTRACT_READY_AFTER_QUOTA_CORRECTION`.

## 9. Safety

No image opened, no model loaded, no training, no inference, no image
generation, no production read/write, no build/deploy, no raw image
transmission. Repository artifacts are the versioned modules, the tests, this
note, the aggregate JSON and a fake-id example manifest.
