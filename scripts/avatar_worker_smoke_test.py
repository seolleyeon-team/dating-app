from __future__ import annotations

import argparse
import io
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]
AI_MODEL_DIR = REPO_ROOT / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

from avatar_generation.model_adapters.azure_contracts import AZURE_GPT_IMAGE_2_MODEL_ID
from avatar_generation.qa import run_avatar_candidate_qa
from avatar_generation.worker import (
    AvatarGenerationError,
    parse_gcs_uri,
    process_avatar_generation_payload,
    redact_gcs_ref,
)


class FakeSnapshot:
    def __init__(self, data: Optional[Mapping[str, Any]]) -> None:
        self._data = data
        self.exists = data is not None

    def to_dict(self) -> Dict[str, Any]:
        return dict(self._data or {})


class FakeDocRef:
    def __init__(self, store: Dict[str, Dict[str, Dict[str, Any]]], collection: str, doc_id: str) -> None:
        self.store = store
        self.collection = collection
        self.doc_id = doc_id

    def get(self) -> FakeSnapshot:
        return FakeSnapshot(self.store.get(self.collection, {}).get(self.doc_id))

    def set(self, data: Dict[str, Any], merge: bool = True) -> None:
        collection = self.store.setdefault(self.collection, {})
        if merge and self.doc_id in collection:
            collection[self.doc_id].update(data)
        else:
            collection[self.doc_id] = dict(data)

    def update(self, data: Dict[str, Any]) -> None:
        self.set(data, merge=True)


class FakeCollection:
    def __init__(self, store: Dict[str, Dict[str, Dict[str, Any]]], name: str) -> None:
        self.store = store
        self.name = name

    def document(self, doc_id: str) -> FakeDocRef:
        return FakeDocRef(self.store, self.name, doc_id)


class FakeFirestore:
    def __init__(self, data: Dict[str, Dict[str, Dict[str, Any]]]) -> None:
        self.data = data

    def collection(self, name: str) -> FakeCollection:
        return FakeCollection(self.data, name)


class FakeBlob:
    def __init__(self, data: bytes = b"") -> None:
        self.data = data
        self.cache_control: Optional[str] = None

    def exists(self) -> bool:
        return bool(self.data)

    def download_as_bytes(self) -> bytes:
        return self.data

    def upload_from_string(self, data: bytes, **_kwargs: Any) -> None:
        self.data = data

    def patch(self) -> None:
        return None


class FakeBucket:
    def __init__(self, blobs: Dict[str, FakeBlob]) -> None:
        self.blobs = blobs

    def blob(self, path: str) -> FakeBlob:
        return self.blobs.setdefault(path, FakeBlob())


class FakeStorage:
    def __init__(self, buckets: Dict[str, FakeBucket]) -> None:
        self.buckets = buckets

    def bucket(self, name: str) -> FakeBucket:
        return self.buckets.setdefault(name, FakeBucket({}))


def _png_bytes() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (32, 32), color=(128, 96, 80)).save(out, format="PNG")
    return out.getvalue()


def _detect_dependencies() -> Dict[str, Any]:
    deps: Dict[str, Any] = {
        "torch": {"available": False, "cudaAvailable": False},
    }
    try:
        import torch

        deps["torch"] = {
            "available": True,
            "version": getattr(torch, "__version__", "unknown"),
            "cudaAvailable": bool(torch.cuda.is_available()),
        }
    except Exception as exc:
        deps["torch"]["error"] = exc.__class__.__name__

    return deps


def _load_payload(path: str) -> Dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise AvatarGenerationError("--payload_json must contain a JSON object.")
    return payload


def _build_payload(args: argparse.Namespace) -> Dict[str, Any]:
    if args.payload_json:
        payload = _load_payload(args.payload_json)
    else:
        payload = {
            "jobId": args.job_id,
            "uid": args.uid,
            "sourcePhotoIds": ["smoke_source_001"],
            "sourcePhotoRefs": [args.source_gcs_uri],
            "candidateCount": args.candidate_count,
            "modelId": AZURE_GPT_IMAGE_2_MODEL_ID,
            "jobType": "avatar_generation",
            "schemaVersion": "avatar_job_v1",
            "idempotencyKey": f"{args.uid}:smoke_source_001:avatar_generation_v1",
        }

    if args.job_id:
        payload["jobId"] = args.job_id
    if args.uid:
        payload["uid"] = args.uid
    if args.source_gcs_uri:
        payload["sourcePhotoRefs"] = [args.source_gcs_uri]
    if args.candidate_count:
        payload["candidateCount"] = args.candidate_count
    return payload


