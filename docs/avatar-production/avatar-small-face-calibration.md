# Avatar small-face calibration

## Status

`BLOCKED_BY_CALIBRATION_DATA`

Synthetic unit/integration fixtures validate the pipeline mechanics (EXIF, tiles, NMS, scoring, crop, landmarker hook, neutralization). They do **not** finalize production thresholds.

## Face-size buckets

| Bucket | Provisional detect | Provisional avatar_usable |
|--------|--------------------|---------------------------|
| < 32px | detect candidates only | reject |
| 32–47px | tile fallback target | usually reject |
| 48–63px | detect + tile | borderline; trait gate applies |
| 64–79px | usable candidate zone | accept if sharp + landmarks ok |
| 80–119px | strong | accept |
| ≥ 120px | legacy-equivalent | accept |

Defaults in code:

- `AVATAR_FACE_MIN_SHORT_SIDE_DETECT_PX=48`
- `AVATAR_FACE_MIN_SHORT_SIDE_TRAIT_PX=64`

## Remaining work

1. Collect consented calibration set across buckets
2. Compare legacy vs full-range vs 2x2/3x3 ladders
3. Freeze thresholds only after false-positive review
4. Do not claim production-ready recall until then
