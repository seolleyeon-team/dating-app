from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence, Tuple

from PIL import Image, ImageDraw, ImageFilter

from .config import SmallFacePipelineConfig
from .types import CropTransform, InternalFaceDetection, NormalizedBox


@dataclass(frozen=True)
class NeutralizationResult:
    image: Image.Image
    secondary_faces_detected: int
    secondary_faces_neutralized: int
    method_version: str = "secondary_face_neutralize_v1"


class SecondaryFaceNeutralizer:
    def __init__(self, config: SmallFacePipelineConfig) -> None:
        self._config = config

    def apply(
        self,
        crop_image: Image.Image,
        *,
        secondary_faces: Sequence[InternalFaceDetection],
        crop_transform: CropTransform,
        original_width: int,
        original_height: int,
        primary: InternalFaceDetection,
    ) -> NeutralizationResult:
        if not secondary_faces:
            return NeutralizationResult(
                image=crop_image,
                secondary_faces_detected=0,
                secondary_faces_neutralized=0,
            )

        working = crop_image.copy().convert("RGB")
        neutralized = 0
        for face in secondary_faces:
            crop_box = crop_transform.original_to_crop_normalized(
                face.bbox_normalized,
                original_width,
                original_height,
            )
            if crop_box.area <= 0.0:
                continue
            # Skip boxes that do not intersect the crop meaningfully.
            if crop_box.width < 0.01 or crop_box.height < 0.01:
                continue
            if crop_box.iou(
                crop_transform.original_to_crop_normalized(
                    primary.bbox_normalized,
                    original_width,
                    original_height,
                )
            ) >= 0.35:
                # Overlap with primary — fail closed at selector; skip neutralize.
                continue
            if self._neutralize_box(working, crop_box):
                neutralized += 1

        return NeutralizationResult(
            image=working,
            secondary_faces_detected=len(secondary_faces),
            secondary_faces_neutralized=neutralized,
        )

    def _neutralize_box(self, image: Image.Image, box: NormalizedBox) -> bool:
        width, height = image.size
        expand = self._config.secondary_mask_expand
        x0 = int(round((box.x_min - box.width * expand) * width))
        y0 = int(round((box.y_min - box.height * expand) * height))
        x1 = int(round((box.x_max + box.width * expand) * width))
        y1 = int(round((box.y_max + box.height * expand) * height))
        x0 = max(0, min(width, x0))
        y0 = max(0, min(height, y0))
        x1 = max(0, min(width, x1))
        y1 = max(0, min(height, y1))
        if x1 - x0 < 2 or y1 - y0 < 2:
            return False

        region = image.crop((x0, y0, x1, y1))
        blurred = region.resize(
            (max(1, region.size[0] // 8), max(1, region.size[1] // 8)),
            Image.Resampling.BILINEAR,
        ).resize(region.size, Image.Resampling.NEAREST)
        blurred = blurred.filter(
            ImageFilter.GaussianBlur(radius=self._config.secondary_blur_radius)
        )

        mask = Image.new("L", region.size, 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0, region.size[0] - 1, region.size[1] - 1), fill=255)
        mask = mask.filter(ImageFilter.GaussianBlur(radius=max(2, region.size[0] // 10)))
        image.paste(Image.composite(blurred, region, mask), (x0, y0))
        return True


__all__ = ["SecondaryFaceNeutralizer", "NeutralizationResult"]
