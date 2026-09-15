"""B3-L10B — FLORENCE_OCR_TWO_FEATURE_STUDY_V1 (pre-registered, analysis only).

Two features that already exist in the PR #100 shadow telemetry are combined
in the simplest monotonic 2D form:

    flagged := rawSequenceScore >= SCORE_THRESHOLD  AND  outputTokenCount <= TOKEN_CAP

Both remain uncalibrated.  rawSequenceScore: beam-search log-probability of the
whole generated OCR string (scoreSource florence_beam_sequence_score,
scoreCalibrated false), usable only when attributionScope == single_region.
outputTokenCount: UNCALIBRATED_AUXILIARY_FEATURE — the length of the top-beam
DECODER output sequence (len(generated.sequences[0])) including the decoder
start token, the forced BOS token and the EOS token; encoder/prompt tokens are
not part of it; bounded by max_new_tokens + 1.  It is a generation-length
feature, not a confidence, not a probability.

No confidence band, no calibration, no policy action is produced.  The score
thresholds are the nine B3-L10A pre-registered values reused verbatim; the
old single-score hypothesis is closed and is not refined here.  Token caps
are a coarse frozen set.  Geometry, human, family and ground-truth fields are
refused.  G1-G3 is development (its feature distributions are already known
from B3-L10A -> DEVELOPMENT_DESIGNED); G4-G5 is FEATURE_SPECIFIC_FROZEN_
VALIDATION_SPLIT_V2, admissible once only if the dual-feature exposure audit
proves neither feature's values were ever displayed or analysed.  A pass on
G4-G5 is still SUPPORTED_ON_EXISTING_FIXED_TEXT_CONSTRUCT until the
TEXT_CONSTRUCT_ROBUSTNESS_V1 challenge (new deterministic synthetic strings of
different lengths/widths) is evaluated with the rule unchanged.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import avatar_ocr_score_separability as st  # noqa: E402
import avatar_owlv2_challenge_v2 as v2  # noqa: E402
import avatar_owlv2_threshold_selection as sel  # noqa: E402

# ------------------------------------------------------------------ versions / semantics

VERSION = "FLORENCE_OCR_TWO_FEATURE_STUDY_V1"
EVIDENCE_LABEL = "G004_UNCALIBRATED_OCR_TWO_FEATURE_EVIDENCE"
DESIGNATION = "DEVELOPMENT_DESIGNED"
RULE_ROLE = "TWO_FEATURE_SEPARABILITY_RULE_V1"
VALIDATION_SPLIT_NAME = "FEATURE_SPECIFIC_FROZEN_VALIDATION_SPLIT_V2"
VALIDATION_LOCK_NAME = "ocr_two_feature_v1_validation.lock"
FROZEN_NAME = "ocr_two_feature_v1_rule_frozen.json"
VALIDATION_RESULT_NAME = "ocr_two_feature_v1_validation_result.json"
ROBUSTNESS_VERSION = "TEXT_CONSTRUCT_ROBUSTNESS_V1"
ROBUSTNESS_ROLE = "ROBUSTNESS_CHALLENGE"
FEATURES = ("rawSequenceScore", "outputTokenCount")
SCORE_FEATURE_ROLE = st.FEATURE_NAME                      # UNCALIBRATED_DISCRIMINATION_FEATURE
TOKEN_FEATURE_ROLE = "UNCALIBRATED_AUXILIARY_FEATURE"
TOKEN_COUNT_SEMANTICS = {
    "definition": "len(generated.sequences[0]) from Florence2ForConditionalGeneration.generate (top beam)",
    "side": "decoder output only; encoder/prompt tokens excluded",
    "includesSpecialTokens": ["decoder_start_token_id=2", "forced_bos_token_id=0", "eos_token_id=2"],
    "upperBound": "max_new_tokens (1024) + 1 decoder start token",
    "stability": "pinned florence-community/Florence-2-large-ft@26b734a5 generation_config (BART text backbone); semantics change with model/revision",
    "notA": ["confidence", "probability", "watermark probability", "OCR correctness probability"],
}
SCORE_DIRECTION = "positive_higher"     # frozen from B3-L10A development evidence
TOKEN_DIRECTION = "positive_shorter"    # frozen from B3-L10A development evidence (opaque 13, translucent 13-15, clean 14-54)
PRIOR_STATUS = {**st.PRIOR_STATUS, "B3_L10A": "FLORENCE_SEQUENCE_SCORE_NOT_SEPARATING", "B3_L10A_VALIDATION_EXECUTIONS": 0}
FORBIDDEN_WORDING = st.FORBIDDEN_WORDING + ("TEXT_POLICY_READY", "CONFIDENCE_CALIBRATED")
FORBIDDEN_FEATURE_INPUTS = st.FORBIDDEN_EXTRACTION_INPUTS | frozenset({"location", "areaBand", "overlayLike", "textQuality", "kind", "repeated", "artifactHint", "confidenceBand", "sourceConsistent"})

# ------------------------------------------------------------------ frozen grids

SCORE_THRESHOLDS = (-1.42351, -1.13944, -1.066554, -0.918332, -0.748467, -0.700672, -0.663906, -0.613713, -0.592678)  # B3-L10A verbatim
TOKEN_CAPS = (16, 24, 32)                # coarse; never densified after a table is seen
CLEAN_FALSE_ESCALATION_CEILING = 0.10
SENSITIVITY_FLOOR = 0.90
CRITERIA = ("A", "B", "C", "D", "E", "F")


@dataclass(frozen=True)
class Candidate:
    score_threshold: float
    token_cap: int

    def __post_init__(self) -> None:
        if self.score_threshold not in SCORE_THRESHOLDS or self.token_cap not in TOKEN_CAPS:
            raise ValueError("candidate outside the frozen grid")

    @property
    def id(self) -> str:
        return f"S{SCORE_THRESHOLDS.index(self.score_threshold) + 1}_C{self.token_cap}"

    @property
    def predicate(self) -> str:
        return f"rawSequenceScore >= {self.score_threshold} AND outputTokenCount <= {self.token_cap}"


CANDIDATES: tuple[Candidate, ...] = tuple(Candidate(s, c) for s in SCORE_THRESHOLDS for c in TOKEN_CAPS)
CANDIDATE_BY_ID = {c.id: c for c in CANDIDATES}

# ------------------------------------------------------------------ robustness constructs (frozen before inference)

ROBUSTNESS_TEXT_SPEC = {"rel_size": 0.06, "placement": "center", "anchor": (0.50, 0.62), "renderer": "avatar_owlv2_challenge_v2.render_family (PIL default font)"}
ROBUSTNESS_ALPHAS = {"opaque": (1.00, True), "translucent": (0.35, False)}   # alpha, stroke  (== F3 / F4 conventions)
ROBUSTNESS_CONSTRUCTS = (
    # code, category, text
    ("R1", "A_SHORT_ONE_WORD", "DRAFT"),
    ("R2", "B_LONG_ONE_WORD", "PLACEHOLDER"),
    ("R3", "C_TWO_WORD_PHRASE", "NOT FINAL"),
    ("R4", "D_SHORT_ALPHANUMERIC", "RX7Q2"),
    ("R5", "E_WIDE_CHARACTERS", "WWMMWW"),
    ("R6", "E_NARROW_CHARACTERS", "IIILLI"),
)
ROBUSTNESS_REQUIRED_CATEGORIES = ("A_SHORT_ONE_WORD", "B_LONG_ONE_WORD", "C_TWO_WORD_PHRASE", "D_SHORT_ALPHANUMERIC", "E_CHARACTER_WIDTHS")
ROBUSTNESS_CATEGORY_OF = {"E_WIDE_CHARACTERS": "E_CHARACTER_WIDTHS", "E_NARROW_CHARACTERS": "E_CHARACTER_WIDTHS"}
ROBUSTNESS_GROUPS = sel.HOLDOUT_GROUPS   # bases: the 8 G4-G5 avatars (rule already frozen; no selection happens here)
ROBUSTNESS_OVERALL_FLOOR = 0.90
ROBUSTNESS_CATEGORY_FLOOR = 0.80
ROBUSTNESS_ALPHA_FLOOR = 0.90


def robustness_specs() -> list[v2.FamilySpec]:
    specs = []
    for code, category, text in ROBUSTNESS_CONSTRUCTS:
        if not v2.no_real_trademark(text):
            raise ValueError("real trademark string in robustness construct")
        for alpha_name, (alpha, stroke) in ROBUSTNESS_ALPHAS.items():
            specs.append(v2.FamilySpec(f"{code}{'O' if alpha_name == 'opaque' else 'T'}", f"{category}:{alpha_name}", "text", text, alpha,
                                       ROBUSTNESS_TEXT_SPEC["rel_size"], ROBUSTNESS_TEXT_SPEC["placement"], ROBUSTNESS_TEXT_SPEC["anchor"], stroke=stroke))
    return specs


def contract_digest() -> str:
    payload = {"version": VERSION, "evidence": EVIDENCE_LABEL, "features": list(FEATURES), "rule": "score >= S AND tokens <= C",
               "scoreDirection": SCORE_DIRECTION, "tokenDirection": TOKEN_DIRECTION, "scoreThresholds": list(SCORE_THRESHOLDS), "tokenCaps": list(TOKEN_CAPS),
               "tokenSemantics": TOKEN_COUNT_SEMANTICS, "criteria": {"A": CLEAN_FALSE_ESCALATION_CEILING, "B": SENSITIVITY_FLOOR, "C": SENSITIVITY_FLOOR, "D": 1.0, "E": False, "F": 0},
               "selection": "min clean FE -> max min(opaque,translucent) -> larger cap -> lower score threshold",
               "split": {"development": list(sel.DEVELOPMENT_GROUPS), "validation": list(sel.HOLDOUT_GROUPS), "validationName": VALIDATION_SPLIT_NAME},
               "robustness": {"version": ROBUSTNESS_VERSION, "constructs": [list(c) for c in ROBUSTNESS_CONSTRUCTS], "alphas": {k: list(v) for k, v in ROBUSTNESS_ALPHAS.items()},
                              "spec": {k: (list(v) if isinstance(v, tuple) else v) for k, v in ROBUSTNESS_TEXT_SPEC.items()}, "groups": list(ROBUSTNESS_GROUPS),
                              "floors": {"overall": ROBUSTNESS_OVERALL_FLOOR, "category": ROBUSTNESS_CATEGORY_FLOOR, "alpha": ROBUSTNESS_ALPHA_FLOOR}},
               "forbiddenFeatureInputs": sorted(FORBIDDEN_FEATURE_INPUTS)}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


# ------------------------------------------------------------------ features


def features(shadow: Mapping[str, Any], **runtime_inputs: Any) -> tuple[float, int]:
    """(rawSequenceScore, outputTokenCount) from a usable single-region shadow record; nothing else is a feature."""

    leaked = FORBIDDEN_FEATURE_INPUTS & set(runtime_inputs)
    if leaked:
        raise ValueError(f"not a feature input: {sorted(leaked)}")
    extra = set(runtime_inputs) - set()
    if extra:
        raise ValueError(f"only {FEATURES} are features; refused: {sorted(extra)}")
    score = st.score_of(shadow)   # raises for whole_sequence / unavailable / calibrated
    tokens = shadow.get("outputTokenCount")
    if not isinstance(tokens, int) or isinstance(tokens, bool) or tokens < 1:
        raise ValueError("outputTokenCount missing")
    return score, tokens


def flagged(score: float, tokens: int, candidate: Candidate) -> bool:
    return score >= candidate.score_threshold and tokens <= candidate.token_cap


def watermark_action_with_features(canonical_action: str, score: float, tokens: int, candidate: Candidate) -> str:
    """Decision-neutral by construction: the canonical action is returned unchanged."""

    del score, tokens, candidate
    if canonical_action not in ("allow", "review", "reject"):
        raise ValueError("unknown canonical action")
    return canonical_action


# ------------------------------------------------------------------ metrics / gate / selection


def _rate(k: int, n: int) -> Optional[float]:
    return round(k / n, 4) if n else None


def candidate_metrics(candidate: Candidate, clean: Sequence[tuple], opaque: Sequence[tuple], translucent: Sequence[tuple]) -> dict[str, Any]:
    cfp = sum(1 for s, t in clean if flagged(s, t, candidate))
    op = sum(1 for s, t in opaque if flagged(s, t, candidate))
    tr = sum(1 for s, t in translucent if flagged(s, t, candidate))
    n_pos = len(opaque) + len(translucent)
    clean_rate, op_rate, tr_rate, comb = _rate(cfp, len(clean)), _rate(op, len(opaque)), _rate(tr, len(translucent)), _rate(op + tr, n_pos)
    bal = round(((1 - clean_rate) + comb) / 2, 4) if clean_rate is not None and comb is not None else None
    return {"candidate": candidate.id, "scoreThreshold": candidate.score_threshold, "tokenCap": candidate.token_cap, "predicate": candidate.predicate,
            "cleanFalseEscalationProxy": {"k": cfp, "n": len(clean), "rate": clean_rate}, "opaqueSensitivity": {"k": op, "n": len(opaque), "rate": op_rate},
            "translucentSensitivity": {"k": tr, "n": len(translucent), "rate": tr_rate}, "combinedSensitivity": {"k": op + tr, "n": n_pos, "rate": comb},
            "balancedAccuracy": bal}


def eligible(metrics: Mapping[str, Any], *, coverage_rate: float, calibrated_flags: set, decision_diff: int) -> dict[str, Any]:
    return st.eligible(metrics, coverage_rate=coverage_rate, calibrated_flags=calibrated_flags, decision_diff=decision_diff)


def select_candidate(development_table: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Development table only; validation and robustness rows are never inputs."""

    elig = [t for t in development_table if t["eligibility"]["eligible"]]
    if not elig:
        return {"status": "NONE", "selectedCandidate": None, "reason": "no candidate satisfies A-F on development"}
    best = sorted(elig, key=lambda t: (t["cleanFalseEscalationProxy"]["rate"],
                                       -min(t["opaqueSensitivity"]["rate"], t["translucentSensitivity"]["rate"]),
                                       -t["tokenCap"], t["scoreThreshold"]))[0]
    return {"status": "SELECTED", "selectedCandidate": best["candidate"], "scoreThreshold": best["scoreThreshold"], "tokenCap": best["tokenCap"],
            "predicate": best["predicate"], "role": RULE_ROLE,
            "reason": "lowest clean false-escalation -> highest min(opaque, translucent) -> less restrictive token cap -> more permissive score boundary"}


