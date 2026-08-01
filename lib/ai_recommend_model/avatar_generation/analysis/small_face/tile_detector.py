from __future__ import annotations

import time
from typing import List, Sequence, Tuple

from PIL import Image

from .config import SmallFacePipelineConfig
from .full_range_detector import FullRangeFaceDetector
from .geometry import build_tile_rects, enrich_detection, map_tile_box_to_original
from .types import InternalFaceDetection, NormalizedBox


class OverlappingTileDetector:
    def __init__(
        self,
        config: SmallFacePipelineConfig,
        detector: FullRangeFaceDetector,
    ) -> None:
        self._config = config
        self._detector = detector

    def should_run_tiles(
        self,
        full_detections: Sequence[InternalFaceDetection],
        *,
        image_width: int,
        image_height: int,
    ) -> bool:
        if not self._config.tile_fallback_enabled:
            return False
        if not full_detections:
            return True
        best = max(full_detections, key=lambda item: item.confidence)
        if best.confidence < self._config.primary_min_confidence:
            return True
        if best.face_short_side_px < self._config.min_short_side_detect_px:
            return True
        # Large images risk losing tiny faces after internal detector downscale.
        if max(image_width, image_height) >= 1600 and best.face_short_side_px < (
            self._config.min_short_side_trait_px
        ):
            return True
        return False

    def detect(
        self,
        image: Image.Image,
        *,
        grids: Sequence[int] | None = None,
    ) -> Tuple[List[InternalFaceDetection], dict]:
        width, height = image.size
        selected_grids = tuple(grids or self._config.tile_grids)
        detections: List[InternalFaceDetection] = []
        tile_count = 0
        started = time.perf_counter()
        for grid_index, grid in enumerate(selected_grids):
            # 3x3 only when earlier grids produced nothing usable.
            if grid >= 3 and grid_index > 0 and detections:
                break
            rects = build_tile_rects(
                width,
                height,
                grid=grid,
                overlap=self._config.tile_overlap,
            )
            for tile_id, rect in rects:
                if tile_count >= self._config.tile_max_count:
                    break
                tile_count += 1
                tile_image = image.crop(rect.as_tuple())
                # Use injected raw path via detector.detect on the tile crop, then
                # remap using detector_pass metadata when possible.
                raw_faces = self._detector.detect(
                    tile_image,
                    min_confidence=self._config.fallback_min_confidence,
                    detector_pass=f"tile_{grid}x{grid}",
                    tile_id=tile_id,
                )
                for face in raw_faces:
                    # face boxes are relative to the tile crop; remap to original.
                    xywh = face.bbox_normalized.as_xywh()
                    mapped = map_tile_box_to_original(
                        xywh, rect, width, height
                    )
                    detections.append(
                        enrich_detection(
                            bbox_normalized=mapped,
                            confidence=face.confidence,
                            image_width=width,
                            image_height=height,
                            detector_pass=face.detector_pass,
                            tile_id=tile_id,
                            keypoints_normalized=(),
                            image=image,
                        )
                    )
            if tile_count >= self._config.tile_max_count:
                break
            if detections and grid == 2:
                # Prefer stopping after successful 2x2.
                break

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return detections, {
            "faceDetectionTileMs": elapsed_ms,
            "tileCount": tile_count,
        }


__all__ = ["OverlappingTileDetector"]
