# PdfServer

Stateless tech-pack **PDF rendering + rasterization** microservice for Aria
(mobile). Mirrors the ExtServer split: **AgentServer** (Node) owns the retained
*document model* and Aria mutates it via tools; **PdfServer** (this, Python)
turns a model into a PDF and rasterizes pages to PNG for Aria's vision loop.

No state is held here. One request in (a full `Document`), bytes out.

## Stack (license-clean for commercial use)
- **ReportLab** (BSD) — PDF generation
- **pypdfium2** (PDFium, Apache/BSD) — PDF→PNG raster. *Deliberately not PyMuPDF
  (AGPL).*
- **Pillow** (HPND), **FastAPI/uvicorn/pydantic**, **requests**

## Run locally
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python test_render.py          # smoke test -> out/sample.pdf + out/page_*.png
uvicorn app:app --reload --port 8080
```

## Endpoints
| Method | Path | Body | Returns |
|--------|------|------|---------|
| GET  | `/health` | — | `{ok, service, version}` |
| POST | `/api/pdf/render` | `{document}` | `application/pdf` (+ `X-Page-Count`) |
| POST | `/api/pdf/raster?fmt=png\|json` | `{document, page, scale}` | `image/png`, or `{png_base64, page, page_count}` |

Optional auth: set `PDFSERVER_API_KEY` to require `Authorization: Bearer <key>`.

## The document model (the contract)
See `models.py`. A `Document` has `pages[]`; each `Page` has a `title` (top-bar
label) and `blocks[]`. Block types:

- `header` — overview info grid (label/value cells)
- `spec_section` — titled bordered section (body paragraph + fields + bullets)
- `table` — headers + rows (auto-paginates across pages)
- `size_chart` — measurement × size grid
- `image_grid` — N-column image grid (fetches http(s) URLs)
- `text`, `divider`, `spacer`
- `abs` — absolute-coordinate escape hatch (`text/rect/line/image` at x,y)

**Glyph safety:** all text passes through `style.safe_text()`, which converts
Unicode fractions (⅜⅝⅞ …) and sub/superscripts to ASCII — ReportLab's built-in
fonts render those as solid black boxes otherwise. Eighth-fractions are routine
in tech-pack measurements, so this matters.

## Files
- `app.py` — FastAPI service
- `models.py` — the document model (pydantic) = the AgentServer⇄PdfServer contract
- `render.py` — model → PDF (ReportLab; `Pen` = top-down coord wrapper)
- `raster.py` — PDF → PNG (pypdfium2)
- `style.py` — house style (ported from AgentServer `pdf/layout.js`) + `safe_text`
- `test_render.py` — smoke test

## Deploy (Render)
- Build: `pip install -r requirements.txt`
- Start: `uvicorn app:app --host 0.0.0.0 --port $PORT`
- `.python-version` pins 3.12 for the platform (local dev on 3.14 is fine).

## Status / TODO
- v0: render + raster working end-to-end; house style matches current PDFs.
- TODO: footer page totals ("N / M"), platypus-based cell wrapping for long
  table values, image-grid overflow paging polish, A4 page size, request
  validation limits.
