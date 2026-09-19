# B3-L17B0 — prospective corpus collection feasibility, sealed-test quota planning, natural-positive incidence pilot design, budget / stopping rule (plan only; nothing generated)

Plan version `B3_L17B0_COLLECTION_FEASIBILITY_V1` on contract
`SUPERVISED_WATERMARK_LOGO_DATASET_V1_1` (contract digest `c1b80fea5509…`, split
plan `2e7e1bb8f31a…`, post-correction main after PR #135). Nothing was
generated (Azure 0, OpenAI image 0), trained, scored or read from production;
no build or deploy. Every number below is planning arithmetic on the frozen
contract; none is a measurement of the generation pipeline.

Immutable and untouched: B3-L16A `DINOV2_VERIFIER_FAILED_DEVELOPMENT`,
`FROZEN_VERIFIER_REPRESENTATION_SEARCH_STOP_RULE`, Phase 0 provenance
correction, B3-L17A `SUPERVISED_DATA_COLLECTION_CONTRACT_READY`, B3-L17A.1
`SUPERVISED_DATA_COLLECTION_CONTRACT_READY_AFTER_QUOTA_CORRECTION`, corpus
`NATURAL_POSITIVE_CORPUS_INSUFFICIENT` / `CLEAN_NEGATIVE_CORPUS_INSUFFICIENT`,
`TRAINING_SIZE_NOT_YET_JUSTIFIED`, `NATURAL_POSITIVE_EVIDENCE_MISSING`,
`TEXT_POLICY_GAP` unresolved.

## 1. The unknown — `NATURAL_POSITIVE_INCIDENCE_UNKNOWN`

How often `BRAND_TEXT_OR_MARK`, `OVERLAY_WATERMARK`, `GRAPHICAL_LOGO` and
`GENERATIVE_TEXT_ARTIFACT` occur naturally in owner-authorized first-party
canonical generation (`azure_gpt_image_2`) is not known. The full corpus
generation budget is therefore **not** fixed in this phase.
`confirmed_generation_budget()` raises until a blinded human-labelled pilot
result exists. "142 per stratum" (B3-L17A.1) is split arithmetic for positive
groups already in hand; it is not a generation count. At 1 % incidence the
expected generation would be two orders of magnitude larger (§6).

## 2. Pilot — `FIRST_PARTY_NATURAL_MARK_INCIDENCE_PILOT_V1` (designed, not run)

Goal: estimate, per class, how often natural positives and representative
clean outputs occur in canonical generation, as an exact binomial estimate over
independent source lineages.

* **Data status from the start: `PILOT_DISCOVERY_NOT_SEALED_TEST`.** Pilot
  records carry `lineageReservation: DEVELOPMENT_ONLY`, provenance
  `FUTURE_TRAINING_ELIGIBLE`, batch prefix `pilot-`; the validator rejects
  `SEALED_TEST` and the incidence report refuses sealed records. Later
  `TRAIN_DEVELOPMENT` / `VALIDATION` eligibility is a separate decision;
  `SEALED_TEST` never.
* **Human labels only.** Every generated pilot output is labelled by blinded
  raters under the V1_1 dual-rater contract. No CLIP, DINOv2, Grounding DINO,
  Florence, OWLv2, future supervised model or model-score filtering touches the
  pilot; any score/prediction/box field is rejected as input
  (`check_pilot_label_input`, `incidence_report`).
* **Unit.** Independent source lineage = group. All outputs regenerated from
  one lineage are one group (`same lineage regeneration = same group`); 20
  outputs from one lineage are one evaluation unit, never 20.

### 2.1 Source lineage authority

| Category | Pilot use | Conditions | Domain validity |
|---|---|---|---|
| `OWNER_VOLUNTEER_REAL_SOURCE` | allowed | explicit volunteer consent + separate privacy authority; source photos stay `RESTRICTED_SOURCE_NOT_MODEL_DATA`; only generated outputs become dataset records | real-source domain (still not a production-population claim) |
| `OWNER_AUTHORIZED_SYNTHETIC_SOURCE` | allowed | owner authorization; source images stay restricted | **`SYNTHETIC_SOURCE_DOMAIN_LIMITATION`**: artifacts are `NATURAL_GENERATION_ARTIFACT`, never `REAL_USER_SOURCE_DOMAIN_VALIDATED` (forbidden claim) |
| `PRODUCTION_USER_SOURCE` | **prohibited** | no production scan, crawl, export or write | not applicable |

### 2.2 Size options (owner decision; the agent does not pick one)

Assumptions declared, not measured: 4 generation attempts per lineage (one
canonical job, max4 candidates), ≤ 2 MB per output, 2 raters, 1.5 rater-minutes
per output. Cost: **`COST_NOT_VERIFIED`** for every option (no fresh verified
provider price source; the repository holds no pricing authority;
`cost_estimate()` computes only when a unit price, its source and verification
date are supplied).

| Option | independent lineages | attempts / lineage | total attempts (= cap) | rater labels (minutes assumed) | storage upper bound | P(≥ 1 positive lineage) at 1 % / 5 % / 10 % / 20 % | 0-observed 95 % upper bound on incidence |
|---|---|---|---|---|---|---|---|
| `SMALL` | 12 | 4 | 48 | 96 (144) | 96 MB | 0.11 / 0.46 / 0.72 / 0.93 | 0.221 |
| `MEDIUM` | 30 | 4 | 120 | 240 (360) | 240 MB | 0.26 / 0.79 / 0.96 / 0.999 | 0.095 |
| `LARGE` | 60 | 4 | 240 | 480 (720) | 480 MB | 0.45 / 0.95 / 0.998 / 1.00 | 0.049 |

Limitations (all options): a class with incidence around 1 % will most likely
not be observed at all, leaving only an upper bound; `SMALL` cannot resolve
classes at 5 %; synthetic-source lineages carry
`SYNTHETIC_SOURCE_DOMAIN_LIMITATION`; nothing from the pilot is sealed
evidence.

### 2.3 Stopping rule (frozen before start)

Fixed generation-attempt cap = the option's total attempts; **no model-score
adaptive continuation**. The only extension trigger is a blinded human-labelled
positive lineage count below the feasibility floor (3 lineages) in a critical
class, and an extension is a **new owner re-approval of a new cap**
(`request_extension` reports `OWNER_REAPPROVAL_REQUIRED`, executes nothing,
`newCap: null`). The agent never increases paid generation
(`execute_generation` always raises).

### 2.4 Incidence report tool (implemented; no values)

`incidence_report()` reports per class, aggregate only: total independent
groups, total generated outputs, natural-positive groups, incidence estimate,
exact two-sided 95 % binomial interval, representative clean groups, uncertain
groups. This task produced no values (`PILOT_NOT_RUN`).

## 3. Sealed-test quota planning

Per critical class ≥ 29 `EVALUATION_ELIGIBLE_SEALED_GROUPS`
(`SEALED_TEST_STATISTICAL_QUOTA_NOT_MET` otherwise; lock blocked).
`NATURAL_CLEAN_REPRESENTATIVE` sealed ≥ 29 (59 aspirational), minimum
collection 142 under the pooled split. `BENIGN_HARD_NEGATIVE_STRESS`: no fixed
quota; defined, not collected; reported only as
`HARD_NEGATIVE_STRESS_FALSE_REVIEW_RATE` and never as a production clean
prevalence. `OVERLAY_TEXT` held separately (`TEXT_POLICY_GAP`).

Two ways to reach the sealed quota, both deterministic and score-free:

* **Pooled split** (`FUTURE` pool, sealed fraction 0.2): 142 collected
  positive groups per class → 29 sealed.
* **Prospective reservation** (`SEALED_TEST_ELIGIBLE_SOURCE_LINEAGES`): before
  full collection, reserve lineages by sha256(SEED + ":reserve:" + lineageId);
  reserved lineages are `FUTURE_HOLDOUT_ELIGIBLE` + `SEALED_RESERVED` (sealed
  only), all others `DEVELOPMENT_ONLY`; no lineage is both, and a lineage used
  for train/dev generation is never reused as sealed. Reserved positives count
  1:1 toward the quota (29 positive reserved lineages per class).

## 4. Full-collection budget calculator (expectation only)

`expected_generation(target, p)` = ceil(required collected positive groups /
p) lineages, × 4 outputs; `lineagesFor95pctSufficiency` is the count at which
P(Binomial(N, p) ≥ required) ≥ 0.95 (upper budget risk). Lineages serve all
strata at once, so the rarest stratum dominates (`combined_expectation`).
Groups and outputs are always separate numbers.

| assumed incidence p | pooled: lineages expected / for 95 % sufficiency (outputs) | reserved-lineage: lineages expected / for 95 % (outputs) |
|---|---|---|
| 0.01 | 14,200 / 16,205 (56,800 / 64,820) | 2,900 / 3,834 (11,600 / 15,336) |
| 0.02 | 7,100 / 8,098 (28,400 / 32,392) | 1,450 / 1,915 (5,800 / 7,660) |
| 0.05 | 2,840 / 3,233 (11,360 / 12,932) | 580 / 763 (2,320 / 3,052) |
| 0.10 | 1,420 / 1,611 (5,680 / 6,444) | 290 / 379 (1,160 / 1,516) |
| 0.20 | 710 / 800 (2,840 / 3,200) | 145 / 187 (580 / 748) |
| 0.50 | 284 / 313 (1,136 / 1,252) | 58 / 71 (232 / 284) |

These rows are hypothetical incidences for sizing only; p is unknown. None is a
training size (`TRAINING_SIZE_NOT_YET_JUSTIFIED`; `training_size_from_budget`
raises).

## 5. Collection batch provenance and provider drift

Every future batch records in the **private** manifest: batch ID, source
authority class, generation provider, model revision, prompt contract digest,
generation date, consent/authority, retention rule (`validate_batch`). If the
canonical provider or model revision changes during collection, the batch
records it; if `SEALED_TEST` spans revisions, the revision distribution is
reported (`revision_distribution`), never silently pooled. The repository holds
aggregate counts only.

## 6. Why no generation plan is fixed now

The required sealed positives are fixed (29 per class). The lineages needed to
find them scale as 1/p: at 20 % incidence the pooled plan is ~700 lineages, at
1 % it is ~14,000. A paid budget fixed before the pilot would be either wasted
or insufficient. The pilot's own cap is fixed per option above.

## 7. Safety

Azure calls 0, OpenAI image calls 0, model training 0, inference 0, production
reads/writes 0, external raw image transmission 0, build/deploy 0. Repository
artifacts: the two planning modules, the test file, this note and the aggregate
JSON. Future paid generation requires explicit owner approval and is never
auto-executed.

## 8. Owner decision required next

Choose one pilot option (`SMALL` / `MEDIUM` / `LARGE`, or decline), the source
category (`OWNER_VOLUNTEER_REAL_SOURCE` with a consent authority, or
`OWNER_AUTHORIZED_SYNTHETIC_SOURCE` with its domain limitation), and provide a
verified provider price source if a cost figure is wanted. Only then can the
pilot cap be approved and generation scheduled by the owner.
