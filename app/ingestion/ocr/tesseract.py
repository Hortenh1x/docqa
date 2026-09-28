"""Tesseract via pytesseract (the ``tesseract`` binary + ``eng`` traineddata).

``image_to_data`` gives words with block/paragraph/line ids, boxes and confidences; we
fold them into paragraph blocks. Automatic page segmentation (psm 3) first; when it finds
almost nothing, the single-block mode (psm 6) rescues photos of a single dense page.
"""

import shutil
import statistics
from collections import defaultdict

import pytesseract
from PIL import Image

from app.ingestion.ocr.base import OcrBlock, OcrError, OcrPage, OcrUnavailableError

_MIN_WORDS_BEFORE_FALLBACK = 20
_OSD_MIN_CONFIDENCE = 2.0


class TesseractOcr:
    def __init__(self, languages: str = "eng") -> None:
        self.languages = languages

    @property
    def name(self) -> str:
        return "tesseract"

    @staticmethod
    def available() -> bool:
        return shutil.which("tesseract") is not None

    def _orient(self, image: Image.Image) -> Image.Image:
        try:
            osd = pytesseract.image_to_osd(image, output_type=pytesseract.Output.DICT)
        except (pytesseract.TesseractError, ValueError, RuntimeError):
            return image  # too little text for OSD — assume upright
        rotate = int(osd.get("rotate") or 0)
        confidence = float(osd.get("orientation_conf") or 0.0)
        if rotate and confidence >= _OSD_MIN_CONFIDENCE:
            return image.rotate(-rotate, expand=True, fillcolor=255)
        return image

    def _data(self, image: Image.Image, psm: int) -> dict[str, list[object]]:
        try:
            result: dict[str, list[object]] = pytesseract.image_to_data(
                image,
                lang=self.languages,
                config=f"--psm {psm}",
                output_type=pytesseract.Output.DICT,
            )
        except pytesseract.TesseractNotFoundError as exc:
            raise OcrUnavailableError("tesseract binary is not installed") from exc
        except pytesseract.TesseractError as exc:
            raise OcrError(f"tesseract failed: {exc}") from exc
        return result

    def recognize(self, image: Image.Image) -> OcrPage:
        image = self._orient(image)
        data = self._data(image, psm=3)
        blocks = _blocks_from_data(data)
        if sum(len(b.text.split()) for b in blocks) < _MIN_WORDS_BEFORE_FALLBACK:
            fallback = _blocks_from_data(self._data(image, psm=6))
            if sum(len(b.text.split()) for b in fallback) > sum(
                len(b.text.split()) for b in blocks
            ):
                blocks = fallback
        return OcrPage(width=image.width, height=image.height, blocks=blocks)


def _blocks_from_data(data: dict[str, list[object]]) -> list[OcrBlock]:
    n = len(data.get("text", []))
    paragraphs: dict[tuple[int, int], dict[int, list[tuple[int, str, float, int, int, int, int]]]]
    paragraphs = defaultdict(lambda: defaultdict(list))
    for i in range(n):
        word = str(data["text"][i]).replace("\x00", "").strip()
        if not word:
            continue
        try:
            conf = float(str(data["conf"][i]))
        except ValueError:
            conf = -1.0
        key = (int(str(data["block_num"][i])), int(str(data["par_num"][i])))
        line = int(str(data["line_num"][i]))
        x, y = int(str(data["left"][i])), int(str(data["top"][i]))
        w, h = int(str(data["width"][i])), int(str(data["height"][i]))
        paragraphs[key][line].append((int(str(data["word_num"][i])), word, conf, x, y, w, h))

    blocks: list[OcrBlock] = []
    for key in sorted(paragraphs):
        lines_text: list[str] = []
        confs: list[float] = []
        heights: list[int] = []
        x0 = y0 = 10**9
        x1 = y1 = -1
        for line_no in sorted(paragraphs[key]):
            words = sorted(paragraphs[key][line_no])
            lines_text.append(" ".join(w[1] for w in words))
            for _, _, conf, x, y, w, h in words:
                if conf >= 0:
                    confs.append(conf)
                heights.append(h)
                x0, y0 = min(x0, x), min(y0, y)
                x1, y1 = max(x1, x + w), max(y1, y + h)
        text = " ".join(lines_text).strip()
        if not text:
            continue
        blocks.append(
            OcrBlock(
                text=text,
                bbox=(x0, y0, x1, y1),
                confidence=statistics.fmean(confs) if confs else None,
                line_height=float(statistics.median(heights)) if heights else None,
                lines=lines_text,
            )
        )
    return blocks
