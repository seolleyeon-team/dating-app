"""B3-L17A.1 — deterministic, group-disjoint, multi-label-aware split planner (no model, no manual override).

Input groups: [{groupId, provenanceClass, evaluationStrata: sorted list, imageCount, lineageReservation?}]
(`stratum: str` is accepted as a one-element shorthand).  A group is one
statistical unit: it is assigned to exactly one partition once, and every
class it carries is credited to that partition's quota for that class.  A
group is never duplicated into two rows.  Legacy contaminated groups can never
reach SEALED_TEST; SEALED_RESERVED lineages can only reach SEALED_TEST.

Frozen algorithm (SUPERVISED_WATERMARK_LOGO_DATASET_V1_1, see
avatar_supervised_dataset_contract.SPLIT_ALGORITHM):
  1. validate opaque ids, reject duplicate groupIds and unknown labels;
  2. pool = allowed partitions (provenance class + lineage reservation);
  3. per (label, pool): integer quotas per partition by largest remainder on
     the renormalised frozen fractions (remainder ties: SEALED_TEST >
     VALIDATION > TRAIN_DEVELOPMENT);
  4. visit groups in sha256(SEED + groupId) order (input-order invariant);
  5. assign each group to the allowed partition with the largest total
     remaining deficit over the group's labels; ties broken by
     sha256(SEED + groupId + partition).
No score, no override, no per-image assignment exists.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import avatar_supervised_dataset_contract as sc  # noqa: E402

PARTITIONS = sc.PARTITIONS
PARTITION_FRACTIONS = dict(sc.PARTITION_FRACTIONS)
SEED = sc.SEED
REMAINDER_TIE_BREAK = ("SEALED_TEST", "VALIDATION", "TRAIN_DEVELOPMENT")
UNSTRATIFIED = "UNSTRATIFIED"


def _order_key(group_id: str) -> str:
    return hashlib.sha256(f"{SEED}:{group_id}".encode("utf-8")).hexdigest()


def _tie_key(group_id: str, partition: str) -> str:
    return hashlib.sha256(f"{SEED}:{group_id}:{partition}".encode("utf-8")).hexdigest()


def integer_quotas(n: int, fractions: Mapping[str, float]) -> dict[str, int]:
    """Largest-remainder apportionment of n groups over the given partition fractions (must sum to 1)."""

    if n < 0:
        raise ValueError("n must be >= 0")
    if abs(sum(fractions.values()) - 1.0) > 1e-9:
        raise ValueError("fractions must sum to 1")
    raw = {p: n * f for p, f in fractions.items()}
    quotas = {p: int(raw[p] // 1) for p in fractions}
    remaining = n - sum(quotas.values())
    order = sorted(fractions, key=lambda p: (-round(raw[p] - quotas[p], 9), REMAINDER_TIE_BREAK.index(p)))
    for p in order[:remaining]:
        quotas[p] += 1
    return quotas


def group_labels(group: Mapping[str, Any]) -> list[str]:
    if "evaluationStrata" in group:
        labels = list(group["evaluationStrata"])
    elif "stratum" in group:
        labels = [group["stratum"]]
    else:
        labels = []
    if not isinstance(labels, list) or len(set(labels)) != len(labels):
        raise ValueError(f"evaluationStrata must be a list without repeats: {group.get('groupId')}")
    for label in labels:
        if label not in sc.SPLIT_LABELS:
            raise ValueError(f"unknown evaluation stratum {label!r} for {group.get('groupId')} (allowed: {sc.SPLIT_LABELS})")
    return sorted(labels) or [UNSTRATIFIED]


def plan_split(groups: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    """groupId -> partition. Deterministic; one partition per group; no override parameter exists."""

    seen: set[str] = set()
    pools: dict[tuple, list] = defaultdict(list)
    labels_by_id: dict[str, list[str]] = {}
    for g in groups:
        if sc.validate_group_id(g["groupId"]):
            raise ValueError(f"opaque groupId required: {g['groupId']}")
        if g["groupId"] in seen:
            raise ValueError(f"duplicate groupId: {g['groupId']} (a group is one statistical unit and appears in exactly one row)")
        seen.add(g["groupId"])
        allowed = sc.group_allowed_partitions(g)
        if not allowed:
            raise ValueError(f"{g['provenanceClass']} is not model data: {g['groupId']}")
        labels_by_id[g["groupId"]] = group_labels(g)
        pools[allowed].append(g["groupId"])
    out: dict[str, str] = {}
    for allowed, ids in pools.items():
        total = sum(PARTITION_FRACTIONS[p] for p in allowed)
        fractions = {p: PARTITION_FRACTIONS[p] / total for p in allowed}
        label_n: Counter = Counter(label for gid in ids for label in labels_by_id[gid])
        quotas = {label: integer_quotas(n, fractions) for label, n in label_n.items()}
        counts: dict[str, Counter] = {label: Counter() for label in label_n}
        for gid in sorted(ids, key=_order_key):
            labels = labels_by_id[gid]
            best = max(allowed, key=lambda p: (sum(quotas[label][p] - counts[label][p] for label in labels), -int(_tie_key(gid, p), 16)))
            out[gid] = best
            for label in labels:
                counts[label][best] += 1
    return out


def verify(plan: Mapping[str, str], groups: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_id = {g["groupId"]: g for g in groups}
    per: dict[str, Counter] = defaultdict(Counter)
    problems = []
    multi = 0
    for gid, partition in plan.items():
        g = by_id.get(gid)
        if g is None:
            problems.append(f"unknown group {gid}")
            continue
        if partition not in sc.group_allowed_partitions(g):
            problems.append(f"{gid}: {g['provenanceClass']} assigned to {partition}")
        labels = group_labels(g)
        multi += int(len(labels) > 1)
        for label in labels:
            per[label][partition] += 1
    missing = [g["groupId"] for g in groups if g["groupId"] not in plan]
    reproducible = plan_split(groups) == dict(plan)
    per_label = {s: dict(c) for s, c in per.items()}
    return {"groupDisjoint": not problems and not missing and len(plan) == len(set(plan)), "reproducible": reproducible, "problems": problems, "missing": missing,
            "perLabelPartitionCounts": per_label, "perStratumPartitionCounts": per_label, "partitionCounts": dict(Counter(plan.values())), "multiLabelGroups": multi,
            "independentGroups": len(plan), "statisticalUnit": sc.STATISTICAL_UNIT}


def split_plan_digest() -> str:
    return sc.split_plan_digest()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--groups", type=Path, required=True, help="private JSON list of {groupId, provenanceClass, evaluationStrata, imageCount, lineageReservation?}")
    parser.add_argument("--out", type=Path, help="private assignment output (never committed)")
    args = parser.parse_args(argv)
    groups = json.loads(args.groups.read_text(encoding="utf-8"))
    plan = plan_split(groups)
    v = verify(plan, groups)
    if args.out:
        args.out.write_text(json.dumps({"datasetVersion": sc.VERSION, "splitPlanDigest": split_plan_digest(), "assignments": plan}, indent=2), encoding="utf-8")
    print(json.dumps({"datasetVersion": sc.VERSION, "splitPlanDigestPrefix": split_plan_digest()[:12],
                      "verify": {k: v[k] for k in ("groupDisjoint", "reproducible", "partitionCounts", "perLabelPartitionCounts", "multiLabelGroups", "independentGroups")}}, indent=2))
    return 0 if v["groupDisjoint"] and v["reproducible"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
