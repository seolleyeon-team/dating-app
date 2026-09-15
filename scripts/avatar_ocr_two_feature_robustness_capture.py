"""B3-L10B local Florence capture for TEXT_CONSTRUCT_ROBUSTNESS_V1. LOCAL ONLY -- never run in CI.

Renders the frozen robustness constructs (six synthetic strings x opaque /
translucent) on the eight G4-G5 avatars in memory with the merged B3-L7
text renderer, and runs the production Florence adapter path
(OCR_WITH_REGION + OD, num_beams 3, fp32 CPU).  Runs only after the
two-feature rule is frozen AND the feature-specific validation has PASSED
under the same contract; fails closed otherwise.  Resource guards as in
B3-L8/L9 (start gate 4.0 GB post-import, per-row hard guard 0.6 GB, never
lowered; checkpoint-resume).
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

import avatar_dual_channel_v3 as v3  # noqa: E402
import avatar_florence_ceiling as bench  # noqa: E402
import avatar_florence_ceiling_run as ceiling_run  # noqa: E402
import avatar_ocr_two_feature as tf  # noqa: E402
import avatar_owlv2_calibration as calib  # noqa: E402
import avatar_owlv2_challenge_v2 as v2  # noqa: E402

CAPTURE_VERSION = "avatar_ocr_two_feature_robustness_capture_v1"
MIN_AVAILABLE_GB_TO_START = 4.0
MIN_AVAILABLE_GB_DURING = 0.6


def _available_gb() -> float:
    import psutil

    return psutil.virtual_memory().available / 2**30


def run(private_dir: Path, out_dir: Path, model_dir: Path) -> int:
    import psutil
    import torch
    import transformers
    import PIL
    from PIL import Image
    from avatar_generation.model_adapters.florence2_visual import Florence2VisualRiskAdapter

    out_dir.mkdir(parents=True, exist_ok=True)
    digest = tf.contract_digest()
    tf.require_frozen(out_dir, digest)
    tf.require_validation_pass(out_dir, digest)

    pinned = v3.pinned_florence_revision()
    revision = ceiling_run._model_revision(model_dir)
    if revision != pinned:
        raise SystemExit(f"STOP_FLORENCE_REVISION_MISMATCH pinned={pinned} local={revision}")
    entries = ceiling_run._load_manifest(private_dir)
    by_id = {e["opaqueId"]: e for e in entries}
    before = ceiling_run._fingerprint(entries)
    if any(before[k][0] != by_id[k]["sha256"] for k in by_id):
        raise SystemExit("ORIGINALS_CHANGED_SINCE_INVENTORY")

    specs = tf.robustness_specs()
    bases = [e for e in entries if e["domain"] == bench.DOMAIN_AVATAR and ceiling_run._group_key(e) in tf.ROBUSTNESS_GROUPS]
    out_path = out_dir / "florence_robustness_capture.jsonl"
    done = set()
    if out_path.exists():
        for line in out_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                done.add(json.loads(line)["conditionId"])
    todo = [(e, s) for e in bases for s in specs if f"{e['opaqueId']}:{s.code}" not in done]
    print(f"robustness bases={len(bases)} specs={[s.code for s in specs]} done={len(done)} todo={len(todo)}", flush=True)
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
        for index, (entry, spec) in enumerate(todo, 1):
            if _available_gb() < MIN_AVAILABLE_GB_DURING:
                raise SystemExit("BLOCKED_LOCAL_RESOURCE_SAFETY during run (checkpoint kept)")
            base_id = entry["opaqueId"]
            if base_id not in base_cache:
                base_cache.clear()
                with Image.open(entry["path"]) as handle:  # read-only
                    base_cache[base_id] = handle.convert("RGB")
            image, truth = v2.render_family(base_cache[base_id], spec)
            latency, tasks = {}, {}
            for task in v3.FLORENCE_TASKS:
                started = time.perf_counter()
                tasks[task] = adapter._run_task(image, task)
                latency["ocr" if task == bench.TASK_OCR_WITH_REGION else "od"] = round(time.perf_counter() - started, 3)
            latency["combined"] = round(sum(latency.values()), 3)
            peak_rss = max(peak_rss, process.memory_info().rss)
            group = ceiling_run._group_key(entry)
            sink.write(json.dumps({
                "captureVersion": CAPTURE_VERSION, "conditionId": f"{base_id}:{spec.code}", "baseOpaqueId": base_id, "opaqueId": base_id, "groupKey": group,
                "split": calib._split(group), "role": tf.ROBUSTNESS_ROLE, "family": spec.family, "familyCode": spec.code, "robustnessVersion": tf.ROBUSTNESS_VERSION,
                "derivativeDigest": v3.image_digest(image), "imageSize": list(image.size), "groundTruth": truth, "tasks": tasks, "latencySec": latency, "florenceRevision": revision,
            }) + "\n")
            sink.flush()
            del image
            gc.collect()
            print(f"{index}/{len(todo)} last={latency['combined']:.1f}s rss={peak_rss / 2**30:.2f}GB avail={_available_gb():.2f}GB", flush=True)

    if ceiling_run._fingerprint(entries) != before:
        raise SystemExit("ORIGINALS_CHANGED")
    meta = {"captureVersion": CAPTURE_VERSION, "robustnessVersion": tf.ROBUSTNESS_VERSION, "florenceRepo": v3.FLORENCE_REPO, "florenceRevision": revision,
            "torch": torch.__version__, "transformers": transformers.__version__, "pillow": PIL.__version__,
            "device": str(next(adapter._model.parameters()).device), "dtype": str(next(adapter._model.parameters()).dtype),
            "modelLoadSec": round(load_sec, 1), "peakRssGb": round(peak_rss / 2**30, 2), "rowsInferred": len(todo), "originalsUnchanged": True, "contractDigestPrefix": digest[:12]}
    (out_dir / "florence_run_meta_robustness.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps(meta, indent=2), flush=True)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    return run(args.private_dir, args.out_dir, args.model_dir)


if __name__ == "__main__":
    raise SystemExit(main())