def _fake_firestore(payload: Mapping[str, Any]) -> FakeFirestore:
    job_id = str(payload["jobId"])
    uid = str(payload["uid"])
    source_photo_ids = payload.get("sourcePhotoIds")
    source_photo_id = (
        str(source_photo_ids[0])
        if isinstance(source_photo_ids, list) and source_photo_ids
        else "smoke_source_001"
    )
    source_ref = str(payload["sourcePhotoRefs"][0])
    return FakeFirestore(
        {
            "avatarJobs": {
                job_id: {
                    "jobId": job_id,
                    "uid": uid,
                    "status": "queued",
                    "sourcePhotoIds": [source_photo_id],
                    "sourcePhotoRefs": [source_ref],
                }
            },
            "userPrivateMedia": {
                uid: {
                    "currentAvatarSourcePhotoId": source_photo_id,
                    "currentAvatarJobId": job_id,
                    "avatarSourceSelectionVersion": 1,
                    "photoConsent": {
                        "avatarGeneration": True,
                        "profileDisplayOriginalPhoto": False,
                    },
                    "sourcePhotos": [
                        {
                            "photoId": source_photo_id,
                            "gcsUri": source_ref,
                            "status": "active",
                            "avatarGenerationState": "current",
                            "purpose": {"avatarGeneration": True},
                        }
                    ],
                }
            },
            "avatarCandidates": {},
        }
    )


def _fake_storage(payload: Mapping[str, Any]) -> FakeStorage:
    source_ref = parse_gcs_uri(str(payload["sourcePhotoRefs"][0]))
    return FakeStorage({source_ref.bucket: FakeBucket({source_ref.path: FakeBlob(_png_bytes())})})


def _smoke_qa(source_ref: str, candidate_ref: str, metadata: Dict[str, Any]):
    qa_metadata = dict(metadata)
    qa_metadata["qaSignals"] = {
        "adultLike": True,
        "brandFit": True,
        "cropConsistent": True,
        "logoTextWatermarkDetected": False,
        "uniqueMarkCopied": False,
        "faceSimilarityScore": 0.10,
        "childlikeScore": 0.05,
        "beautificationScore": 0.05,
    }
    return run_avatar_candidate_qa(source_ref, candidate_ref, qa_metadata)


def _write_report(report: Dict[str, Any], path: Optional[str]) -> None:
    encoded = json.dumps(report, ensure_ascii=False, indent=2)
    if path:
        Path(path).write_text(encoded + "\n", encoding="utf-8")
    print(encoded)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Smoke test the Seolleyeon avatar worker.")
    parser.add_argument("--payload_json")
    parser.add_argument("--job_id", default="avatar_smoke_job")
    parser.add_argument("--uid", default="avatar_smoke_user")
    parser.add_argument(
        "--source_gcs_uri",
        default="gs://seolleyeon-final-private-source-photos/users/avatar_smoke_user/source/smoke_source_001.jpg",
    )
    parser.add_argument("--candidate_count", type=int, default=4)
    parser.add_argument("--dry_run", action="store_true")
    parser.add_argument("--real_gpu", action="store_true")
    parser.add_argument("--output_report_json")
    args = parser.parse_args(argv)

    if args.real_gpu:
        parser.error("--real_gpu is retired: local-model generation no longer exists. Use --dry_run.")

    payload = _build_payload(args)
    mode = "dry_run"
    dependencies = _detect_dependencies()
    report: Dict[str, Any] = {
        "status": "started",
        "mode": mode,
        "jobId": str(payload.get("jobId", "")),
        "uid": str(payload.get("uid", "")),
        "sourceRef": redact_gcs_ref(str(payload.get("sourcePhotoRefs", [""])[0])),
        "candidateCount": int(payload.get("candidateCount") or 0),
        "dependencies": dependencies,
    }

    try:
        if mode == "dry_run":
            with tempfile.TemporaryDirectory(prefix="avatar-worker-smoke-") as temp_dir:
                fake_storage = _fake_storage(payload)

                def qa_runner(source_ref: str, candidate_ref: str, metadata: Dict[str, Any]):
                    qa_metadata = dict(metadata)
                    qa_metadata["_storage_client"] = fake_storage
                    return _smoke_qa(source_ref, candidate_ref, qa_metadata)

                result = process_avatar_generation_payload(
                    payload,
                    firestore_client=_fake_firestore(payload),
                    storage_client=fake_storage,
                    qa_runner=qa_runner,
                    mode=mode,
                    fixture_output_dir=Path(temp_dir),
                )
        else:
            result = process_avatar_generation_payload(payload, mode=mode)
        report["status"] = "ok"
        report["result"] = result.to_dict()
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = str(exc)[:240]
        _write_report(report, args.output_report_json)
        return 1

    _write_report(report, args.output_report_json)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
