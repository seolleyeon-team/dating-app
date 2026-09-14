"""B3-L9 local Florence capture for the HOLDOUT text derivatives. LOCAL ONLY -- never run in CI.

Only TEXT_WATERMARK_OPAQUE (F3) and TEXT_WATERMARK_TRANSLUCENT (F4) on the
G4-G5 bases (8 x 2 = 16 rows), rendered in memory with the merged B3-L7
generator on the untouched originals.  Runs only after the selected
candidate is frozen (text_policy_v1_selected.json matching the contract
digest); fails closed otherwise.  Same production adapter path as B3-L8
(OCR_WITH_REGION + OD, num_beams 3, fp32 CPU); every row carries the
derivative pixel digest.

Resource guards: start gate (operator guard) and a per-row hard guard that
stops with the checkpoint kept.  The per-row guard is never lowered to obtain
a result.
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
import avatar_owlv2_calibration as calib  # noqa: E402
import avatar_owlv2_challenge_v2 as v2  # noqa: E402
import avatar_text_policy_shadow as tp  # noqa: E402

CAPTURE_VERSION = "avatar_text_policy_shadow_holdout_capture_v1"
FAMILY_CODES = ("F3", "F4")
# Operator start gate, measured after torch/transformers import (~0.3 GB): B3-L8 ended at 4.0
# (record: 4.6 -> 4.2 -> 4.0 during B3-L8, per-row hard guard unchanged at 0.6).
MIN_AVAILABLE_GB_TO_START = 4.0
MIN_AVAILABLE_GB_DURING = 0.6   # hard guard: never lowered


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
    digest = tp.contract_digest()
    tp.require_selected(out_dir, digest)   # fail closed: holdout inference only after the freeze

    pinned = v3.pinned_florence_revision()
    revision = ceiling_run._model_revision(model_dir)
    if revision != pinned:
        raise SystemExit(f"STOP_FLORENCE_REVISION_MISMATCH pinned={pinned} local={revision}")
    entries = ceiling_run._load_manifest(private_dir)
    by_id = {e["opaqueId"]: e for e in entries}
    before = ceiling_run._fingerprint(entries)
    if any(before[k][0] != by_id[k]["sha256"] for k in by_id):
        raise SystemExit("ORIGINALS_CHANGED_SINCE_INVENTORY")

    families = [f for f in v2.FAMILIES if f.code in FAMILY_CODES]
    bases = [e for e in entries if e["domain"] == bench.DOMAIN_AVATAR and ceiling_run._group_key(e) in tp.sel.HOLDOUT_GROUPS]
    out_path = out_dir / "florence_holdout_text_capture.jsonl"
    done = set()
    if out_path.exists():
        for line in out_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                done.add(json.loads(line)["conditionId"])
    todo = [(e, f) for e in bases for f in families if f"{e['opaqueId']}:{f.code}" not in done]
    print(f"holdout bases={len(bases)} families={[f.code for f in families]} done={len(done)} todo={len(todo)}", flush=True)
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
            group = ceiling_run._group_key(entry)
            sink.write(json.dumps({
                "captureVersion": CAPTURE_VERSION, "conditionId": f"{base_id}:{family.code}", "baseOpaqueId": base_id, "opaqueId": base_id,
                "groupKey": group, "split": calib._split(group), "family": family.family, "familyCode": family.code,
                "generatorVersion": "avatar_owlv2_challenge_v2_generator_v1", "derivativeDigest": v3.image_digest(image),
                "imageSize": list(image.size), "groundTruth": truth, "tasks": tasks, "latencySec": latency, "florenceRevision": revision,
            }) + "\n")
            sink.flush()
            del image
            gc.collect()
            print(f"{index}/{len(todo)} last={latency['combined']:.1f}s rss={peak_rss / 2**30:.2f}GB avail={_available_gb():.2f}GB", flush=True)

    if ceiling_run._fingerprint(entries) != before:
        raise SystemExit("ORIGINALS_CHANGED")
    meta = {"captureVersion": CAPTURE_VERSION, "florenceRepo": v3.FLORENCE_REPO, "florenceRevision": revision, "torch": torch.__version__,
            "transformers": transformers.__version__, "pillow": PIL.__version__, "device": str(next(adapter._model.parameters()).device),
            "dtype": str(next(adapter._model.parameters()).dtype), "modelLoadSec": round(load_sec, 1), "peakRssGb": round(peak_rss / 2**30, 2),
            "rowsInferred": len(todo), "originalsUnchanged": True, "contractDigestPrefix": digest[:12]}
    (out_dir / "florence_run_meta_holdout_text.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps(meta, indent=2), flush=True)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-dir", type=Path, required=True, help="B3-L4 restricted dir (manifest)")
    parser.add_argument("--out-dir", type=Path, required=True, help="B3-L9 restricted dir (holds the selected marker)")
    parser.add_argument("--model-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    return run(args.private_dir, args.out_dir, args.model_dir)


if __name__ == "__main__":
    raise SystemExit(main())
