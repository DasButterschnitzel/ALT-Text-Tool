"""Tests for review queue persistence."""
from __future__ import annotations

from pathlib import Path

from alttext.review import ReviewItem, clear_queue, load_queue, review_queue_path, save_queue


def test_save_and_load_roundtrip(tmp_path: Path):
    items = [
        ReviewItem(image_path=str(tmp_path / "a.jpg"), alt_text="Hund", confidence=4, reasoning="unsicher"),
        ReviewItem(image_path=str(tmp_path / "b.jpg"), alt_text="Katze", confidence=5, reasoning=""),
    ]
    save_queue(tmp_path, items)
    loaded = load_queue(tmp_path)
    assert len(loaded) == 2
    assert loaded[0].alt_text == "Hund"
    assert loaded[1].confidence == 5


def test_load_empty_when_missing(tmp_path: Path):
    assert load_queue(tmp_path) == []


def test_clear_queue_removes_file(tmp_path: Path):
    items = [ReviewItem(image_path="x", alt_text="y", confidence=3, reasoning="")]
    save_queue(tmp_path, items)
    assert review_queue_path(tmp_path).exists()
    clear_queue(tmp_path)
    assert not review_queue_path(tmp_path).exists()


def test_clear_queue_idempotent(tmp_path: Path):
    clear_queue(tmp_path)  # nothing to clear, must not raise
