"""Language font tests. Run: python test_languages.py

Proves the `lang` switch for translated documents:
  * no lang (and Helvetica languages like "es") lay out exactly as before,
  * a Chinese document is measured with the bundled Noto font, so every wrapped
    line fits its box, and lines break without spaces,
  * the PDF embeds the Noto font, so the Chinese renders instead of black boxes,
  * a language whose font is not installed fails clearly (422 at the endpoint).
"""
import json

from pypdfium2 import PdfDocument
from reportlab.pdfbase.pdfmetrics import stringWidth

from layout import layout_document
from models import Document, Page, SizeChartBlock, SpecSectionBlock, TableBlock, TextBlock
from render import render_pdf
from style import FONTS_DIR, LANGUAGE_FONTS, use_language
from test_fixtures import full_document


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def chinese_document():
    return Document(pages=[Page(id="p1", title="尺寸表", blocks=[
        TextBlock(id="t", variant="heading", text="做旧工艺说明"),
        SpecSectionBlock(id="s", title="做旧规格", bullets=[
            "袖身大面积开放式破洞，边缘毛边不锁边，破洞周围增加细小磨损痕迹；袖口同样做旧处理，罗纹破损并保留毛边效果，整体外观需与确认样一致",
            "袖口同样做旧处理，罗纹破损并保留毛边效果",
            "工厂需按确认样的破洞形状、毛边程度和整体外观执行 26 1/8",
        ]),
        TableBlock(id="tb", title="细节", headers=["#", "细节"], rows=[["1", "连帽 — 套头款"], ["2", "圆领开口 — 无抽绳"]]),
        SizeChartBlock(id="sc", title="成衣尺寸（英寸）", sizes=["XS", "S"], measurements={"衣长": {"XS": "26 1/8", "S": "27 1/8"}}),
    ])])


def test_default_unchanged():
    doc = full_document()
    baseline = json.dumps(layout_document(doc), sort_keys=True)
    with use_language(None):
        check(json.dumps(layout_document(doc), sort_keys=True) == baseline, "lang=None changed the layout")
    with use_language("es"):
        check(json.dumps(layout_document(doc), sort_keys=True) == baseline, "a Helvetica language changed the layout")


def test_chinese_fits_its_boxes():
    doc = chinese_document()
    with use_language("zh-Hans"):
        result = layout_document(doc)
    texts = [e for p in result["pages"] for e in p["elements"] if e["type"] == "text"]
    check(texts, "no text elements")
    for element in texts:
        font = "NotoSansSC-Bold" if element.get("bold") else "NotoSansSC"
        for line in element["text"].split("\n"):
            width = stringWidth(line, font, element["fontSize"])
            box = element.get("boxWidth") or element["width"]
            check(width <= box + 0.5, f"line overflows its box: {line!r} {width:.1f} > {box:.1f}")
    bullets = [e for e in texts if e["binding"].get("role") == "bullet"]
    check(any("\n" in e["text"] for e in bullets), "long Chinese bullets did not wrap")
    check(all(" " not in line.strip("• ") for e in bullets[:2] for line in e["text"].split("\n")),
          "CJK wrapping inserted spaces between characters")

    #HELVETICA HAS NO CHINESE GLYPHS AND MEASURES THEM WRONG; THE NOTO LAYOUT MUST DIFFER//
    check(json.dumps(result, sort_keys=True) != json.dumps(layout_document(doc), sort_keys=True),
          "zh-Hans layout identical to Helvetica layout")


def test_chinese_pdf_embeds_noto():
    with use_language("zh-Hans"):
        pdf = render_pdf(chinese_document())
    check(b"NotoSansSC" in pdf, "the PDF does not embed the Noto font")
    text = PdfDocument(pdf)[0].get_textpage().get_text_range()
    check("做旧规格" in text and "尺寸表" in text, "Chinese text did not survive into the PDF")


def test_missing_font_is_clear():
    missing = [lang for lang, (family, _) in LANGUAGE_FONTS.items() if not (FONTS_DIR / family / f"{family}-Regular.ttf").is_file()]
    for lang in missing:
        try:
            with use_language(lang):
                pass
        except ValueError as error:
            check("not installed" in str(error), f"unclear error for {lang}: {error}")
        else:
            raise AssertionError(f"{lang} has no font but did not fail")
    return missing


def main():
    test_default_unchanged()
    test_chinese_fits_its_boxes()
    test_chinese_pdf_embeds_noto()
    missing = test_missing_font_is_clear()
    print("languages ok" + (f" (fonts not installed yet: {', '.join(missing)})" if missing else ""))


if __name__ == "__main__":
    main()
