# B3-L10B — two-feature OCR score/length separability, feature-specific validation, construct robustness

Offline, analysis only. **0 Florence inferences**, 0 OWLv2, 0 external calls,
no policy / confidence-band / calibration / worker / env / build / deploy
change. Aggregate only. Contract digest `390251927491…` frozen in
[b3-l10b-preregistration.md](b3-l10b-preregistration.md) before any
two-feature metric and before any G4–G5 feature value was read. Designation
**`DEVELOPMENT_DESIGNED`**.

**Verdict: `FLORENCE_TWO_FEATURE_NOT_SEPARATING`** · validation executed **0**
(G4–G5 score and token-count values remain unseen) · robustness **not
executed** · confidenceBand changed **NO** · calibration performed **NO** ·
decision diff **0** · `TEXT_POLICY_GAP` unresolved ·
`GRAPHICAL_DETECTOR_STUDY_REQUIRED` · `NATURAL_POSITIVE_EVIDENCE_MISSING`.

## 1. The finding in one sentence

Adding `outputTokenCount` to the frozen score thresholds does not create a
separating rule: the cap only removes clean rows that the score already
separates at higher thresholds, while the rows that actually overlap — two
clean avatars whose single OCR region is both short (≤ 16 tokens) and
high-scoring, and three translucent watermarks that score below −0.918 —
look the same on both features, so every one of the 27 frozen candidates
fails criterion A or C on development and the validation split was never
opened.

## 2. Feature semantics (fresh audit)

* `rawSequenceScore` — `UNCALIBRATED_DISCRIMINATION_FEATURE`; beam log-prob
  of the whole generated string; `scoreSource = florence_beam_sequence_score`,
  `scoreCalibrated = false`; single-region rows only.
* `outputTokenCount` — `UNCALIBRATED_AUXILIARY_FEATURE`;
  `len(generated.sequences[0])`, the top beam's **decoder** output length
  including decoder start (2), forced BOS (0) and EOS (2); prompt/encoder
  tokens excluded; ≤ `max_new_tokens + 1`; bound to the pinned
  `florence-community/Florence-2-large-ft@26b734a5` generation config. Not
  confidence, not probability.

Directions frozen from B3-L10A development evidence: score `positive_higher`,
tokens `positive_shorter`. Rule form `score ≥ S AND tokens ≤ C` only.

## 3. Exposure audit and admissibility

G4–G5 `rawSequenceScore` and `outputTokenCount` values: never displayed,
aggregated or analysed by any script, report, stdout, PR body or memory note
(B3-L10A evaluated development only; B3-L9 printed typed geometry only).
Values inside raw restricted captures are not "seen". The split was therefore
admissible as `FEATURE_SPECIFIC_FROZEN_VALIDATION_SPLIT_V2`; it was **not
opened** because no development candidate was eligible, so both feature
values remain unseen for any future study.

## 4. Development table (G1–G3: 12 clean / 12 opaque / 12 translucent; coverage 100 %, `scoreCalibrated=false`, decision diff 0)

| S (B3-L10A verbatim) | C = 16: clean · opaque · translucent | C = 24 | C = 32 | A–F |
|---|---|---|---|---|
| −1.4235 | **2** · 12 · 12 | 4 · 12 · 12 | 6 · 12 · 12 | ✗ A |
| −1.1394 | **2** · 12 · 12 | 3 · 12 · 12 | 4 · 12 · 12 | ✗ A |
| −1.0666 | **2** · 12 · 11 | 2 · 12 · 11 | 2 · 12 · 11 | ✗ A |
| −0.9183 | 0 · 12 · **9** | 0 · 12 · 9 | 0 · 12 · 9 | ✗ C |
| −0.7485 | 0 · 12 · 6 | 0 · 12 · 6 | 0 · 12 · 6 | ✗ C |
| −0.7007 | 0 · 11 · 4 | 0 · 11 · 4 | 0 · 11 · 4 | ✗ C |
| −0.6639 … −0.5927 | 0 · ≤ 10 · ≤ 1 | same | same | ✗ B C |

(Cells list clean false-escalations / 12, opaque hits / 12, translucent hits / 12.)

* The cap changes only the clean side and only at the two lowest thresholds
  (8→2 and 5→2 at C = 16); it never changes a positive count because every
  controlled positive is 13–15 tokens.
* The two clean rows that survive every cap at S ≤ −1.0666 carry a single
  short region with a positive-like score — exactly the profile of the
  injected word. The three translucent rows missed at S ≥ −0.9183 are short
  too; the cap cannot recover them.
* **Selected candidate: NONE** → `FLORENCE_TWO_FEATURE_NOT_SEPARATING`. No
  freeze record, no validation lock, no robustness inference. No cap was
  added and no threshold refined.

## 5. Robustness stage

Pre-registered (`TEXT_CONSTRUCT_ROBUSTNESS_V1`: 6 new synthetic strings ×
opaque/translucent × 8 bases, real-trademark blocklist, rule unchanged) but
**not executed**: the contract permits it only after a validation pass. The
overfit concern it was designed to test — that a short-token cap learns the
fixed synthetic word length — remains a live caveat for any future
length-based feature and is one more reason not to revisit the cap.

## 6. What is and is not established

* Established (controlled, 36 development rows): the length feature does not
  add separation where the single score fails; the residual overlap is on
  rows where both features agree.
* Not established: anything about calibration, confidence bands, policy
  actions, natural watermarks, or the graphical channel.

## 7. Verdicts

`FLORENCE_TWO_FEATURE_NOT_SEPARATING` · validation 0 · robustness not run ·
`TEXT_POLICY_GAP` unresolved · `GRAPHICAL_DETECTOR_STUDY_REQUIRED` ·
`NATURAL_POSITIVE_EVIDENCE_MISSING`.

## 8. Exact next step (owner decision; none taken here)

The two shadow-telemetry features are exhausted as a monotonic rule on this
corpus: the single score (B3-L10A) and score + length (this study) both leave
the same clean/translucent overlap. The remaining honest options are (1)
close the Florence-telemetry text path and treat `TEXT_POLICY_GAP` as
requiring a different signal source — the detector study already required
for the graphical gap could be scoped to cover text watermarks on new
held-out constructs; or (2) an evidence study on whether the translucent
overlap is a rendering-alpha artefact of the synthetic construct (natural
watermarks are not necessarily 35 % alpha) — descriptive only, no rule. No
confidence band is implied by either. `approveAvatarCandidate` deployment
remains a separate release blocker.

## 9. Safety

Florence 0 · OWLv2 0 · Azure/external 0 · production writes 0 · builds/deploys
0 · live decision diff 0 · originals **28/28** unchanged · all prior locks
untouched · Rater C artifacts untouched.
