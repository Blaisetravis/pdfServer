"""Fixture documents exercising every block type. Shared by the smoke test,
the layout parity test and local baselines."""
import base64
from io import BytesIO

from PIL import Image, ImageDraw

from models import (
    AbsBlock, AbsElement, CalloutPoint, CalloutsBlock, DividerBlock, Document, HeaderBlock,
    ImageGridBlock, ImageItem, LabelValue, Page, SizeChartBlock, SpacerBlock, SpecSectionBlock,
    SwatchGridBlock, SwatchItem, TableBlock, TextBlock,
)


def data_url(width=400, height=520, color=(230, 226, 214)):
    image = Image.new("RGB", (width, height), color)
    draw = ImageDraw.Draw(image)
    draw.rectangle([width * 0.2, height * 0.15, width * 0.8, height * 0.9], outline=(40, 40, 40), width=4)
    draw.ellipse([width * 0.4, height * 0.05, width * 0.6, height * 0.2], outline=(40, 40, 40), width=4)
    buffer = BytesIO()
    image.save(buffer, "PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


GARMENT = data_url()
SWATCH = data_url(200, 200, (120, 90, 60))


def full_document() -> Document:
    overview = Page(id="p_overview", title="Overview", blocks=[
        HeaderBlock(id="b_header", fields=[
            LabelValue(label="Brand", value="Glocky"),
            LabelValue(label="Style Name", value="Cersi Tee"),
            LabelValue(label="Garment Type", value="Short Sleeve T-Shirt"),
            LabelValue(label="Season", value="FW26"),
            LabelValue(label="Date", value="9/22/2026"),
        ]),
        TextBlock(id="b_title", text="CERSI TEE – TECH PACK", variant="title"),
        ImageGridBlock(id="b_front", cols=2, max_height=260, images=[
            ImageItem(src=GARMENT, label="Front view"),
            ImageItem(src=GARMENT, label="Back view\nsecond line"),
        ]),
        SpecSectionBlock(id="b_colorway", title="Colorway", fields=[LabelValue(label="Body", value="Off-white / cream")]),
        SpecSectionBlock(id="b_fabric", title="Fabric",
                         body="130gsm cotton slub jersey. 100% cotton. Wide unisex fit with a soft enzyme wash "
                              "that keeps the hand relaxed after repeated laundering.",
                         bullets=["Pre-shrunk", "Garment dyed"]),
        DividerBlock(id="b_divider"),
        TextBlock(id="b_note", text="All measurements in inches, ½ tolerance.", variant="small"),
    ])
    specs = Page(id="p_specs", title="Specifications", blocks=[
        SpecSectionBlock(id="b_graphics", title="Graphics", body="Front center chest graphic", fields=[
            LabelValue(label="Artwork", value="Renaissance cherub painting with text underneath"),
            LabelValue(label="Method", value="Screen print"),
        ], bullets=["Placement: Center chest (front)", "Colors: Full color (sepia / earth tones)"]),
        SizeChartBlock(id="b_sizes", title="Measurements", sizes=["S", "M", "L", "XL", "2XL"], measurements={
            "Body Length": {"S": "25 3/8", "M": "26 3/8", "L": "27 3/8", "XL": "28 3/8", "2XL": "29 3/8"},
            "Chest Width": {"S": "18 7/8", "M": "20 7/8", "L": "22 7/8", "XL": "24 7/8", "2XL": "26 7/8"},
            "Sleeve": {"S": "8 3/8", "M": "8 3/4", "L": "9", "XL": "9 1/4"},
        }),
        SpacerBlock(id="b_spacer", height=10),
        TableBlock(id="b_bom", title="Bill of Materials", headers=["Component", "Supplier", "Color", "Qty"], rows=[
            [f"Component {index}", "TBD", "Cream", str(index)] for index in range(1, 46)
        ]),
        TableBlock(id="b_headerless", headers=["", ""], rows=[["Left", "Right"], ["Second", ""]]),
    ])
    materials = Page(id="p_materials", title="Materials", blocks=[
        SwatchGridBlock(id="b_swatches", title="Swatches", cols=3, swatches=[
            SwatchItem(src=SWATCH, label="Main Shell", caption="130gsm slub jersey"),
            SwatchItem(color="#1A1A1A", label="Rib", caption="1x1 rib"),
            SwatchItem(label="Care Label", caption="Printed"),
        ]),
        CalloutsBlock(id="b_callouts", image=GARMENT, view="Front", accent="#E11D2A", max_height=300, points=[
            CalloutPoint(n=1, x=0.5, y=0.1, label="Ribbed crew neck"),
            CalloutPoint(n=2, x=0.2, y=0.4, label="Set-in sleeve"),
            CalloutPoint(n=3, x=0.8, y=0.85, label="Double-needle hem"),
        ]),
        AbsBlock(id="b_abs", elements=[
            AbsElement(kind="text", x=60, y=700, text="Absolute note", font_size=8, bold=True),
            AbsElement(kind="rect", x=300, y=690, w=80, h=30, color="#8E7EAE"),
            AbsElement(kind="line", x=300, y=740, x2=380, y2=760),
            AbsElement(kind="image", x=420, y=680, w=60, h=60, src=GARMENT),
        ]),
    ])
    return Document(id="doc_full", title="Cersi Tee — Tech Pack", pages=[overview, specs, materials])
