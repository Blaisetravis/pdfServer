"""
PdfServer — stateless tech-pack PDF rendering + rasterization microservice.

Mirrors the ExtServer split: AgentServer (Node) owns the retained document model
and calls this service to (a) render the model to a PDF and (b) rasterize a page
to PNG for Aria's vision loop. No state is held here.

Endpoints:
  GET  /health
  POST /api/pdf/render   -> application/pdf            (body: {document})
  POST /api/pdf/raster   -> image/png                  (body: {document, page, scale})

Optional auth: set PDFSERVER_API_KEY to require `Authorization: Bearer <key>`.
"""

import base64
import os

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse, Response

from models import RasterRequest, RenderRequest
from raster import page_count, render_page_png
from render import render_pdf

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
