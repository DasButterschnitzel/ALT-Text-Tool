"""Manual person annotation for images.

Lets the user attach named persons to images so the vision model can
reference them by name in the alt text. The annotations are stored
per folder in `alttext_people.json` and are picked up automatically
by `alttext generate`.

No face detection, no embeddings, no DSGVO surprises. The user is
responsible for whose names go in.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from rich.console import Console
from rich.prompt import Prompt

from .image_utils import discover_images

PEOPLE_FILE = "alttext_people.json"


def annotations_path(folder: Path) -> Path:
    return folder / PEOPLE_FILE


def load_annotations(folder: Path) -> dict[str, list[str]]:
    """Return a mapping of absolute image path -> list of names."""
    path = annotations_path(folder)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    # Be lenient: accept either {"path": [names]} or
    # {"images": {"path": [names]}}
    if isinstance(data, dict) and "images" in data and isinstance(data["images"], dict):
        return {k: list(v) for k, v in data["images"].items()}
    if isinstance(data, dict):
        return {k: list(v) for k, v in data.items() if isinstance(v, list)}
    return {}


def save_annotations(folder: Path, annotations: dict[str, list[str]]) -> Path:
    target = annotations_path(folder)
    target.write_text(
        json.dumps({"images": annotations}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return target


def open_preview(image_path: Path) -> None:
    """Open the image in the OS default viewer. Best-effort, never raises."""
    try:
        if sys.platform == "win32":
            os.startfile(str(image_path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(image_path)])
        else:
            subprocess.Popen(
                ["xdg-open", str(image_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    except Exception:
        pass


def parse_names(raw: str) -> list[str]:
    return [n.strip() for n in raw.split(",") if n.strip()]


def format_for_prompt(names: list[str], lang: str = "de") -> str:
    """Render a person list as a sentence for the vision prompt."""
    if not names:
        return ""
    if len(names) == 1:
        if lang == "de":
            return f"Auf dem Bild zu sehen: {names[0]}."
        return f"Person in the image: {names[0]}."
    listed = ", ".join(names)
    if lang == "de":
        return f"Auf dem Bild zu sehen (von links nach rechts): {listed}."
    return f"People in the image (left to right): {listed}."


def annotate_folder(
    folder: Path,
    *,
    recursive: bool,
    console: Console,
    preview: bool,
    redo: bool = False,
) -> dict[str, list[str]]:
    """Walk images and prompt the user for person names. Saves after each entry."""
    images, _ = discover_images(folder, recursive=recursive)
    if not images:
        console.print("[yellow]Keine Bilder gefunden.[/yellow]")
        return {}

    annotations = load_annotations(folder)
    console.print(
        f"[bold]{len(images)}[/bold] Bilder im Ordner. "
        f"Bereits annotiert: [bold]{len(annotations)}[/bold]."
    )
    console.print(
        "[dim]Eingabe pro Bild: Komma-getrennte Namen von links nach rechts. "
        "Leer = keine Angabe / zu grosse Gruppe. 'q' = abbrechen, 'd' = vorhandene loeschen.[/dim]"
    )

    for index, path in enumerate(images, start=1):
        key = str(path)
        if key in annotations and not redo:
            console.print(
                f"[dim]({index}/{len(images)}) {path.name} schon annotiert: "
                f"{annotations[key] or 'leer'}[/dim]"
            )
            continue

        if preview:
            open_preview(path)
        existing = annotations.get(key, [])
        default = ", ".join(existing) if existing else ""
        prompt_text = (
            f"({index}/{len(images)}) {path.name} - Personen "
            "(links nach rechts, leer = keine, q = abbrechen, d = leeren)"
        )
        raw = Prompt.ask(prompt_text, default=default)
        cmd = raw.strip().lower()
        if cmd == "q":
            console.print("[yellow]Abgebrochen. Bisheriger Stand bleibt gespeichert.[/yellow]")
            break
        if cmd == "d":
            annotations.pop(key, None)
        else:
            annotations[key] = parse_names(raw)
        save_annotations(folder, annotations)

    return annotations
