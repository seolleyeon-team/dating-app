from __future__ import annotations

import io
from dataclasses import dataclass
from typing import BinaryIO, Optional, Union

from PIL import Image, ImageOps

ImageInput = Union[bytes, bytearray, memoryview, BinaryIO, Image.Image]


@dataclass(frozen=True)
class NormalizedImage:
    image: Image.Image
    width: int
    height: int
    exif_orientation_applied: bool


class ImageOrientationNormalizer:
    """Apply EXIF orientation once, strip EXIF, return RGB image."""

    def normalize(self, image_data: ImageInput) -> Optional[NormalizedImage]:
        try:
            if isinstance(image_data, Image.Image):
                source = image_data
                # Caller-owned image: copy before mutating orientation.
                working = source.copy()
                working.load()
            else:
                if isinstance(image_data, memoryview):
                    raw = image_data.tobytes()
                elif isinstance(image_data, (bytes, bytearray)):
                    raw = bytes(image_data)
                else:
                    raw = image_data.read()
                with Image.open(io.BytesIO(raw)) as opened:
                    opened.load()
                    working = opened.copy()

            had_exif = bool(getattr(working, "getexif", lambda: {})())
            transposed = ImageOps.exif_transpose(working)
            if transposed is None:
                transposed = working
            rgb = transposed.convert("RGB")
            # Drop residual EXIF by round-tripping through a clean image.
            clean = Image.new("RGB", rgb.size)
            clean.paste(rgb)
            return NormalizedImage(
                image=clean,
                width=clean.size[0],
                height=clean.size[1],
                exif_orientation_applied=had_exif,
            )
        except Exception:
            return None


__all__ = ["ImageOrientationNormalizer", "NormalizedImage"]
