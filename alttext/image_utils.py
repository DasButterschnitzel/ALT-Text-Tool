"""Pillow helpers: discovery, resizing, base64 encoding."""
from __future__ import annotations

import base64
import io
from pathlib import Path
from typing import Iterable

from PIL import Image, UnidentifiedImageError

try:
    import pillow_heif

    pillow_heif.register_heif_opener()
    HEIF_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dep
    HEIF_AVAILABLE = False

from .config import HEIC_EXTENSIONS, MAX_IMAGE_DIMENSION, SUPPORTED_EXTENSIONS


def discover_images(folder: Path, recursive: bool) -> tuple[list[Path], list[Path]]:
    """Return (processable_images, unsupported_heic) below folder.

    When pillow-heif is available, HEIC/HEIF files are added to the
    processable list. Otherwise they go into the second list as a hint
    to the user.
    """
    if not folder.exists() or not folder.is_dir():
        raise NotADirectoryError(f"Ordner nicht gefunden: {folder}")

    iterator: Iterable[Path] = folder.rglob("*") if recursive else folder.iterdir()
    supported: list[Path] = []
    heic_skipped: list[Path] = []
    for path in iterator:
        if not path.is_file():
            continue
        ext = path.suffix.lower()
        if ext in SUPPORTED_EXTENSIONS:
            supported.append(path)
        elif ext in HEIC_EXTENSIONS:
            if HEIF_AVAILABLE:
                supported.append(path)
            else:
                heic_skipped.append(path)
    supported.sort()
    heic_skipped.sort()
    return supported, heic_skipped


def load_and_resize(path: Path, max_dim: int = MAX_IMAGE_DIMENSION) -> bytes:
    """Open an image, downscale long edge to max_dim, return JPEG bytes."""
    try:
        with Image.open(path) as img:
            img.load()
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            longest = max(img.size)
            if longest > max_dim:
                scale = max_dim / longest
                new_size = (int(img.size[0] * scale), int(img.size[1] * scale))
                img = img.resize(new_size, Image.LANCZOS)
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=88, optimize=True)
            return buffer.getvalue()
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError(f"Bilddatei nicht lesbar: {path.name}") from exc


def encode_base64(image_bytes: bytes) -> str:
    return base64.b64encode(image_bytes).decode("ascii")


def thumbnail_data_uri(path: Path, max_dim: int = 320) -> str:
    """Build a small data URI for HTML reports."""
    data = load_and_resize(path, max_dim=max_dim)
    return "data:image/jpeg;base64," + encode_base64(data)
