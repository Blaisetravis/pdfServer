"""
The tech-pack document model — the contract between AgentServer (which Aria
mutates via tools) and PdfServer (which renders it).

PdfServer is STATELESS: it receives a full Document, renders a PDF or rasterizes
a page, and returns bytes. AgentServer owns the retained model across turns.

Blocks are SEMANTIC (header, spec_section, table, size_chart, image_grid, …) so
the renderer handles layout. `abs` is the absolute-coordinate escape hatch for
when Aria needs to pin something precisely.
"""

from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, Field


# --- shared sub-types -------------------------------------------------------

class LabelValue(BaseModel):
    label: str = ""
    value: str = ""


class ImageItem(BaseModel):
    src: str                       # http(s) URL (Supabase signed URL, etc.)
    label: Optional[str] = None


# --- blocks -----------------------------------------------------------------

class HeaderBlock(BaseModel):
    """Top OVERVIEW info grid (brand / style / season / fabric, etc.)."""
    type: Literal["header"] = "header"
    id: Optional[str] = None
    fields: list[LabelValue] = Field(default_factory=list)
    columns: int = 3


class TextBlock(BaseModel):
    type: Literal["text"] = "text"
    id: Optional[str] = None
    text: str = ""
    variant: Literal["title", "heading", "body", "small"] = "body"


class SpecSectionBlock(BaseModel):
    """A bordered titled section: optional body paragraph + label/value fields
    + bullet list (any combination)."""
    type: Literal["spec_section"] = "spec_section"
    id: Optional[str] = None
    title: str = ""
    body: Optional[str] = None
    fields: list[LabelValue] = Field(default_factory=list)
    bullets: list[str] = Field(default_factory=list)


class TableBlock(BaseModel):
    type: Literal["table"] = "table"
    id: Optional[str] = None
    title: Optional[str] = None
    headers: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)


class SizeChartBlock(BaseModel):
    """Measurement x size grid. measurements maps a measurement name to a
    {size: value} dict, e.g. {"Chest": {"S": "20 1/2", "M": "21 1/2"}}."""
    type: Literal["size_chart"] = "size_chart"
    id: Optional[str] = None
    title: Optional[str] = "Size Chart"
    sizes: list[str] = Field(default_factory=list)
    measurements: dict[str, dict[str, str]] = Field(default_factory=dict)


class ImageGridBlock(BaseModel):
    type: Literal["image_grid"] = "image_grid"
    id: Optional[str] = None
    cols: int = 2
    images: list[ImageItem] = Field(default_factory=list)
    max_height: float = 280.0


class SwatchItem(BaseModel):
    # src optional: label/packaging rows render as a blank captioned card (no image).
    src: Optional[str] = None      # http(s) URL (generated swatch / hardware render)
    label: Optional[str] = None    # bold name under the cell, e.g. "MAIN SHELL"
    caption: Optional[str] = None  # small line, e.g. "14oz denim · Antique brass"


class SwatchGridBlock(BaseModel):
    """A grid of captioned square cards — fabric swatches and rendered hardware
    for the BOM / materials page."""
    type: Literal["swatch_grid"] = "swatch_grid"
    id: Optional[str] = None
    title: Optional[str] = None
    cols: int = 3
    swatches: list[SwatchItem] = Field(default_factory=list)


class DividerBlock(BaseModel):
    type: Literal["divider"] = "divider"
    id: Optional[str] = None


class SpacerBlock(BaseModel):
    type: Literal["spacer"] = "spacer"
    id: Optional[str] = None
    height: float = 12.0


# --- absolute escape hatch --------------------------------------------------

class AbsElement(BaseModel):
    """A single primitive drawn at an absolute top-left (x, y) in points."""
    kind: Literal["text", "rect", "line", "image"]
    x: float
    y: float
    # text
    text: Optional[str] = None
    font_size: Optional[float] = 9
    bold: bool = False
    # rect / line / image
    w: Optional[float] = None
    h: Optional[float] = None
    x2: Optional[float] = None
    y2: Optional[float] = None
    src: Optional[str] = None
    color: Optional[str] = None     # hex, e.g. "#333333"


class AbsBlock(BaseModel):
    type: Literal["abs"] = "abs"
    id: Optional[str] = None
    elements: list[AbsElement] = Field(default_factory=list)


Block = Annotated[
    Union[
        HeaderBlock,
        TextBlock,
        SpecSectionBlock,
        TableBlock,
        SizeChartBlock,
        ImageGridBlock,
        SwatchGridBlock,
        DividerBlock,
        SpacerBlock,
        AbsBlock,
    ],
    Field(discriminator="type"),
]


class Page(BaseModel):
    id: Optional[str] = None
    title: str = ""                 # right-side label in the top bar
    blocks: list[Block] = Field(default_factory=list)


class Document(BaseModel):
    id: Optional[str] = None
    title: str = "Tech Pack"        # PDF metadata title
    author: str = "Tchpack by Aria"
    page_size: Literal["letter"] = "letter"   # A4 later
    pages: list[Page] = Field(default_factory=list)


# --- request envelopes ------------------------------------------------------

class RenderRequest(BaseModel):
    document: Document


class RasterRequest(BaseModel):
    document: Document
    page: int = 1                   # 1-based page number to rasterize
    scale: float = 2.0              # render scale for the PNG
