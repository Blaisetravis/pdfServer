"""
House style for tech-pack PDFs.

Ported 1:1 from the existing Node renderer (AgentServer pdf/layout.js) so the
ReportLab output matches the look the team already ships. All geometry is in
PDF points (72 pt = 1 in), Letter size.

NOTE on coordinates: ReportLab's canvas origin is BOTTOM-left (y increases up).
The original layout.js used a TOP-left origin (y increases down). We keep all the
constants below in the original TOP-DOWN convention and flip to ReportLab space
inside the Pen helper (render.py). That keeps these numbers identical to the JS.
"""

from reportlab.lib.colors import HexColor

# --- Page geometry (Letter, points) ---
PAGE_W = 612.0
PAGE_H = 792.0
MARGIN = 36.0

CONTENT_W = PAGE_W - 2 * MARGIN   # 540
CONTENT_H = PAGE_H - 2 * MARGIN   # 720

# Inner content area (inside the page border) — top-down coords
INNER_X = MARGIN
INNER_Y = MARGIN          # distance from TOP of page to the border
INNER_W = CONTENT_W
INNER_H = CONTENT_H

# --- Colors ---
COLORS = {
    "black": HexColor("#000000"),
    "white": HexColor("#FFFFFF"),
    "darkGrey": HexColor("#333333"),
    "medGrey": HexColor("#666666"),
    "lightGrey": HexColor("#999999"),
    "borderGrey": HexColor("#CCCCCC"),
    "border": HexColor("#000000"),
    "bgLight": HexColor("#F5F5F5"),
    "headerBg": HexColor("#1A1A1A"),
    "accent": HexColor("#8E7EAE"),
}

# --- Font sizes ---
FONT = {
    "headerBar": 7,
    "sectionTitle": 11,
    "label": 8,
    "body": 9,
    "small": 7,
    "pageTitle": 9,
}

# ReportLab built-in font names (Helvetica family — glyph-safe for WinAnsi)
F_REG = "Helvetica"
F_BOLD = "Helvetica-Bold"

# --- Spacing ---
CELL_PAD = 6.0
SECTION_PAD = 10.0


# --- Glyph safety -----------------------------------------------------------
# CRITICAL (per the Anthropic pdf skill): ReportLab's built-in fonts do NOT
# contain Unicode subscript/superscript or the eighth-fractions (⅛⅜⅝⅞ …).
# Emitting them renders SOLID BLACK BOXES. Tech-pack measurements use eighths
# constantly ("26 7/8"), so we convert any such glyph to plain ASCII before it
# ever reaches the canvas.

_FRACTION_MAP = {
    "¼": "1/4", "½": "1/2", "¾": "3/4",
    "⅐": "1/7", "⅑": "1/9", "⅒": "1/10",
    "⅓": "1/3", "⅔": "2/3",
    "⅕": "1/5", "⅖": "2/5", "⅗": "3/5", "⅘": "4/5",
    "⅙": "1/6", "⅚": "5/6",
    "⅛": "1/8", "⅜": "3/8", "⅝": "5/8", "⅞": "7/8",
    "⅟": "1/",
}

_SUPERSCRIPT_MAP = {
    "⁰": "0", "¹": "1", "²": "2", "³": "3", "⁴": "4",
    "⁵": "5", "⁶": "6", "⁷": "7", "⁸": "8", "⁹": "9",
    "⁺": "+", "⁻": "-", "⁼": "=", "⁽": "(", "⁾": ")",
}

_SUBSCRIPT_MAP = {
    "₀": "0", "₁": "1", "₂": "2", "₃": "3", "₄": "4",
    "₅": "5", "₆": "6", "₇": "7", "₈": "8", "₉": "9",
    "₊": "+", "₋": "-", "₌": "=", "₍": "(", "₎": ")",
}

_GLYPH_MAP = {**_FRACTION_MAP, **_SUPERSCRIPT_MAP, **_SUBSCRIPT_MAP}


def safe_text(value) -> str:
    """Sanitize a string for ReportLab's built-in fonts.

    Converts Unicode fractions / sub / superscripts to ASCII so they never
    render as black boxes. Pass everything user/Aria-supplied through this
    before drawing.
    """
    if value is None:
        return ""
    s = str(value)
    if not s:
        return s
    for bad, good in _GLYPH_MAP.items():
        if bad in s:
            s = s.replace(bad, good)
    return s
