"""B3-L13 local proposal-crop embedding. LOCAL ONLY -- never run in CI.

For one split, builds the frozen proposal union from the three B3-L11
detector captures, re-renders each derivative deterministically from the
untouched originals (digest-checked against the capture row), crops every
proposal with the frozen crop contract, and embeds the crop with the
production CLIP model (openai/clip-vit-large-patch14 @ pinned revision, local
files only).  Writes one restricted JSONL row per proposal with its label
authority (positive / negative / ambiguous from the ground-truth boxes) and
the L2-normalized embedding.  No raw crop is persisted.  Resource guards as
in earlier stages; the detectors are never resident while CLIP runs.
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
import avatar_proposal_verifier as pv  # noqa: E402
import avatar_visual_mark_challenge_v3 as c3  # noqa: E402
import avatar_visual_mark_detectors as det  # noqa: E402

EMBED_VERSION = "avatar_proposal_verifier_embed_v1"
MIN_AVAILABLE_GB_TO_START = 3.0
MIN_AVAILABLE_GB_DURING = 0.6


def _available_gb() -> float:
    import psutil

    return psutil.virtual_memory().available / 2**30


def _load_rows(capture_dir: Path, split: str) -> dict[str, dict[str, dict]]:
    by_cond: dict[str, dict[str, dict]] = {}
    for name in pv.PROPOSAL_GENERATORS:
        path = capture_dir / f"capture_{name}_{split}.jsonl"
        if not path.exists():
            raise SystemExit(f"CAPTURE_MISSING {name} {split}")
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                by_cond.setdefault(r["conditionId"], {})[name] = r
    return by_cond


def _model_dir(repo: str, revision: str) -> Path:
    from huggingface_hub import snapshot_download

    return Path(snapshot_download(repo_id=repo, revision=revision, local_files_only=True))


def run(split: str, private_dir: Path, capture_dir: Path, out_dir: Path) -> int:
    import psutil
    import torch
    from PIL import Image
    from transformers import CLIPModel, CLIPProcessor

    out_dir.mkdir(parents=True, exist_ok=True)
    digest = pv.contract_digest()
    if split == "holdout":
        pv.require_selected(out_dir, digest)   # fail closed: holdout embeddings only after the freeze
    entries = ceiling_run._load_manifest(private_dir)
    by_id = {e["opaqueId"]: e for e in entries}
    before = ceiling_run._fingerprint(entries)
    if any(before[k][0] != by_id[k]["sha256"] for k in by_id):
        raise SystemExit("ORIGINALS_CHANGED_SINCE_INVENTORY")
    by_cond = _load_rows(capture_dir, split)
    variant = c3.DEV_VARIANT if split == "development" else c3.HOLDOUT_VARIANT
    cond_by_code = {c.code: c for c in c3.conditions(variant)}
    out_path = out_dir / f"proposal_embeddings_{split}.jsonl"
    done = set()
    if out_path.exists():
        for line in out_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                done.add(json.loads(line)["conditionId"])
    todo = [cid for cid in sorted(by_cond) if cid not in done]
    print(f"split={split} conditions={len(by_cond)} done={len(done)} todo={len(todo)}", flush=True)
    if not todo:
        return 0
    if _available_gb() < MIN_AVAILABLE_GB_TO_START:
        raise SystemExit(f"BLOCKED_LOCAL_RESOURCE_SAFETY available={_available_gb():.2f}GB")
    model_dir = _model_dir(pv.VERIFIER["repo"], pv.VERIFIER["revision"])
    t0 = time.perf_counter()
    processor = CLIPProcessor.from_pretrained(model_dir, local_files_only=True)
    model = CLIPModel.from_pretrained(model_dir, local_files_only=True)
    model.eval()
    torch.set_grad_enabled(False)
    load_sec = time.perf_counter() - t0
    process = psutil.Process()
    peak = process.memory_info().rss
    base_cache: dict = {}
    n_props = 0
    with out_path.open("a", encoding="utf-8") as sink:
        for index, cid in enumerate(todo, 1):
            if _available_gb() < MIN_AVAILABLE_GB_DURING:
                raise SystemExit("BLOCKED_LOCAL_RESOURCE_SAFETY during run (checkpoint kept)")
            rows = by_cond[cid]
            any_row = next(iter(rows.values()))
            base_id = any_row["opaqueId"]
            if base_id not in base_cache:
                base_cache.clear()
                with Image.open(by_id[base_id]["path"]) as handle:  # read-only
                    base = handle.convert("RGB")
                if max(base.size) > det.MAX_LONG_SIDE:
                    scale = det.MAX_LONG_SIDE / max(base.size)
                    base = base.resize((int(round(base.size[0] * scale)), int(round(base.size[1] * scale))), Image.LANCZOS)
                base_cache[base_id] = base
            clean = cid.endswith(":CLEAN")
            if clean:
                image, truth = base_cache[base_id], []
            else:
                cond = cond_by_code[cid.split(":", 1)[1]]
                image, truth = c3.render(base_cache[base_id], cond)
                for r in rows.values():
                    if r.get("derivativeDigest") and r["derivativeDigest"] != c3.image_digest(image):
                        raise SystemExit(f"DERIVATIVE_DIGEST_MISMATCH {cid}")
            props = pv.union_proposals({name: r["detections"] for name, r in rows.items()}, image.size)
            record = {"embedVersion": EMBED_VERSION, "conditionId": cid, "opaqueId": base_id, "groupKey": any_row["groupKey"], "split": split, "clean": clean,
                      "meta": any_row.get("meta", {}), "imageSize": list(image.size), "groundTruth": truth, "proposals": []}
            crops = [image.crop(pv.crop_box(p["box"], image.size)) for p in props]
            embeddings = []
            for start in range(0, len(crops), 16):
                batch = crops[start:start + 16]
                inputs = processor(images=batch, return_tensors="pt")
                feats = model.get_image_features(pixel_values=inputs["pixel_values"])
                feats = feats / feats.norm(dim=-1, keepdim=True)
                embeddings.extend([[round(float(v), 6) for v in row] for row in feats.tolist()])
            for k, (p, emb) in enumerate(zip(props, embeddings)):
                label, iou = pv.proposal_label(p["box"], truth, clean_image=clean)
                record["proposals"].append({"proposalId": f"{cid}#{k}", "source": p["source"], "box": p["box"], "label": label, "bestIou": round(iou, 4), "embedding": emb})
            n_props += len(props)
            sink.write(json.dumps(record) + "\n")
            sink.flush()
            peak = max(peak, process.memory_info().rss)
            del crops
            gc.collect()
            if index % 20 == 0 or index == len(todo):
                print(f"{index}/{len(todo)} proposals={n_props} rss={peak / 2**30:.2f}GB avail={_available_gb():.2f}GB", flush=True)
    if ceiling_run._fingerprint(entries) != before:
        raise SystemExit("ORIGINALS_CHANGED")
    meta = {"embedVersion": EMBED_VERSION, "split": split, "verifier": {k: pv.VERIFIER[k] for k in ("repo", "revision", "license", "embeddingDim")}, "modelLoadSec": round(load_sec, 1),
            "peakRssGb": round(peak / 2**30, 2), "conditionsEmbedded": len(todo), "proposalsEmbedded": n_props, "originalsUnchanged": True, "contractDigestPrefix": digest[:12]}
    (out_dir / f"embed_meta_{split}.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps(meta, indent=2), flush=True)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", required=True, choices=("development", "holdout"))
    parser.add_argument("--private-dir", type=Path, required=True)
    parser.add_argument("--capture-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    return run(args.split, args.private_dir, args.capture_dir, args.out_dir)


if __name__ == "__main__":
    raise SystemExit(main())
