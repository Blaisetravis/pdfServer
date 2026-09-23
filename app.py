"""
PdfServer — stateless tech-pack PDF rendering + rasterization microservice.

Mirrors the ExtServer split: AgentServer (Node) owns the retained document model
and calls this service to (a) render the model to a PDF and (b) rasterize a page
to PNG for Aria's vision loop. No state is held here.

Endpoints:
  GET  /health
  POST /api/pdf/render   -> application/pdf            (body: {document})
  POST /api/pdf/raster   -> image/png                  (body: {document, page, scale})
       ?fmt=json&all_pages -> {page_count, png_base64, pages:[{page, png_base64}]}
  POST /api/pdf/layout   -> model-bound canvas geometry (body: {document, mode, chrome, image_sizes})

Optional auth: set PDFSERVER_API_KEY to require `Authorization: Bearer <key>`.
"""

import base64
import os

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse, Response

from models import LayoutRequest, RasterRequest, RenderRequest, CalloutsBlock
from callout_layout import layout_callouts
from layout import layout_document
from raster import page_count, render_all_pages_png, render_page_png
from render import render_pdf
from canvas_export import CanvasExportRequest, render_canvas_pdf

app = FastAPI(title="PdfServer", version="0.1.0")

API_KEY = os.environ.get("PDFSERVER_API_KEY", "").strip()


def _check_auth(authorization: str | None):
    if not API_KEY:
        return  # auth disabled
    expected = f"Bearer {API_KEY}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="invalid or missing API key")


@app.get("/health")
def health():
    return {"ok": True, "service": "pdfServer", "version": "0.1.0"}


@app.post("/api/pdf/callouts/layout")
def callouts_layout(req: CalloutsBlock, authorization: str | None = Header(default=None)):
    _check_auth(authorization)
    try:
        return layout_callouts(req)
    except (ValueError, OSError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/api/pdf/layout")
def layout(req: LayoutRequest, authorization: str | None = Header(default=None)):
    """Editable canvas geometry for the document, produced by the same block
    renderers as /render. Every element carries a `binding` naming the block,
    page, role and JSON Pointer field it represents."""
    _check_auth(authorization)
    if len(req.document.pages) > 50 or sum(len(p.blocks) for p in req.document.pages) > 2000:
        raise HTTPException(status_code=413, detail="Document too large for one layout request")
    for size in req.image_sizes.values():
        if not all(0 < v <= 20000 for v in size):
            raise HTTPException(status_code=422, detail="Invalid image size")
    try:
        return layout_document(req.document, mode=req.mode, image_sizes=req.image_sizes, chrome=req.chrome)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/api/pdf/render")
def render(req: RenderRequest, authorization: str | None = Header(default=None)):
    _check_auth(authorization)
    pdf = render_pdf(req.document)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "X-Page-Count": str(page_count(pdf)),
            "Content-Disposition": 'inline; filename="techpack.pdf"',
        },
    )


@app.post("/api/pdf/canvas")
def canvas_export(req: CanvasExportRequest, authorization: str | None = Header(default=None)):
    _check_auth(authorization)
    try:
        pdf = render_canvas_pdf(req)
    except (ValueError, OSError) as error:
        raise HTTPException(status_code=422, detail="Invalid canvas content") from error
    return Response(content=pdf, media_type="application/pdf",
                    headers={"X-Page-Count": str(len(req.pages)),
                             "Content-Disposition": 'attachment; filename="techpack.pdf"'})


@app.post("/api/pdf/raster")
def raster(req: RasterRequest, authorization: str | None = Header(default=None),
           fmt: str = "png"):
    """Render the model and return the requested page as a PNG.

    fmt=png       -> raw image/png bytes
    fmt=json      -> {png_base64, page, page_count}  (handy for the agent)
    """
    _check_auth(authorization)
    pdf = render_pdf(req.document)
    total = page_count(pdf)
    if fmt == "json" and req.all_pages:
        pages = [base64.b64encode(png).decode("ascii") for png in render_all_pages_png(pdf, scale=req.scale)]
        idx = max(0, min(req.page - 1, total - 1))
        return JSONResponse({
            "page": req.page,
            "page_count": total,
            "png_base64": pages[idx],
            "pages": [{"page": i + 1, "png_base64": png} for i, png in enumerate(pages)],
        })
    png = render_page_png(pdf, page=req.page, scale=req.scale)
    if fmt == "json":
        return JSONResponse({
            "page": req.page,
            "page_count": total,
            "png_base64": base64.b64encode(png).decode("ascii"),
        })
    return Response(
        content=png,
        media_type="image/png",
        headers={"X-Page-Count": str(total), "X-Page": str(req.page)},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