# ------------------------------------------------------------------ freeze / validation / robustness guards


class RuleNotFrozen(RuntimeError):
    pass


class RetuningRefused(RuntimeError):
    pass


def frozen_path(private_dir: Path) -> Path:
    return Path(private_dir) / FROZEN_NAME


def write_frozen(private_dir: Path, selection: Mapping[str, Any], digest: str, dev_inputs_digest: str) -> Path:
    path = frozen_path(private_dir)
    path.write_text(json.dumps({"version": VERSION, "role": RULE_ROLE, "contractDigest": digest, "developmentInputsDigest": dev_inputs_digest,
                                "selectedCandidate": selection["selectedCandidate"], "scoreThreshold": selection["scoreThreshold"], "tokenCap": selection["tokenCap"],
                                "notPolicyRule": True, "notConfidenceRule": True, "frozenAt": datetime.now(timezone.utc).isoformat()}, indent=2), encoding="utf-8")
    return path


def require_frozen(private_dir: Path, digest: str) -> Mapping[str, Any]:
    path = frozen_path(private_dir)
    if not path.exists():
        raise RuleNotFrozen("requires a frozen two-feature rule")
    record = json.loads(path.read_text(encoding="utf-8"))
    if record.get("contractDigest") != digest or record.get("version") != VERSION or record.get("selectedCandidate") not in CANDIDATE_BY_ID:
        raise RuleNotFrozen("frozen record does not match the study contract")
    return record


