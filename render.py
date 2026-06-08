"""
ReportLab renderer: Document model -> PDF bytes.

The `Pen` class wraps a ReportLab canvas and exposes TOP-DOWN drawing helpers
(y grows downward, like the original pdfkit layout.js) so the block renderers
read like the existing JS. All user text goes through style.safe_text() to avoid
the black-box glyph problem.
"""

from io import BytesIO
from typing import Optional

import requests
from PIL import Image
from reportlab.lib.colors import HexColor
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, Table, TableStyle
from xml.sax.saxutils import escape

from models import Document
from style import (
    PAGE_W, PAGE_H, MARGIN, CONTENT_W, INNER_X, INNER_Y, INNER_W, INNER_H,
    COLORS, FONT, F_REG, F_BOLD, CELL_PAD, SECTION_PAD, safe_text,
)

C = COLORS  # shorthand


# --- image fetch ------------------------------------------------------------

def fetch_image(src: str) -> Optional[Image.Image]:
    if not src or not str(src).startswith("http"):
        return None
    try:
        r = requests.get(src, timeout=15)
        r.raise_for_status()
        img = Image.open(BytesIO(r.content))
        img.load()
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        return img
    except Exception as e:
        print(f"[render] image fetch failed ({src[:60]}...): {e}")
        return None


# --- the Pen ----------------------------------------------------------------

class Pen:
    def __init__(self, c: canvas.Canvas):
        self.c = c
        self.H = PAGE_H
        self.page_num = 0
        self._title = ""
        self._content_top = INNER_Y + 30

    # geometry: top-down -> reportlab (bottom-left) ---------------------------
    def fill_rect(self, x, y_top, w, h, color):
        self.c.setFillColor(color)
        self.c.rect(x, self.H - (y_top + h), w, h, stroke=0, fill=1)

    def stroke_rect(self, x, y_top, w, h, color, lw=0.5):
        self.c.setStrokeColor(color)
        self.c.setLineWidth(lw)
        self.c.rect(x, self.H - (y_top + h), w, h, stroke=1, fill=0)

    def line(self, x1, y1_top, x2, y2_top, color, lw=0.5):
        self.c.setStrokeColor(color)
        self.c.setLineWidth(lw)
        self.c.line(x1, self.H - y1_top, x2, self.H - y2_top)

    def string_width(self, s, size, bold=False):
        return stringWidth(safe_text(s), F_BOLD if bold else F_REG, size)

    def text(self, x, y_top, s, size, color, bold=False, align="left", width=None):
        s = safe_text(s)
        font = F_BOLD if bold else F_REG
        self.c.setFont(font, size)
        self.c.setFillColor(color)
        tx = x
        if align in ("center", "right") and width is not None:
            sw = stringWidth(s, font, size)
            tx = x + (width - sw) / 2 if align == "center" else x + width - sw
        self.c.drawString(tx, self.H - (y_top + size), s)

    def paragraph(self, x, y_top, s, width, size, color, bold=False, leading=None) -> float:
        font = F_BOLD if bold else F_REG
        style = ParagraphStyle(
            "p", fontName=font, fontSize=size, textColor=color,
            leading=leading or size * 1.3,
        )
        html = escape(safe_text(s)).replace("\n", "<br/>")
        p = Paragraph(html, style)
        w, h = p.wrapOn(self.c, width, 100000)
        p.drawOn(self.c, x, self.H - (y_top + h))
        return h

    def image(self, img: Image.Image, x, y_top, w, h):
        try:
            self.c.drawImage(
                ImageReader(img), x, self.H - (y_top + h),
                width=w, height=h, preserveAspectRatio=True, anchor="c", mask="auto",
            )
        except Exception as e:
            print(f"[render] drawImage failed: {e}")

    def circle(self, x, y_top, r, fill=None, stroke=None, lw=1.0):
        if fill is not None:
            self.c.setFillColor(fill)
        if stroke is not None:
            self.c.setStrokeColor(stroke)
            self.c.setLineWidth(lw)
        self.c.circle(x, self.H - y_top, r,
                      stroke=1 if stroke is not None else 0,
                      fill=1 if fill is not None else 0)

    # page chrome -------------------------------------------------------------
    def _border(self):
        self.stroke_rect(INNER_X, INNER_Y, INNER_W, INNER_H, C["border"], 1)

    def _top_bar(self, title) -> float:
        bar_h = 22
        self.fill_rect(INNER_X, INNER_Y, INNER_W, bar_h, C["headerBg"])
        self.text(INNER_X + CELL_PAD, INNER_Y + 7, "T C H P A C K",
                  FONT["pageTitle"], C["white"], bold=True)
        if title:
            self.text(INNER_X + INNER_W / 2, INNER_Y + 7, title.upper(),
                      FONT["pageTitle"], C["white"], bold=True,
                      align="right", width=INNER_W / 2 - CELL_PAD)
        return INNER_Y + bar_h

    def _footer(self):
        self.text(MARGIN, PAGE_H - MARGIN - 14, f"Page {self.page_num}",
                  FONT["small"], C["lightGrey"], align="center", width=CONTENT_W)

    def new_page(self, title) -> float:
        """Close the current page (if any) and start a fresh one. Returns the
        starting y (top-down) for content."""
        if self.page_num > 0:
            self._footer()
            self.c.showPage()
        self.page_num += 1
        self._title = title
        self._border()
        y = self._top_bar(title) + 8
        self._content_top = y
        return y

    def ensure_space(self, needed, y_top, title) -> float:
        if y_top + needed > INNER_Y + INNER_H:
            return self.new_page(title)
        return y_top

    def draw_flowable(self, flow, y_top, page_title, x=None, width=None) -> float:
        """Draw a platypus Flowable (e.g. a Table) at top-down y_top, splitting
        it across pages when it doesn't fit. Returns the y after the last piece."""
        x = INNER_X + SECTION_PAD if x is None else x
        width = INNER_W - 2 * SECTION_PAD if width is None else width
        bottom = INNER_Y + INNER_H
        while flow is not None:
            avail_h = bottom - y_top
            _w, h = flow.wrapOn(self.c, width, avail_h)
            if h <= avail_h:
                flow.drawOn(self.c, x, self.H - (y_top + h))
                return y_top + h
            parts = flow.split(width, avail_h)
            if parts:
                first = parts[0]
                _w1, h1 = first.wrapOn(self.c, width, avail_h)
                first.drawOn(self.c, x, self.H - (y_top + h1))
                flow = parts[1] if len(parts) > 1 else None
                if flow is not None:
                    y_top = self.new_page(page_title)
                else:
                    return y_top + h1
            elif abs(y_top - self._content_top) < 1:
                # already on a fresh page and still won't fit / can't split → draw clipped
                flow.drawOn(self.c, x, self.H - (y_top + h))
                return y_top + h
            else:
                y_top = self.new_page(page_title)
        return y_top

    def finalize(self):
        if self.page_num > 0:
            self._footer()
            self.c.showPage()
        self.c.save()


