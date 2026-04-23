"""Grid image captcha generator: 4×3 number grid with 4 highlighted positions."""

import io
import random

from PIL import Image, ImageDraw, ImageFont

# Grid layout: 4 columns × 3 rows = 12 cells, all filled
_COLS = 4
_ROWS = 3
_CELL_W = 100
_CELL_H = 100
_IMG_W = _COLS * _CELL_W  # 400
_IMG_H = _ROWS * _CELL_H  # 300

_BG_COLOR = (18, 18, 32)
_GRID_LINE = (50, 50, 80)
_DIGIT_COLOR = (200, 200, 220)
_HIGHLIGHT_COLORS = [
    (255, 130, 0),  # 1 — orange
    (0, 200, 110),  # 2 — green
    (70, 150, 255),  # 3 — blue
    (220, 70, 190),  # 4 — pink
]


def _get_font(size: int) -> ImageFont.ImageFont:
    """Try to load a system font, fall back to default."""
    for path in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial Bold.ttf",
    ]:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def generate_grid_captcha() -> tuple[bytes, str]:
    """Generate a 400×300 grid captcha image.

    Returns (png_bytes, expected_4digit_string).
    All 12 cells are filled: digits 0–9 placed randomly, 2 cells get random filler digits.
    Four cells are highlighted with order badges 1/2/3/4; user types those digits in order.
    """
    all_positions = [(c, r) for r in range(_ROWS) for c in range(_COLS)]
    random.shuffle(all_positions)

    # Assign digits 0–9 to the first 10 positions
    digit_positions = all_positions[:10]
    filler_positions = all_positions[10:]  # 2 filler cells

    digit_map: dict[tuple[int, int], str] = {pos: str(digit) for digit, pos in enumerate(digit_positions)}
    # Fill remaining 2 cells with random digits (won't be highlighted)
    for pos in filler_positions:
        digit_map[pos] = str(random.randint(0, 9))

    # Pick 4 highlighted positions from the unique-digit cells only
    highlight_positions = random.sample(digit_positions, 4)
    expected = "".join(digit_map[pos] for pos in highlight_positions)

    # ── Draw image ────────────────────────────────────────────────────────────
    img = Image.new("RGB", (_IMG_W, _IMG_H), _BG_COLOR)
    draw = ImageDraw.Draw(img)

    digit_font = _get_font(46)
    badge_font = _get_font(20)

    # Subtle background noise
    for _ in range(250):
        x = random.randint(0, _IMG_W - 1)
        y = random.randint(0, _IMG_H - 1)
        gray = random.randint(28, 55)
        draw.point((x, y), fill=(gray, gray, gray + 8))

    # Grid lines
    for c in range(1, _COLS):
        draw.line([(c * _CELL_W, 0), (c * _CELL_W, _IMG_H)], fill=_GRID_LINE, width=1)
    for r in range(1, _ROWS):
        draw.line([(0, r * _CELL_H), (_IMG_W, r * _CELL_H)], fill=_GRID_LINE, width=1)

    # Build set of highlighted positions for color lookup
    highlight_map = {pos: idx for idx, pos in enumerate(highlight_positions)}

    # Draw digits (highlighted ones get a tinted color)
    for (col, row), digit in digit_map.items():
        cx = col * _CELL_W + _CELL_W // 2
        cy = row * _CELL_H + _CELL_H // 2
        jx = random.randint(-5, 5)
        jy = random.randint(-5, 5)
        bbox = draw.textbbox((0, 0), digit, font=digit_font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        if (col, row) in highlight_map:
            color = _HIGHLIGHT_COLORS[highlight_map[(col, row)]]
            # Bright version of highlight color for the digit
            digit_color = tuple(min(255, int(c * 1.3)) for c in color)
        else:
            digit_color = _DIGIT_COLOR
        draw.text(
            (cx - tw // 2 + jx, cy - th // 2 + jy),
            digit,
            font=digit_font,
            fill=digit_color,
        )

    # Draw highlight rings + prominent order badges
    for order_idx, pos in enumerate(highlight_positions):
        col, row = pos
        color = _HIGHLIGHT_COLORS[order_idx]
        cx = col * _CELL_W + _CELL_W // 2
        cy = row * _CELL_H + _CELL_H // 2

        # Ring around the digit
        ring_r = 38
        draw.ellipse(
            [(cx - ring_r, cy - ring_r), (cx + ring_r, cy + ring_r)],
            outline=color,
            width=3,
        )

        # Solid badge circle in top-right corner of the cell with the order number
        badge_cx = col * _CELL_W + _CELL_W - 18
        badge_cy = row * _CELL_H + 18
        badge_r = 14
        draw.ellipse(
            [(badge_cx - badge_r, badge_cy - badge_r), (badge_cx + badge_r, badge_cy + badge_r)],
            fill=color,
        )
        label = str(order_idx + 1)  # "1", "2", "3", "4"
        bbox = draw.textbbox((0, 0), label, font=badge_font)
        lw, lh = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(
            (badge_cx - lw // 2, badge_cy - lh // 2),
            label,
            font=badge_font,
            fill=(10, 10, 20),
        )

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue(), expected
