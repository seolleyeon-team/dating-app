"""B3-L14A local detector capture for EDGE_MARK_GENERALIZATION_V1. LOCAL ONLY -- never run in CI.

One detector, one split, one model resident.  Renders the edge derivatives in
memory from the untouched originals (EDGE_DEV_VARIANT on G1-G3,
EDGE_HOLDOUT_VARIANT on G4-G5) and stores one low-floor inference per image
(the frozen operating point is a filter over that output; no re-inference per
threshold).  No clean rows: this is a proposal-ceiling study, not a clean-
response study.  Holdout capture fails closed unless the development-pass
freeze exists and matches the contract, and refuses to run once the holdout
lock exists.  Checkpoint-resume; resource guards identical to B3-L11 (start
gate per model kind; per-row hard guard never lowered); revision and
originals verified.  The original B3-L11 HOLDOUT_VARIANT is never rendered,
inferred or evaluated here (different construct module, different file names).

Usage:
  python scripts/avatar_edge_mark_capture.py --detector grounding-dino-tiny --split development \
      --private-dir <b3l4 dir> --out-dir <b3l14a dir> --model-dir <model dir>
"""

from __future__ import annotations

import argparse
import gc
import json
import sys
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import avatar_edge_mark_generalization as eg  # noqa: E402
import avatar_florence_ceiling as bench  # noqa: E402
import avatar_florence_ceiling_run as ceiling_run  # noqa: E402
import avatar_owlv2_threshold_selection as sel  # noqa: E402
import avatar_visual_mark_capture as l11cap  # noqa: E402
import avatar_visual_mark_detectors as det  # noqa: E402

CAPTURE_VERSION = "avatar_edge_mark_capture_v1"
CAPTURE_FILE_PREFIX = "edge_capture_"
RUN_META_PREFIX = "edge_run_meta_"
MIN_AVAILABLE_GB_TO_START = dict(l11cap.MIN_AVAILABLE_GB_TO_START)     # {"owl": 4.0, "gdino": 3.0, "florence": 4.0} — unchanged
MIN_AVAILABLE_GB_DURING = l11cap.MIN_AVAILABLE_GB_DURING               # 0.6 — never lowered
MAX_LONG_SIDE = det.MAX_LONG_SIDE


def _available_gb() -> float:
    import psutil

    return psutil.virtual_memory().available / 2**30


def holdout_conditions(private_dir: Path) -> list[eg.EdgeCondition]:
    """Holdout derivatives exist only after the development-pass freeze and before the single evaluation."""

    eg.require_dev_passed(private_dir, eg.contract_digest())
    if (Path(private_dir) / eg.HOLDOUT_LOCK_NAME).exists():
        raise sel.HoldoutAlreadyEvaluated("edge holdout already evaluated once; no further holdout inference")
    return eg.conditions(eg.HOLDOUT_VARIANT)