# --- block renderers --------------------------------------------------------

def _chunk(lst, n):
    return [lst[i:i + n] for i in range(0, len(lst), n)]


def render_header(pen: Pen, b, y, title):
    cols = max(1, b.columns)
    col_w = INNER_W / cols
    row_h = 20
    for row in _chunk(b.fields, cols):
        pen.stroke_rect(INNER_X, y, INNER_W, row_h, C["border"], 0.5)
        for c, cell in enumerate(row):
            cx = INNER_X + c * col_w
            if c > 0:
                pen.line(cx, y, cx, y + row_h, C["border"], 0.5)
            label = f"{(cell.label or '').upper()}:"
            pen.text(cx + CELL_PAD, y + 4, label, FONT["headerBar"], C["black"], bold=True)
            lw = pen.string_width(label + " ", FONT["headerBar"], bold=True)
            pen.text(cx + CELL_PAD + lw + 2, y + 4, cell.value or "",
                     FONT["headerBar"], C["darkGrey"])
        y += row_h
    return y + CELL_PAD


def _render_field(pen, f, x, y, width):
    label = f"{f.label.upper()}:"
    pen.text(x, y, label, FONT["label"], C["black"], bold=True)
    lw = pen.string_width(label + " ", FONT["label"], bold=True)
    h = pen.paragraph(x + lw + 4, y, f.value or "—", width - lw - 4, FONT["body"], C["darkGrey"])
    return y + max(h, 12) + 4


