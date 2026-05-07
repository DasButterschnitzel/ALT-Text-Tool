# AltText Generator

Bulk-Generierung BITV-konformer Alt-Texte fuer Bilder, lokal mit Ollama und Qwen2.5-VL. Schreibt die Beschreibungen direkt in IPTC- und XMP-Metadaten. Keine Cloud, kein Upload, alles bleibt auf deiner Maschine.

> Du brauchst kein Cloud-Konto. Alle Modellaufrufe gehen ueber `localhost` an dein lokales Ollama.

## Voraussetzungen

- Windows mit NVIDIA-GPU (CPU funktioniert auch, aber langsam)
- Python 3.11 oder neuer
- [Ollama](https://ollama.com/download) installiert und gestartet
- ExifTool (Windows-Binary in `./bin/exiftool.exe` oder ueber Paketmanager)

## Installation

```bash
# 1. Repo klonen
git clone https://github.com/DasButterschnitzel/ALT-Text-Tool.git
cd ALT-Text-Tool

# 2. Virtuelle Umgebung
python -m venv .venv
.\.venv\Scripts\activate            # Windows
source .venv/bin/activate            # Linux/macOS

# 3. Python-Abhaengigkeiten
pip install -r requirements.txt
pip install -e .

# 4. Vision-Modell ziehen (einmalig, ca. 6 GB)
ollama pull qwen2.5vl:7b

# 5. Setup pruefen
alttext check
```

### ExifTool bereitstellen

Lege `exiftool.exe` (Windows) bzw. `exiftool` (Linux/macOS) in den Ordner `./bin/`. Der Windows-Build ist hier zu finden: <https://exiftool.org>. Linux: `sudo apt install libimage-exiftool-perl`. macOS: `brew install exiftool`.

## Beispiel-Aufrufe

```bash
# Standard-Lauf, rekursiv, deutsche Texte
alttext generate ./fotos --recursive

# Englische Texte, ohne Backup-Dateien
alttext generate ./photos --lang en --no-backup

# 4 Bilder gleichzeitig analysieren (Ollama-Server haelt das gut aus)
alttext generate ./fotos --workers 4

# Nur die ersten 5 Bilder verarbeiten (Test-Lauf)
alttext generate ./fotos --limit 5 --dry-run

# Nur trocken testen, nichts schreiben
alttext generate ./fotos --dry-run

# CSV-Export ohne Metadaten zu beruehren
alttext generate ./fotos --export-csv

# Bestehende Alt-Texte ueberspringen
alttext generate ./fotos --skip-existing

# Review-Queue eines vorigen Laufs erneut starten
alttext review ./fotos

# Statistik fuer einen Ordner
alttext stats ./fotos

# Setup-Check
alttext check
```

### HEIC/HEIF (iPhone-Bilder)

Standardmaessig werden HEIC/HEIF-Dateien uebersprungen. Mit dem optionalen Extra geht das auch:

```bash
pip install 'alttext[heic]'
```

## Was sind BITV-konforme Alt-Texte?

Alt-Texte machen Bilder fuer Screenreader und damit fuer Menschen mit Sehbehinderungen zugaenglich. BITV 2.0 und WCAG 2.1 verlangen:

- Beschreibe das Wesentliche, was zu sehen ist
- Maximal etwa 125 Zeichen
- Keine Floskeln wie "Bild von" oder "Foto zeigt"
- Personen werden allgemein beschrieben, keine Identifikationsversuche
- Konkret und sachlich, keine Spekulationen

Das Tool weist das Modell entsprechend an und prueft die Confidence pro Bild.

## Welche Metadatenfelder werden geschrieben?

Fuer maximale Kompatibilitaet werden alle drei gaengigen Felder gefuellt:

| Feld | Zweck |
|------|------|
| `IPTC:Caption-Abstract` | klassisch, wird von vielen CMS und News-Workflows gelesen |
| `XMP-dc:description` | moderner, plattformuebergreifender Standard (Dublin Core) |
| `XMP-iptc4xmpCore:AltTextAccessibility` | Adobe-Standard speziell fuer Barrierefreiheit |

Bestehende Werte werden nicht ueberschrieben, ausser du setzt `--force`.

## Confidence-Modus

- **>= 7**: Alt-Text wird automatisch geschrieben
- **< 7**: Bild landet in der Review-Queue (`alttext_review_queue.json`)
- Phrasen wie "moeglicherweise", "vermutlich", "scheint" senken die Confidence automatisch unter 7

## Logfile und Sidecars

- Pro Lauf wird `alttext_log_YYYYMMDD_HHMMSS.csv` im Zielordner erzeugt
- Mit `--sidecar` legst du pro Bild ein `<bild>.alttext.json` an
- Mit `--html-report` bekommst du eine Uebersichtsseite mit Thumbnails

## Troubleshooting

**Ollama nicht erreichbar.** Pruefe mit `ollama list`, ob der Dienst laeuft. Standardport ist `127.0.0.1:11434`. Eine andere Adresse setzt du via Umgebungsvariable `OLLAMA_HOST`.

**Modell fehlt.** Fuehre `ollama pull qwen2.5vl:7b` aus.

**ExifTool wird nicht gefunden.** Lege das Binary in `./bin/` ab oder installiere es ueber den Paketmanager. `alttext check` zeigt den gefundenen Pfad.

**Bild wird uebersprungen.** Schau ins Logfile, dort steht der Grund. Korrupte Dateien werden ohne Crash ausgelassen.

**Antwort war kein gueltiges JSON.** Das Tool versucht es einmal erneut. Bleibt der Fehler, landet das Bild in der Review-Queue mit Eintrag im Log.

**HEIC/HEIF-Dateien.** Werden erkannt, aber nicht beschrieben. Wandle sie z. B. mit ImageMagick um.

## Sicherheit und Datenschutz

- Keine Telemetrie
- Keine externen Calls ausser zu `localhost` (Ollama)
- Alle Bilder bleiben auf deiner Maschine
- ExifTool macht standardmaessig ein Backup (`*.jpg_original`), das du auch behalten solltest

## Build als .exe

```bash
pip install pyinstaller
pyinstaller --onefile -n alttext alttext/cli.py
```

Die fertige Binary findest du unter `dist/alttext.exe`. Vergiss nicht, `bin/exiftool.exe` mitzuverteilen.
