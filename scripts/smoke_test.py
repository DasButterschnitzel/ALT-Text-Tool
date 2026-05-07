"""End-to-end smoke test using a small Ollama vision model.

Generates a synthetic image, runs the full vision pipeline and writes
metadata via ExifTool. Intended for CI; configurable via env vars.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

from alttext.metadata import read_alt_fields, write_alt_text
from alttext.vision import VisionClient


def _make_image(path: Path) -> None:
    img = Image.new("RGB", (640, 480), color=(220, 230, 245))
    draw = ImageDraw.Draw(img)
    draw.rectangle((40, 40, 600, 440), outline=(0, 60, 120), width=8)
    draw.ellipse((220, 160, 420, 320), fill=(255, 200, 0))
    img.save(path, "JPEG")


def main() -> int:
    model = os.environ.get("ALTTEXT_SMOKE_MODEL", "moondream:latest")
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "smoke.jpg"
        _make_image(target)

        client = VisionClient(model=model)
        ok, message = client.check_available()
        if not ok:
            print(f"[smoke] Setup-Check fehlgeschlagen: {message}", file=sys.stderr)
            return 1
        print(f"[smoke] Modell ok: {message}")

        try:
            result = client.describe(target, lang="en", batch_context="abstract test image")
        except Exception as exc:
            print(f"[smoke] describe() Fehler: {exc}", file=sys.stderr)
            return 1
        print(
            f"[smoke] alt='{result.alt_text}' confidence={result.confidence} review={result.needs_review}"
        )

        write_alt_text(target, result.alt_text or "abstract test image", backup=False, force=True)
        fields = read_alt_fields(target)
        print(f"[smoke] geschriebene Felder: {list(fields)}")
        if not fields:
            print("[smoke] Keine Metadaten gelesen, Fehler.", file=sys.stderr)
            return 1
    print("[smoke] OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