def render_spec_section(pen: Pen, b, y, title):
    y = pen.ensure_space(60, y, title)
    pen.text(INNER_X + SECTION_PAD, y + 5, b.title, FONT["sectionTitle"], C["black"], bold=True)
    content_start = y + 20
    pen.line(INNER_X, content_start, INNER_X + INNER_W, content_start, C["border"], 0.5)
    cx = INNER_X + SECTION_PAD
    cw = INNER_W - 2 * SECTION_PAD
    cy = content_start + CELL_PAD
    if b.body:
        cy += pen.paragraph(cx, cy, b.body, cw, FONT["body"], C["darkGrey"]) + 4
    for f in b.fields:
        cy = _render_field(pen, f, cx, cy, cw)
    for bullet in b.bullets:
        cy += pen.paragraph(cx, cy, f"•  {bullet}", cw, FONT["body"], C["darkGrey"]) + 3
    return cy + CELL_PAD


_ALIGN = {"left": 0, "center": 1, "right": 2}  # TA_LEFT / TA_CENTER / TA_RIGHT


def _cell(text, *, bold=False, color=None, align="left", upper=False):
    s = safe_text(text)
    if upper:
        s = s.upper()
    style = ParagraphStyle(
        "cell", fontName=F_BOLD if bold else F_REG, fontSize=FONT["small"],
        textColor=color or C["darkGrey"], leading=FONT["small"] * 1.25,
        alignment=_ALIGN[align],
    )
    return Paragraph(escape(s) or "—", style)


def build_table(headers, rows, width):
    """A platypus Table styled to match the house look — dark header, alternating
    rows, thin grid. Cells are Paragraphs so long values WRAP instead of clipping,
    and the header repeats when the table splits across pages."""
    n = max(1, len(headers))
    col_w = width / n
    head = [_cell(h, bold=True, color=C["white"], align="left" if i == 0 else "center", upper=True)
            for i, h in enumerate(headers)]
    data = [head]
    for row in rows:
        data.append([
            _cell(row[i] if i < len(row) else "—", align="left" if i == 0 else "center")
            for i in range(n)
        ])
    t = Table(data, colWidths=[col_w] * n, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), C["headerBg"]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), CELL_PAD),
        ("RIGHTPADDING", (0, 0), (-1, -1), CELL_PAD),
        ("GRID", (0, 0), (-1, -1), 0.25, C["borderGrey"]),
        ("BOX", (0, 0), (-1, -1), 0.5, C["border"]),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, C["border"]),
    ]
    for r in range(1, len(data)):
        if (r - 1) % 2 == 0:
            style.append(("BACKGROUND", (0, r), (-1, r), C["bgLight"]))
    t.setStyle(TableStyle(style))
    return t


def render_table(pen: Pen, title, headers, rows, y, page_title):
    x = INNER_X + SECTION_PAD
    width = INNER_W - 2 * SECTION_PAD
    if title:
        y = pen.ensure_space(60, y, page_title)
        pen.text(x, y, title, FONT["sectionTitle"], C["black"], bold=True)
        y += 18
        pen.line(x, y, x + width, y, C["border"], 0.5)
        y += 10
    if not headers:
        return y
    table = build_table(headers, rows, width)
    y = pen.draw_flowable(table, y, page_title, x=x, width=width)
    return y + CELL_PAD


def render_size_chart(pen: Pen, b, y, page_title):
    sizes = list(b.sizes)
    if not sizes:
        seen = []
        for m in b.measurements.values():
            for s in m.keys():
                if s not in seen:
                    seen.append(s)
        sizes = seen
    headers = ["Measurement", *[s.upper() for s in sizes]]
    rows = []
    for name, by_size in b.measurements.items():
        rows.append([name.replace("_", " "), *[str(by_size.get(s, "—")) for s in sizes]])
    return render_table(pen, b.title or "Size Chart", headers, rows, y, page_title)


def render_image_grid(pen: Pen, b, y, page_title):
    cols = max(1, b.cols)
    gap = 15
    cell_w = (INNER_W - (cols + 1) * gap) / cols
    maxh = b.max_height
    items = [(fetch_image(it.src), it.label) for it in b.images]
    for row in _chunk(items, cols):
        y = pen.ensure_space(maxh + 24, y, page_title)
        for c, (img, label) in enumerate(row):
            ix = INNER_X + gap + c * (cell_w + gap)
            if img is not None:
                pen.image(img, ix, y, cell_w, maxh)
            pen.text(ix, y + maxh + 4, (label or "IMAGE").upper(), FONT["small"],
                     C["medGrey"], align="center", width=cell_w)
        y += maxh + 24
    return y


