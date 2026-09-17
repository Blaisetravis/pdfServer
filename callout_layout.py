"""Editable callout geometry produced by the same renderer as mobile PDFs."""
from io import BytesIO
from math import isfinite
from reportlab.pdfgen import canvas
from render import Pen, render_callouts
from style import COLORS, INNER_X, INNER_W, CELL_PAD, SECTION_PAD, safe_text


def color(value):
    return value.hexval().replace("0x", "#") if value is not None else "transparent"


class LayoutPen(Pen):
    # An infinite sheet: retain PDF block geometry without page breaks/chrome.
    def __init__(self):
        super().__init__(canvas.Canvas(BytesIO()))
        self.elements = []

    def ensure_space(self, needed, y_top, title):
        return y_top

    def fill_rect(self, x, y_top, w, h, fill):
        self.elements.append(dict(type="rectangle", x=x, y=y_top, width=w, height=h,
                                  backgroundColor=color(fill), strokeColor="transparent"))

    def stroke_rect(self, x, y_top, w, h, stroke, lw=0.5):
        self.elements.append(dict(type="rectangle", x=x, y=y_top, width=w, height=h,
                                  strokeColor=color(stroke), strokeWidth=lw))

    def line(self, x1, y1, x2, y2, stroke, lw=0.5):
        self.elements.append(dict(type="line", x=x1, y=y1, points=[[0, 0], [x2-x1, y2-y1]],
                                  strokeColor=color(stroke), strokeWidth=lw))

    def text(self, x, y_top, s, size, fill, bold=False, align="left", width=None):
        text = safe_text(s)
        if width is not None and align in ("center", "right"):
            remaining = width - self.string_width(text, size, bold)
            x += remaining / 2 if align == "center" else remaining
        self.elements.append(dict(type="text", x=x, y=y_top, text=text, fontSize=size,
                                  strokeColor=color(fill)))

    def image(self, img, x, y_top, w, h):
        self.elements.append(dict(type="image", x=x, y=y_top, width=w, height=h))

    def circle(self, x, y_top, r, fill=None, stroke=None, lw=1):
        self.elements.append(dict(type="ellipse", x=x-r, y=y_top-r, width=2*r, height=2*r,
                                  backgroundColor=color(fill), strokeColor=color(stroke), strokeWidth=lw))

    def draw_flowable(self, flow, y_top, page_title, x=None, width=None):
        # Callout legends are ReportLab Tables. Use their measured rows and
        # Paragraph line breaks rather than independently re-laying out the text.
        x = INNER_X + SECTION_PAD if x is None else x
        width = INNER_W - 2 * SECTION_PAD if width is None else width
        flow.wrapOn(self.c, width, 100000)
        y = y_top
        for row_index, (row, height) in enumerate(zip(flow._cellvalues, flow._rowHeights)):
            xx = x
            for column, (values, cell_width) in enumerate(zip(row, flow._colWidths)):
                fill = COLORS["headerBg"] if row_index == 0 else COLORS["bgLight"] if row_index % 2 else COLORS["white"]
                self.fill_rect(xx, y, cell_width, height, fill)
                self.stroke_rect(xx, y, cell_width, height, COLORS["borderGrey"], .25)
                paragraphs = values if isinstance(values, (tuple, list)) else [values]
                for paragraph in paragraphs:
                    _, ph = paragraph.wrap(cell_width - 2 * CELL_PAD, 100000)
                    yy = y + (height-ph)/2
                    for line in paragraph.blPara.lines:
                        if paragraph.blPara.kind == 0:
                            text = " ".join(line[1])
                        else:
                            text = "".join(getattr(word, "text", "") for word in line.words)
                        self.text(xx+CELL_PAD, yy, text, paragraph.style.fontSize,
                                  paragraph.style.textColor, bold=row_index == 0,
                                  align="left" if column == 0 else "center", width=cell_width-2*CELL_PAD)
                        yy += paragraph.style.leading
                xx += cell_width
            y += height
        return y


def layout_callouts(block):
    if not block.image.startswith(("data:image/png;base64,", "data:image/jpeg;base64,")):
        raise ValueError("An embedded garment image is required")
    if not 1 <= len(block.points) <= 24:
        raise ValueError("Use between 1 and 24 callouts per garment")
    if not 100 <= block.max_height <= 600:
        raise ValueError("Invalid callout height")
    numbers = set()
    for point in block.points:
        if point.n in numbers or point.n < 1 or not point.label or len(point.label) > 2000:
            raise ValueError("Invalid callout label or number")
        numbers.add(point.n)
        if not all(isfinite(v) and 0 <= v <= 1 for v in (point.x, point.y)):
            raise ValueError("Feature coordinates must be within the garment image")
    pen = LayoutPen()
    height = render_callouts(pen, block, 20, "CALLOUTS")
    if not any(e["type"] == "image" for e in pen.elements):
        raise ValueError("The garment image could not be loaded")
    return dict(width=612, height=height+20, elements=pen.elements)
