"""CLI entry point built with Typer."""
from __future__ import annotations

import csv
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.prompt import Confirm, Prompt
from rich.table import Table

from . import __version__
from .config import DEFAULT_MODEL, find_exiftool, ollama_host
from .image_utils import discover_images, thumbnail_data_uri
from .metadata import (
    ExifToolMissingError,
    has_existing_alt,
    stats_for_folder,
    write_alt_text,
)
from .people import annotate_folder, load_annotations
from .review import ReviewItem, clear_queue, load_queue, run_review, save_queue
from .vision import VisionClient

app = typer.Typer(
    add_completion=False,
    help="Bulk-Generator fuer BITV-konforme Alt-Texte ueber lokales Ollama.",
    no_args_is_help=True,
)
console = Console()


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"alttext {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None, "--version", callback=_version_callback, is_eager=True, help="Version anzeigen"
    ),
) -> None:
    """AltText Generator."""


@app.command()
def check() -> None:
    """Prueft Setup: Ollama erreichbar? Modell installiert? ExifTool da?"""
    table = Table(title="Setup-Pruefung")
    table.add_column("Komponente")
    table.add_column("Status")
    table.add_column("Hinweis")

    binary = find_exiftool()
    if binary:
        table.add_row("ExifTool", "[green]ok[/green]", binary)
    else:
        table.add_row(
            "ExifTool",
            "[red]fehlt[/red]",
            "Lege exiftool(.exe) in ./bin/ ab oder installiere ueber Paketmanager.",
        )

    client = VisionClient()
    ok, message = client.check_available()
    table.add_row(
        "Ollama / Modell",
        "[green]ok[/green]" if ok else "[red]fehlt[/red]",
        f"{ollama_host()} | {message}",
    )
    console.print(table)
    if not (binary and ok):
        raise typer.Exit(code=1)


@app.command()
def stats(folder: Path = typer.Argument(..., exists=True, file_okay=False, dir_okay=True),
          recursive: bool = typer.Option(True, "--recursive/--no-recursive")) -> None:
    """Zeigt, wie viele Bilder im Ordner schon Alt-Texte in den Metadaten haben."""
    images, heic = discover_images(folder, recursive=recursive)
    if heic:
        console.print(f"[yellow]Hinweis: {len(heic)} HEIC/HEIF-Datei(en) werden uebersprungen.[/yellow]")
    if not images:
        console.print("[yellow]Keine unterstuetzten Bilder gefunden.[/yellow]")
        raise typer.Exit()
    try:
        counts = stats_for_folder(images)
    except ExifToolMissingError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)

    table = Table(title=f"Alt-Text-Statistik: {folder}")
    table.add_column("Kategorie")
    table.add_column("Anzahl", justify="right")
    table.add_row("Bilder gesamt", str(counts["total"]))
    table.add_row("Mit Alt-Text", str(counts["with_alt"]))
    table.add_row("Ohne Alt-Text", str(counts["without_alt"]))
    if counts["errors"]:
        table.add_row("Fehler beim Lesen", str(counts["errors"]))
    console.print(table)


def _write_log_row(writer: csv.writer, filename: str, alt_text: str, confidence: int, status: str) -> None:
    writer.writerow([filename, alt_text, confidence, status, datetime.now().isoformat(timespec="seconds")])


def _write_sidecar(image_path: Path, payload: dict) -> None:
    sidecar = image_path.with_suffix(image_path.suffix + ".alttext.json")
    sidecar.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _render_html_report(folder: Path, rows: list[dict]) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = folder / f"alttext_report_{timestamp}.html"
    cards = []
    for row in rows:
        try:
            thumb = thumbnail_data_uri(Path(row["path"]))
        except Exception:
            thumb = ""
        cards.append(
            f"""<article>
  <img src='{thumb}' alt='{row['alt_text']}' />
  <div>
    <h3>{Path(row['path']).name}</h3>
    <p><strong>Alt:</strong> {row['alt_text']}</p>
    <p><strong>Confidence:</strong> {row['confidence']} | <strong>Status:</strong> {row['status']}</p>
  </div>
</article>"""
        )
    html = f"""<!doctype html>
<html lang='de'>
<head>
<meta charset='utf-8' />
<title>AltText Report {timestamp}</title>
<style>
body {{ font-family: system-ui, sans-serif; max-width: 960px; margin: 2rem auto; padding: 0 1rem; }}
article {{ display: flex; gap: 1rem; border-bottom: 1px solid #ddd; padding: 1rem 0; }}
article img {{ width: 240px; height: auto; object-fit: cover; }}
h3 {{ margin: 0 0 .5rem 0; }}
</style>
</head>
<body>
<h1>AltText Report</h1>
<p>Erstellt: {datetime.now().isoformat(timespec='seconds')}</p>
{''.join(cards)}
</body>
</html>"""
    target.write_text(html, encoding="utf-8")
    return target


