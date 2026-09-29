"""OCR quality on synthetic scans of the demo corpus (English, Tesseract).

Ten corpus policies are typeset to PDF pages (DejaVu Sans, 11 pt body / 16 pt headings),
rasterised at 200 dpi and degraded three ways:

- ``scan``   — clean rasterisation (a flatbed scanner)
- ``skewed`` — 3° rotation + gaussian noise (a hurried scan)
- ``photo``  — 1400 px wide, perspective tilt, lighting gradient, JPEG q=70 (a phone)

Each variant goes through ``ImageParser`` (preprocessing + OCR + layout). Metrics per
variant: word error rate against the typeset text (word-level edit distance / words),
heading recall (typeset headings found in ``ParsedPage.headings``), mean confidence,
seconds per page. Writes ``eval/results_ocr.md``. Run:

    OCR_PROVIDER=tesseract uv run python -m eval.ocr.run_ocr_eval
"""

import io
import random
import re
import statistics
import time
from dataclasses import dataclass
from pathlib import Path

import fitz
import numpy as np
from PIL import Image, ImageFilter
from PIL.PngImagePlugin import PngInfo

from app.ingestion.parsers.image import ImageParser

CORPUS = Path("corpus")
DOCS = [
    "HR-001",
    "HR-002",
    "HR-003",
    "FIN-001",
    "OPS-001",
    "POL-001-v2",
    "SEC-001",
    "POL-006",
    "HR-004",
    "EXEC-001",
]
OUT = Path("eval/results_ocr.md")
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
DPI = 200
MAX_PAGES_PER_DOC = 2
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


@dataclass
class Typeset:
    words: list[str]
    headings: list[str]


def _strip_front_matter(text: str) -> str:
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[end + 4 :]
    return text


def typeset(md: str) -> tuple[bytes, list[Typeset]]:
    """Markdown → PDF pages; returns the PDF and the words/headings placed on each page."""
    doc = fitz.open()
    pages: list[Typeset] = []
    page = doc.new_page(width=595, height=842)
    y = 60.0
    current = Typeset([], [])
    body_font = fitz.Font(fontfile=FONT)
    bold_font = fitz.Font(fontfile=FONT_BOLD)
    page.insert_font(fontname="body", fontbuffer=body_font.buffer)
    page.insert_font(fontname="bold", fontbuffer=bold_font.buffer)

    def new_page() -> None:
        nonlocal page, y, current
        pages.append(current)
        current = Typeset([], [])
        page = doc.new_page(width=595, height=842)
        page.insert_font(fontname="body", fontbuffer=body_font.buffer)
        page.insert_font(fontname="bold", fontbuffer=bold_font.buffer)
        y = 60.0

    for raw in _strip_front_matter(md).splitlines():
        line = raw.strip()
        if not line or line.startswith("|") or line.startswith("```"):
            continue
        match = _HEADING_RE.match(line)
        if len(pages) >= MAX_PAGES_PER_DOC and y > 700:
            break
        if match:
            text = match.group(2)
            if y > 760:
                new_page()
            y += 10
            page.insert_text((50, y), text, fontsize=16, fontname="bold")
            current.headings.append(text)
            current.words.extend(text.split())
            y += 26
            continue
        text = re.sub(r"[*_`]", "", line)
        text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", text)
        # wrap at ~95 chars for 11 pt
        words = text.split()
        row: list[str] = []
        for word in words:
            if sum(len(w) + 1 for w in row) + len(word) > 92:
                if y > 780:
                    new_page()
                page.insert_text((50, y), " ".join(row), fontsize=11, fontname="body")
                current.words.extend(row)
                y += 16
                row = []
            row.append(word)
        if row:
            if y > 780:
                new_page()
            page.insert_text((50, y), " ".join(row), fontsize=11, fontname="body")
            current.words.extend(row)
            y += 16
        y += 6
        if len(pages) >= MAX_PAGES_PER_DOC:
            break
    pages.append(current)
    payload = doc.tobytes()
    doc.close()
    return payload, pages[:MAX_PAGES_PER_DOC]


def rasterise(pdf: bytes, index: int) -> Image.Image:
    with fitz.open(stream=pdf, filetype="pdf") as doc:
        pix = doc[index].get_pixmap(dpi=DPI, colorspace=fitz.csGRAY, alpha=False)
        return Image.frombytes("L", (pix.width, pix.height), pix.samples)


