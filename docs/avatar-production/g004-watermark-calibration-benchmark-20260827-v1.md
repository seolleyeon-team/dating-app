# G004 Watermark Calibration Benchmark — Human Checkpoint

Status: `HUMAN_WATERMARK_LABELS_REQUIRED`

Use the already provisioned authenticated/private G004 review boundary. Compare
each candidate with its normalized source using only the ordinal pair in the
worksheet. Do not copy images, create derivatives, export URLs, or record
paths, names, raw OCR, brands, schools, coordinates, or bounding boxes.

For every row, fill these required fields:

- `candidateVisualClass`: `no_visible_text_or_logo`, `benign_text_or_logo`,
  `clear_watermark_or_brand_overlay`, or `uncertain`
- `sameVisibleMarkInSource`: `yes`, `no`, `not_applicable`, or `uncertain`
- `overlayAppearance`: `yes`, `no`, or `uncertain`
- `humanLabelConfidence`: `high`, `medium`, or `low`

Optional `location` may be `corner`, `edge`, `clothing_zone`, `central`,
`none`, or `uncertain`.

`uncertain` is valid and is excluded from primary precision/recall
denominators. Empty required fields are not valid. This watermark label
checkpoint is separate from G004 `humanSignoff`, which remains false.
