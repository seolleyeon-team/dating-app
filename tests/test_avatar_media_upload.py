import io
import sys
from pathlib import Path

from PIL import Image

AI_MODEL_DIR = Path(__file__).resolve().parents[1] / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

from avatar_media_upload import (
    PRIVATE_SOURCE_BUCKET,
    build_photo_id,
    build_source_photo_gcs_uri,
    build_user_private_media_update,
    sha256_bytes,
    strip_exif,
)


def _jpeg_with_metadata() -> bytes:
    image = Image.new("RGB", (8, 8), color=(20, 40, 60))
    out = io.BytesIO()
    image.save(out, format="JPEG", exif=b"Exif\x00\x00test")
    return out.getvalue()


def test_strip_exif_keeps_image_loadable():
    cleaned = strip_exif(_jpeg_with_metadata())
    with Image.open(io.BytesIO(cleaned)) as image:
        assert image.size == (8, 8)
        assert not image.getexif()


def test_source_uri_uses_private_bucket():
    digest = sha256_bytes(b"photo")
    photo_id = build_photo_id(digest)
    assert build_source_photo_gcs_uri("u1", photo_id) == (
        f"gs://{PRIVATE_SOURCE_BUCKET}/users/u1/source/{photo_id}.jpg"
    )


def test_private_media_update_dedupes_active_sha():
    digest = sha256_bytes(b"photo")
    photo_id = build_photo_id(digest)
    payload = build_user_private_media_update(
        uid="u1",
        photo_id=photo_id,
        storage_bucket=PRIVATE_SOURCE_BUCKET,
        storage_path=f"users/u1/source/{photo_id}.jpg",
        content_type="image/jpeg",
        size_bytes=123,
        sha256=digest,
        existing_source_photos=[{"photoId": photo_id, "sha256": digest, "status": "active"}],
        server_timestamp="SERVER_TS",
    )
    assert len(payload["sourcePhotos"]) == 1
    assert payload["photoConsent"]["profileDisplayOriginalPhoto"] is False
    assert payload["clip"]["embeddingStatus"] == "pending"
