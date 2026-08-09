"""Shared image preprocessing pipeline (P2-104).

Transforms applied in the fixed order deskew → denoise → CLAHE when
preprocessing is enabled. A transform failure, an unloadable image, a missing
optional dependency (Pillow/numpy), or an image beyond the dimension guard
returns the original path with a logged warning — the original is never lost.
Shared with Milestone 2.5: one module, not two (R-a). The Milestone 2.5
``intelligence.images.max_dimensions``/``max_bytes`` settings are the formal
decompression-bomb bounds (P2-503); they supersede the historical
``MAX_EDGE = 8000`` guard while keeping it as the default.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

# Optional dependencies — the module degrades to a logged-warning no-op when
# Pillow/numpy are absent (C-3 DoD clause for P2-104).
def _load_dependencies() -> tuple[Any, Any, Any]:
    try:
        import numpy as np
        from PIL import Image, ImageFilter
    except ImportError:
        return None, None, None
    return np, Image, ImageFilter


np, Image, ImageFilter = _load_dependencies()
_DEPENDENCIES_AVAILABLE = all(dep is not None for dep in (np, Image, ImageFilter))

# Sane dimension guard before processing; overridable per call (P2-503).
MAX_EDGE = 8000
DEFAULT_MAX_BYTES = 25 * 1024 * 1024

# Frozen §4.5 declares ``max_dimensions: [8192, 8192]`` — a scalar applies the
# cap to both width and height, a 2-tuple sets each axis independently.
DimGuard = int | tuple[int, int]


def _resolve_dim_guard(max_dimensions: DimGuard | None) -> tuple[int, int]:
    """Normalize the dimension guard to ``(max_width, max_height)``."""
    if max_dimensions is None:
        return MAX_EDGE, MAX_EDGE
    if isinstance(max_dimensions, (tuple, list)):
        width, height = max_dimensions
        return int(width), int(height)
    return int(max_dimensions), int(max_dimensions)


class Preprocessor:
    """Apply the fixed deskew → denoise → CLAHE pipeline to an image path.

    ``process(path)`` returns the preprocessed temp path, or the original
    ``path`` unchanged when preprocessing is disabled, dependencies are
    missing, or a transform fails. The caller owns any returned temp path.
    """

    def __init__(
        self,
        *,
        enabled: bool = False,
        max_dimensions: DimGuard | None = None,
        max_bytes: int | None = None,
    ) -> None:
        self._enabled = enabled
        self._max_dimensions = max_dimensions
        self._max_bytes = max_bytes

    def process(self, path: Path) -> Path:
        """Return a preprocessed temp path, or ``path`` when disabled/failed."""
        if not self._enabled:
            return path
        return preprocess_image(
            path,
            max_dimensions=self._max_dimensions,
            max_bytes=self._max_bytes,
        )


def preprocess_image(
    path: Path,
    *,
    max_dimensions: DimGuard | None = None,
    max_bytes: int | None = None,
) -> Path:
    """Preprocess an image and return a temp processed path (caller cleans up).

    Applies deskew → denoise → CLAHE. Returns ``path`` unchanged with a logged
    warning if dependencies are missing, the image cannot be loaded, it exceeds
    the dimension or byte guard, or any transform fails. The guards default to
    the module ``MAX_EDGE``/``DEFAULT_MAX_BYTES`` (resolved at call time so the
    constants stay monkeypatch-able and the config value can override).
    """
    if not _DEPENDENCIES_AVAILABLE:
        logger.warning(
            "Pillow/numpy unavailable; skipping image preprocessing.",
            extra={"path": str(path)},
        )
        return path

    max_width, max_height = _resolve_dim_guard(max_dimensions)
    byte_guard = DEFAULT_MAX_BYTES if max_bytes is None else max_bytes

    try:
        with Image.open(path) as image:
            image.load()
            if image.width > max_width or image.height > max_height:
                logger.warning(
                    "Image exceeds dimension guard; skipping preprocessing.",
                    extra={"path": str(path), "size": f"{image.width}x{image.height}"},
                )
                return path
            if path.stat().st_size > byte_guard:
                logger.warning(
                    "Image exceeds byte guard; skipping preprocessing.",
                    extra={"path": str(path), "size": path.stat().st_size},
                )
                return path
            try:
                processed = _apply_transforms(image)
            except Exception:
                logger.warning(
                    "Image preprocessing failed; returning original.",
                    extra={"path": str(path)},
                    exc_info=True,
                )
                return path
    except Exception:
        logger.warning(
            "Failed to open image for preprocessing.",
            extra={"path": str(path)},
            exc_info=True,
        )
        return path

    try:
        return _write_temp(processed)
    except Exception:
        logger.warning(
            "Failed to write preprocessed image; returning original.",
            extra={"path": str(path)},
            exc_info=True,
        )
        return path


def _apply_transforms(image: Any) -> Any:
    """Apply the spec-fixed transform order deskew → denoise → CLAHE."""
    gray = image.convert("L")
    gray = _deskew(gray)
    gray = _denoise(gray)
    out = _clahe(np.asarray(gray, dtype=np.uint8))
    return Image.fromarray(out, mode="L")


def estimate_skew_angle(image: Any, *, limit: float = 5.0, step: float = 0.5) -> float:
    """Return the rotation angle (degrees) that straightens text in ``image``.

    Scores candidate rotations by horizontal-projection variance, which is
    maximized when text baselines run horizontally. The returned angle is what
    to pass to ``Image.rotate`` to correct the skew.
    """
    arr = np.asarray(image.convert("L"), dtype=np.uint8)
    binary = (arr < arr.mean()).astype(np.uint8)
    if max(binary.shape) > 512:
        small = Image.fromarray(binary * 255, mode="L")
        small.thumbnail((512, 512))
        binary = (np.asarray(small) > 127).astype(np.uint8)

    best_angle = 0.0
    best_score = -1.0
    for angle in np.arange(-limit, limit + step, step):
        rotated = _rotate_binary(binary, float(angle))
        profile = rotated.sum(axis=1)
        score = float(np.dot(profile, profile))
        if score > best_score:
            best_score, best_angle = score, float(angle)
    return best_angle


def _rotate_binary(binary: Any, angle: float) -> Any:
    """Rotate a 0/1 array, returning floats in [0, 1] for projection scoring."""
    img = Image.fromarray(binary * 255, mode="L")
    return np.asarray(img.rotate(angle, resample=Image.BICUBIC), dtype=np.float64) / 255.0


def _deskew(image: Any) -> Any:
    angle = estimate_skew_angle(image)
    if abs(angle) < 0.5:
        return image
    return image.rotate(angle, resample=Image.BICUBIC, fillcolor=255)


def _denoise(image: Any) -> Any:
    """Median filter — removes salt-and-pepper noise while preserving edges."""
    return image.filter(ImageFilter.MedianFilter(size=3))


def _clahe(
    gray: Any,
    *,
    clip_limit: float = 40.0,
    grid: tuple[int, int] = (8, 8),
) -> Any:
    """Contrast-limited adaptive histogram equalization (vectorized).

    Each tile's histogram is clipped at ``clip_limit`` times the mean bin
    count and the excess redistributed; every pixel is mapped with bilinear
    interpolation across its four neighboring tile LUTs.
    """
    h, w = gray.shape
    nh, nw = grid
    th = (h + nh - 1) // nh
    tw = (w + nw - 1) // nw
    ph, pw = nh * th, nw * tw
    padded = np.pad(gray, ((0, ph - h), (0, pw - w)), mode="edge")

    clip = clip_limit * th * tw / 256.0
    luts = np.zeros((nh, nw, 256), dtype=np.float64)
    for i in range(nh):
        for j in range(nw):
            tile = padded[i * th : (i + 1) * th, j * tw : (j + 1) * tw].ravel()
            hist = np.bincount(tile, minlength=256).astype(np.float64)
            excess = float(np.maximum(hist - clip, 0.0).sum())
            hist = np.minimum(hist, clip) + excess / 256.0
            cdf = np.cumsum(hist)
            luts[i, j] = cdf / cdf[-1] * 255.0

    ys = np.linspace(0.0, nh - 1.0, ph)
    xs = np.linspace(0.0, nw - 1.0, pw)
    y0 = np.floor(ys).astype(int)[:, None]
    y1 = np.minimum(y0 + 1, nh - 1)
    wy = ys[:, None] - y0
    x0 = np.floor(xs).astype(int)[None, :]
    x1 = np.minimum(x0 + 1, nw - 1)
    wx = xs[None, :] - x0

    v = padded
    top = luts[y0, x0, v] * (1.0 - wx) + luts[y0, x1, v] * wx
    bottom = luts[y1, x0, v] * (1.0 - wx) + luts[y1, x1, v] * wx
    out = top * (1.0 - wy) + bottom * wy
    return np.clip(out, 0, 255).astype(np.uint8)[:h, :w]


def _write_temp(image: Any) -> Path:
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    image.save(tmp_path, format="PNG")
    return tmp_path
