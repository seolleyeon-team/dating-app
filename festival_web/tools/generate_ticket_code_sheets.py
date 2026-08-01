#!/usr/bin/env python3
"""
입장 코드 200개 → A4 PDF 4장 (5행 × 10열 = 50코드/장)

Usage:
  python3 tools/generate_ticket_code_sheets.py
  python3 tools/generate_ticket_code_sheets.py --output dist/ticket_codes_sheets.pdf
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SEED = ROOT / "ticket_codes_seed.json"
DEFAULT_OUTPUT = ROOT / "dist" / "ticket_code_sheets.pdf"

COLS = 10
ROWS = 5
CODES_PER_PAGE = COLS * ROWS
PAGES = 4

MARGIN_X = 8 * mm
MARGIN_Y = 10 * mm
HEADER_HEIGHT = 14 * mm
FOOTER_HEIGHT = 8 * mm


def load_codes(seed_path: Path) -> list[str]:
    data = json.loads(seed_path.read_text(encoding="utf-8"))
    codes = [t["code"] for t in data.get("tickets", []) if t.get("code")]
    if len(codes) != 200:
        raise SystemExit(f"Expected 200 codes, got {len(codes)} in {seed_path}")
    return codes


def register_fonts() -> tuple[str, str]:
    """Prefer system sans; fall back to Helvetica."""
    candidates = [
        Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
        Path("/Library/Fonts/Arial Bold.ttf"),
        Path("/Library/Fonts/Arial.ttf"),
    ]
    bold_path = candidates[0] if candidates[0].exists() else None
    regular_path = candidates[1] if candidates[1].exists() else None
    if bold_path and regular_path:
        pdfmetrics.registerFont(TTFont("SheetBold", str(bold_path)))
        pdfmetrics.registerFont(TTFont("SheetRegular", str(regular_path)))
        return "SheetBold", "SheetRegular"
    return "Helvetica-Bold", "Helvetica"


def draw_vertical_centered(
    c: canvas.Canvas,
    text: str,
    cx: float,
    cy: float,
    font_name: str,
    font_size: float,
    color: colors.Color,
) -> None:
    """Rotate 90° so text runs along the tall side of each cell (no horizontal overlap)."""
    c.saveState()
    c.setFont(font_name, font_size)
    c.setFillColor(color)
    text_w = c.stringWidth(text, font_name, font_size)
    c.translate(cx, cy)
    c.rotate(90)
    c.drawString(-text_w / 2, -font_size * 0.32, text)
    c.restoreState()


def draw_page(
    c: canvas.Canvas,
    page_index: int,
    codes: list[str],
    font_bold: str,
    font_regular: str,
) -> None:
    width, height = A4
    usable_w = width - 2 * MARGIN_X
    usable_h = height - MARGIN_Y - HEADER_HEIGHT - FOOTER_HEIGHT - MARGIN_Y
    cell_w = usable_w / COLS
    cell_h = usable_h / ROWS

    # Header
    c.setFont(font_bold, 11)
    c.setFillColor(colors.HexColor("#4A313B"))
    c.drawString(
        MARGIN_X,
        height - MARGIN_Y - 4 * mm,
        f"설레연 페스티벌 · 입장 코드  ({page_index + 1} / {PAGES})",
    )
    c.setFont(font_regular, 8)
    c.setFillColor(colors.HexColor("#9A7785"))
    c.drawRightString(
        width - MARGIN_X,
        height - MARGIN_Y - 4 * mm,
        "seolleyeon-festival.web.app",
    )

    # Grid origin (bottom-left of grid area)
    grid_bottom = MARGIN_Y + FOOTER_HEIGHT
    grid_left = MARGIN_X

    code_font_size = 13
    hint_font_size = 5.5

    for row in range(ROWS):
        for col in range(COLS):
            idx = row * COLS + col
            code = codes[idx]
            x = grid_left + col * cell_w
            y = grid_bottom + (ROWS - 1 - row) * cell_h
            cx = x + cell_w / 2
            cy = y + cell_h / 2

            # Cell border
            c.setStrokeColor(colors.HexColor("#F0DCE5"))
            c.setLineWidth(0.6)
            c.rect(x, y, cell_w, cell_h, stroke=1, fill=0)

            # Index (small, horizontal — fits in corner)
            global_num = page_index * CODES_PER_PAGE + idx + 1
            c.setFont(font_regular, 6)
            c.setFillColor(colors.HexColor("#C6A8B4"))
            c.drawString(x + 1.5 * mm, y + cell_h - 4.5 * mm, f"#{global_num:03d}")

            # Entry code — vertical (90°)
            draw_vertical_centered(
                c,
                code,
                cx,
                cy + 1.5 * mm,
                font_bold,
                code_font_size,
                colors.HexColor("#B8587A"),
            )

            # Hint — vertical, offset toward bottom of cell
            draw_vertical_centered(
                c,
                "입장코드",
                cx - cell_w * 0.22,
                cy - cell_h * 0.18,
                font_regular,
                hint_font_size,
                colors.HexColor("#9A7785"),
            )

    # Footer
    c.setFont(font_regular, 7)
    c.setFillColor(colors.HexColor("#9A7785"))
    c.drawCentredString(
        width / 2,
        MARGIN_Y + 2 * mm,
        "앱에서 코드 입력 또는 QR 스캔 · 프로필·취향 입력 후 20:00 추천 공개",
    )

    c.showPage()


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate ticket code sheet PDF")
    parser.add_argument("--seed", type=Path, default=DEFAULT_SEED)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    codes = load_codes(args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)

    font_bold, font_regular = register_fonts()
    c = canvas.Canvas(str(args.output), pagesize=A4)
    c.setTitle("설레연 페스티벌 입장 코드")
    c.setAuthor("seolleyeon-festival")

    for page in range(PAGES):
        start = page * CODES_PER_PAGE
        chunk = codes[start : start + CODES_PER_PAGE]
        draw_page(c, page, chunk, font_bold, font_regular)

    c.save()
    print(f"Wrote {args.output} ({PAGES} pages, {len(codes)} codes)")


if __name__ == "__main__":
    main()
