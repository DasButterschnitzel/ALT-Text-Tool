"""Project-wide constants and paths."""
from __future__ import annotations

import os
import platform
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BIN_DIR = PROJECT_ROOT / "bin"

DEFAULT_MODEL = "qwen3-vl:8b"
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".tiff", ".tif"}
HEIC_EXTENSIONS = {".heic", ".heif"}

MAX_IMAGE_DIMENSION = 1568
MAX_ALT_TEXT_LENGTH = 125
CONFIDENCE_THRESHOLD = 7

# Phrases that automatically lower the model confidence
LOW_CONFIDENCE_PHRASES = (
    "moeglicherweise",
    "möglicherweise",
    "vermutlich",
    "scheint",
    "koennte sein",
    "könnte sein",
    "schwer erkennbar",
    "unklar",
    "ich kann nicht",
)

METADATA_FIELDS = (
    "IPTC:Caption-Abstract",
    "XMP-dc:Description",
    "XMP-iptc4xmpCore:AltTextAccessibility",
)


def find_exiftool() -> str | None:
    """Locate exiftool binary, preferring the bundled one in ./bin."""
    bundled_name = "exiftool.exe" if platform.system() == "Windows" else "exiftool"
    bundled = BIN_DIR / bundled_name
    if bundled.exists():
        return str(bundled)
    on_path = shutil.which("exiftool")
    if on_path:
        return on_path
    return None


def ollama_host() -> str:
    return os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