@app.command()
def generate(
    folder: Path = typer.Argument(..., exists=True, file_okay=False, dir_okay=True, help="Bilderordner"),
    recursive: bool = typer.Option(True, "--recursive/--no-recursive", help="Unterordner einbeziehen"),
    lang: str = typer.Option("de", "--lang", help="Sprache: de oder en"),
    force: bool = typer.Option(False, "--force", help="Bestehende Alt-Texte ueberschreiben"),
    no_backup: bool = typer.Option(False, "--no-backup", help="Kein .original Backup behalten"),
    skip_existing: bool = typer.Option(
        False, "--skip-existing", help="Bilder mit bestehendem Alt-Text ueberspringen"
    ),
    model: str = typer.Option(DEFAULT_MODEL, "--model", help="Ollama Modellname"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Nichts schreiben, nur zeigen"),
    export_csv: bool = typer.Option(False, "--export-csv", help="Nur CSV exportieren, keine Metadaten schreiben"),
    html_report: bool = typer.Option(False, "--html-report", help="HTML-Report mit Thumbnails erzeugen"),
    sidecar: bool = typer.Option(False, "--sidecar", help="Pro Bild eine .alttext.json schreiben"),
    workers: int = typer.Option(
        1, "--workers", "-w", min=1, max=16,
        help="Anzahl paralleler Vision-Aufrufe (Ollama unterstuetzt mehrere Requests).",
    ),
    limit: Optional[int] = typer.Option(
        None, "--limit", min=1,
        help="Nur die ersten N Bilder verarbeiten (nuetzlich zum Testen).",
    ),
) -> None:
    """Generiert Alt-Texte fuer alle Bilder im Ordner."""
    if lang not in {"de", "en"}:
        console.print("[red]--lang muss 'de' oder 'en' sein.[/red]")
        raise typer.Exit(code=2)

    images, heic = discover_images(folder, recursive=recursive)
    if heic:
        console.print(
            f"[yellow]Hinweis: {len(heic)} HEIC/HEIF-Datei(en) uebersprungen. "
            "Installiere pillow-heif (pip install 'alttext[heic]') fuer Support.[/yellow]"
        )
    if not images:
        console.print("[yellow]Keine unterstuetzten Bilder gefunden.[/yellow]")
        raise typer.Exit()
    if limit is not None and limit < len(images):
        console.print(f"[cyan]--limit aktiv: nur die ersten {limit} von {len(images)} Bildern.[/cyan]")
        images = images[:limit]

    console.print(f"[bold]{len(images)}[/bold] Bilder gefunden in {folder}.")
    batch_context: Optional[str] = None
    if Confirm.ask("Moechtest du einen Batch-Kontext angeben?", default=False):
        batch_context = Prompt.ask("Kontext (z. B. 'Aktionstag im Buergerhaus, Mai 2026')")

    client = VisionClient(model=model)
    if not export_csv:
        ok, message = client.check_available()
        if not ok:
            console.print(f"[red]{message}[/red]")
            raise typer.Exit(code=1)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = folder / f"alttext_log_{timestamp}.csv"
    review_items: list[ReviewItem] = []
    report_rows: list[dict] = []

    # utf-8-sig writes a BOM so Excel opens umlauts correctly.
    log_file = log_path.open("w", encoding="utf-8-sig", newline="")
    writer = csv.writer(log_file)
    writer.writerow(["filename", "alt_text", "confidence", "status", "timestamp"])

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console,
    )

    auto_count = 0
    review_count = 0
    skip_count = 0
    error_count = 0

    # Pre-filter: skip-existing check is sequential because it touches ExifTool.
    pending: list[Path] = []
    if skip_existing and not force:
        for path in images:
            try:
                if has_existing_alt(path):
                    _write_log_row(writer, str(path), "", 0, "skip-existing")
                    skip_count += 1
                else:
                    pending.append(path)
            except ExifToolMissingError as exc:
                console.print(f"[red]{exc}[/red]")
                log_file.close()
                raise typer.Exit(code=1)
    else:
        pending = list(images)

    people_map = load_annotations(folder)
    if people_map:
        annotated_in_batch = sum(1 for p in pending if str(p) in people_map)
        console.print(
            f"[cyan]Personen-Annotationen gefunden: {annotated_in_batch}/{len(pending)} "
            "Bilder mit Namen.[/cyan]"
        )

    def _describe(path: Path):
        try:
            names = people_map.get(str(path)) or None
            return (
                path,
                client.describe(path, lang=lang, batch_context=batch_context, people=names),
                None,
            )
        except Exception as exc:
            return path, None, exc

    def _iter_results():
        if workers > 1:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = [executor.submit(_describe, p) for p in pending]
                for fut in as_completed(futures):
                    yield fut.result()
        else:
            for p in pending:
                yield _describe(p)

    try:
        with progress:
            task_id = progress.add_task("Analysiere Bilder", total=len(pending))
            for path, result, exc in _iter_results():
                progress.update(task_id, description=f"[cyan]{path.name}")
                if exc is not None:
                    error_count += 1
                    _write_log_row(writer, str(path), "", 0, f"error:{exc}")
                    progress.advance(task_id)
                    continue

                row = {
                    "path": str(path),
                    "alt_text": result.alt_text,
                    "confidence": result.confidence,
                    "status": "review" if result.needs_review else "auto",
                }

                if sidecar:
                    _write_sidecar(
                        path,
                        {
                            "alt_text": result.alt_text,
                            "confidence": result.confidence,
                            "reasoning": result.reasoning,
                            "model": model,
                            "lang": lang,
                            "context": batch_context or "",
                            "timestamp": datetime.now().isoformat(timespec="seconds"),
                        },
                    )

                if export_csv:
                    _write_log_row(writer, str(path), result.alt_text, result.confidence, row["status"])
                    report_rows.append(row)
                    progress.advance(task_id)
                    continue

                if result.needs_review:
                    review_items.append(
                        ReviewItem(
                            image_path=str(path),
                            alt_text=result.alt_text,
                            confidence=result.confidence,
                            reasoning=result.reasoning,
                        )
                    )
                    review_count += 1
                    _write_log_row(writer, str(path), result.alt_text, result.confidence, "review")
                else:
                    try:
                        write_alt_text(
                            path,
                            result.alt_text,
                            force=force,
                            backup=not no_backup,
                            dry_run=dry_run,
                        )
                        auto_count += 1
                        _write_log_row(
                            writer,
                            str(path),
                            result.alt_text,
                            result.confidence,
                            "auto-dryrun" if dry_run else "auto",
                        )
                    except Exception as exc:
                        error_count += 1
                        _write_log_row(writer, str(path), result.alt_text, result.confidence, f"error:{exc}")
                        review_items.append(
                            ReviewItem(
                                image_path=str(path),
                                alt_text=result.alt_text,
                                confidence=result.confidence,
                                reasoning=f"Schreibfehler: {exc}",
                            )
                        )

                report_rows.append(row)
                progress.advance(task_id)
    finally:
        log_file.close()

    summary = Table(title="Zusammenfassung")
    summary.add_column("Status")
    summary.add_column("Anzahl", justify="right")
    summary.add_row("auto geschrieben", str(auto_count))
    summary.add_row("Review noetig", str(review_count))
    summary.add_row("uebersprungen", str(skip_count))
    summary.add_row("Fehler", str(error_count))
    console.print(summary)
    console.print(f"Logfile: {log_path}")

    if html_report and report_rows:
        report = _render_html_report(folder, report_rows)
        console.print(f"HTML-Report: {report}")

    if export_csv:
        console.print("[green]CSV-Export erstellt, Metadaten unveraendert.[/green]")
        return

    if review_items:
        save_queue(folder, review_items)
        console.print(
            f"[yellow]{len(review_items)} Eintraege warten in der Review-Queue. "
            "Starte sie mit: alttext review <ordner>[/yellow]"
        )
        if Confirm.ask("Review jetzt starten?", default=True):
            run_review(console, review_items, force=force, backup=not no_backup, dry_run=dry_run)


