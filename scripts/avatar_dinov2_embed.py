"""B3-L16A local DINOv2 proposal-crop embedding. LOCAL ONLY -- never run in CI.

Same datasets, proposals, crops and labels as B3-L15A (identity verified
against the B3-L15A embedding records where they exist); only the embedding
model changes: facebook/dinov2-base @ pinned revision, official processor
defaults, pooler_output (final-LayerNorm [CLS]), L2-normalized.  Detectors are
never loaded.  Guards as in B3-L15A (start 3.0 GB, per-row 0.6 GB; never
lowered); checkpoint-resume; no raw crop persisted.
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

import avatar_dinov2_verifier as dv  # noqa: E402
import avatar_edge_scan_embed as em  # noqa: E402
import avatar_florence_ceiling_run as ceiling_run  # noqa: E402
import avatar_visual_mark_detectors as det  # noqa: E402

EMBED_VERSION = "avatar_dinov2_embed_v1"
MIN_AVAILABLE_GB_TO_START = 3.0
MIN_AVAILABLE_GB_DURING = 0.6
BATCH = 16
DATASETS = dict(em.DATASETS)


def _available_gb() -> float:
    import psutil

    return psutil.virtual_memory().available / 2**30


def processor_kwargs() -> dict:
    """Official preprocessor defaults only; nothing overridden."""

    return {}


def require_embedding_allowed(private_dir: Path, dataset: str) -> None:
    digest = dv.contract_digest()
    dv.require_frozen(private_dir, digest)
    if dataset in ("l11_dev", "l14a_dev"):
        return
    if dataset == "l14a_holdout":
        dv.require_selected(private_dir, digest)
        return
    if dataset == "l11_holdout":
        dv.require_selected(private_dir, digest)
        dv.require_stress_passed(private_dir, digest)
        if not (Path(private_dir) / dv.L11_AUDIT_NAME).exists():
            raise dv.NotFrozen("original B3-L11 holdout embeddings require the unopened audit marker")
        return
    raise ValueError(dataset)


def provenance_exact(l15a_record, props, labels) -> bool:
    """Same proposal identity as the B3-L15A record: ids, sources, boxes and labels, in order."""

    prior = l15a_record["proposals"]
    if len(prior) != len(props):
        return False
    return all(a["proposalId"] == b["proposalId"] and a["source"] == b["source"] and [float(v) for v in a["box"]] == [float(v) for v in b["box"]] and a["label"] == lab
               for a, b, lab in zip(prior, props, labels))


def _model_dir() -> Path:
    from huggingface_hub import snapshot_download

    return Path(snapshot_download(repo_id=dv.VERIFIER["repo"], revision=dv.require_pinned_revision(dv.VERIFIER["revision"]), local_files_only=True))


def run(dataset: str, private_dir: Path, l11_dir: Path, l14a_dir: Path, l15a_dir: Path, out_dir: Path) -> int:
    import psutil
    import torch
    from PIL import Image
    from transformers import AutoImageProcessor, Dinov2Model

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
    by_cond = em.load_rows(l11_dir if spec["dir"] == "l11" else l14a_dir, spec["prefix"], spec["split"])
    prior_path = Path(l15a_dir) / f"edge_scan_embeddings_{dataset}.jsonl"
    prior = {}
    if prior_path.exists():
        for line in prior_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                prior[r["conditionId"]] = r
    out_path = out_dir / f"{dv.EMBEDDINGS_PREFIX}{dataset}.jsonl"
    done = set()
    if out_path.exists():
        for line in out_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                done.add(json.loads(line)["conditionId"])
    todo = [cid for cid in sorted(by_cond) if cid not in done]
    print(f"dataset={dataset} conditions={len(by_cond)} priorRecords={len(prior)} done={len(done)} todo={len(todo)}", flush=True)
    if not todo:
        return 0
    if _available_gb() < MIN_AVAILABLE_GB_TO_START:
        raise SystemExit(f"BLOCKED_LOCAL_RESOURCE_SAFETY available={_available_gb():.2f}GB")
    model_dir = _model_dir()
    t0 = time.perf_counter()
    processor = AutoImageProcessor.from_pretrained(model_dir, local_files_only=True, **processor_kwargs())
    model = Dinov2Model.from_pretrained(model_dir, local_files_only=True)
    model.eval()
    torch.set_grad_enabled(False)
    load_sec = time.perf_counter() - t0
    process = psutil.Process()
    peak = process.memory_info().rss
    base_cache: dict = {}
    n_props = 0
    exact = 0
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
                image, truth, digest = em._render(spec, base_cache[base_id], cid)
                for r in rows.values():
                    if r.get("derivativeDigest") and r["derivativeDigest"] != digest:
                        raise SystemExit(f"DERIVATIVE_DIGEST_MISMATCH {cid}")
            props = [{"proposalId": f"{dataset}:{cid}#{k}", **p} for k, p in enumerate(dv.runtime_proposals({name: r["detections"] for name, r in rows.items()}, image.size))]
            labels = [dv.proposal_label(p, truth, clean_image=clean) for p in props]
            if cid in prior:
                if not provenance_exact(prior[cid], props, labels):
                    raise SystemExit(f"PROPOSAL_PROVENANCE_MISMATCH {cid}")
                exact += 1
            crops = [image.crop(dv.runtime_crop(p["box"], image.size)) for p in props]
            embeddings = []
            for start in range(0, len(crops), BATCH):
                inputs = processor(images=crops[start:start + BATCH], return_tensors="pt")
                feats = dv.image_embedding(model(pixel_values=inputs["pixel_values"]))
                feats = feats / feats.norm(dim=-1, keepdim=True)
                embeddings.extend([[round(float(v), 6) for v in row] for row in feats.tolist()])
            record = {"embedVersion": EMBED_VERSION, "dataset": dataset, "conditionId": cid, "opaqueId": base_id, "groupKey": any_row["groupKey"], "clean": clean, "meta": any_row.get("meta", {}),
                      "imageSize": list(image.size), "groundTruth": truth, "proposalProvenanceExact": cid in prior,
                      "proposals": [{"proposalId": p["proposalId"], "source": p["source"], "box": p["box"], "label": lab, "embedding": emb} for p, lab, emb in zip(props, labels, embeddings)]}
            n_props += len(props)
            sink.write(json.dumps(record) + "\n")
            sink.flush()
            peak = max(peak, process.memory_info().rss)
            del crops
            gc.collect()
            if index % 10 == 0 or index == len(todo):
                print(f"{index}/{len(todo)} proposals={n_props} exactProvenance={exact} rss={peak / 2**30:.2f}GB avail={_available_gb():.2f}GB", flush=True)
    if ceiling_run._fingerprint(entries) != before:
        raise SystemExit("ORIGINALS_CHANGED")
    meta = {"embedVersion": EMBED_VERSION, "dataset": dataset, "verifier": {k: dv.VERIFIER[k] for k in ("repo", "revision", "license", "embeddingDim", "embeddingSemantics")}, "modelLoadSec": round(load_sec, 1),
            "peakRssGb": round(peak / 2**30, 2), "conditionsEmbeddedThisRun": len(todo), "proposalsEmbeddedThisRun": n_props, "priorProvenanceExactThisRun": exact, "originalsUnchanged": True,
            "contractDigestPrefix": dv.contract_digest()[:12]}
    (out_dir / f"dinov2_embed_meta_{dataset}.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps(meta, indent=2), flush=True)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, choices=sorted(DATASETS))
    parser.add_argument("--private-dir", type=Path, required=True)
    parser.add_argument("--l11-dir", type=Path, required=True)
    parser.add_argument("--l14a-dir", type=Path, required=True)
    parser.add_argument("--l15a-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    return run(args.dataset, args.private_dir, args.l11_dir, args.l14a_dir, args.l15a_dir, args.out_dir)


if __name__ == "__main__":
    raise SystemExit(main())