def frozen_candidate(record: Mapping[str, Any]) -> Candidate:
    cand = CANDIDATE_BY_ID[record["selectedCandidate"]]
    if cand.score_threshold != record.get("scoreThreshold") or cand.token_cap != record.get("tokenCap"):
        raise RetuningRefused("frozen rule parameters were altered")
    return cand


def validation_guard(private_dir: Path, digest: str, exposure_audit: Mapping[str, Any]) -> Path:
    require_frozen(private_dir, digest)
    if exposure_audit.get("validationScoreValuesPreviouslySeen") is not False or exposure_audit.get("validationTokenCountValuesPreviouslySeen") is not False:
        raise st.ValidationScoresPreviouslySeen("dual-feature exposure audit not clean: BLOCKED_NEW_HELDOUT_REQUIRED")
    lock = Path(private_dir) / VALIDATION_LOCK_NAME
    if lock.exists():
        raise sel.HoldoutAlreadyEvaluated(f"two-feature validation already evaluated once: {lock.name}")
    return lock


def mark_validation_evaluated(lock: Path, digest: str) -> None:
    lock.write_text(json.dumps({"version": VERSION, "contractDigest": digest, "evaluatedAt": datetime.now(timezone.utc).isoformat()}), encoding="utf-8")


def write_validation_result(private_dir: Path, digest: str, passed: bool) -> Path:
    path = Path(private_dir) / VALIDATION_RESULT_NAME
    path.write_text(json.dumps({"version": VERSION, "contractDigest": digest, "validationPassed": bool(passed)}), encoding="utf-8")
    return path


