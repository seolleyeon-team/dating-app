"""B3-L15A local proposal-crop embedding (frozen union + deterministic edge scan). LOCAL ONLY -- never run in CI.

Datasets:
  l11_dev       B3-L11 G1-G3 DEV_VARIANT captures (+ 12 clean)      requires the ceiling-pass marker
  l14a_dev      B3-L14A G1-G3 EDGE_DEV_VARIANT captures             requires the ceiling-pass marker
  l14a_holdout  B3-L14A G4-G5 EDGE_HOLDOUT_VARIANT (stress gate)     requires the frozen selected candidate
  l11_holdout   B3-L11 G4-G5 HOLDOUT_VARIANT (one shot)              requires stress pass, audit marker, no lock

Re-renders every derivative deterministically from the untouched originals
(digest-checked against the capture rows), builds runtime proposals (frozen
union OR scan tiles), crops each with the frozen crop contract and embeds it
with the production CLIP model (local files only).  Label authority is the
ground-truth box (positive / negative / excluded).  No raw crop persisted.
Detectors are never resident while CLIP runs.  Guards as in B3-L13.
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
import avatar_edge_scan_verifier as es  # noqa: E402
import avatar_florence_ceiling_run as ceiling_run  # noqa: E402
import avatar_visual_mark_challenge_v3 as c3  # noqa: E402
import avatar_visual_mark_detectors as det  # noqa: E402

EMBED_VERSION = "avatar_edge_scan_embed_v1"
MIN_AVAILABLE_GB_TO_START = 3.0
MIN_AVAILABLE_GB_DURING = 0.6
BATCH = 16
DATASETS = {
    "l11_dev": {"dir": "l11", "prefix": "capture_", "split": "development", "construct": "l11", "variant": c3.DEV_VARIANT},
    "l14a_dev": {"dir": "l14a", "prefix": "edge_capture_", "split": "development", "construct": "l14a", "variant": eg.DEV_VARIANT},
    "l14a_holdout": {"dir": "l14a", "prefix": "edge_capture_", "split": "holdout", "construct": "l14a", "variant": eg.HOLDOUT_VARIANT},
    "l11_holdout": {"dir": "l11", "prefix": "capture_", "split": "holdout", "construct": "l11", "variant": c3.HOLDOUT_VARIANT},
}


def _available_gb() -> float:
    import psutil

    return psutil.virtual_memory().available / 2**30


def require_embedding_allowed(private_dir: Path, dataset: str) -> None:
    digest = es.contract_digest()
    if dataset in ("l11_dev", "l14a_dev"):
        es.require_ceiling_passed(private_dir, digest)
    elif dataset == "l14a_holdout":
        es.require_selected(private_dir, digest)
    elif dataset == "l11_holdout":
        es.require_selected(private_dir, digest)
        es.require_stress_passed(private_dir, digest)
        if not (Path(private_dir) / es.L11_AUDIT_NAME).exists():
            raise es.NotFrozen("original B3-L11 holdout embeddings require the unopened audit marker")
    else:
        raise ValueError(dataset)


def load_rows(capture_dir: Path, prefix: str, split: str) -> dict[str, dict[str, dict]]:
    by_cond: dict[str, dict[str, dict]] = {}
    for name in es.PROPOSAL_GENERATORS:
        path = capture_dir / f"{prefix}{name}_{split}.jsonl"
        if not path.exists():
            raise SystemExit(f"CAPTURE_MISSING {name} {split}")
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                by_cond.setdefault(r["conditionId"], {})[name] = r
    return {cid: rows for cid, rows in by_cond.items() if set(rows) == set(es.PROPOSAL_GENERATORS)}


def _render(spec, base, cid: str):
    code = cid.split(":", 1)[1]
    if spec["construct"] == "l11":
        cond = {c.code: c for c in c3.conditions(spec["variant"])}[code]
        image, truth = c3.render(base, cond)
        return image, truth, c3.image_digest(image)
    cond = {c.code: c for c in eg.conditions(spec["variant"])}[code]
    image, truth = eg.render(base, cond)
    return image, truth, eg.image_digest(image)


def _model_dir(repo: str, revision: str) -> Path:
    from huggingface_hub import snapshot_download

    return Path(snapshot_download(repo_id=repo, revision=revision, local_files_only=True))


def run(dataset: str, private_dir: Path, l11_dir: Path, l14a_dir: Path, out_dir: Path) -> int:
    import psutil
    import torch
    from PIL import Image
    from transformers import CLIPModel, CLIPProcessor

    spec = DATASETS[dataset]
    out_dir.mkdir(parents=True, exist_ok=True)
    require_embedding_allowed(out_dir, dataset)
    if dataset == "l11_holdout" and (l11_dir / det.HOLDOUT_LOCK_NAME).exists():
        raise SystemExit("HOLDOUT_ALREADY_EVALUATED")
    entries = ceiling_run._load_manifest(private_dir)
    by_id = {e["opaqueId"]: e for e in entries}
    before = ceiling_run._fingerprint(entries)
    if any(before[k][0] != by_id[k]["sha256"] for k in by_id):
        raise SystemExit("ORIGINALS_CHANGED_SINCE_INVENTORY")
    by_cond = load_rows(l11_dir if spec["dir"] == "l11" else l14a_dir, spec["prefix"], spec["split"])
    out_path = out_dir / f"edge_scan_embeddings_{dataset}.jsonl"
    done = set()
    if out_path.exists():
        for line in out_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                done.add(json.loads(line)["conditionId"])
    todo = [cid for cid in sorted(by_cond) if cid not in done]
    print(f"dataset={dataset} conditions={len(by_cond)} done={len(done)} todo={len(todo)}", flush=True)
    if not todo:
        return 0
    if _available_gb() < MIN_AVAILABLE_GB_TO_START:
        raise SystemExit(f"BLOCKED_LOCAL_RESOURCE_SAFETY available={_available_gb():.2f}GB")
    model_dir = _model_dir(es.VERIFIER["repo"], es.VERIFIER["revision"])
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
                image, truth, digest = _render(spec, base_cache[base_id], cid)
                for r in rows.values():
                    if r.get("derivativeDigest") and r["derivativeDigest"] != digest:
                        raise SystemExit(f"DERIVATIVE_DIGEST_MISMATCH {cid}")
            props = es.runtime_proposals({name: r["detections"] for name, r in rows.items()}, image.size)
            crops = [image.crop(es.runtime_crop(p["box"], image.size)) for p in props]
            embeddings = []
            for start in range(0, len(crops), BATCH):
                inputs = processor(images=crops[start:start + BATCH], return_tensors="pt")
                feats = model.get_image_features(pixel_values=inputs["pixel_values"])
                feats = feats / feats.norm(dim=-1, keepdim=True)
                embeddings.extend([[round(float(v), 6) for v in row] for row in feats.tolist()])
            record = {"embedVersion": EMBED_VERSION, "dataset": dataset, "conditionId": cid, "opaqueId": base_id, "groupKey": any_row["groupKey"], "clean": clean, "meta": any_row.get("meta", {}),
                      "imageSize": list(image.size), "groundTruth": truth,
                      "proposals": [{"proposalId": f"{dataset}:{cid}#{k}", "source": p["source"], "box": p["box"], "label": es.proposal_label(p, truth, clean_image=clean), "embedding": emb}
                                    for k, (p, emb) in enumerate(zip(props, embeddings))]}
            n_props += len(props)
            sink.write(json.dumps(record) + "\n")
            sink.flush()
            peak = max(peak, process.memory_info().rss)
            del crops
            gc.collect()
            if index % 10 == 0 or index == len(todo):
                print(f"{index}/{len(todo)} proposals={n_props} rss={peak / 2**30:.2f}GB avail={_available_gb():.2f}GB", flush=True)
    if ceiling_run._fingerprint(entries) != before:
        raise SystemExit("ORIGINALS_CHANGED")
    meta = {"embedVersion": EMBED_VERSION, "dataset": dataset, "verifier": {k: es.VERIFIER[k] for k in ("repo", "revision", "license", "embeddingDim")}, "modelLoadSec": round(load_sec, 1),
            "peakRssGb": round(peak / 2**30, 2), "conditionsEmbeddedThisRun": len(todo), "proposalsEmbeddedThisRun": n_props, "originalsUnchanged": True, "contractDigestPrefix": es.contract_digest()[:12]}
    (out_dir / f"edge_scan_embed_meta_{dataset}.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps(meta, indent=2), flush=True)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, choices=sorted(DATASETS))
    parser.add_argument("--private-dir", type=Path, required=True)
    parser.add_argument("--l11-dir", type=Path, required=True)
    parser.add_argument("--l14a-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    return run(args.dataset, args.private_dir, args.l11_dir, args.l14a_dir, args.out_dir)


if __name__ == "__main__":
    raise SystemExit(main())
