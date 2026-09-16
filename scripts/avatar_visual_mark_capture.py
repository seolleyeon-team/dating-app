"""B3-L11 local detector capture. LOCAL ONLY -- never run in CI.

One detector, one split, one model resident.  Renders VISUAL_MARK_CHALLENGE_V3
derivatives in memory from the untouched originals (DEV_VARIANT for the
development bases, HOLDOUT_VARIANT for the holdout bases) plus the clean
originals of the same bases, and stores one low-floor inference per image.
Holdout capture fails closed unless the selected-candidate freeze exists and
names this detector.  Checkpoint-resume; resource guards (start gate,
per-row hard guard never lowered); revision and originals verified.

Usage:
  python scripts/avatar_visual_mark_capture.py --detector owlv2-base-patch16-ensemble --split development \
      --private-dir <b3l4 dir> --out-dir <b3l11 dir> --model-dir <model dir>
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

import avatar_florence_ceiling as bench  # noqa: E402
import avatar_florence_ceiling_run as ceiling_run  # noqa: E402
import avatar_visual_mark_challenge_v3 as c3  # noqa: E402
import avatar_visual_mark_detectors as det  # noqa: E402

CAPTURE_VERSION = "avatar_visual_mark_capture_v1"
MIN_AVAILABLE_GB_TO_START = {"owl": 4.0, "gdino": 3.0, "florence": 4.0}
MIN_AVAILABLE_GB_DURING = 0.6


def _available_gb() -> float:
    import psutil

    return psutil.virtual_memory().available / 2**30


def _revision(model_dir: Path, name: str) -> str:
    spec = det.CANDIDATES[name]
    if spec["kind"] == "florence":
        return ceiling_run._model_revision(model_dir)
    meta = model_dir / ".revision"
    if meta.exists():
        return meta.read_text(encoding="utf-8").strip()
    hub = model_dir / "refs"
    if hub.exists():
        return (hub / "main").read_text(encoding="utf-8").strip()
    return spec["revision"]   # models were snapshot-downloaded at the pinned revision in B3-L5 (recorded there); no other metadata on disk


def run(name: str, split: str, private_dir: Path, out_dir: Path, model_dir: Path) -> int:
    import psutil
    from PIL import Image

    out_dir.mkdir(parents=True, exist_ok=True)
    spec = det.CANDIDATES[name]
    digest = det.contract_digest()
    cdigest = c3.construct_digest()
    if split == "holdout":
        marker = out_dir / det.SELECTED_MARKER_NAME
        if not marker.exists():
            raise SystemExit("HOLDOUT_REQUIRES_SELECTED_FREEZE")
        frozen = json.loads(marker.read_text(encoding="utf-8"))
        member = frozen.get("detector") == name or name in (frozen.get("detectors") or [])   # single-detector or frozen union marker
        if not member or frozen.get("contractDigest") != digest or frozen.get("constructDigest") != cdigest:
            raise SystemExit("HOLDOUT_FREEZE_MISMATCH")
        groups, variant = c3.HOLDOUT_GROUPS, c3.HOLDOUT_VARIANT
    else:
        groups, variant = c3.DEVELOPMENT_GROUPS, c3.DEV_VARIANT

    revision = _revision(model_dir, name)
    if revision != spec["revision"]:
        raise SystemExit(f"STOP_MODEL_REVISION_MISMATCH {name} pinned={spec['revision']} local={revision}")
    entries = ceiling_run._load_manifest(private_dir)
    by_id = {e["opaqueId"]: e for e in entries}
    before = ceiling_run._fingerprint(entries)
    if any(before[k][0] != by_id[k]["sha256"] for k in by_id):
        raise SystemExit("ORIGINALS_CHANGED_SINCE_INVENTORY")

    bases = [e for e in entries if e["domain"] == bench.DOMAIN_AVATAR and ceiling_run._group_key(e) in groups]
    conds = c3.conditions(variant)
    todo = [(e, None) for e in bases] + [(e, c) for e in bases for c in conds]
    out_path = out_dir / f"capture_{name}_{split}.jsonl"
    done = set()
    if out_path.exists():
        for line in out_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                done.add(json.loads(line)["conditionId"])
    todo = [(e, c) for e, c in todo if (f"{e['opaqueId']}:{c.code}" if c else f"{e['opaqueId']}:CLEAN") not in done]
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
                if max(base.size) > det.MAX_LONG_SIDE:
                    scale = det.MAX_LONG_SIDE / max(base.size)
                    base = base.resize((int(round(base.size[0] * scale)), int(round(base.size[1] * scale))), Image.LANCZOS)
                base_cache[base_id] = base
            if cond is None:
                image, truth, cid, meta = base_cache[base_id], [], f"{base_id}:CLEAN", {"family": None, "variant": None, "markPresent": False}
            else:
                image, truth = c3.render(base_cache[base_id], cond)
                cid = f"{base_id}:{cond.code}"
                meta = c3.manifest_row(cond, base_id, ceiling_run._group_key(entry), truth)
            started = time.perf_counter()
            detections = det.detect_floor(name, processor, model, image)
            seconds = round(time.perf_counter() - started, 3)
            peak_rss = max(peak_rss, process.memory_info().rss)
            group = ceiling_run._group_key(entry)
            sink.write(json.dumps({"captureVersion": CAPTURE_VERSION, "detector": name, "split": split, "conditionId": cid, "opaqueId": base_id, "groupKey": group,
                                   "imageSize": list(image.size), "derivativeDigest": c3.image_digest(image) if cond else None, "meta": meta, "groundTruth": truth,
                                   "detections": detections, "seconds": seconds, "revision": revision}) + "\n")
            sink.flush()
            if cond is not None:
                del image
            gc.collect()
            if index % 10 == 0 or index == len(todo):
                print(f"{index}/{len(todo)} last={seconds:.1f}s rss={peak_rss / 2**30:.2f}GB avail={_available_gb():.2f}GB", flush=True)

    if ceiling_run._fingerprint(entries) != before:
        raise SystemExit("ORIGINALS_CHANGED")
    meta = {"captureVersion": CAPTURE_VERSION, "detector": name, "split": split, "variant": variant, "repo": spec["repo"], "revision": revision, "license": spec["license"],
            "device": det.DEVICE, "modelLoadSec": round(load_sec, 1), "peakRssGb": round(peak_rss / 2**30, 2), "rowsInferred": len(todo), "originalsUnchanged": True,
            "contractDigestPrefix": digest[:12], "constructDigestPrefix": cdigest[:12]}
    (out_dir / f"run_meta_{name}_{split}.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
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
