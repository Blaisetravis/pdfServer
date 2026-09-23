"""Layout engine tests. Run: python test_layout.py

Proves /api/pdf/layout is the PDF renderer wearing a recording pen:
  * pages mode paginates exactly like the PDF,
  * every editable model value appears as a text element bound to a resolvable
    JSON Pointer whose target holds that value,
  * nothing is emitted without a role,
  * sheet mode has no page chrome,
  * the legacy callouts contract is unchanged.
"""
import json

from models import CalloutPoint, CalloutsBlock
from callout_layout import layout_callouts
from layout import layout_document
from raster import page_count
from render import render_pdf
from style import PAGE_H, PAGE_W, safe_text
from test_fixtures import GARMENT, full_document

CHROME = {"page_border", "page_bar", "page_brand", "page_title", "page_footer"}
EDITABLE_TEXT = {"label", "value", "heading", "body", "bullet", "small", "cell", "header_cell", "caption", "marker_number", "abs_text", "row_label"}


def resolve(block, field):
    node = block
    for part in field.split("/")[1:]:
        part = part.replace("~1", "/").replace("~0", "~")
        node = node[int(part)] if isinstance(node, list) else node[part]
    return node


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def test_pages_match_pdf(doc, result):
    check(result["pageCount"] == page_count(render_pdf(doc)), "layout page count differs from the PDF")
    for page in result["pages"]:
        for element in page["elements"]:
            check(element["binding"]["role"] is not None, f"untagged element {element['type']}")
            check(-1 <= element["x"] <= PAGE_W + 1 and -1 <= element["y"] <= PAGE_H + 1, "element outside the page")
    for box in result["blocks"]:
        check(box["width"] >= 0 and box["height"] >= 0 and box["blockId"], "invalid block bounds")
    for page in result["pages"]:
        for element in page["elements"]:
            if element["binding"]["role"] in CHROME:
                check(element["binding"]["blockId"] is None, "page chrome attributed to a block")
    tallest = max(box["height"] for box in result["blocks"])
    check(tallest < PAGE_H - 100, f"a block box swallowed page chrome ({tallest:.0f}pt tall)")


def test_bindings_resolve(doc, result):
    blocks = {block.id: block.model_dump() for page in doc.pages for block in page.blocks}
    bound = 0
    for page in result["pages"]:
        for element in page["elements"]:
            binding = element["binding"]
            if element["type"] != "text" or binding["role"] not in EDITABLE_TEXT or not binding["field"]:
                continue
            check(binding["blockId"] in blocks, f"unknown block {binding['blockId']}")
            if binding["role"] == "row_label":
                # The pointer names a dictionary key; the label shows that key.
                key = binding["field"].rsplit("/", 1)[1].replace("~1", "/").replace("~0", "~")
                check(resolve(blocks[binding["blockId"]], binding["field"]) is not None and key.replace("_", " ") == element["text"],
                      f"{binding['blockId']}{binding['field']}: row label {element['text']!r} does not name the key")
                bound += 1
                continue
            value = resolve(blocks[binding["blockId"]], binding["field"])
            normalize = lambda text: " ".join(str(text).split()).upper().replace("•  ", "").replace(":", "")
            expected = normalize(safe_text(value).replace("_", " ") if binding["role"] == "cell" else safe_text(value))
            shown = normalize(element["text"])
            check(expected in shown or shown in expected,
                  f"{binding['blockId']}{binding['field']}: expected {value!r}, laid out {element['text']!r}")
            bound += 1
    check(bound > 150, f"suspiciously few bound text elements ({bound})")
    return bound


