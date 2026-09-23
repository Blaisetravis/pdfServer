"""
Model-bound canvas geometry from the PDF renderer.

`LayoutPen` runs the exact block renderers in render.py, but instead of drawing
it records every primitive as a canvas element tagged with the model node it
represents: block id, block type, page id, a role (heading, cell, leader …) and
a JSON Pointer field into the block. Web places those elements as editable
shapes bound to the document, so canvas and PDF come from one layout code path.

Two modes:
  pages — Letter pages with chrome and real pagination, identical to the PDF.
  sheet — one infinite sheet, no chrome, no page breaks (single-block relayout).

No images are fetched here. Callers pass `image_sizes` (src -> [w, h]); embedded
data URLs are measured locally; unknown remote images fall back to a square slot
flagged `sizeUnknown`.
"""
from contextlib import contextmanager
from io import BytesIO

from reportlab.pdfgen import canvas

from render import Pen, draw_document, fetch_image
from style import CELL_PAD, COLORS, INNER_X, INNER_Y, INNER_W, PAGE_H, PAGE_W, SECTION_PAD, safe_text

SHEET_GAP = 40.0
UNKNOWN_IMAGE_SIZE = (1000.0, 1000.0)
CHROME_ROLES = {"page_border", "page_bar", "page_brand", "page_title", "page_footer"}


def color(value):
    return value.hexval().replace("0x", "#") if value is not None else "transparent"


class ImageSlot:
    """Stands in for a PIL image: renderers only read width/height/size."""
    def __init__(self, src, width, height, known=True):
        self.src, self.width, self.height, self.known = src, float(width), float(height), known
        self.size = (self.width, self.height)


def paragraph_lines(paragraph):
    lines = []
    for line in paragraph.blPara.lines:
        if paragraph.blPara.kind == 0:
            lines.append(" ".join(line[1]))
        else:
            lines.append("".join(getattr(word, "text", "") for word in line.words))
    return lines