def degrade(image: Image.Image, variant: str, rng: random.Random) -> Image.Image:
    if variant == "scan":
        return image
    if variant == "skewed":
        rotated = image.rotate(3.0, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=255)
        arr = np.asarray(rotated, dtype=np.float32)
        noise = np.random.default_rng(rng.randint(0, 10**6)).normal(0, 12, arr.shape)
        return Image.fromarray(np.clip(arr + noise, 0, 255).astype(np.uint8), "L")
    # photo: downscale, perspective tilt, lighting gradient, blur, JPEG
    w, h = image.size
    scale = 1400 / w
    small = image.resize((1400, int(h * scale)), Image.Resampling.LANCZOS)
    sw, sh = small.size
    tilt = int(sw * 0.04)
    coeffs = _perspective(
        [(0, 0), (sw, 0), (sw, sh), (0, sh)],
        [(tilt, 0), (sw - tilt // 2, tilt // 2), (sw, sh), (0, sh - tilt)],
    )
    warped = small.transform(
        (sw, sh), Image.Transform.PERSPECTIVE, coeffs, Image.Resampling.BICUBIC, fillcolor=235
    )
    arr = np.asarray(warped, dtype=np.float32)
    gradient = np.linspace(0.65, 1.0, sw, dtype=np.float32)[None, :]
    arr = arr * gradient
    photo = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "L")
    photo = photo.filter(ImageFilter.GaussianBlur(0.6))
    buffer = io.BytesIO()
    photo.convert("RGB").save(buffer, format="JPEG", quality=70)
    return Image.open(io.BytesIO(buffer.getvalue())).convert("L")


def _perspective(src: list[tuple[int, int]], dst: list[tuple[int, int]]) -> list[float]:
    matrix = []
    for (x, y), (u, v) in zip(dst, src, strict=True):
        matrix.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        matrix.append([0, 0, 0, x, y, 1, -v * x, -v * y])
    a = np.array(matrix, dtype=np.float64)
    b = np.array([c for pt in src for c in pt], dtype=np.float64)
    return list(np.linalg.solve(a, b))


def word_error_rate(reference: list[str], hypothesis: list[str]) -> float:
    ref = [_norm(w) for w in reference]
    hyp = [_norm(w) for w in hypothesis]
    ref = [w for w in ref if w]
    hyp = [w for w in hyp if w]
    if not ref:
        return 0.0
    prev = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        cur = [i] + [0] * len(hyp)
        for j, h in enumerate(hyp, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (r != h))
        prev = cur
    return prev[-1] / len(ref)


def _norm(word: str) -> str:
    return re.sub(r"[^a-z0-9]", "", word.lower())


def main() -> None:
    rng = random.Random(7)
    parser = ImageParser()
    rows: dict[str, list[tuple[float, float, float | None, float]]] = {
        "scan": [],
        "skewed": [],
        "photo": [],
    }
    tmp = Path("eval/ocr/tmp")
    tmp.mkdir(parents=True, exist_ok=True)
    for name in DOCS:
        path = CORPUS / f"{name}.md"
        if not path.exists():
            continue
        pdf, pages = typeset(path.read_text(encoding="utf-8"))
        for index, truth in enumerate(pages):
            if not truth.words:
                continue
            base = rasterise(pdf, index)
            for variant in rows:
                image = degrade(base, variant, rng)
                file = tmp / f"{name}-{index}-{variant}.png"
                info = PngInfo()
                image.save(file, pnginfo=info)
                started = time.perf_counter()
                parsed = parser.parse(file)
                elapsed = time.perf_counter() - started
                page = parsed.pages[0]
                wer = word_error_rate(truth.words, page.text.split())
                found = [h for _, h in page.headings]
                recall = (
                    sum(1 for h in truth.headings if any(_norm(h) == _norm(f) for f in found))
                    / len(truth.headings)
                    if truth.headings
                    else 1.0
                )
                rows[variant].append((wer, recall, page.confidence, elapsed))
                print(
                    f"{name} p{index + 1} {variant:6s} WER={wer:.3f} headings={recall:.2f} "
                    f"conf={page.confidence} {elapsed:.1f}s"
                )

    lines = [
        "# OCR evaluation (Tesseract, English, synthetic scans of the demo corpus)",
        "",
        f"{sum(len(v) for v in rows.values()) // 3} typeset pages × 3 degradations; "
        "see `eval/ocr/run_ocr_eval.py` for how they are made.",
        "",
        "| Variant | Pages | Word error rate (mean / median) | Heading recall "
        "| Mean confidence | s / page |",
        "|---|---|---|---|---|---|",
    ]
    for variant, values in rows.items():
        if not values:
            continue
        wers = [v[0] for v in values]
        recalls = [v[1] for v in values]
        confs = [v[2] for v in values if v[2] is not None]
        secs = [v[3] for v in values]
        lines.append(
            f"| {variant} | {len(values)} | {statistics.mean(wers):.3f} / "
            f"{statistics.median(wers):.3f} "
            f"| {statistics.mean(recalls):.2f} | {statistics.mean(confs):.1f} | "
            f"{statistics.mean(secs):.1f} |"
        )
    lines += [
        "",
        "Word error rate = word-level edit distance between the typeset words and the recognised "
        "text, divided by the typeset word count (punctuation and case ignored). Heading recall = "
        "typeset headings that the line-height heuristic turned into section headings.",
    ]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
