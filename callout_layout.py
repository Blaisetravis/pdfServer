"""Editable callout geometry produced by the same renderer as mobile PDFs.

Kept for the existing /api/pdf/callouts/layout contract (flat, untagged
elements on one sheet). New work should use /api/pdf/layout, which returns
the same geometry with model bindings for every block type."""
from math import isfinite
from layout import LayoutPen
from render import render_callouts


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
    pen = LayoutPen(mode="sheet")
    height = render_callouts(pen, block, 20, "CALLOUTS")
    if not any(e["type"] == "image" for e in pen.elements):
        raise ValueError("The garment image could not be loaded")
    # Legacy shape: exactly the keys the canvas client already consumes, no
    # bindings or page index, and never echo the garment bytes back.
    keep = {"rectangle": ("type", "x", "y", "width", "height", "backgroundColor", "strokeColor", "strokeWidth"),
            "ellipse": ("type", "x", "y", "width", "height", "backgroundColor", "strokeColor", "strokeWidth"),
            "line": ("type", "x", "y", "points", "strokeColor", "strokeWidth"),
            "text": ("type", "x", "y", "text", "fontSize", "strokeColor"),
            "image": ("type", "x", "y", "width", "height")}
    elements = [{k: e[k] for k in keep[e["type"]] if k in e} for e in pen.elements]
    return dict(width=612, height=height + 20, elements=elements)