def require_validation_pass(private_dir: Path, digest: str) -> None:
    path = Path(private_dir) / VALIDATION_RESULT_NAME
    if not path.exists():
        raise RuleNotFrozen("robustness requires the feature-specific validation to have run")
    record = json.loads(path.read_text(encoding="utf-8"))
    if record.get("contractDigest") != digest or record.get("validationPassed") is not True:
        raise RuleNotFrozen("robustness requires a validation PASS under this contract")


# ------------------------------------------------------------------ robustness metrics


def robustness_metrics(candidate: Candidate, rows: Sequence[Mapping[str, Any]], *, frozen: Mapping[str, Any], calibrated_flags: set, decision_diff: int) -> dict[str, Any]:
    """rows: [{category, alphaName, score, tokens}] — rule is applied, never tuned."""

    if frozen_candidate(frozen) != candidate:
        raise RetuningRefused("robustness must use the frozen rule")
    hits = [(r, flagged(r["score"], r["tokens"], candidate)) for r in rows]
    by_cat: dict[str, Counter] = {}
    by_alpha: dict[str, Counter] = {}
    for r, h in hits:
        cat = ROBUSTNESS_CATEGORY_OF.get(r["category"], r["category"])
        by_cat.setdefault(cat, Counter())["n"] += 1
        by_cat[cat]["k"] += int(h)
        by_alpha.setdefault(r["alphaName"], Counter())["n"] += 1
        by_alpha[r["alphaName"]]["k"] += int(h)
    overall = {"k": sum(h for _, h in hits), "n": len(hits), "rate": _rate(sum(h for _, h in hits), len(hits))}
    cats = {c: {"k": v["k"], "n": v["n"], "rate": _rate(v["k"], v["n"])} for c, v in sorted(by_cat.items())}
    alphas = {a: {"k": v["k"], "n": v["n"], "rate": _rate(v["k"], v["n"])} for a, v in sorted(by_alpha.items())}
    checks = {
        "A": overall["rate"] is not None and overall["rate"] >= ROBUSTNESS_OVERALL_FLOOR,
        "B": all(c in cats and cats[c]["rate"] is not None and cats[c]["rate"] >= ROBUSTNESS_CATEGORY_FLOOR for c in ROBUSTNESS_REQUIRED_CATEGORIES),
        "C": "opaque" in alphas and alphas["opaque"]["rate"] is not None and alphas["opaque"]["rate"] >= ROBUSTNESS_ALPHA_FLOOR,
        "D": "translucent" in alphas and alphas["translucent"]["rate"] is not None and alphas["translucent"]["rate"] >= ROBUSTNESS_ALPHA_FLOOR,
        "E": True,                      # frozen_candidate() above raised otherwise
        "F": calibrated_flags == {False},
        "G": decision_diff == 0,
    }
    return {"version": ROBUSTNESS_VERSION, "role": ROBUSTNESS_ROLE, "rule": candidate.predicate, "overall": overall, "categories": cats, "alphas": alphas,
            "criteria": checks, "passed": all(checks.values()), "failed": [k for k, v in checks.items() if not v]}