def test_every_value_is_bound(doc, result):
    fields = {(e["binding"]["blockId"], e["binding"]["field"]) for p in result["pages"] for e in p["elements"] if e["binding"]["field"]}
    for page in doc.pages:
        for block in page.blocks:
            data = block.model_dump()
            if block.type == "table":
                for r, row in enumerate(data["rows"]):
                    for c in range(len(row)):
                        check((block.id, f"/rows/{r}/{c}") in fields, f"{block.id} cell {r},{c} not bound")
            if block.type == "size_chart":
                for name, by_size in data["measurements"].items():
                    for size in by_size:
                        check((block.id, f"/measurements/{name}/{size}") in fields, f"{block.id} {name}/{size} not bound")
            if block.type == "callouts":
                for i, _ in enumerate(data["points"]):
                    for role in ("leader", "dot", "marker"):
                        check(any(e["binding"]["blockId"] == block.id and e["binding"]["role"] == role and e["binding"]["field"] == f"/points/{i}"
                                  for p in result["pages"] for e in p["elements"]), f"{block.id} point {i} has no {role}")
                    check((block.id, f"/points/{i}/label") in fields, f"{block.id} point {i} label not bound")
            if block.type in ("header", "spec_section"):
                for i, _ in enumerate(data["fields"]):
                    check((block.id, f"/fields/{i}/value") in fields, f"{block.id} field {i} not bound")


def test_sheet_mode(doc):
    result = layout_document(doc, mode="sheet")
    roles = {e["binding"]["role"] for e in result["elements"]}
    check(not roles & CHROME, "sheet mode emitted page chrome")
    check(result["height"] > PAGE_H, "sheet mode did not flow past one page")
    check(all(e["binding"]["role"] for e in result["elements"]), "untagged sheet element")
    check(len({b["blockId"] for b in result["blocks"]}) == sum(len(p.blocks) for p in doc.pages) - 1, "sheet blocks mismatch (spacer emits nothing)")


def test_no_chrome(doc):
    result = layout_document(doc, mode="pages", chrome=False)
    roles = {e["binding"]["role"] for p in result["pages"] for e in p["elements"]}
    check(not roles & CHROME, "chrome=False still emitted chrome")
    check(result["pageCount"] == layout_document(doc)["pageCount"], "chrome flag changed pagination")


def test_remote_image_sizes():
    from models import Document, ImageGridBlock, ImageItem, Page
    doc = Document(pages=[Page(id="p", blocks=[ImageGridBlock(id="g", cols=1, max_height=200, images=[ImageItem(src="https://example.com/a.png", label="A")])])])
    unknown = layout_document(doc)["pages"][0]["elements"]
    image = next(e for e in unknown if e["type"] == "image")
    check(image.get("sizeUnknown") is True and image["src"] == "https://example.com/a.png", "unknown remote image not flagged")
    known = layout_document(doc, image_sizes={"https://example.com/a.png": (400, 200)})["pages"][0]["elements"]
    image = next(e for e in known if e["type"] == "image")
    check("sizeUnknown" not in image and abs(image["width"] / image["height"] - 2) < 0.01, "image size not honoured")


def test_legacy_callouts():
    block = CalloutsBlock(image=GARMENT, points=[CalloutPoint(n=1, x=.5, y=.1, label="Neck"), CalloutPoint(n=2, x=.2, y=.6, label="Hem")], max_height=300)
    result = layout_callouts(block)
    check(result["width"] == 612 and result["height"] > 300, "legacy callout sheet size")
    allowed = {"type", "x", "y", "width", "height", "points", "text", "fontSize", "strokeColor", "backgroundColor", "strokeWidth"}
    for element in result["elements"]:
        check(set(element) <= allowed, f"legacy element leaked keys {set(element) - allowed}")
        check("src" not in element, "legacy image echoed the garment")
    check(sum(e["type"] == "image" for e in result["elements"]) == 1, "legacy layout needs exactly one image slot")


def main():
    doc = full_document()
    result = layout_document(doc, mode="pages")
    json.dumps(result)
    test_pages_match_pdf(doc, result)
    bound = test_bindings_resolve(doc, result)
    test_every_value_is_bound(doc, result)
    test_sheet_mode(doc)
    test_no_chrome(doc)
    test_remote_image_sizes()
    test_legacy_callouts()
    total = sum(len(p["elements"]) for p in result["pages"])
    print(f"layout ok: {result['pageCount']} pages, {total} elements, {bound} bound text values, {len(result['blocks'])} block boxes")


if __name__ == "__main__":
    main()
