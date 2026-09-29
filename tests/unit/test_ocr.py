"""OCR: preprocessing, layout heuristics, stub/tesseract providers, image + PDF parsers,
searchable PDF. Tesseract-backed tests skip when the binary is missing."""

import io

import fitz
import pytest
from PIL import Image, ImageDraw, ImageFont
from PIL.PngImagePlugin import PngInfo

from app.config import get_settings
from app.ingestion.ocr.base import OcrBlock, OcrPage
from app.ingestion.ocr.layout import heading_levels, page_from_ocr
from app.ingestion.ocr.preprocess import estimate_skew, prepare
from app.ingestion.ocr.searchable import build_searchable_pdf
from app.ingestion.ocr.stub import STUB_TEXT_KEY, StubOcr
from app.ingestion.ocr.tesseract import TesseractOcr, _blocks_from_data
from app.ingestion.parsers import ParsedDocument, ParserError, get_parser
from app.ingestion.parsers.image import ImageParser, frame_count

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def _png_with_text(text: str, size=(800, 600)) -> bytes:
    image = Image.new("RGB", size, "white")
    info = PngInfo()
    info.add_text(STUB_TEXT_KEY, text)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", pnginfo=info)
    return buffer.getvalue()


def _lined_page(angle: float = 0.0) -> Image.Image:
    """Synthetic text lines (black bars) on white, rotated by ``angle`` degrees."""
    image = Image.new("L", (1200, 900), 255)
    draw = ImageDraw.Draw(image)
    for y in range(120, 800, 40):
        draw.rectangle((100, y, 1100 - (y % 3) * 60, y + 14), fill=0)
    if angle:
        image = image.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=255)
    return image


# --- preprocessing --------------------------------------------------------------------


@pytest.mark.parametrize("angle", [0.0, 3.0, -6.5])
def test_estimate_skew_recovers_the_rotation(angle):
    skew = estimate_skew(_lined_page(angle))
    assert abs(skew + angle) <= 0.6  # rotate() is counter-clockwise; the estimate undoes it


