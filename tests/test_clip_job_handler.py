import base64
import json
import sys
from pathlib import Path

import pytest

AI_MODEL_DIR = Path(__file__).resolve().parents[1] / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

from seolleyeon_clip_job_handler import (
    build_clip_embedding_document,
    decode_clip_job_payload,
    process_clip_job_payload,
    select_private_clip_sources,
)


def _payload():
    return {
        "uid": "u1",
        "sourcePhotoIds": ["src_001"],
        "sourcePhotoRefs": [
            "gs://seolleyeon-final-private-source-photos/users/u1/source/src_001.jpg"
        ],
        "embeddingVersion": "clip-vit-large-patch14_v1",
        "jobType": "clip_embedding",
        "schemaVersion": "clip_job_v1",
        "idempotencyKey": "u1:src_001:clip_embedding_v1",
    }


def test_decode_clip_job_payload_accepts_direct_and_pubsub_wrapper():
    direct = decode_clip_job_payload(_payload())
    assert direct["uid"] == "u1"

    encoded = base64.b64encode(json.dumps(_payload()).encode("utf-8")).decode("ascii")
    wrapped = decode_clip_job_payload({"message": {"data": encoded}})
    assert wrapped["schemaVersion"] == "clip_job_v1"


def test_decode_clip_job_payload_rejects_wrong_schema():
    payload = _payload()
    payload["schemaVersion"] = "old"
    with pytest.raises(ValueError, match="Unsupported schemaVersion"):
        decode_clip_job_payload(payload)


def test_select_private_clip_sources_filters_consent_status_scheme_and_ids():
    private_doc = {
        "photoConsent": {
            "clipRecommendation": True,
            "profileDisplayOriginalPhoto": False,
        },
        "sourcePhotos": [
            {
                "photoId": "src_001",
                "gcsUri": "gs://seolleyeon-final-private-source-photos/users/u1/source/src_001.jpg",
                "status": "active",
                "purpose": {"clipRecommendation": True},
            },
            {
                "photoId": "src_002",
                "gcsUri": "https://example.com/original.jpg",
                "status": "active",
                "purpose": {"clipRecommendation": True},
            },
            {
                "photoId": "src_003",
                "gcsUri": "gs://seolleyeon-final-private-source-photos/users/u1/source/src_003.jpg",
                "status": "deleted",
                "purpose": {"clipRecommendation": True},
            },
        ],
    }

    source_ids, refs = select_private_clip_sources(
        private_doc,
        uid="u1",
        requested_source_photo_ids=["src_001", "src_002"],
    )

    assert source_ids == ["src_001"]
    assert refs == ["gs://seolleyeon-final-private-source-photos/users/u1/source/src_001.jpg"]


def test_select_private_clip_sources_requires_no_original_display_consent():
    with pytest.raises(ValueError, match="profileDisplayOriginalPhoto"):
        select_private_clip_sources(
            {
                "photoConsent": {
                    "clipRecommendation": True,
                    "profileDisplayOriginalPhoto": True,
                },
                "sourcePhotos": [],
            },
            uid="u1",
        )


def test_select_private_clip_sources_rejects_non_allowlisted_bucket():
    with pytest.raises(ValueError, match="bucket is not allowed"):
        select_private_clip_sources(
            {
                "photoConsent": {
                    "clipRecommendation": True,
                    "profileDisplayOriginalPhoto": False,
                },
                "sourcePhotos": [
                    {
                        "photoId": "src_001",
                        "gcsUri": "gs://wrong-bucket/users/u1/source/src_001.jpg",
                        "status": "active",
                        "purpose": {"clipRecommendation": True},
                    }
                ],
            },
            uid="u1",
            allowed_buckets={"seolleyeon-final-private-source-photos"},
        )


def test_build_clip_embedding_document_shape():
    doc = build_clip_embedding_document(
        vector=[0.1, 0.2],
        dims=2,
        source_photo_ids=["src_001"],
        embedding_version="clip-vit-large-patch14_v1",
        model_id="openai/clip-vit-large-patch14",
    )

    assert doc["vector"] == [0.1, 0.2]
    assert doc["dims"] == 2
    assert doc["normalized"] is True
    assert doc["sourcePhotoIds"] == ["src_001"]


