#!/usr/bin/env python3
"""Read-only PNG amplitude and spatial analysis for the MBTI golden."""

from __future__ import annotations

import hashlib
import json
import statistics
import struct
import sys
import zlib
from pathlib import Path


THRESHOLDS = (0, 1, 2, 3, 4, 5, 8, 10, 16, 24, 32, 48, 64, 96)


def _paeth(left: int, above: int, upper_left: int) -> int:
    estimate = left + above - upper_left
    distances = (
        abs(estimate - left),
        abs(estimate - above),
        abs(estimate - upper_left),
    )
    return (left, above, upper_left)[distances.index(min(distances))]


def _decode_png(path: Path) -> tuple[int, int, list[tuple[int, int, int, int]]]:
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"Not a PNG: {path}")

    position = 8
    compressed = bytearray()
    width = height = color_type = bit_depth = None
    while position < len(data):
        length = struct.unpack(">I", data[position : position + 4])[0]
        kind = data[position + 4 : position + 8]
        payload = data[position + 8 : position + 8 + length]
        position += length + 12
        if kind == b"IHDR":
            width, height, bit_depth, color_type = struct.unpack(">IIBB", payload[:10])
        elif kind == b"IDAT":
            compressed.extend(payload)
        elif kind == b"IEND":
            break

    if bit_depth != 8 or color_type not in (2, 6):
        raise ValueError(f"Unsupported PNG format: depth={bit_depth}, color={color_type}")
    channels = 4 if color_type == 6 else 3
    stride = width * channels
    decoded = zlib.decompress(bytes(compressed))
    rows: list[bytearray] = []
    offset = 0
    previous = bytearray(stride)
    for _ in range(height):
        filter_type = decoded[offset]
        raw = bytearray(decoded[offset + 1 : offset + 1 + stride])
        offset += stride + 1
        row = bytearray(stride)
        for index, value in enumerate(raw):
            left = row[index - channels] if index >= channels else 0
            above = previous[index]
            upper_left = previous[index - channels] if index >= channels else 0
            if filter_type == 0:
                predictor = 0
            elif filter_type == 1:
                predictor = left
            elif filter_type == 2:
                predictor = above
            elif filter_type == 3:
                predictor = (left + above) // 2
            elif filter_type == 4:
                predictor = _paeth(left, above, upper_left)
            else:
                raise ValueError(f"Unsupported PNG filter: {filter_type}")
            row[index] = (value + predictor) & 0xFF
        rows.append(row)
        previous = row

    pixels: list[tuple[int, int, int, int]] = []
    for row in rows:
        for index in range(0, len(row), channels):
            values = tuple(row[index : index + channels])
            pixels.append(values if channels == 4 else (*values, 255))
    return width, height, pixels


def _percentile(sorted_values: list[int], percentile: float) -> int:
    return sorted_values[round((len(sorted_values) - 1) * percentile)]


def _inside(x: int, y: int, rect: tuple[int, int, int, int]) -> bool:
    left, top, right, bottom = rect
    return left <= x < right and top <= y < bottom


def _region_stats(
    deltas: list[int],
    width: int,
    include: list[tuple[int, int, int, int]],
    exclude: list[tuple[int, int, int, int]] | None = None,
) -> dict[str, float | int]:
    selected = []
    for index, delta in enumerate(deltas):
        x, y = index % width, index // width
        if any(_inside(x, y, rect) for rect in include) and not any(
            _inside(x, y, rect) for rect in (exclude or [])
        ):
            selected.append(delta)
    changed = sum(delta > 0 for delta in selected)
    return {
        "pixels": len(selected),
        "changed_pct": round(changed * 100 / len(selected), 6),
        "mean_max_channel_delta": round(statistics.fmean(selected), 6),
    }


def main(expected_path: str, actual_path: str) -> None:
    expected_file, actual_file = Path(expected_path), Path(actual_path)
    width, height, expected = _decode_png(expected_file)
    actual_width, actual_height, actual = _decode_png(actual_file)
    if (width, height) != (actual_width, actual_height):
        raise ValueError(
            f"Dimension mismatch: expected={width}x{height}, "
            f"actual={actual_width}x{actual_height}"
        )

    deltas = [
        max(abs(left - right) for left, right in zip(master, test))
        for master, test in zip(expected, actual)
    ]
    sorted_deltas = sorted(deltas)
    total = len(deltas)
    surface = (15, 296, 375, 548)
    shadow_extent = (0, 272, 390, 572)
    button_lefts = (29, 116, 203, 290)
    glyphs = [
        (left + 19, top + 15, left + 52, top + 55)
        for left in button_lefts
        for top in (361, 447)
    ]
    full = [(0, 0, width, height)]
    report = {
        "dimensions": f"{width}x{height}",
        "expected_sha256": hashlib.sha256(expected_file.read_bytes()).hexdigest(),
        "actual_sha256": hashlib.sha256(actual_file.read_bytes()).hexdigest(),
        "intensity_pct": {
            f">{threshold}": round(
                sum(delta > threshold for delta in deltas) * 100 / total, 6
            )
            for threshold in THRESHOLDS
        },
        "distribution_all_pixels": {
            "mean": round(statistics.fmean(deltas), 6),
            "median": statistics.median(deltas),
            "p90": _percentile(sorted_deltas, 0.90),
            "p95": _percentile(sorted_deltas, 0.95),
            "p99": _percentile(sorted_deltas, 0.99),
            "max": max(deltas),
        },
        "regions": {
            "modal_sheet_interior": _region_stats(deltas, width, [surface]),
            "modal_shadow_border": _region_stats(
                deltas, width, [shadow_extent], [surface]
            ),
            "dimmed_background": _region_stats(
                deltas, width, full, [shadow_extent]
            ),
            "mbti_letter_glyph_boxes": _region_stats(deltas, width, glyphs),
            "header_text_buttons": _region_stats(
                deltas, width, [(15, 296, 375, 347)]
            ),
            "background_profile_cards": _region_stats(
                deltas, width, [(16, 80, 374, 844)], [shadow_extent]
            ),
        },
        "region_definitions_half_open": {
            "surface": surface,
            "shadow_extent": shadow_extent,
            "glyph_boxes": glyphs,
        },
    }
    print("PROFILE_EDIT_MBTI_ANALYSIS_JSON=" + json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
