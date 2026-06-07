"""
Smoke test: build a sample tech-pack Document, render a PDF, rasterize page 1.
Writes out/sample.pdf and out/page_1.png. Run: python test_render.py
"""

import os

from models import (
    Document, Page, HeaderBlock, SpecSectionBlock, TableBlock, SizeChartBlock,
    DividerBlock, LabelValue,
)
from raster import page_count, render_page_png
from render import render_pdf


def build_sample() -> Document:
    overview = Page(title="Overview", blocks=[
        HeaderBlock(fields=[
            LabelValue(label="Brand", value="Glocky"),
            LabelValue(label="Designer", value="B. Travis"),
            LabelValue(label="Description", value="Boxy Heavyweight Tee"),
            LabelValue(label="Season", value="FW26"),
            LabelValue(label="Date", value="June 7, 2026"),
            LabelValue(label="Main Fabric", value="100% Cotton, 240gsm"),
            LabelValue(label="Style Name", value="Atlas Tee"),
            LabelValue(label="Style #", value="GLK-AT-001"),
            LabelValue(label="Size Range", value="S - XL"),
        ]),
    ])

    specs = Page(title="Specifications", blocks=[
        SpecSectionBlock(title="Colors", fields=[
            LabelValue(label="Body", value="Vintage Black (Pantone 19-0303 TCX)"),
            LabelValue(label="Rib", value="Vintage Black"),
        ]),
        SpecSectionBlock(title="Fabric",
                         body="100% combed ring-spun cotton, 240 gsm, garment-dyed. "
                              "Pre-shrunk, soft-hand enzyme wash."),
        SpecSectionBlock(title="Construction", bullets=[
            "Double-needle topstitch at hem and sleeves",
            "1x1 ribbed crew neck collar",
            "Tonal woven label at center back neck",
            "Side-seamed body",
        ]),
    ])

    sizing = Page(title="Size Chart", blocks=[
        SizeChartBlock(
            title="Measurements (inches, 1/2 tolerance)",
            sizes=["S", "M", "L", "XL"],
            measurements={
                # eighth-fractions on purpose: must NOT render as black boxes
                "Body Length": {"S": "27 1/8", "M": "28 1/8", "L": "29 1/8", "XL": "30 1/8"},
                "Chest Width": {"S": "20 1/2", "M": "21 7/8", "L": "23 1/4", "XL": "24 5/8"},
                "Shoulder": {"S": "17 3/8", "M": "18", "L": "18 5/8", "XL": "19 1/4"},
                "Sleeve Length": {"S": "8 3/4", "M": "9", "L": "9 1/4", "XL": "9 1/2"},
            },
        ),
        DividerBlock(),
        TableBlock(
            title="Bill of Materials",
            headers=["Component", "Supplier", "Color", "Qty"],
            rows=[
                ["Main fabric", "TBD", "Vintage Black", "1.4 yd"],
                ["Rib knit", "TBD", "Vintage Black", "0.2 yd"],
                ["Woven label", "TBD", "Black/White", "1"],
                ["Care label", "TBD", "White", "1"],
            ],
        ),
    ])

    return Document(title="Atlas Tee — Tech Pack", pages=[overview, specs, sizing])


def main():
    os.makedirs("out", exist_ok=True)
    doc = build_sample()
    pdf = render_pdf(doc)
    with open("out/sample.pdf", "wb") as f:
        f.write(pdf)
    n = page_count(pdf)
    print(f"PDF: {len(pdf)/1024:.1f} KB, {n} pages -> out/sample.pdf")
    for p in range(1, n + 1):
        png = render_page_png(pdf, page=p)
        with open(f"out/page_{p}.png", "wb") as f:
            f.write(png)
        print(f"  page {p}: {len(png)/1024:.1f} KB -> out/page_{p}.png")


if __name__ == "__main__":
    main()
