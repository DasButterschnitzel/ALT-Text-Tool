"""End-to-end smoke test using a small Ollama vision model.

Verifies plumbing: Ollama reachable, model installed, image accepted,
response returned, ExifTool can write the triple metadata fields.

JSON-strict output is NOT required here (small models like moondream
often hedge formatting). The full JSON parser is covered by unit tests.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import ollama
from PIL import Image, ImageDraw

from alttext.config import ollama_host
from alttext.image_utils import encode_base64, load_and_resize
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

        # 1. Setup check via VisionClient
        client = VisionClient(model=model)
        ok, message = client.check_available()
        if not ok:
            print(f"[smoke] Setup-Check fehlgeschlagen: {message}", file=sys.stderr)
            return 1
        print(f"[smoke] Modell ok: {message}")

        # 2. Low-level chat call: verify Ollama accepts the image and returns content
        ollama_client = ollama.Client(host=ollama_host())
        encoded = encode_base64(load_and_resize(target))
        response = ollama_client.chat(
            model=model,
            messages=[{"role": "user", "content": "Describe this image briefly.", "images": [encoded]}],
            options={"temperature": 0.0},
        )
        content = (
            response["message"]["content"]
            if isinstance(response, dict)
            else response.message.content
        )
        if not content or not content.strip():
            print("[smoke] Modell-Antwort war leer.", file=sys.stderr)
            return 1
        print(f"[smoke] Modell-Antwort ({len(content)} chars): {content[:120]!r}")

        # 3. Try the full describe() pipeline. Tolerate JSON-format failures
        #    from small models — that path is covered by unit tests.
        try:
            result = client.describe(target, lang="en", batch_context="abstract test image")
            print(
                f"[smoke] describe() ok: alt='{result.alt_text}' "
                f"confidence={result.confidence} review={result.needs_review}"
            )
            alt_text = result.alt_text or "abstract test image"
        except ValueError as exc:
            print(f"[smoke] describe() lieferte kein striktes JSON (toleriert): {exc}")
            alt_text = "abstract test image"

        # 4. Metadata roundtrip
        write_alt_text(target, alt_text, backup=False, force=True)
        fields = read_alt_fields(target)
        print(f"[smoke] geschriebene Felder: {sorted(fields)}")
        if not fields:
            print("[smoke] Keine Metadaten gelesen, Fehler.", file=sys.stderr)
            return 1
        if len(fields) < 3:
            print(
                f"[smoke] Nur {len(fields)}/3 Felder gesetzt — erwartet alle drei.",
                file=sys.stderr,
            )
            return 1

    print("[smoke] OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