def _draw_cards(pen, items, cols, cell, gap, y, page_title, *, label_size):
    """Draw a grid of cards (image or outlined-blank) + label + caption, paging
    by row. Each row is CENTERED so an incomplete row never leaves a right-only
    gap. Returns y after the last row."""
    label_block = label_size + 16  # room for label + caption under each card
    for row in _chunk(items, cols):
        y = pen.ensure_space(cell + label_block + 8, y, page_title)
        n = len(row)
        row_w = n * cell + (n - 1) * gap
        start_x = INNER_X + max(0, (INNER_W - row_w) / 2)  # center the row
        for c, (img, label, cap, color) in enumerate(row):
            ix = start_x + c * (cell + gap)
            if img is not None:
                pen.image(img, ix, y, cell, cell)
            elif color:
                try:
                    pen.fill_rect(ix, y, cell, cell, HexColor(color))
                except Exception:
                    pass
                pen.stroke_rect(ix, y, cell, cell, C["borderGrey"], 0.5)
            else:
                pen.stroke_rect(ix, y, cell, cell, C["borderGrey"], 0.5)
            ly = y + cell + 4
            if label:
                pen.text(ix, ly, label, label_size, C["black"], bold=True, align="center", width=cell)
                ly += label_size + 3
            if cap:
                pen.text(ix, ly, cap, FONT["small"], C["medGrey"], align="center", width=cell)
        y += cell + label_block + 8
    return y


def render_swatch_grid(pen: Pen, b, y, page_title):
    gap = 16
    # Cards WITH a visual (image swatch/render, or a solid colour chip) render
    # BIG; blank label/packaging cards (no image, no colour) render COMPACT.
    vis_items = [
        (fetch_image(s.src) if s.src else None, s.label, s.caption, s.color)
        for s in b.swatches if (s.src or s.color)
    ]
    blank_items = [(None, s.label, s.caption, None) for s in b.swatches if not (s.src or s.color)]

    if b.title:
        y = pen.ensure_space(30, y, page_title)
        pen.text(INNER_X + SECTION_PAD, y, b.title, FONT["sectionTitle"], C["black"], bold=True)
        y += 18
        pen.line(INNER_X, y, INNER_X + INNER_W, y, C["border"], 0.5)
        y += 10

    if vis_items:
        # Use no more columns than there are cards, so 2 cards fill the width
        # (big, side-by-side) instead of leaving empty columns on the right.
        cols = max(1, min(b.cols, len(vis_items)))
        cell = min((INNER_W - (cols + 1) * gap) / cols, 280)  # cap so 1 card isn't oversized
        y = _draw_cards(pen, vis_items, cols, cell, gap, y, page_title, label_size=FONT["label"])

    if blank_items:
        y += 6
        cols = 4  # more per row → smaller tiles
        cell = min((INNER_W - (cols + 1) * gap) / cols, 96)  # cap ~1.3" so they stay compact
        y = _draw_cards(pen, blank_items, cols, cell, gap, y, page_title, label_size=FONT["small"])
    return y


def render_text(pen: Pen, b, y, page_title):
    size = {"title": FONT["sectionTitle"], "heading": 10,
            "body": FONT["body"], "small": FONT["small"]}[b.variant]
    bold = b.variant in ("title", "heading")
    y = pen.ensure_space(size * 2, y, page_title)
    h = pen.paragraph(INNER_X + SECTION_PAD, y, b.text, INNER_W - 2 * SECTION_PAD,
                      size, C["black"] if bold else C["darkGrey"], bold=bold)
    return y + h + 6


def render_divider(pen: Pen, b, y, page_title):
    y = pen.ensure_space(10, y, page_title)
    pen.line(INNER_X + SECTION_PAD, y, INNER_X + INNER_W - SECTION_PAD, y, C["borderGrey"], 0.5)
    return y + 8


def render_spacer(pen: Pen, b, y, page_title):
    return y + b.height


