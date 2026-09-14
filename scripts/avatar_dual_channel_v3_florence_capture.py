"""B3-L8 local Florence capture for V3 challenge derivatives. LOCAL ONLY -- never run in CI.

Runs the production Florence adapter task path (OCR_WITH_REGION + OD, num_beams 3)
on the B3-L7 challenge derivatives whose Florence output cannot be reused
exactly from the B3-L4 capture.  Order of minimisation (pre-registered):

  1. exact reuse audit (identical spec + byte-identical re-render)      -> no inference
  2. missing DEVELOPMENT rows only                                        -> local inference
  3. HOLDOUT rows only after the V3 development pass marker exists       -> local inference

Derivatives are rendered in memory from the originals with the merged B3-L7
generator; originals are never written.  Every row records the derivative's
pixel digest so the evaluator can prove the Florence output belongs to the
exact construct.  Raw OCR text stays in the restricted directory.

Usage:
  python scripts/avatar_dual_channel_v3_florence_capture.py --private-dir <b3l4 dir> \
      --out-dir <b3l8 dir> --model-dir <florence2 dir> --split development
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import sys
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import avatar_dual_channel_v3 as v3  # noqa: E402
import avatar_florence_ceiling as bench  # noqa: E402
import avatar_florence_ceiling_run as ceiling_run  # noqa: E402
import avatar_owlv2_challenge_v2 as v2  # noqa: E402
import avatar_owlv2_calibration as calib  # noqa: E402

CAPTURE_VERSION = "avatar_dual_channel_v3_florence_capture_v1"
# Start gate: the fp32 Florence-2-large process peaks ~4.0 GB RSS on this machine.
# The hard stop is the per-row guard below (checkpoint kept, fail closed).
# Measured after torch/transformers are imported (~0.3 GB), so 4.0 here is ~4.3 GB pre-import.
MIN_AVAILABLE_GB_TO_START = 4.0
MIN_AVAILABLE_GB_DURING = 0.6


def _available_gb() -> float:
    import psutil

    return psutil.virtual_memory().available / 2**30


def reuse_audit(entries, existing_variants):
    from PIL import Image

    bases = []
    for e in entries:
        if e["domain"] != bench.DOMAIN_AVATAR:
            continue
        with Image.open(e["path"]) as handle:  # read-only
            bases.append(handle.convert("RGB"))
    out = {"generatorVersion": "avatar_owlv2_challenge_v2_generator_v1", "families": {}}
    for family in v2.FAMILIES:
        out["families"][family.family] = v3.reuse_verdict(family, bases, existing_variants)
    del bases
    gc.collect()
    return out


def run(private_dir: Path, out_dir: Path, model_dir: Path, split: str, florence_rows_path: Path) -> int:
    import psutil
    import torch
    import transformers
    import PIL
    from PIL import Image
    from avatar_generation.model_adapters.florence2_visual import Florence2VisualRiskAdapter

    out_dir.mkdir(parents=True, exist_ok=True)
    pinned = v3.pinned_florence_revision()
    revision = ceiling_run._model_revision(model_dir)
    if revision != pinned:
        raise SystemExit(f"STOP_FLORENCE_REVISION_MISMATCH pinned={pinned} local={revision}")

    entries = ceiling_run._load_manifest(private_dir)
    by_id = {e["opaqueId"]: e for e in entries}
    before = ceiling_run._fingerprint(entries)
    if any(before[k][0] != by_id[k]["sha256"] for k in by_id):
        raise SystemExit("ORIGINALS_CHANGED_SINCE_INVENTORY")

    existing_variants = sorted({json.loads(l)["variant"] for l in florence_rows_path.read_text(encoding="utf-8").splitlines() if l.strip()})
    audit_path = out_dir / "reuse_audit.json"
    if audit_path.exists():
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
    else:
        audit = reuse_audit(entries, existing_variants)
        audit_path.write_text(json.dumps(audit, indent=2), encoding="utf-8")
    missing_families = [f for f in v2.FAMILIES if audit["families"][f.family]["verdict"] != v3.REUSE_EXACT]
    print("reuse:", {k: v["verdict"] for k, v in audit["families"].items()}, flush=True)

    digest = v3.contract_digest()
    if split == "holdout":
        v3.require_development_pass(out_dir, digest)  # fail closed
        groups = v3.HOLDOUT_GROUPS
    else:
        groups = v3.DEVELOPMENT_GROUPS

    bases = [e for e in entries if e["domain"] == bench.DOMAIN_AVATAR and ceiling_run._group_key(e) in groups]
    todo = [(e, f) for e in bases for f in missing_families]
    out_path = out_dir / "florence_challenge_capture.jsonl"
    done = set()
    if out_path.exists():
        for line in out_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                done.add(json.loads(line)["conditionId"])
    todo = [(e, f) for e, f in todo if f"{e['opaqueId']}:{f.code}" not in done]
    print(f"split={split} bases={len(bases)} missingFamilies={len(missing_families)} done={len(done)} todo={len(todo)}", flush=True)
    if not todo:
        return 0

    available = _available_gb()
    if available < MIN_AVAILABLE_GB_TO_START:
        raise SystemExit(f"BLOCKED_LOCAL_RESOURCE_SAFETY available={available:.2f}GB")

    process = psutil.Process()
    adapter = Florence2VisualRiskAdapter(model_id=str(model_dir), local_files_only=True)
    t0 = time.perf_counter()
    adapter._ensure_loaded()
    load_sec = time.perf_counter() - t0
    peak_rss = process.memory_info().rss
    base_cache: dict = {}
    with out_path.open("a", encoding="utf-8") as sink:
        for index, (entry, family) in enumerate(todo, 1):
            if _available_gb() < MIN_AVAILABLE_GB_DURING:
                raise SystemExit("BLOCKED_LOCAL_RESOURCE_SAFETY during run (checkpoint kept)")
            base_id = entry["opaqueId"]
            if base_id not in base_cache:
                base_cache.clear()
                with Image.open(entry["path"]) as handle:  # read-only
                    base_cache[base_id] = handle.convert("RGB")
            image, truth = v2.render_family(base_cache[base_id], family)
            latency, tasks = {}, {}
            for task in v3.FLORENCE_TASKS:
                started = time.perf_counter()
                tasks[task] = adapter._run_task(image, task)
                latency["ocr" if task == bench.TASK_OCR_WITH_REGION else "od"] = round(time.perf_counter() - started, 3)
            latency["combined"] = round(sum(latency.values()), 3)
            peak_rss = max(peak_rss, process.memory_info().rss)
            record = {
                "captureVersion": CAPTURE_VERSION,
                "conditionId": f"{base_id}:{family.code}",
                "baseOpaqueId": base_id,
                "opaqueId": base_id,
                "groupKey": ceiling_run._group_key(entry),
                "split": calib._split(ceiling_run._group_key(entry)),
                "family": family.family,
                "familyCode": family.code,
                "generatorVersion": "avatar_owlv2_challenge_v2_generator_v1",
                "derivativeDigest": v3.image_digest(image),
                "imageSize": list(image.size),
                "groundTruth": truth,
                "tasks": tasks,
                "latencySec": latency,
                "florenceRevision": revision,
            }
            sink.write(json.dumps(record) + "\n")
            sink.flush()
            del image
            gc.collect()
            if index % 5 == 0 or index == len(todo):
                print(f"{index}/{len(todo)} last={latency['combined']:.1f}s rss={peak_rss / 2**30:.2f}GB avail={_available_gb():.2f}GB", flush=True)

    after = ceiling_run._fingerprint(entries)
    if after != before:
        raise SystemExit("ORIGINALS_CHANGED")
    meta = {
        "captureVersion": CAPTURE_VERSION,
        "split": split,
        "florenceRepo": v3.FLORENCE_REPO,
        "florenceRevision": revision,
        "torch": torch.__version__,
        "transformers": transformers.__version__,
        "pillow": PIL.__version__,
        "device": str(next(adapter._model.parameters()).device),
        "dtype": str(next(adapter._model.parameters()).dtype),
        "modelLoadSec": round(load_sec, 1),
        "peakRssGb": round(peak_rss / 2**30, 2),
        "rowsInferred": len(todo),
        "originalsUnchanged": True,
        "contractDigestPrefix": digest[:12],
    }
    (out_dir / f"florence_run_meta_{split}.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps(meta, indent=2), flush=True)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-dir", type=Path, required=True, help="B3-L4 restricted dir (manifest)")
    parser.add_argument("--out-dir", type=Path, required=True, help="B3-L8 restricted dir")
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--florence-rows", type=Path, required=True, help="B3-L4 raw_outputs.jsonl")
    parser.add_argument("--split", choices=("development", "holdout"), required=True)
    args = parser.parse_args(argv)
    return run(args.private_dir, args.out_dir, args.model_dir, args.split, args.florence_rows)


if __name__ == "__main__":
    raise SystemExit(main())
