"""Interactive review queue for items below the confidence threshold."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from .metadata import write_alt_text


@dataclass
class ReviewItem:
    image_path: str
    alt_text: str
    confidence: int
    reasoning: str

    @classmethod
    def from_dict(cls, data: dict) -> "ReviewItem":
        return cls(
            image_path=data["image_path"],
            alt_text=data["alt_text"],
            confidence=int(data["confidence"]),
            reasoning=data.get("reasoning", ""),
        )


def review_queue_path(folder: Path) -> Path:
    return folder / "alttext_review_queue.json"


def save_queue(folder: Path, items: list[ReviewItem]) -> Path:
    payload = {
        "created": datetime.now().isoformat(timespec="seconds"),
        "items": [asdict(item) for item in items],
    }
    target = review_queue_path(folder)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def load_queue(folder: Path) -> list[ReviewItem]:
    target = review_queue_path(folder)
    if not target.exists():
        return []
    raw = json.loads(target.read_text(encoding="utf-8"))
    return [ReviewItem.from_dict(entry) for entry in raw.get("items", [])]


def run_review(
    console: Console,
    items: list[ReviewItem],
    *,
    force: bool,
    backup: bool,
    dry_run: bool,
) -> dict[str, int]:
    """Interactively walk through items and write accepted alt texts."""
    counts = {"accepted": 0, "edited": 0, "skipped": 0, "errors": 0}
    if not items:
        console.print("[green]Keine Eintraege in der Review-Queue.[/green]")
        return counts

    for index, item in enumerate(items, start=1):
        console.print(
            Panel.fit(
                f"[bold]{item.image_path}[/bold]\n"
                f"Vorschlag: {item.alt_text}\n"
                f"Confidence: {item.confidence}/10\n"
                f"Begruendung: {item.reasoning}",
                title=f"Review {index}/{len(items)}",
            )
        )
        choice = Prompt.ask(
            "Was tun? [a]kzeptieren, [b]earbeiten, [s]kippen",
            choices=["a", "b", "s"],
            default="b",
        )
        if choice == "s":
            counts["skipped"] += 1
            continue

        text = item.alt_text
        if choice == "b":
            edited = Prompt.ask("Neuer Alt-Text", default=item.alt_text)
            text = edited.strip() or item.alt_text
            counts["edited"] += 1
        else:
            counts["accepted"] += 1

        try:
            written = write_alt_text(
                Path(item.image_path),
                text,
                force=force,
                backup=backup,
                dry_run=dry_run,
            )
            if not written:
                console.print(
                    "[yellow]Bestehende Metadaten nicht ueberschrieben (nutze --force).[/yellow]"
                )
        except Exception as exc:
            counts["errors"] += 1
            console.print(f"[red]Fehler beim Schreiben: {exc}[/red]")
    return counts