def test_prepare_upscales_small_images_and_flattens_lighting():
    image = Image.new("RGB", (600, 400), (200, 200, 200))
    draw = ImageDraw.Draw(image)
    for x in range(600):  # a lighting gradient a phone photo would have
        draw.line((x, 0, x, 400), fill=(60 + x // 4,) * 3)
    prepared = prepare(image)
    assert prepared.transform.scale == 2.0
    assert prepared.image.size == (1200, 800)
    assert prepared.image.mode == "L"
    assert prepared.transform.deskew_deg == 0.0


def test_noisy_scans_are_median_filtered_clean_ones_are_not():
    import numpy as np

    clean = _lined_page()
    assert prepare(clean, deskew=False).transform.denoised is False
    arr = np.asarray(clean, dtype=np.float32)
    noise = np.random.default_rng(1).normal(0, 14, arr.shape)
    noisy = Image.fromarray(np.clip(arr + noise, 0, 255).astype(np.uint8), "L")
    prepared = prepare(noisy, deskew=False)
    assert prepared.transform.denoised is True
    # the filtered paper is flat again
    assert np.asarray(prepared.image)[:60, :].std() < 8


def test_prepare_applies_exif_orientation():
    image = Image.new("RGB", (400, 200), "white")
    exif = image.getexif()
    exif[0x0112] = 6  # rotate 90° CW
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", exif=exif.tobytes())
    prepared = prepare(Image.open(io.BytesIO(buffer.getvalue())), deskew=False)
    assert prepared.transform.exif_rotated is True
    assert prepared.image.width < prepared.image.height


# --- layout ----------------------------------------------------------------------------


def _block(text, line_height, lines=None, y=0):
    lines = lines or [text]
    return OcrBlock(
        text=text,
        bbox=(10, y, 500, y + int(line_height) * len(lines)),
        confidence=90.0,
        line_height=line_height,
        lines=lines,
    )


def test_headings_from_line_height_with_levels():
    page1 = OcrPage(
        1000,
        1400,
        [
            _block("Travel Policy", 60.0),
            _block("This policy applies to every employee of the company.", 24.0),
            _block("Per-diems", 40.0),
            _block("Rates depend on the destination country.", 24.0),
            _block("Not a heading because it ends with a period.", 40.0),
        ],
    )
    page2 = OcrPage(1000, 1400, [_block("Appendix", 40.0), _block("Tables follow.", 24.0)])
    levels = heading_levels([page1, page2])
    parsed = page_from_ocr(1, page1, levels)
    assert parsed.headings == [(1, "Travel Policy"), (2, "Per-diems")]
    assert parsed.text.startswith("Travel Policy\n\nThis policy applies")
    assert parsed.ocr is True and parsed.confidence == 90.0 and parsed.size == (1000, 1400)
    assert page_from_ocr(2, page2, levels).headings == [(2, "Appendix")]


def test_ocr_page_confidence_is_length_weighted():
    page = OcrPage(
        100,
        100,
        [
            OcrBlock("a" * 90, (0, 0, 1, 1), 100.0),
            OcrBlock("b" * 10, (0, 0, 1, 1), 0.0),
            OcrBlock("", (0, 0, 1, 1), 0.0),
        ],
    )
    assert page.confidence == 90.0


# --- providers ------------------------------------------------------------------------


def test_stub_reads_png_metadata_into_blocks_and_headings():
    image = Image.open(
        io.BytesIO(_png_with_text("# Expense Policy\n\nKeep every receipt.\nSubmit monthly."))
    )
    page = StubOcr().recognize(image)
    assert [b.text for b in page.blocks] == [
        "Expense Policy",
        "Keep every receipt. Submit monthly.",
    ]
    assert page.blocks[0].line_height == 48.0 and page.blocks[1].line_height == 24.0
    assert page.confidence == 95.0


def test_tesseract_data_is_grouped_into_paragraph_blocks():
    data = {
        "text": ["Title", "", "Body", "text", "here", "Second", "line"],
        "conf": ["96", "-1", "90", "80", "85", "70", "60"],
        "block_num": [1, 1, 2, 2, 2, 2, 2],
        "par_num": [1, 1, 1, 1, 1, 1, 1],
        "line_num": [1, 1, 1, 1, 1, 2, 2],
        "word_num": [1, 2, 1, 2, 3, 1, 2],
        "left": [10, 0, 10, 60, 110, 10, 70],
        "top": [10, 0, 100, 100, 100, 130, 130],
        "width": [40, 0, 40, 40, 40, 50, 40],
        "height": [30, 0, 20, 20, 20, 20, 20],
    }
    blocks = _blocks_from_data(data)
    assert [b.text for b in blocks] == ["Title", "Body text here Second line"]
    assert blocks[0].bbox == (10, 10, 50, 40) and blocks[0].confidence == 96.0
    assert blocks[1].lines == ["Body text here", "Second line"]
    assert blocks[1].bbox == (10, 100, 150, 150) and blocks[1].line_height == 20.0
    assert blocks[1].confidence == pytest.approx(77.0)


@pytest.mark.skipif(not TesseractOcr.available(), reason="tesseract binary not installed")
def test_tesseract_reads_a_rendered_skewed_page():
    image = Image.new("L", (1600, 1000), 255)
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(FONT, 56)
    body = ImageFont.truetype(FONT, 34)
    draw.text((120, 100), "Vacation Policy", fill=0, font=font)
    draw.text((120, 260), "Employees receive 27 vacation days per year.", fill=0, font=body)
    draw.text((120, 330), "Unused days expire on March 31.", fill=0, font=body)
    skewed = image.rotate(2.5, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=255)

    prepared = prepare(skewed)
    assert abs(prepared.transform.deskew_deg + 2.5) <= 0.6
    page = TesseractOcr().recognize(prepared.image)
    text = page.text
    assert "Vacation Policy" in text
    assert "27 vacation days" in text
    assert "March 31" in text
    assert page.confidence is not None and page.confidence > 70
    heading = next(b for b in page.blocks if "Vacation Policy" in b.text)
    assert heading.line_height is not None and heading.line_height > 40


# --- parsers ---------------------------------------------------------------------------


def test_image_parser_png_frames_and_headings(tmp_path):
    path = tmp_path / "scan.png"
    path.write_bytes(
        _png_with_text("# Onboarding\n\nAccess: hr only\n\nBadges are issued on day one.")
    )
    parsed = ImageParser().parse(path)
    assert len(parsed.pages) == 1
    page = parsed.pages[0]
    assert page.number == 1 and page.ocr is True
    assert page.headings == [(1, "Onboarding")]
    assert page.text == "Onboarding\n\nAccess: hr only\n\nBadges are issued on day one."
    assert get_parser("image/png").__class__ is ImageParser


def test_multi_frame_tiff_is_one_page_per_frame_and_capped(tmp_path, monkeypatch):
    frames = [Image.new("L", (300, 200), 255) for _ in range(3)]
    path = tmp_path / "scan.tiff"
    frames[0].save(path, save_all=True, append_images=frames[1:])
    assert frame_count(path) == 3
    parsed = ImageParser().parse(path)
    assert [p.number for p in parsed.pages] == [1, 2, 3]

    monkeypatch.setenv("OCR_MAX_PAGES", "2")
    get_settings.cache_clear()
    try:
        with pytest.raises(ParserError, match="OCR limit is 2"):
            ImageParser().parse(path)
    finally:
        get_settings.cache_clear()


def test_heic_from_a_phone_is_decoded(tmp_path):
    path = tmp_path / "photo.heic"
    Image.new("RGB", (320, 240), "white").save(path)
    assert frame_count(path) == 1
    assert len(ImageParser().parse(path).pages) == 1


def test_garbage_image_is_a_parser_error(tmp_path):
    path = tmp_path / "broken.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\nnot really")
    assert frame_count(path) is None
    with pytest.raises(ParserError):
        ImageParser().parse(path)


def test_pdf_pages_without_text_layer_go_through_ocr(tmp_path, monkeypatch):
    doc = fitz.open()
    text_page = doc.new_page()
    text_page.insert_text((72, 80), "1. Introduction", fontsize=20)
    text_page.insert_text((72, 120), "This page has a real text layer.", fontsize=11)
    scan_page = doc.new_page()
    scan_page.insert_image(scan_page.rect, stream=_png_with_text("ignored by rasterisation"))
    path = tmp_path / "mixed.pdf"
    doc.save(path)
    doc.close()

    seen = []

    def fake_recognize(image):
        seen.append(image.size)
        return OcrPage(
            image.width,
            image.height,
            [_block("Scanned Appendix", 60.0), _block("Recognised body text.", 24.0)],
        )

    monkeypatch.setattr("app.ingestion.parsers.image.recognize_image", fake_recognize)
    parsed = get_parser("application/pdf").parse(path)
    assert len(seen) == 1  # only the image-only page was rasterised
    assert seen[0][0] > 1000  # 200 dpi of a letter-sized page
    assert parsed.pages[0].ocr is False and "Introduction" in parsed.pages[0].text
    assert parsed.pages[1].ocr is True
    assert parsed.pages[1].headings == [(1, "Scanned Appendix")]
    assert parsed.pages[1].text == "Scanned Appendix\n\nRecognised body text."


# --- searchable pdf ---------------------------------------------------------------------


def test_searchable_pdf_carries_an_invisible_text_layer(tmp_path):
    path = tmp_path / "scan.png"
    path.write_bytes(_png_with_text("# Invoice 4711\n\nTotal due: 1,250.00 EUR"))
    parsed = ImageParser().parse(path)
    payload = build_searchable_pdf(path, False, parsed)
    assert payload is not None
    with fitz.open(stream=payload, filetype="pdf") as pdf:
        assert pdf.page_count == 1
        text = pdf[0].get_text()
        assert "Invoice 4711" in text and "1,250.00 EUR" in text
        assert pdf[0].get_images()  # the original pixels are still the page

    plain = ParsedDocument(pages=[parsed.pages[0].__class__(number=1, text="x")])
    assert build_searchable_pdf(path, False, plain) is None


def test_searchable_pdf_preserves_unicode_and_long_lines(tmp_path):
    from app.ingestion.parsers.base import ParsedPage

    path = tmp_path / "scan.png"
    Image.new("RGB", (800, 600), "white").save(path)
    text = "Rechnung € — Привет " + "invoice amount " * 16
    parsed = ParsedDocument(
        pages=[
            ParsedPage(
                number=1,
                text=text,
                ocr=True,
                size=(800, 600),
                ocr_blocks=[OcrBlock(text, (20, 20, 780, 50), 95, lines=[text])],
            )
        ]
    )
    payload = build_searchable_pdf(path, False, parsed)
    with fitz.open(stream=payload, filetype="pdf") as pdf:
        assert " ".join(pdf[0].get_text().split()) == text.strip()


def test_searchable_pdf_includes_vision_text_without_boxes(tmp_path):
    from app.ingestion.parsers.base import ParsedPage

    path = tmp_path / "scan.png"
    Image.new("RGB", (800, 600), "white").save(path)
    text = "Invoice 123 Total EUR 450"
    parsed = ParsedDocument(
        pages=[
            ParsedPage(
                number=1,
                text=text,
                ocr=True,
                size=(800, 600),
                ocr_blocks=[OcrBlock(text, None, None)],
            )
        ]
    )
    payload = build_searchable_pdf(path, False, parsed)
    with fitz.open(stream=payload, filetype="pdf") as pdf:
        assert text in pdf[0].get_text()


def test_searchable_photo_preserves_exif_orientation(tmp_path):
    path = tmp_path / "phone.jpg"
    image = Image.new("RGB", (800, 400), "white")
    exif = image.getexif()
    exif[0x0112] = 6
    image.save(path, exif=exif)
    parsed = ImageParser().parse(path)
    # The stub has no text in a JPEG; supply one OCR block to exercise the copy.
    parsed.pages[0].ocr_blocks = [_block("Invoice", 24)]
    payload = build_searchable_pdf(path, False, parsed)
    with fitz.open(stream=payload, filetype="pdf") as pdf:
        assert pdf[0].rect.width < pdf[0].rect.height


def test_prepare_bounds_large_image_before_processing():
    from app.ingestion.ocr.preprocess import MAX_SIDE

    image = Image.new("L", (MAX_SIDE + 100, 100), 255)
    assert max(prepare(image, deskew=False).image.size) <= MAX_SIDE


def test_oversized_image_is_a_parser_error(tmp_path, monkeypatch):
    path = tmp_path / "large.png"
    Image.new("L", (100, 100), 255).save(path)
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 100)
    assert frame_count(path) is None
    with pytest.raises(ParserError):
        ImageParser().parse(path)


def test_pdf_rasterization_bounds_dimensions_before_allocation():
    from app.ingestion.ocr.preprocess import MAX_SIDE
    from app.ingestion.parsers.pdf import _rasterize

    with fitz.open() as document:
        page = document.new_page(width=3000, height=100)
        raster = _rasterize(page, 200)
        assert max(raster.size) <= MAX_SIDE
