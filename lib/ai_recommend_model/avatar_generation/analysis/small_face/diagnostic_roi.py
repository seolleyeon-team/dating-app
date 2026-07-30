"""Pure ROI helpers for local small-face quality diagnostics.

The returned geometry is process-local. Callers must not serialize coordinates.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from PIL import Image, ImageFilter

from .types import PixelBox


@dataclass(frozen=True)
class DiagnosticRoi:
    image: Image.Image = field(repr=False, compare=False)
    valid_mask: Image.Image = field(repr=False, compare=False)
    source_box: PixelBox = field(repr=False, compare=False)

    @property
    def valid_pixel_ratio(self) -> float:
        histogram = self.valid_mask.convert("L").histogram()
        total = max(1, self.valid_mask.size[0] * self.valid_mask.size[1])
        valid = sum(histogram[128:])
        return valid / float(total)


def full_image_roi(image: Image.Image) -> DiagnosticRoi:
    rgb = image.convert("RGB")
    return DiagnosticRoi(
        image=rgb,
        valid_mask=Image.new("L", rgb.size, 255),
        source_box=PixelBox(0, 0, rgb.size[0], rgb.size[1]),
    )


def face_quality_roi(
    image: Image.Image,
    face_box: PixelBox,
    *,
    margin_ratio: float = 0.12,
) -> DiagnosticRoi:
    """Build a modestly expanded native face region for quality measurement."""

    face = face_box.clamp(*image.size)
    margin_x = int(round(face.width * max(0.0, float(margin_ratio))))
    margin_y = int(round(face.height * max(0.0, float(margin_ratio))))
    desired = PixelBox(
        face.x_min - margin_x,
        face.y_min - margin_y,
        face.x_max + margin_x,
        face.y_max + margin_y,
    )
    return extract_with_valid_mask(image, desired)


def head_shoulders_native_roi(
    image: Image.Image,
    face_box: PixelBox,
    *,
    expand_horizontal: float,
    expand_top: float,
    expand_bottom: float,
) -> DiagnosticRoi:
    """Mirror the generation crop geometry without resizing or losing its mask."""

    face = face_box.clamp(*image.size)
    face_width = max(1, face.width)
    face_height = max(1, face.height)
    center_x = (face.x_min + face.x_max) / 2.0
    center_y = (face.y_min + face.y_max) / 2.0 + face_height * 0.08
    x_min = int(round(center_x - face_width * (0.5 + expand_horizontal)))
    x_max = int(round(center_x + face_width * (0.5 + expand_horizontal)))
    y_min = int(round(center_y - face_height * (0.5 + expand_top)))
    y_max = int(round(center_y + face_height * (0.5 + expand_bottom)))
    side = max(1, x_max - x_min, y_max - y_min)
    x_min = int(round(center_x - side / 2.0))
    y_min = int(round(center_y - side / 2.0))
    return extract_with_valid_mask(
        image,
        PixelBox(x_min, y_min, x_min + side, y_min + side),
    )


def extract_with_valid_mask(
    image: Image.Image,
    desired_box: PixelBox,
    *,
    neutral_fill: tuple[int, int, int] = (247, 242, 236),
) -> DiagnosticRoi:
    """Extract a possibly out-of-bounds region and mark source-backed pixels."""

    output_width = max(1, desired_box.width)
    output_height = max(1, desired_box.height)
    output = Image.new("RGB", (output_width, output_height), neutral_fill)
    mask = Image.new("L", output.size, 0)
    source = desired_box.clamp(*image.size)
    if source.width > 0 and source.height > 0:
        region = image.convert("RGB").crop(source.as_tuple())
        offset = (
            source.x_min - desired_box.x_min,
            source.y_min - desired_box.y_min,
        )
        output.paste(region, offset)
        valid = Image.new("L", region.size, 255)
        mask.paste(valid, offset)
    return DiagnosticRoi(
        image=output,
        valid_mask=mask,
        source_box=desired_box,
    )


def canonical_downscale(
    roi: DiagnosticRoi,
    *,
    canonical_short_side: int = 160,
) -> tuple[DiagnosticRoi, float]:
    """Downscale to a canonical short side; never invent pixels by upscaling."""

    width, height = roi.image.size
    short_side = max(1, min(width, height))
    scale = min(1.0, max(1, int(canonical_short_side)) / float(short_side))
    if scale >= 1.0:
        return roi, 1.0
    size = (
        max(1, int(round(width * scale))),
        max(1, int(round(height * scale))),
    )
    resized_mask = roi.valid_mask.resize(size, Image.Resampling.NEAREST)
    # A destination pixel can sample source pixels up to three source pixels
    # away under LANCZOS. Exclude that projected support near padding so neutral
    # fill cannot influence canonical quality metrics.
    support_radius = 3
    resized_mask = resized_mask.filter(
        ImageFilter.MinFilter(size=support_radius * 2 + 1)
    )
    return (
        DiagnosticRoi(
            image=roi.image.resize(size, Image.Resampling.LANCZOS),
            valid_mask=resized_mask,
            source_box=roi.source_box,
        ),
        scale,
    )


def resize_roi(
    roi: DiagnosticRoi,
    size: tuple[int, int],
) -> tuple[DiagnosticRoi, float]:
    """Resize an ROI and its valid-pixel mask for post-crop stage diagnostics."""

    target = (max(1, int(size[0])), max(1, int(size[1])))
    source_short = max(1, min(roi.image.size))
    scale = min(target) / float(source_short)
    return (
        DiagnosticRoi(
            image=roi.image.resize(target, Image.Resampling.LANCZOS),
            valid_mask=roi.valid_mask.resize(target, Image.Resampling.NEAREST),
            source_box=roi.source_box,
        ),
        scale,
    )


__all__ = [
    "DiagnosticRoi",
    "canonical_downscale",
    "extract_with_valid_mask",
    "face_quality_roi",
    "full_image_roi",
    "head_shoulders_native_roi",
    "resize_roi",
]
