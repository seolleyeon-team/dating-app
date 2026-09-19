"""B3-L17A — deterministic, group-disjoint, class-aware split planner (no model, no manual override).

Input groups: [{groupId, provenanceClass, stratum, imageCount}].  Legacy
contaminated groups can never reach SEALED_TEST.  Assignment is reproducible
from the frozen seed and independent of input order.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

import sys

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import avatar_supervised_dataset_contract as sc  # noqa: E402

PARTITIONS = sc.PARTITIONS
PARTITION_FRACTIONS = dict(sc.PARTITION_FRACTIONS)
SEED = sc.SEED


def _order_key(group_id: str) -> str:
    return hashlib.sha256(f"{SEED}:{group_id}".encode("utf-8")).hexdigest()


def _assign(n: int, index: int, fractions: Mapping[str, float]) -> str:
    position = (index + 0.5) / n
    cumulative = 0.0
    for partition in PARTITIONS:
        if partition not in fractions:
            continue
        cumulative += fractions[partition]
        if position <= cumulative + 1e-12:
            return partition
    return [p for p in PARTITIONS if p in fractions][-1]


def plan_split(groups: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    """groupId -> partition. Deterministic per (stratum, provenance pool); no override parameter exists."""

    seen = set()
    for g in groups:
        if sc.validate_group_id(g["groupId"]):
            raise ValueError(f"opaque groupId required: {g['groupId']}")
        if g["groupId"] in seen:
            raise ValueError(f"duplicate groupId: {g['groupId']}")
        seen.add(g["groupId"])
        if not sc.allowed_partitions(g["provenanceClass"]):
            raise ValueError(f"{g['provenanceClass']} is not model data: {g['groupId']}")
    pools: dict[tuple, list] = defaultdict(list)
    for g in groups:
        pools[(g.get("stratum", "UNSTRATIFIED"), sc.allowed_partitions(g["provenanceClass"]))].append(g["groupId"])
    out: dict[str, str] = {}
    for (stratum, allowed), ids in pools.items():
        total = sum(PARTITION_FRACTIONS[p] for p in allowed)
        fractions = {p: PARTITION_FRACTIONS[p] / total for p in allowed}
        ordered = sorted(ids, key=_order_key)
        for i, gid in enumerate(ordered):
            out[gid] = _assign(len(ordered), i, fractions)
    return out


def verify(plan: Mapping[str, str], groups: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_id = {g["groupId"]: g for g in groups}
    per: dict[str, Counter] = defaultdict(Counter)
    problems = []
    for gid, partition in plan.items():
        g = by_id.get(gid)
        if g is None:
            problems.append(f"unknown group {gid}")
            continue
        if partition not in sc.allowed_partitions(g["provenanceClass"]):
            problems.append(f"{gid}: {g['provenanceClass']} assigned to {partition}")
        per[g.get("stratum", "UNSTRATIFIED")][partition] += 1
    missing = [g["groupId"] for g in groups if g["groupId"] not in plan]
    reproducible = plan_split(groups) == dict(plan)
    return {"groupDisjoint": not problems and not missing and len(plan) == len(set(plan)), "reproducible": reproducible, "problems": problems, "missing": missing,
            "perStratumPartitionCounts": {s: dict(c) for s, c in per.items()}, "partitionCounts": dict(Counter(plan.values()))}


def split_plan_digest() -> str:
    return sc.split_plan_digest()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--groups", type=Path, required=True, help="private JSON list of {groupId, provenanceClass, stratum, imageCount}")
    parser.add_argument("--out", type=Path, help="private assignment output (never committed)")
    args = parser.parse_args(argv)
    groups = json.loads(args.groups.read_text(encoding="utf-8"))
    plan = plan_split(groups)
    v = verify(plan, groups)
    if args.out:
        args.out.write_text(json.dumps({"datasetVersion": sc.VERSION, "splitPlanDigest": split_plan_digest(), "assignments": plan}, indent=2), encoding="utf-8")
    print(json.dumps({"datasetVersion": sc.VERSION, "splitPlanDigestPrefix": split_plan_digest()[:12], "verify": {k: v[k] for k in ("groupDisjoint", "reproducible", "partitionCounts", "perStratumPartitionCounts")}}, indent=2))
    return 0 if v["groupDisjoint"] and v["reproducible"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
