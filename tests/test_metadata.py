"""Tests for metadata writer behaviour. Most are skipped without exiftool."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from PIL import Image

from alttext.config import find_exiftool
from alttext.metadata import _matches_field, has_existing_alt, read_alt_fields, write_alt_text

requires_exiftool = pytest.mark.skipif(
    find_exiftool() is None, reason="ExifTool nicht installiert"
)


@pytest.fixture
def jpeg_image(tmp_path: Path) -> Path:
    target = tmp_path / "sample.jpg"
    Image.new("RGB", (100, 100), color=(180, 200, 220)).save(target, "JPEG")
    return target


def test_dry_run_does_not_touch_file(jpeg_image: Path):
    before = jpeg_image.read_bytes()
    written = write_alt_text(jpeg_image, "Testbeschreibung", dry_run=True)
    assert "IPTC:Caption-Abstract" in written
    assert jpeg_image.read_bytes() == before


@requires_exiftool
def test_write_then_read(jpeg_image: Path):
    write_alt_text(jpeg_image, "Ein blaues Quadrat", backup=False)
    fields = read_alt_fields(jpeg_image)
    assert any("blaues Quadrat" in value for value in fields.values())
    assert has_existing_alt(jpeg_image) is True


@requires_exiftool
def test_no_overwrite_without_force(jpeg_image: Path):
    write_alt_text(jpeg_image, "Erster Text", backup=False)
    written = write_alt_text(jpeg_image, "Zweiter Text", backup=False, force=False)
    assert written == {}
    fields = read_alt_fields(jpeg_image)
    assert any("Erster" in value for value in fields.values())


@requires_exiftool
def test_force_overwrites(jpeg_image: Path):
    write_alt_text(jpeg_image, "Erster Text", backup=False)
    write_alt_text(jpeg_image, "Zweiter Text", backup=False, force=True)
    fields = read_alt_fields(jpeg_image)
    assert any("Zweiter" in value for value in fields.values())


def test_matches_field_exact():
    assert _matches_field("XMP:Description", "XMP-dc:Description") is True
    assert _matches_field("XMP-dc:Description", "XMP-dc:Description") is True
    assert _matches_field("IPTC:Caption-Abstract", "IPTC:Caption-Abstract") is True


def test_matches_field_rejects_substrings():
    # EXIF:ImageDescription should NOT count as XMP-dc:Description
    assert _matches_field("EXIF:ImageDescription", "XMP-dc:Description") is False
    assert _matches_field("XMP:UserComment", "XMP-dc:Description") is False


def test_matches_field_alt_text_accessibility():
    assert _matches_field(
        "XMP:AltTextAccessibility", "XMP-iptc4xmpCore:AltTextAccessibility"
    ) is True