def render_abs(pen: Pen, b, y, page_title):
    for el in b.elements:
        color = HexColor(el.color) if el.color else C["darkGrey"]
        if el.kind == "text":
            pen.text(el.x, el.y, el.text or "", el.font_size or 9, color, bold=el.bold)
        elif el.kind == "rect":
            pen.stroke_rect(el.x, el.y, el.w or 0, el.h or 0, color, 1)
        elif el.kind == "line":
            pen.line(el.x, el.y, el.x2 if el.x2 is not None else el.x,
                     el.y2 if el.y2 is not None else el.y, color, 1)
        elif el.kind == "image":
            img = fetch_image(el.src)
            if img is not None:
                pen.image(img, el.x, el.y, el.w or 100, el.h or 100)
    return y


def render_callouts(pen: Pen, b, y, page_title):
    if b.view:
        y = pen.ensure_space(26, y, page_title)
        pen.text(INNER_X + SECTION_PAD, y, b.view.upper(), FONT["sectionTitle"], C["black"], bold=True)
        y += 20

    img = fetch_image(b.image)
    box_w = INNER_W * 0.66          # leave side margins for the circles + leader lines
    box_h = b.max_height
    y = pen.ensure_space(box_h + 16, y, page_title)

    if img is not None:
        iw, ih = img.size
        scale = min(box_w / iw, box_h / ih)
        dw, dh = iw * scale, ih * scale
        ix = INNER_X + (INNER_W - dw) / 2
        iy = y
        pen.image(img, ix, iy, dw, dh)

        # Marker colour — Aria picks one that pops against the garment; default red.
        try:
            accent = HexColor(b.accent) if b.accent else HexColor("#E11D2A")
        except Exception:
            accent = HexColor("#E11D2A")

        r = 9.0
        spacing = 2 * r + 8
        clamp01 = lambda v: max(0.0, min(1.0, v))

        def place(side_points, circle_x):
            prev_cy = iy - spacing
            for p in side_points:
                fx = ix + clamp01(p.x) * dw
                fy = iy + clamp01(p.y) * dh
                cy = min(max(fy, prev_cy + spacing), iy + dh)
                prev_cy = cy
                pen.line(circle_x, cy, fx, fy, accent, 1.0)           # leader line
                pen.circle(fx, fy, 2.2, fill=accent)                  # dot on the feature
                pen.circle(circle_x, cy, r, fill=C["white"], stroke=accent, lw=1.4)
                pen.text(circle_x - r, cy - 3.0, str(p.n), 8, accent, bold=True, align="center", width=2 * r)

        left = sorted([p for p in b.points if p.x < 0.5], key=lambda p: p.y)
        right = sorted([p for p in b.points if p.x >= 0.5], key=lambda p: p.y)
        place(left, INNER_X + 16)
        place(right, INNER_X + INNER_W - 16)
        y = iy + dh + 14
    else:
        pen.stroke_rect(INNER_X, y, box_w, box_h, C["borderGrey"], 0.5)
        y += box_h + 14

    if b.points:
        rows = [[str(p.n), (p.label or "").upper()] for p in sorted(b.points, key=lambda p: p.n)]
        y = render_table(pen, "CALLOUTS", ["#", "DETAIL"], rows, y, page_title)
    return y


_DISPATCH = {
    "header": render_header,
    "spec_section": render_spec_section,
    "table": lambda pen, b, y, t: render_table(pen, b.title, b.headers, b.rows, y, t),
    "size_chart": render_size_chart,
    "image_grid": render_image_grid,
    "swatch_grid": render_swatch_grid,
    "callouts": render_callouts,
    "text": render_text,
    "divider": render_divider,
    "spacer": render_spacer,
    "abs": render_abs,
}


def render_pdf(document: Document) -> bytes:
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=(PAGE_W, PAGE_H))
    c.setTitle(safe_text(document.title))
    c.setAuthor(safe_text(document.author))
    pen = Pen(c)

    pages = document.pages or [None]
    for page in pages:
        title = page.title if page else ""
        y = pen.new_page(title)
        if page:
            for block in page.blocks:
                renderer = _DISPATCH.get(block.type)
                if renderer:
                    y = renderer(pen, block, y, title)
    pen.finalize()
    return buf.getvalue()