# ------------------------------------------------------------------ verdicts


def verdict(dev_selected: bool, validation_allowed: Optional[bool], validation_pass: Optional[bool], robustness_pass: Optional[bool]) -> str:
    if not dev_selected:
        return "FLORENCE_TWO_FEATURE_NOT_SEPARATING"
    if validation_allowed is False:
        return "BLOCKED_NEW_HELDOUT_REQUIRED"
    if validation_pass is None:
        return "FLORENCE_TWO_FEATURE_DEVELOPMENT_SELECTED_VALIDATION_PENDING"
    if not validation_pass:
        return "FLORENCE_TWO_FEATURE_VALIDATION_FAILED"
    if robustness_pass is None:
        return "FLORENCE_TWO_FEATURE_SUPPORTED_ON_EXISTING_FIXED_TEXT_CONSTRUCT"
    if not robustness_pass:
        return "FLORENCE_TWO_FEATURE_CONSTRUCT_OVERFIT"
    return "FLORENCE_TWO_FEATURE_SEPARABILITY_ROBUSTNESS_SUPPORTED"


def definitions() -> dict[str, Any]:
    return {"candidates": [dict(asdict(c), id=c.id, predicate=c.predicate) for c in CANDIDATES], "scoreThresholds": list(SCORE_THRESHOLDS), "tokenCaps": list(TOKEN_CAPS),
            "robustnessConstructs": [{"code": c, "category": k, "textLength": len(t), "wordCount": len(t.split())} for c, k, t in ROBUSTNESS_CONSTRUCTS]}
