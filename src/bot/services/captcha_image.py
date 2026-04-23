"""Grid image captcha generator: 4×3 number grid with 4 highlighted positions."""

import io
import random

from PIL import Image, ImageDraw, ImageFont

# Grid layout: 4 columns × 3 rows = 12 cells; 10 digits fill 10, 2 cells stay blank
_COLS = 4
_ROWS = 3
_CELL_W = 100
_CELL_H = 100
_IMG_W = _COLS * _CELL_W  # 400
_IMG_H = _ROWS * _CELL_H  # 300

_BG_COLOR = (18, 18, 32)
_GRID_LINE = (50, 50, 80)
_DIGIT_COLOR = (220, 220, 240)
_HIGHLIGHT_COLORS = [
    (255, 140, 0),  # ① orange
    (0, 200, 120),  # ② green
    (80, 160, 255),  # ③ blue
    (230, 80, 200),  # ④ pink
]
_CIRCLE_LABELS = ["①", "②", "③", "④"]


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
    Digits 0–9 are placed randomly in a 4×3 grid (2 cells blank).
    Four cells are highlighted ①②③④; the user must type those digits in order.
    """
    # ── Shuffle digit positions ──────────────────────────────────────────────
    positions = [(c, r) for r in range(_ROWS) for c in range(_COLS)]
    random.shuffle(positions)
    digit_positions = positions[:10]
    digit_map: dict[tuple[int, int], str] = {pos: str(digit) for digit, pos in enumerate(digit_positions)}

    # ── Pick 4 highlighted positions (must be digit cells) ───────────────────
    highlight_positions = random.sample(digit_positions, 4)
    expected = "".join(digit_map[pos] for pos in highlight_positions)

    # ── Draw image ───────────────────────────────────────────────────────────
    img = Image.new("RGB", (_IMG_W, _IMG_H), _BG_COLOR)
    draw = ImageDraw.Draw(img)

    digit_font = _get_font(42)
    label_font = _get_font(22)

    # Draw subtle noise
    for _ in range(300):
        x = random.randint(0, _IMG_W - 1)
        y = random.randint(0, _IMG_H - 1)
        gray = random.randint(30, 60)
        draw.point((x, y), fill=(gray, gray, gray + 10))

    # Draw grid lines
    for c in range(1, _COLS):
        x = c * _CELL_W
        draw.line([(x, 0), (x, _IMG_H)], fill=_GRID_LINE, width=1)
    for r in range(1, _ROWS):
        y = r * _CELL_H
        draw.line([(0, y), (_IMG_W, y)], fill=_GRID_LINE, width=1)

    # Draw digits
    for (col, row), digit in digit_map.items():
        cx = col * _CELL_W + _CELL_W // 2
        cy = row * _CELL_H + _CELL_H // 2
        # Slight random jitter to defeat trivial OCR
        jx = random.randint(-6, 6)
        jy = random.randint(-6, 6)
        bbox = draw.textbbox((0, 0), digit, font=digit_font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(
            (cx - tw // 2 + jx, cy - th // 2 + jy),
            digit,
            font=digit_font,
            fill=_DIGIT_COLOR,
        )

    # Draw highlight circles + order labels
    for order_idx, pos in enumerate(highlight_positions):
        col, row = pos
        color = _HIGHLIGHT_COLORS[order_idx]
        label = _CIRCLE_LABELS[order_idx]
        cx = col * _CELL_W + _CELL_W // 2
        cy = row * _CELL_H + _CELL_H // 2
        r = 36
        # Colored ring
        draw.ellipse(
            [(cx - r, cy - r), (cx + r, cy + r)],
            outline=color,
            width=3,
        )
        # Small label in corner of cell
        lx = col * _CELL_W + 6
        ly = row * _CELL_H + 4
        bbox = draw.textbbox((0, 0), label, font=label_font)
        lw, lh = bbox[2] - bbox[0], bbox[3] - bbox[1]
        # Label background pill
        pad = 3
        draw.rounded_rectangle(
            [(lx - pad, ly - pad), (lx + lw + pad, ly + lh + pad)],
            radius=4,
            fill=color,
        )
        draw.text((lx, ly), label, font=label_font, fill=(10, 10, 20))

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue(), expected