class LayoutPen(Pen):
    def __init__(self, mode="pages", image_sizes=None, chrome=True):
        super().__init__(canvas.Canvas(BytesIO()))
        if mode not in ("pages", "sheet"):
            raise ValueError("mode must be 'pages' or 'sheet'")
        self.mode = mode
        self.image_sizes = image_sizes or {}
        self.chrome = chrome
        self.elements = []
        self.pages = []          # [{page, pageId, title}]
        self.blocks = {}         # (blockId, page) -> bounds
        self._block = None
        self._tags = []
        self._page_id = None
        self._sheet_bottom = 0.0

    # --- model context -------------------------------------------------------
    @contextmanager
    def block(self, block_id, block_type):
        previous = self._block
        self._block = (block_id, block_type)
        try:
            yield
        finally:
            self._block = previous

    @contextmanager
    def tag(self, role, field=None, **extra):
        self._tags.append((role, field, extra))
        try:
            yield
        finally:
            self._tags.pop()

    def _binding(self):
        role, field, extra = self._tags[-1] if self._tags else (None, None, {})
        # Page chrome drawn during a block's page break belongs to the page, not the block.
        block = None if role in CHROME_ROLES else self._block
        binding = {"blockId": block[0] if block else None,
                   "blockType": block[1] if block else None,
                   "pageId": self._page_id, "role": role, "field": field}
        binding.update(extra)
        return binding

    def _emit(self, element, bounds):
        element["page"] = self.page_num
        element["binding"] = self._binding()
        self.elements.append(element)
        x0, y0, x1, y1 = bounds
        self._sheet_bottom = max(self._sheet_bottom, y1)
        if self._block and element["binding"]["blockId"]:
            key = (self._block[0], self.page_num)
            box = self.blocks.get(key)
            if box is None:
                self.blocks[key] = {"blockId": self._block[0], "blockType": self._block[1], "pageId": self._page_id,
                                    "page": self.page_num, "x": x0, "y": y0, "right": x1, "bottom": y1}
            else:
                box["x"], box["y"] = min(box["x"], x0), min(box["y"], y0)
                box["right"], box["bottom"] = max(box["right"], x1), max(box["bottom"], y1)

    # --- images --------------------------------------------------------------
    def load_image(self, src):
        if not src:
            return None
        size = self.image_sizes.get(src)
        if size:
            return ImageSlot(src, size[0], size[1])
        if str(src).startswith("data:image/"):
            image = fetch_image(src)   # embedded: measured locally, no network
            return ImageSlot(src, image.width, image.height) if image is not None else None
        return ImageSlot(src, *UNKNOWN_IMAGE_SIZE, known=False)

    # --- primitives ----------------------------------------------------------
    def fill_rect(self, x, y_top, w, h, fill):
        self._emit(dict(type="rectangle", x=x, y=y_top, width=w, height=h,
                        backgroundColor=color(fill), strokeColor="transparent"), (x, y_top, x + w, y_top + h))

    def stroke_rect(self, x, y_top, w, h, stroke, lw=0.5):
        self._emit(dict(type="rectangle", x=x, y=y_top, width=w, height=h,
                        strokeColor=color(stroke), strokeWidth=lw), (x, y_top, x + w, y_top + h))

    def line(self, x1, y1, x2, y2, stroke, lw=0.5):
        self._emit(dict(type="line", x=x1, y=y1, points=[[0, 0], [x2 - x1, y2 - y1]],
                        strokeColor=color(stroke), strokeWidth=lw),
                   (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)))

    def text(self, x, y_top, s, size, fill, bold=False, align="left", width=None):
        text = safe_text(s)
        if not text.strip():
            return
        text_width = self.string_width(text, size, bold)
        if width is not None and align in ("center", "right"):
            remaining = width - text_width
            x += remaining / 2 if align == "center" else remaining
        self._emit(dict(type="text", x=x, y=y_top, width=text_width, height=size * 1.25, text=text, fontSize=size,
                        lineHeight=1.25, textAlign="left", bold=bold, strokeColor=color(fill)),
                   (x, y_top, x + text_width, y_top + size * 1.25))

    def place_paragraph(self, p, x, y_top, h):
        lines = paragraph_lines(p)
        text = "\n".join(lines)
        if not text.strip():
            return
        style = p.style
        bold = "Bold" in style.fontName
        align = ("left", "center", "right", "left")[style.alignment]
        widest = max((self.string_width(line, style.fontSize, bold) for line in lines), default=0)
        # Resolve alignment here with the PDF's own metrics: the element's x is
        # its left edge, its width is the widest line, and textAlign only
        # centers shorter lines within that width. Clients never re-measure.
        if align == "center":
            x += (p.width - widest) / 2
        elif align == "right":
            x += p.width - widest
        self._emit(dict(type="text", x=x, y=y_top, width=widest, height=h, text=text, fontSize=style.fontSize,
                        lineHeight=style.leading / style.fontSize, textAlign=align, boxWidth=p.width,
                        bold=bold, strokeColor=color(style.textColor)),
                   (x, y_top, x + widest, y_top + h))

    def image(self, img, x, y_top, w, h):
        # Same fit as drawImage(preserveAspectRatio=True, anchor="c").
        scale = min(w / img.width, h / img.height)
        dw, dh = img.width * scale, img.height * scale
        ix, iy = x + (w - dw) / 2, y_top + (h - dh) / 2
        element = dict(type="image", x=ix, y=iy, width=dw, height=dh, src=getattr(img, "src", None))
        if not getattr(img, "known", True):
            element["sizeUnknown"] = True
        self._emit(element, (ix, iy, ix + dw, iy + dh))

    def circle(self, x, y_top, r, fill=None, stroke=None, lw=1):
        self._emit(dict(type="ellipse", x=x - r, y=y_top - r, width=2 * r, height=2 * r,
                        backgroundColor=color(fill), strokeColor=color(stroke), strokeWidth=lw),
                   (x - r, y_top - r, x + r, y_top + r))

    # --- pages ---------------------------------------------------------------
    def _border(self):
        if self.chrome:
            super()._border()

    def _top_bar(self, title):
        if self.chrome:
            return super()._top_bar(title)
        return INNER_Y + 22   # same content top as the drawn bar, nothing emitted

    def _footer(self):
        if self.chrome:
            super()._footer()

    def new_page(self, title, page_id=None):
        if self.mode == "sheet":
            self.page_num += 1
            self._title = title
            self._page_id = page_id
            y = self._sheet_bottom + (SHEET_GAP if self.page_num > 1 else 0)
            self._content_top = y
            self.pages.append({"page": self.page_num, "pageId": page_id, "title": title, "y": y})
            return y
        if self.page_num > 0:
            self._footer()
        self.page_num += 1
        self._title = title
        self._page_id = page_id
        self.pages.append({"page": self.page_num, "pageId": page_id, "title": title})
        self._border()
        y = self._top_bar(title) + 8
        self._content_top = y
        return y

    def ensure_space(self, needed, y_top, title):
        if self.mode == "sheet":
            return y_top
        return super().ensure_space(needed, y_top, title)

    def draw_flowable(self, flow, y_top, page_title, x=None, width=None):
        if self.mode != "sheet":
            return super().draw_flowable(flow, y_top, page_title, x=x, width=width)
        x = INNER_X + SECTION_PAD if x is None else x
        width = INNER_W - 2 * SECTION_PAD if width is None else width
        flow.wrapOn(self.c, width, 1000000)
        _, h = flow.wrap(width, 1000000)
        self._place_flowable(flow, x, y_top, h)
        return y_top + h

    def _place_flowable(self, flow, x, y_top, h):
        """Tables: emit cell backgrounds, borders and one text element per cell,
        using the table's own measured rows, column widths and style commands."""
        rows = len(flow._cellvalues)
        cols = len(flow._colWidths)
        backgrounds = {}
        for command in getattr(flow, "_bkgrndcmds", []):
            if command[0] != "BACKGROUND":
                continue
            (sc, sr), (ec, er), fill = command[1], command[2], command[3]
            sc, ec = (c if c >= 0 else cols + c for c in (sc, ec))
            sr, er = (r if r >= 0 else rows + r for r in (sr, er))
            for r in range(sr, er + 1):
                for c in range(sc, ec + 1):
                    backgrounds[(r, c)] = fill
        y = y_top
        for row_index, (row, height) in enumerate(zip(flow._cellvalues, flow._rowHeights)):
            xx = x
            for column, (values, cell_width) in enumerate(zip(row, flow._colWidths)):
                paragraphs = [v for v in (values if isinstance(values, (tuple, list)) else [values]) if hasattr(v, "wrap")]
                meta = getattr(paragraphs[0], "_aria", {}) if paragraphs else {}
                cell_role = meta.get("role", "cell")
                cell_field = meta.get("field")
                fill = backgrounds.get((row_index, column), COLORS["white"])
                with self.tag(cell_role + "_bg", cell_field):
                    self.fill_rect(xx, y, cell_width, height, fill)
                with self.tag(cell_role + "_border", cell_field):
                    self.stroke_rect(xx, y, cell_width, height, COLORS["borderGrey"], .25)
                for paragraph in paragraphs:
                    _, ph = paragraph.wrap(cell_width - 2 * CELL_PAD, 100000)
                    with self.tag(cell_role, cell_field):
                        self.place_paragraph(paragraph, xx + CELL_PAD, y + (height - ph) / 2, ph)
                xx += cell_width
            y += height
        with self.tag("table_box"):
            self.stroke_rect(x, y_top, sum(flow._colWidths), y - y_top, COLORS["border"], .5)

    def finalize(self):
        if self.page_num > 0 and self.mode == "pages":
            self._footer()

    # --- result --------------------------------------------------------------
    def result(self):
        blocks = [{**box, "width": box["right"] - box["x"], "height": box["bottom"] - box["y"]} for box in self.blocks.values()]
        for box in blocks:
            box.pop("right"), box.pop("bottom")
        if self.mode == "sheet":
            return {"mode": "sheet", "width": PAGE_W, "height": self._sheet_bottom + SHEET_GAP / 2,
                    "elements": self.elements, "blocks": blocks, "pageCount": self.page_num}
        pages = [{**page, "width": PAGE_W, "height": PAGE_H,
                  "elements": [e for e in self.elements if e["page"] == page["page"]]} for page in self.pages]
        return {"mode": "pages", "pageSize": {"width": PAGE_W, "height": PAGE_H}, "pageCount": self.page_num,
                "pages": pages, "blocks": blocks}


def layout_document(document, mode="pages", image_sizes=None, chrome=True):
    pen = LayoutPen(mode=mode, image_sizes=image_sizes, chrome=chrome)
    draw_document(pen, document)
    pen.finalize()
    return pen.result()
