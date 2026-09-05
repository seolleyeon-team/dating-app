from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from PIL import Image, ImageOps

from .config import SmallFacePipelineConfig
from .types import CropTransform, InternalFaceDetection, PixelBox


@dataclass(frozen=True)
class HeadShouldersCropResult:
    image: Image.Image
    transform: CropTransform
    used_max_size: bool


class HeadShouldersCropper:
    def __init__(self, config: SmallFacePipelineConfig) -> None:
        self._config = config

    def crop(
        self,
        image: Image.Image,
        primary: InternalFaceDetection,
    ) -> HeadShouldersCropResult:
        width, height = image.size
        face = primary.bbox_pixels.clamp(width, height)
        fw = max(1, face.width)
        fh = max(1, face.height)
        cx = (face.x_min + face.x_max) / 2.0
        cy = (face.y_min + face.y_max) / 2.0 + fh * 0.08

        expand_h = self._config.crop_expand_horizontal
        expand_top = self._config.crop_expand_top
        expand_bottom = self._config.crop_expand_bottom

        x0 = int(round(cx - fw * (0.5 + expand_h)))
        x1 = int(round(cx + fw * (0.5 + expand_h)))
        y0 = int(round(cy - fh * (0.5 + expand_top)))
        y1 = int(round(cy + fh * (0.5 + expand_bottom)))

        # Force a square crop aligned to the shared analysis contract.
        side = max(x1 - x0, y1 - y0, 1)
        x0 = int(round(cx - side / 2.0))
        y0 = int(round(cy - side / 2.0))
        x1 = x0 + side
        y1 = y0 + side

        # Keep desired box in original image coordinates (may extend outside).
        desired_original = PixelBox(x0, y0, x1, y1)
        pad_left = max(0, -desired_original.x_min)
        pad_top = max(0, -desired_original.y_min)
        pad_right = max(0, desired_original.x_max - width)
        pad_bottom = max(0, desired_original.y_max - height)

        working = image
        crop_box_working = desired_original
        if pad_left or pad_top or pad_right or pad_bottom:
            # Neutral solid padding — never reflect other faces/text into the canvas.
            working = ImageOps.expand(
                image,
                border=(pad_left, pad_top, pad_right, pad_bottom),
                fill=(247, 242, 236),
            )
            crop_box_working = PixelBox(
                desired_original.x_min + pad_left,
                desired_original.y_min + pad_top,
                desired_original.x_max + pad_left,
                desired_original.y_max + pad_top,
            )

        cropped = working.crop(crop_box_working.as_tuple())
        target = self._config.primary_crop_target_size
        used_max = False
        if (
            primary.face_short_side_px < self._config.min_short_side_trait_px
            and self._config.primary_crop_max_size > target
        ):
            target = self._config.primary_crop_max_size
            used_max = True

        resized = cropped.resize((target, target), Image.Resampling.LANCZOS)
        scale = target / float(max(1, desired_original.width))
        # padded_box stores the crop window in original coordinates for mapping.
        transform = CropTransform(
            original_box=face,
            padded_box=desired_original,
            target_width=target,
            target_height=target,
            scale_x=scale,
            scale_y=scale,
            offset_x=0.0,
            offset_y=0.0,
        )
        return HeadShouldersCropResult(
            image=resized,
            transform=transform,
            used_max_size=used_max,
        )


__all__ = ["HeadShouldersCropper", "HeadShouldersCropResult"]
