"""Render edited canvas sheets without rebuilding or rewriting their content."""
import base64
import math
from io import BytesIO
from typing import List, Literal, Optional

from PIL import Image
from pydantic import BaseModel, ConfigDict, Field
from reportlab.lib.colors import HexColor
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas


class CanvasElement(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    type: Literal["rectangle", "ellipse", "line", "text", "image"]
    x: float = Field(ge=-10000, le=10000)
    y: float = Field(ge=-10000, le=10000)
    width: float = Field(ge=0, le=10000)
    height: float = Field(ge=0, le=10000)
    angle: float = Field(default=0, ge=-100, le=100)
    stroke: str = "#000000"
    fill: str = "transparent"
    strokeWidth: float = Field(default=1, ge=0, le=100)
    strokeStyle: str = "solid"
    opacity: float = Field(default=100, ge=0, le=100)
    points: Optional[List[List[float]]] = Field(default=None, max_length=10000)
    text: str = Field(default="", max_length=50000)
    fontSize: float = Field(default=9, gt=0, le=1000)
    lineHeight: float = Field(default=1.25, gt=0, le=10)
    textAlign: str = "left"
    data: Optional[str] = Field(default=None, max_length=20000000)


class CanvasPage(BaseModel):
    width: Literal[612] = 612
    height: Literal[792] = 792
    elements: List[CanvasElement] = Field(min_length=1, max_length=10000)


class CanvasExportRequest(BaseModel):
    title: str = Field(default="Tech Pack", max_length=200)
    pages: List[CanvasPage] = Field(min_length=1, max_length=50)


def render_canvas_pdf(request: CanvasExportRequest) -> bytes:
    output = BytesIO()
    pdf = canvas.Canvas(output, pagesize=(612, 792), pageCompression=1)
    pdf.setTitle(request.title)
    for page in request.pages:
        pdf.setPageSize((page.width, page.height))
        for element in page.elements:
            e = element
            pdf.saveState()
            # Browser angles are clockwise in a downward-positive coordinate system.
            cx, cy = e.x + e.width / 2, e.y + e.height / 2
            pdf.translate(cx, page.height - cy)
            pdf.rotate(-math.degrees(e.angle))
            pdf.translate(-e.width / 2, -e.height / 2)
            pdf.setFillAlpha(e.opacity / 100)
            pdf.setStrokeAlpha(e.opacity / 100)
            stroke = e.stroke != "transparent"
            fill = e.fill != "transparent"
            if stroke:
                pdf.setStrokeColor(HexColor(e.stroke))
            if fill:
                pdf.setFillColor(HexColor(e.fill))
            pdf.setLineWidth(e.strokeWidth)
            if e.strokeStyle == "dashed":
                pdf.setDash([e.strokeWidth * 8, e.strokeWidth * 8])
            elif e.strokeStyle == "dotted":
                pdf.setDash([e.strokeWidth, e.strokeWidth * 4])
            if e.type == "rectangle":
                pdf.rect(0, 0, e.width, e.height, stroke=int(stroke), fill=int(fill))
            elif e.type == "ellipse":
                pdf.ellipse(0, 0, e.width, e.height, stroke=int(stroke), fill=int(fill))
            elif e.type == "line":
                points = e.points or []
                if any(len(p) != 2 or any(not math.isfinite(v) or abs(v) > 10000 for v in p) for p in points):
                    raise ValueError("Invalid line points")
                if points:
                    path = pdf.beginPath()
                    path.moveTo(points[0][0], e.height - points[0][1])
                    for x, y in points[1:]:
                        path.lineTo(x, e.height - y)
                    pdf.drawPath(path, stroke=int(stroke), fill=0)
            elif e.type == "text":
                pdf.setFillColor(HexColor(e.stroke))
                lines = e.text.split("\n")
                # Liberation Sans is metrically compatible with PDF Helvetica.
                # Fit the widest line to the actual current canvas text box.
                natural = max((stringWidth(line, "Helvetica", e.fontSize) for line in lines), default=0)
                scale = e.width / natural if natural else 1
                for index, line in enumerate(lines):
                    line_width = stringWidth(line, "Helvetica", e.fontSize) * scale
                    x = (e.width - line_width) / 2 if e.textAlign == "center" else e.width - line_width if e.textAlign == "right" else 0
                    baseline = e.height - e.fontSize * 0.93 - index * e.fontSize * e.lineHeight
                    text = pdf.beginText(x, baseline)
                    text.setFont("Helvetica", e.fontSize)
                    text.setHorizScale(scale * 100)
                    text.textOut(line)
                    pdf.drawText(text)
            elif e.type == "image":
                if not e.data or not e.data.startswith("data:image/png;base64,"):
                    raise ValueError("Expected an embedded PNG image")
                raw = base64.b64decode(e.data.split(",", 1)[1], validate=True)
                with Image.open(BytesIO(raw)) as image:
                    if image.width * image.height > 40000000:
                        raise ValueError("Image dimensions exceed export limit")
                    pdf.drawImage(ImageReader(image), 0, 0, e.width, e.height, mask="auto")
            pdf.restoreState()
        pdf.showPage()
    pdf.save()
    return output.getvalue()
