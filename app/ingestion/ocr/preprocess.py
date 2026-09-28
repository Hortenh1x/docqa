"""Photo/scan normalisation before recognition — Pillow + NumPy only.

Steps (each recorded in ``Prepared.transform`` so boxes can be mapped back):
EXIF orientation → grayscale → shadow flattening (divide by a heavily blurred copy, which
removes the lighting gradient of a phone photo) → auto-contrast → deskew (projection
profile search, ±15°) → 2× upscale when the shorter side is under ``MIN_SIDE`` px.
Binarisation is left to the engine: Tesseract's own thresholding beats a global Otsu on
uneven photos.
"""

from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageFilter, ImageOps

MIN_SIDE = 1500
MAX_SIDE = 4500
_SEARCH_DEG = 15.0
_COARSE_STEP = 1.0
_FINE_STEP = 0.1
_ANALYSIS_WIDTH = 800
_MIN_GAIN = 1.15
_MIN_PEAK = 1.3


@dataclass(frozen=True)
class Transform:
    exif_rotated: bool
    deskew_deg: float
    scale: float


@dataclass(frozen=True)
class Prepared:
    image: Image.Image
    transform: Transform


def _flatten_lighting(gray: Image.Image) -> Image.Image:
    radius = max(gray.width, gray.height) // 20 or 1
    background = gray.filter(ImageFilter.GaussianBlur(radius))
    fg = np.asarray(gray, dtype=np.float32)
    bg = np.asarray(background, dtype=np.float32)
    flattened = np.clip(fg / np.maximum(bg, 1.0) * 255.0, 0, 255).astype(np.uint8)
    return Image.fromarray(flattened, mode="L")


def _projection_score(binary: np.ndarray) -> float:
    rows = binary.sum(axis=1, dtype=np.int64)
    return float(np.var(rows))


def _rotate_bool(binary: np.ndarray, angle: float) -> np.ndarray:
    img = Image.fromarray((binary * 255).astype(np.uint8), mode="L")
    rotated = img.rotate(angle, resample=Image.Resampling.BILINEAR, expand=False, fillcolor=0)
    return np.asarray(rotated) > 127


def estimate_skew(gray: Image.Image) -> float:
    """Angle (degrees, counter-clockwise positive) that maximises row-profile variance."""
    if gray.width > _ANALYSIS_WIDTH:
        ratio = _ANALYSIS_WIDTH / gray.width
        gray = gray.resize((_ANALYSIS_WIDTH, max(1, int(gray.height * ratio))))
    arr = np.asarray(gray, dtype=np.uint8)
    # drop the outer 3%: lighting flattening leaves artefacts along the border
    mx, my = max(1, arr.shape[1] // 33), max(1, arr.shape[0] // 33)
    arr = arr[my:-my, mx:-mx]
    if arr.size == 0:
        return 0.0
    threshold = int(np.mean(arr)) - 20
    ink = arr < threshold
    ink_fraction = float(ink.mean())
    # no text-like ink (blank page, photo of a gradient) or a mostly dark image: no skew
    if ink_fraction < 0.002 or ink_fraction > 0.4:
        return 0.0

    def best(candidates: list[float]) -> tuple[float, float]:
        scores = [(_projection_score(_rotate_bool(ink, a)), a) for a in candidates]
        return max(scores)

    coarse = [a * _COARSE_STEP for a in range(int(-_SEARCH_DEG), int(_SEARCH_DEG) + 1)]
    coarse_scores = sorted(_projection_score(_rotate_bool(ink, a)) for a in coarse)
    _, centre = best(coarse)
    fine = [centre + i * _FINE_STEP for i in range(-10, 11)]
    score, angle = best(fine)
    # aligned text lines make the row profile sharply spikier than at any other angle;
    # a gain that is flat against the unrotated image or the typical angle is noise
    # a gradient/stripe artefact ramps smoothly with the angle; real text peaks sharply,
    # so compare with the upper quartile rather than the median
    typical = coarse_scores[(len(coarse_scores) * 3) // 4]
    if score < max(_projection_score(ink) * _MIN_GAIN, typical * _MIN_PEAK):
        return 0.0
    return round(angle, 2)


def prepare(image: Image.Image, *, deskew: bool = True) -> Prepared:
    exif_rotated = False
    transposed = ImageOps.exif_transpose(image)
    if transposed is not None and transposed.size != image.size:
        exif_rotated = True
    image = transposed or image
    gray = image.convert("L")
    gray = _flatten_lighting(gray)
    gray = ImageOps.autocontrast(gray, cutoff=1)

    angle = estimate_skew(gray) if deskew else 0.0
    if abs(angle) >= 0.2:
        gray = gray.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=255)
    else:
        angle = 0.0

    scale = 1.0
    shorter = min(gray.width, gray.height)
    if shorter < MIN_SIDE:
        scale = min(2.0, MAX_SIDE / max(gray.width, gray.height))
        if scale > 1.0:
            gray = gray.resize(
                (int(gray.width * scale), int(gray.height * scale)),
                resample=Image.Resampling.LANCZOS,
            )
        else:
            scale = 1.0
    gray.info = dict(image.info)  # metadata survives (the stub provider reads it)
    return Prepared(image=gray, transform=Transform(exif_rotated, angle, scale))
