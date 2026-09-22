"""
Rasterize a rendered PDF to PNG for Aria's vision loop.

Uses pypdfium2 (PDFium, Apache/BSD) — deliberately NOT PyMuPDF/fitz, which is
AGPL and unsuitable for a commercial product. This is the engine behind the
`pdf_observe` tool: render the model -> PDF -> PNG -> hand the image to Aria.
"""

from io import BytesIO

import pypdfium2 as pdfium


def page_count(pdf_bytes: bytes) -> int:
    pdf = pdfium.PdfDocument(pdf_bytes)
    try:
        return len(pdf)
    finally:
        pdf.close()


def _page_png(pdf, idx: int, scale: float, max_dim: int) -> bytes:
    pil = pdf[idx].render(scale=scale).to_pil()
    w, h = pil.size
    if max(w, h) > max_dim:
        f = max_dim / max(w, h)
        pil = pil.resize((int(w * f), int(h * f)))
    if pil.mode not in ("RGB", "L"):
        pil = pil.convert("RGB")
    out = BytesIO()
    pil.save(out, "PNG")
    return out.getvalue()


def render_page_png(pdf_bytes: bytes, page: int = 1, scale: float = 2.0,
                    max_dim: int = 1600) -> bytes:
    """Render a 1-based page number to PNG bytes, downscaling so the longest
    side is <= max_dim (keeps the image small enough for a vision request)."""
    pdf = pdfium.PdfDocument(pdf_bytes)
    try:
        idx = max(0, min(page - 1, len(pdf) - 1))
        return _page_png(pdf, idx, scale, max_dim)
    finally:
        pdf.close()


def render_all_pages_png(pdf_bytes: bytes, scale: float = 2.0,
                         max_dim: int = 1600) -> list[bytes]:
    """Render every page once from a single open document. One request for
    the whole review loop instead of re-uploading the document per page."""
    pdf = pdfium.PdfDocument(pdf_bytes)
    try:
        return [_page_png(pdf, idx, scale, max_dim) for idx in range(len(pdf))]
    finally:
        pdf.close()
