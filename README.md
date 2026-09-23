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
| POST | `/api/pdf/layout` | `{document, mode, chrome, image_sizes}` | model-bound canvas geometry (below) |
| POST | `/api/pdf/callouts/layout` | `CalloutsBlock` | legacy flat callout sheet geometry |

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

## Layout endpoint (canvas ⇄ PDF from one code path)
`POST /api/pdf/layout` runs the same block renderers as `/render` with a
recording pen (`layout.py`) and returns editable canvas elements instead of a
PDF. Every element carries a `binding`:

```json
{"type": "text", "x": 52, "y": 118, "text": "26 3/8", "fontSize": 7, "page": 2,
 "binding": {"blockId": "b_sizes", "blockType": "size_chart", "pageId": "p_specs",
             "role": "cell", "field": "/measurements/Body Length/M"}}
```

- `field` is a JSON Pointer (RFC 6901) into the block; `null` means the element
  is derived (grid line, fixed heading) and not directly editable. Role
  `row_label` is the one pointer that names a dictionary KEY (a size-chart
  measurement name): editing it renames the key rather than setting a value.
- Roles: page chrome `page_border page_bar page_brand page_title page_footer`;
  text `heading label value body bullet small caption cell header_cell
  row_label marker_number abs_text`; structure `rule divider grid_border grid_divider
  table_box cell_bg cell_border header_cell_bg header_cell_border card_border`;
  media `image image_placeholder swatch abs_image abs_rect abs_line`; callouts
  `leader dot marker` (each also carries `n`).
- `mode: "pages"` (default) returns `pages[]` of Letter frames with real
  pagination, identical to the PDF; `chrome: false` drops the border/bar/footer
  but keeps the same content geometry. `mode: "sheet"` lays everything on one
  infinite sheet with no page breaks, for single-block relayout.
- `blocks[]` gives each block's bounding box per page it touches.
- **No images are fetched.** Send `image_sizes: {src: [w, h]}` for remote
  images; embedded data URLs are measured locally; unknown remote images get a
  square slot flagged `sizeUnknown: true`.

Element types match the canvas client: `rectangle ellipse line text image`,
with `strokeColor / backgroundColor / strokeWidth`, relative `points` for lines,
and one text element per paragraph or table cell (`lineHeight` is a ratio).
Tables are emitted from the platypus table's own measured rows, column widths
and style commands, so split tables, header repeats and zebra rows match the PDF.

Run `python test_layout.py` after touching `render.py` or `layout.py`.

## Files
- `app.py` — FastAPI service
- `models.py` — the document model (pydantic) = the AgentServer⇄PdfServer contract
- `render.py` — model → PDF (ReportLab; `Pen` = top-down coord wrapper)
- `raster.py` — PDF → PNG (pypdfium2)
- `layout.py` — recording pen: model → tagged canvas geometry (`/api/pdf/layout`)
- `callout_layout.py` — legacy flat callout geometry, built on `layout.py`
- `test_fixtures.py` — all-block fixture documents; `test_layout.py` — layout tests
- `style.py` — house style (ported from AgentServer `pdf/layout.js`) + `safe_text`
- `test_render.py` — smoke test

## Deploy (Render)
A `render.yaml` blueprint is included. **New → Blueprint → pick this repo**, or set up a
Web Service manually with:
- Build: `pip install -r requirements.txt`
- Start: `uvicorn app:app --host 0.0.0.0 --port $PORT`
- Health check: `/health`
- `.python-version` pins 3.12 (local dev on 3.14 is fine).

After it's live, on the **AgentServer** side set `PDFSERVER_URL=https://<your-pdfserver>.onrender.com`
(it defaults to `http://localhost:8080`). If you set `PDFSERVER_API_KEY` on this service,
set the same value on AgentServer so it sends `Authorization: Bearer <key>`.

## Status / TODO
- v0: render + raster working end-to-end; house style matches current PDFs.
- TODO: footer page totals ("N / M"), platypus-based cell wrapping for long
  table values, image-grid overflow paging polish, A4 page size, request
  validation limits.