class _FakeSnapshot:
    def __init__(self, data, exists=True):
        self._data = data
        self.exists = exists

    def to_dict(self):
        return self._data


class _FakeDocument:
    def __init__(self, store, path):
        self.store = store
        self.path = path

    def get(self):
        if self.path not in self.store:
            return _FakeSnapshot({}, exists=False)
        return _FakeSnapshot(self.store[self.path], exists=True)

    def set(self, data, merge=False):
        if merge:
            existing = dict(self.store.get(self.path, {}))
            existing.update(data)
            self.store[self.path] = existing
        else:
            self.store[self.path] = data


class _FakeCollection:
    def __init__(self, store, collection):
        self.store = store
        self.collection = collection

    def document(self, uid):
        return _FakeDocument(self.store, f"{self.collection}/{uid}")


class _FakeFirestoreClient:
    def __init__(self, store):
        self.store = store

    def collection(self, name):
        return _FakeCollection(self.store, name)


class _FakeFirestoreModule:
    SERVER_TIMESTAMP = "SERVER_TIMESTAMP"

    def __init__(self, store):
        self.store = store

    def Client(self, project, database=None):
        return _FakeFirestoreClient(self.store)


class _FakeEmbedder:
    model_id = "openai/clip-vit-large-patch14"

    def __init__(self):
        self.sources = []

    def embed_profile_mean(self, sources, normalize=True):
        self.sources = list(sources)
        return [0.6, 0.8], 2


def test_process_clip_job_payload_writes_embedding_and_private_status(monkeypatch):
    store = {
        "userPrivateMedia/u1": {
            "photoConsent": {
                "clipRecommendation": True,
                "profileDisplayOriginalPhoto": False,
            },
            "sourcePhotos": [
                {
                    "photoId": "src_001",
                    "gcsUri": "gs://seolleyeon-final-private-source-photos/users/u1/source/src_001.jpg",
                    "status": "active",
                    "purpose": {"clipRecommendation": True},
                }
            ],
        }
    }
    fake_firestore = _FakeFirestoreModule(store)
    monkeypatch.setattr("seolleyeon_clip_job_handler.firestore", fake_firestore)
    embedder = _FakeEmbedder()

    result = process_clip_job_payload(
        _payload(),
        firestore_project="demo",
        embedder=embedder,
    )

    assert result["status"] == "ready"
    assert embedder.sources == [
        "gs://seolleyeon-final-private-source-photos/users/u1/source/src_001.jpg"
    ]
    assert store["clipEmbeddings/u1"]["vector"] == [0.6, 0.8]
    assert store["clipEmbeddings/u1"]["sourcePhotoIds"] == ["src_001"]
    assert store["userPrivateMedia/u1"]["clip"]["embeddingStatus"] == "ready"


def test_process_clip_job_payload_rejects_cross_user_source_path(monkeypatch):
    store = {
        "userPrivateMedia/u1": {
            "photoConsent": {
                "clipRecommendation": True,
                "profileDisplayOriginalPhoto": False,
            },
            "sourcePhotos": [
                {
                    "photoId": "src_001",
                    "gcsUri": (
                        "gs://seolleyeon-final-private-source-photos/"
                        "users/u2/source/src_001.jpg"
                    ),
                    "status": "active",
                    "purpose": {"clipRecommendation": True},
                }
            ],
        }
    }
    fake_firestore = _FakeFirestoreModule(store)
    monkeypatch.setattr("seolleyeon_clip_job_handler.firestore", fake_firestore)
    embedder = _FakeEmbedder()

    with pytest.raises(ValueError, match="source photo object path does not belong to uid"):
        process_clip_job_payload(
            _payload(),
            firestore_project="demo",
            embedder=embedder,
        )

    assert embedder.sources == []
    assert "clipEmbeddings/u1" not in store
    assert store["userPrivateMedia/u1"]["clip"]["embeddingStatus"] == "failed"
