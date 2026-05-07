"""Smoke tests for the CLI using Typer's CliRunner and mocked Ollama calls."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from PIL import Image
from typer.testing import CliRunner

from alttext.cli import app
from alttext.vision import VisionResult


def _make_image(path: Path, color=(120, 120, 120)) -> None:
    Image.new("RGB", (50, 50), color=color).save(path, "JPEG")


def _fake_describe_factory(confidence: int = 9):
    def _fake(self, image_path, lang, batch_context, retries=1):
        return VisionResult(
            alt_text=f"Test alt for {Path(image_path).name}",
            confidence=confidence,
            reasoning="ok",
            raw="{}",
            needs_review=confidence < 7,
        )

    return _fake


def test_generate_dry_run_with_limit(tmp_path: Path):
    for i in range(5):
        _make_image(tmp_path / f"img{i}.jpg")

    runner = CliRunner()
    with patch("alttext.vision.VisionClient.check_available", return_value=(True, "ok")), \
         patch("alttext.vision.VisionClient.describe", new=_fake_describe_factory(9)):
        result = runner.invoke(
            app,
            ["generate", str(tmp_path), "--dry-run", "--limit", "2", "--no-recursive"],
            input="N\n",  # decline batch context prompt
        )

    assert result.exit_code == 0, result.output
    assert "limit aktiv" in result.output.lower() or "Limit aktiv" in result.output
    log_files = list(tmp_path.glob("alttext_log_*.csv"))
    assert len(log_files) == 1
    rows = log_files[0].read_text(encoding="utf-8").strip().splitlines()
    # header + 2 rows
    assert len(rows) == 3


def test_generate_workers_parallel(tmp_path: Path):
    for i in range(4):
        _make_image(tmp_path / f"p{i}.jpg")

    runner = CliRunner()
    with patch("alttext.vision.VisionClient.check_available", return_value=(True, "ok")), \
         patch("alttext.vision.VisionClient.describe", new=_fake_describe_factory(9)):
        result = runner.invoke(
            app,
            ["generate", str(tmp_path), "--dry-run", "--workers", "3", "--no-recursive"],
            input="N\n",
        )

    assert result.exit_code == 0, result.output
    log_files = list(tmp_path.glob("alttext_log_*.csv"))
    rows = log_files[0].read_text(encoding="utf-8").strip().splitlines()
    assert len(rows) == 5  # header + 4


def test_generate_review_queue_for_low_confidence(tmp_path: Path):
    _make_image(tmp_path / "low.jpg")

    runner = CliRunner()
    with patch("alttext.vision.VisionClient.check_available", return_value=(True, "ok")), \
         patch("alttext.vision.VisionClient.describe", new=_fake_describe_factory(3)):
        result = runner.invoke(
            app,
            ["generate", str(tmp_path), "--dry-run", "--no-recursive"],
            input="N\nN\n",  # no context, no review now
        )

    assert result.exit_code == 0, result.output
    queue_path = tmp_path / "alttext_review_queue.json"
    assert queue_path.exists()
