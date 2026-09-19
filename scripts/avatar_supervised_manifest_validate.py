"""B3-L17A — private manifest validator (aggregate-only output; the raw manifest is never committed).

Checks schema, forbidden identifiers, region boxes, provenance/partition rules,
group disjointness across partitions, exact and near duplicates across
partitions, and derives aggregate counts (images, groups, regions per class,
uncertainty rate, natural-positive independent groups per stratum, clean
independent groups).  No model, no score, no training.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import avatar_supervised_dataset_contract as sc  # noqa: E402


def _rate(k, n):
    return round(k / n, 4) if n else None


def aggregate(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    per_class: Counter = Counter()
    per_partition_images: Counter = Counter()
    per_partition_groups: dict[str, set] = defaultdict(set)
    per_provenance: Counter = Counter()
    natural_groups: dict[str, set] = defaultdict(set)
    clean_groups: set = set()
    synthetic_positive_images = 0
    uncertain_images = 0
    eligible = 0
    for r in records:
        regions = r.get("regions", [])
        for g in regions:
            per_class[g.get("class")] += 1
        per_partition_images[r.get("split")] += 1
        per_partition_groups[r.get("split")].add(r["groupId"])
        per_provenance[r.get("provenanceClass")] += 1
        uncertain = any(g.get("class") == "UNCERTAIN" or g.get("annotationStatus") == "uncertain" for g in regions)
        uncertain_images += int(uncertain)
        eligible += int(sc.primary_training_eligible(r))
        relevant = [g for g in regions if g.get("class") in sc.RELEVANT_CLASSES]
        if r.get("originKind") == "NATURAL_GENERATED_OUTPUT":
            for g in relevant:
                natural_groups[g["class"]].add(r["groupId"])
            if not relevant and not uncertain:
                clean_groups.add(r["groupId"])
        elif relevant:
            synthetic_positive_images += 1
    n = len(records)
    return {"images": n, "groups": len({r["groupId"] for r in records}), "regionsTotal": sum(len(r.get("regions", [])) for r in records), "regionsByClass": dict(per_class),
            "imagesByPartition": dict(per_partition_images), "groupsByPartition": {k: len(v) for k, v in per_partition_groups.items()}, "imagesByProvenance": dict(per_provenance),
            "uncertaintyRate": _rate(uncertain_images, n), "primaryTrainingEligibleImages": eligible,
            "naturalPositiveIndependentGroups": {c: len(natural_groups.get(c, set())) for c in sc.RELEVANT_CLASSES}, "cleanNaturalIndependentGroups": len(clean_groups),
            "cleanNaturalUncontaminatedGroups": len({r["groupId"] for r in records if r["groupId"] in clean_groups and r.get("provenanceClass") != "LEGACY_DEVELOPMENT_CONTAMINATED"}),
            "syntheticPositiveImages": synthetic_positive_images, "statisticalUnit": sc.STATISTICAL_UNIT}


def validate_manifest(manifest: Mapping[str, Any], allow_transcription: bool = False) -> dict[str, Any]:
    errors: list[str] = []
    if manifest.get("datasetVersion") != sc.VERSION:
        errors.append(f"datasetVersion must be {sc.VERSION}")
    records = manifest.get("images", [])
    for r in records:
        errors += [f"{r.get('opaqueImageId', '?')}: {e}" for e in sc.validate_image_record(r, allow_transcription)]
    ids = [r.get("opaqueImageId") for r in records]
    if len(ids) != len(set(ids)):
        errors.append("duplicate opaqueImageId")
    partitions_by_group: dict[str, set] = defaultdict(set)
    for r in records:
        partitions_by_group[r.get("groupId")].add(r.get("split"))
    for gid, parts in partitions_by_group.items():
        if len(parts) > 1:
            errors.append(f"group {gid} spans partitions {sorted(parts)}")
    valid = [r for r in records if not sc.validate_image_record(r, allow_transcription)]
    for i, a in enumerate(valid):
        for b in valid[i + 1:]:
            if a["split"] == b["split"]:
                continue
            if a["sha256"] == b["sha256"]:
                errors.append(f"exact duplicate sha256 across partitions: {a['opaqueImageId']} / {b['opaqueImageId']}")
            elif sc.hamming(a["perceptualHash"], b["perceptualHash"]) <= sc.DUPLICATE_POLICY["hammingThreshold"]:
                errors.append(f"near duplicate (pHash Hamming <= {sc.DUPLICATE_POLICY['hammingThreshold']}) across partitions: {a['opaqueImageId']} / {b['opaqueImageId']}")
    return {"errors": errors, "aggregate": aggregate(records), "datasetVersion": sc.VERSION, "annotationSchemaVersion": sc.ANNOTATION_SCHEMA_VERSION}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True, help="private manifest JSON (never committed)")
    parser.add_argument("--allow-transcription", action="store_true")
    parser.add_argument("--out", type=Path, help="aggregate-only output")
    args = parser.parse_args(argv)
    result = validate_manifest(json.loads(args.manifest.read_text(encoding="utf-8")), args.allow_transcription)
    report = {"datasetVersion": result["datasetVersion"], "errorCount": len(result["errors"]), "errors": result["errors"][:50], "aggregate": result["aggregate"], "contractDigestPrefix": sc.contract_digest()[:12]}
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if not result["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