@app.command()
def review(
    folder: Path = typer.Argument(..., exists=True, file_okay=False, dir_okay=True),
    force: bool = typer.Option(False, "--force"),
    no_backup: bool = typer.Option(False, "--no-backup"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Arbeitet die Review-Queue eines vorherigen Laufs ab."""
    items = load_queue(folder)
    if not items:
        console.print("[yellow]Keine Review-Queue vorhanden.[/yellow]")
        raise typer.Exit()
    counts = run_review(console, items, force=force, backup=not no_backup, dry_run=dry_run)
    table = Table(title="Review abgeschlossen")
    for key, value in counts.items():
        table.add_row(key, str(value))
    console.print(table)
    if not dry_run:
        clear_queue(folder)
        console.print("[green]Review-Queue aufgeraeumt.[/green]")


@app.command()
def annotate(
    folder: Path = typer.Argument(..., exists=True, file_okay=False, dir_okay=True),
    recursive: bool = typer.Option(True, "--recursive/--no-recursive"),
    no_preview: bool = typer.Option(
        False, "--no-preview", help="Bilder nicht im Standard-Viewer oeffnen."
    ),
    redo: bool = typer.Option(
        False, "--redo", help="Schon annotierte Bilder erneut abfragen."
    ),
) -> None:
    """Personen pro Bild annotieren - die Namen landen automatisch im Vision-Prompt.

    Du gibst pro Bild Komma-getrennt die Namen von links nach rechts an.
    Leerlassen, wenn die Gruppe zu gross ist oder du keine Namen nennen willst.
    Die Annotationen werden in alttext_people.json gespeichert und beim
    naechsten 'alttext generate' automatisch verwendet.
    """
    annotations = annotate_folder(
        folder,
        recursive=recursive,
        console=console,
        preview=not no_preview,
        redo=redo,
    )
    annotated = sum(1 for v in annotations.values() if v)
    skipped = sum(1 for v in annotations.values() if not v)
    table = Table(title="Annotation gespeichert")
    table.add_row("Mit Namen", str(annotated))
    table.add_row("Bewusst leer (z.B. zu grosse Gruppe)", str(skipped))
    table.add_row("Datei", str(folder / "alttext_people.json"))
    console.print(table)


if __name__ == "__main__":
    app()
