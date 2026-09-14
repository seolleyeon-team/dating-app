"""B3-L7 - capture raw OWLv2 detections on the V2 challenge derivatives, once, at the floor.

LOCAL ONLY, never in CI. For every authorized generated avatar and every V2
family that is not reused from the existing capture, renders the derivative in
memory and stores every detection above FLOOR_SCORE. Threshold sweeps are then
filtering, never re-inference. F1 (GRAPHIC_SYMBOL) rows are copied from the
existing B3-L6 capture (variant V8: the same construct at the same spec).

Originals are opened read-only and fingerprinted before and after. Raw rows stay
in the restricted directory (they carry boxes/scores for real user-derived
images); only aggregates leave it.

  python scripts/avatar_owlv2_challenge_capture.py --private-dir <b3l4-eval> --models-dir <dir> \
      --existing-capture <owlv2_raw_capture.json> --out <b3l7-eval/challenge_capture.json>
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import avatar_florence_ceiling as bench  # noqa: E402
import avatar_logo_detector_benchmark as logo  # noqa: E402
import avatar_owlv2_challenge_v2 as v2  # noqa: E402

CAPTURE_VERSION = "avatar_owlv2_challenge_capture_v1"
DETECTOR = "owlv2-base-patch16-ensemble"


def run(private_dir: Path, models_dir: Path, existing_capture: Path, out: Path, only_codes: set[str] | None) -> dict:
    import psutil
    from PIL import Image

    spec = dict(logo.CANDIDATES[DETECTOR])
    spec["threshold"] = v2.FLOOR_SCORE
    manifest = json.loads((private_dir / "restricted_manifest.json").read_text(encoding="utf-8"))
    entries = [e for e in manifest["entries"] if e["domain"] == bench.DOMAIN_AVATAR]
    if len(entries) != bench.EXPECTED_COUNTS[bench.DOMAIN_AVATAR]:
        raise SystemExit(f"BLOCKED_G004_AVATAR_SET_COUNT_{len(entries)}")
    before = {e["opaqueId"]: Path(e["path"]).stat().st_mtime_ns for e in entries}

    existing = json.loads(existing_capture.read_text(encoding="utf-8"))
    if existing.get("revision") != spec["revision"]:
        raise SystemExit("EXISTING_CAPTURE_REVISION_MISMATCH")
    reused_rows = []
    for fam in v2.FAMILIES:
        if fam.reuse_variant:
            for row in existing["rows"]:
                if row["variant"] == fam.reuse_variant:
                    reused_rows.append({**row, "conditionId": f"{row['opaqueId']}:{fam.code}", "family": fam.family,
                                        "familyCode": fam.code, "reusedFrom": fam.reuse_variant})

    rows: list[dict] = []
    done = set()
    if out.exists():
        prior = json.loads(out.read_text(encoding="utf-8"))
        rows = [r for r in prior["rows"] if not r.get("reusedFrom")]
        done = {r["conditionId"] for r in rows}

    process = psutil.Process()
    t0 = time.perf_counter()
    processor, model = logo._load(spec["kind"], models_dir / spec["dir"])
    load_seconds = time.perf_counter() - t0
    peak = process.memory_info().rss
    todo_fams = [f for f in v2.FAMILIES if not f.reuse_variant and (only_codes is None or f.code in only_codes)]
    manifest_rows = []
    for entry in entries:
        with Image.open(entry["path"]) as handle:  # read-only
            base = handle.convert("RGB")
        group = logo._group_key_for(entry)
        for fam in todo_fams:
            cid = f"{entry['opaqueId']}:{fam.code}"
            image, truth = v2.render_family(base, fam)
            manifest_rows.append(v2.manifest_row(fam, entry["opaqueId"], group, truth))
            if cid in done:
                continue
            t1 = time.perf_counter()
            detections = logo._detect(spec["kind"], processor, model, image, spec)
            rows.append(
                {
                    "conditionId": cid,
                    "opaqueId": entry["opaqueId"],
                    "groupKey": group,
                    "domain": entry["domain"],
                    "family": fam.family,
                    "familyCode": fam.code,
                    "imageSize": list(image.size),
                    "groundTruth": [b["box"] for b in truth],
                    "detections": detections,
                    "seconds": round(time.perf_counter() - t1, 3),
                }
            )
            peak = max(peak, process.memory_info().rss)
            del image
            # checkpoint so an OOM does not lose the run
            out.write_text(json.dumps({"captureVersion": CAPTURE_VERSION, "partial": True, "rows": rows}), encoding="utf-8")
        del base
        gc.collect()

    after = {e["opaqueId"]: Path(e["path"]).stat().st_mtime_ns for e in entries}
    if after != before:
        raise SystemExit("ORIGINALS_CHANGED")
    result = {
        "captureVersion": CAPTURE_VERSION,
        "generatorVersion": v2.GENERATOR_VERSION,
        "detector": DETECTOR,
        "repo": spec["repo"],
        "revision": spec["revision"],
        "floorScore": v2.FLOOR_SCORE,
        "prompts": list(v2.PROMPTS),
        "modelLoadSeconds": round(load_seconds, 1),
        "peakRssGb": round(peak / 2**30, 2),
        "families": v2.family_definitions(),
        "constructionManifest": manifest_rows,
        "rows": rows + reused_rows,
    }
    out.write_text(json.dumps(result), encoding="utf-8")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-dir", type=Path, required=True)
    parser.add_argument("--models-dir", type=Path, required=True)
    parser.add_argument("--existing-capture", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--only", default=None, help="comma-separated family codes")
    args = parser.parse_args(argv)
    only = set(args.only.split(",")) if args.only else None
    result = run(args.private_dir, args.models_dir, args.existing_capture, args.out, only)
    fresh = [r for r in result["rows"] if not r.get("reusedFrom")]
    print(json.dumps({"rows": len(result["rows"]), "freshInference": len(fresh), "reused": len(result["rows"]) - len(fresh),
                      "peakRssGb": result["peakRssGb"], "meanSeconds": round(sum(r["seconds"] for r in fresh) / max(1, len(fresh)), 2)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
