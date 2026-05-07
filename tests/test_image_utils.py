"""Tests for image discovery and resizing helpers."""
from __future__ import annotations

import io
from pathlib import Path

from PIL import Image

from alttext.image_utils import discover_images, encode_base64, load_and_resize


def _make(path: Path, size=(50, 50)) -> None:
    Image.new("RGB", size, color=(120, 120, 120)).save(path, "JPEG")


def test_discover_finds_supported_extensions(tmp_path: Path):
    _make(tmp_path / "a.jpg")
    _make(tmp_path / "b.png")
    (tmp_path / "ignore.txt").write_text("nope")
    images, heic = discover_images(tmp_path, recursive=False)
    names = sorted(p.name for p in images)
    assert names == ["a.jpg", "b.png"]
    assert heic == []


def test_discover_recursive(tmp_path: Path):
    sub = tmp_path / "sub"
    sub.mkdir()
    _make(tmp_path / "a.jpg")
    _make(sub / "b.jpg")
    images, _ = discover_images(tmp_path, recursive=True)
    assert len(images) == 2
    images, _ = discover_images(tmp_path, recursive=False)
    assert len(images) == 1


def test_discover_reports_heic(tmp_path: Path):
    import alttext.image_utils as iu

    (tmp_path / "photo.heic").write_bytes(b"fake")
    images, heic = discover_images(tmp_path, recursive=False)
    if iu.HEIF_AVAILABLE:
        # When pillow-heif is installed, HEIC is processable, no skip-list entry.
        assert any(p.name == "photo.heic" for p in images)
        assert heic == []
    else:
        assert len(heic) == 1


def test_load_and_resize_downscales(tmp_path: Path):
    target = tmp_path / "big.jpg"
    Image.new("RGB", (3000, 2000), color=(255, 0, 0)).save(target, "JPEG")
    data = load_and_resize(target, max_dim=1568)
    with Image.open(io.BytesIO(data)) as resized:
        assert max(resized.size) <= 1568
        assert max(resized.size) >= 1566


def test_encode_base64():
    encoded = encode_base64(b"hello")
    assert encoded == "aGVsbG8="