def run(name: str, split: str, private_dir: Path, out_dir: Path, model_dir: Path) -> int:
    import psutil
    from PIL import Image

    out_dir.mkdir(parents=True, exist_ok=True)
    spec = det.CANDIDATES[name]
    digest = eg.contract_digest()
    cdigest = eg.construct_digest()
    if split == "holdout":
        conds, groups, variant = holdout_conditions(out_dir), eg.HOLDOUT_GROUPS, eg.HOLDOUT_VARIANT
    else:
        conds, groups, variant = eg.conditions(eg.DEV_VARIANT), eg.DEVELOPMENT_GROUPS, eg.DEV_VARIANT

    revision = l11cap._revision(model_dir, name)
    if revision != spec["revision"]:
        raise SystemExit(f"STOP_MODEL_REVISION_MISMATCH {name} pinned={spec['revision']} local={revision}")
    entries = ceiling_run._load_manifest(private_dir)
    by_id = {e["opaqueId"]: e for e in entries}
    before = ceiling_run._fingerprint(entries)
    if any(before[k][0] != by_id[k]["sha256"] for k in by_id):
        raise SystemExit("ORIGINALS_CHANGED_SINCE_INVENTORY")

    bases = [e for e in entries if e["domain"] == bench.DOMAIN_AVATAR and ceiling_run._group_key(e) in groups]
    if len(bases) != eg.EXPECTED_BASES[split]:
        raise SystemExit(f"BASE_COUNT_MISMATCH split={split} expected={eg.EXPECTED_BASES[split]} actual={len(bases)}")
    todo = [(e, c) for e in bases for c in conds]
    out_path = out_dir / f"{CAPTURE_FILE_PREFIX}{name}_{split}.jsonl"
    done = set()
    if out_path.exists():
        for line in out_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                done.add(json.loads(line)["conditionId"])
    todo = [(e, c) for e, c in todo if f"{e['opaqueId']}:{c.code}" not in done]
    print(f"{name} split={split} variant={variant} bases={len(bases)} conditions={len(conds)} done={len(done)} todo={len(todo)}", flush=True)
    if not todo:
        return 0
    available = _available_gb()
    if available < MIN_AVAILABLE_GB_TO_START[spec["kind"]]:
        raise SystemExit(f"BLOCKED_LOCAL_RESOURCE_SAFETY available={available:.2f}GB")

    process = psutil.Process()
    t0 = time.perf_counter()
    processor, model = det.load(name, model_dir)
    load_sec = time.perf_counter() - t0
    peak_rss = process.memory_info().rss
    base_cache: dict = {}
    with out_path.open("a", encoding="utf-8") as sink:
        for index, (entry, cond) in enumerate(todo, 1):
            if _available_gb() < MIN_AVAILABLE_GB_DURING:
                raise SystemExit("BLOCKED_LOCAL_RESOURCE_SAFETY during run (checkpoint kept)")
            base_id = entry["opaqueId"]
            if base_id not in base_cache:
                base_cache.clear()
                with Image.open(entry["path"]) as handle:  # read-only
                    base = handle.convert("RGB")
                if max(base.size) > MAX_LONG_SIDE:
                    scale = MAX_LONG_SIDE / max(base.size)
                    base = base.resize((int(round(base.size[0] * scale)), int(round(base.size[1] * scale))), Image.LANCZOS)
                base_cache[base_id] = base
            image, truth = eg.render(base_cache[base_id], cond)
            group = ceiling_run._group_key(entry)
            cid = f"{base_id}:{cond.code}"
            started = time.perf_counter()
            detections = det.detect_floor(name, processor, model, image)
            seconds = round(time.perf_counter() - started, 3)
            peak_rss = max(peak_rss, process.memory_info().rss)
            sink.write(json.dumps({"captureVersion": CAPTURE_VERSION, "detector": name, "split": split, "conditionId": cid, "opaqueId": base_id, "groupKey": group,
                                   "imageSize": list(image.size), "derivativeDigest": eg.image_digest(image), "meta": eg.manifest_row(cond, base_id, group, truth), "groundTruth": truth,
                                   "detections": detections, "seconds": seconds, "revision": revision}) + "\n")
            sink.flush()
            del image
            gc.collect()
            if index % 10 == 0 or index == len(todo):
                print(f"{index}/{len(todo)} last={seconds:.1f}s rss={peak_rss / 2**30:.2f}GB avail={_available_gb():.2f}GB", flush=True)

    if ceiling_run._fingerprint(entries) != before:
        raise SystemExit("ORIGINALS_CHANGED")
    meta = {"captureVersion": CAPTURE_VERSION, "detector": name, "split": split, "variant": variant, "repo": spec["repo"], "revision": revision, "license": spec["license"],
            "device": det.DEVICE, "modelLoadSec": round(load_sec, 1), "peakRssGb": round(peak_rss / 2**30, 2), "rowsInferredThisRun": len(todo), "originalsUnchanged": True,
            "contractDigestPrefix": digest[:12], "constructDigestPrefix": cdigest[:12], "detectorSetDigestPrefix": det.contract_digest()[:12]}
    (out_dir / f"{RUN_META_PREFIX}{name}_{split}.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps(meta, indent=2), flush=True)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--detector", required=True, choices=sorted(det.CANDIDATES))
    parser.add_argument("--split", required=True, choices=("development", "holdout"))
    parser.add_argument("--private-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    return run(args.detector, args.split, args.private_dir, args.out_dir, args.model_dir)


if __name__ == "__main__":
    raise SystemExit(main())
