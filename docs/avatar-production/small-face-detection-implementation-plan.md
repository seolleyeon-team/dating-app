# Small-face detection implementation plan

## Current implementation

- Primary detector path: `MediaPipeFaceDetector` runs **FaceLandmarker on the full image** when `face_landmarker.task` is present (`analysis/detectors.py`).
- Fallback: MediaPipe Solutions `FaceDetection(model_selection=1)` created **per detect call**.
- EXIF: `_load_image` converts to RGB but does **not** apply `ImageOps.exif_transpose`.
- Secondary faces: kept on in-memory `SourceAnalysisResult.faces`, omitted from `to_document()` (good for privacy). Preprocessing reads `faces` via `face_regions_from_source_analysis`.
- Analysis vs generation references: already split in `ReferencePreprocessResult.analysis_image` / `.image`.
- `production_bridge`: treated production-like in `worker.py` (`BRIDGE_ENVIRONMENT`).

## Exact change files

| File | Change |
|------|--------|
| `analysis/small_face/*` | New modular pipeline |
| `analysis/config.py` | Small-face env flags |
| `analysis/source_analyzer.py` | EXIF + pipeline wire-in |
| `analysis/detectors.py` | Tasks FaceDetector adapter + process reuse |
| `preprocessing/reference.py` | Stronger secondary neutralization metadata |
| `Dockerfile` | Download full-range FaceDetector model |
| `tests/test_avatar_small_face_*.py` | Unit + integration |
| `out/avatar-small-face-calibration.json` | Calibration stub |
| `docs/avatar-production/avatar-small-face-calibration.md` | Calibration notes |

## Data flow

```
bytes → EXIF normalize → FullRangeFaceDetector
  → (optional) OverlappingTileDetector → CrossPassNMS
  → PrimaryFaceSelector → quality gate
  → HeadShouldersCropper → resize 512/768
  → CropFaceLandmarker → InternalFaceAnalysis (memory only)
  → SecondaryFaceNeutralizer → AnalysisReference → TraitCard
  → GenerationPrivacyReference → FLUX
```

## New internal types

`NormalizedBox`, `PixelBox`, `InternalFaceDetection`, `PrimaryFaceSelection`, `CropTransform`, `InternalFaceAnalysis` — never serialized to Firestore/client.

## Feature flags

- `AVATAR_SMALL_FACE_PIPELINE_ENABLED` (rollback = `false`)
- Full-range / tile / NMS / crop size envs (see `SmallFacePipelineConfig`)
- Production-like + model missing → **fail-closed**, no silent legacy fallback when flag is on

## Test plan

Unit: EXIF, tiles, NMS, scoring, crop, quality, neutralization  
Integration: fake detector → analyzer → preprocess (tile success path)  
Regression: existing `tests/test_avatar_source_analysis.py`

## Rollback

Set `AVATAR_SMALL_FACE_PIPELINE_ENABLED=false`. When enabled and detector model missing in production/production_bridge → hard fail (no quiet legacy).
