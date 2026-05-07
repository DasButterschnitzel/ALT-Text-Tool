"""ExifTool wrapper: read existing alt texts and write the triple metadata set."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import exiftool

from .config import METADATA_FIELDS, find_exiftool


class ExifToolMissingError(RuntimeError):
    pass


@contextmanager
def exif_helper() -> Iterator[exiftool.ExifToolHelper]:
    binary = find_exiftool()
    if not binary:
        raise ExifToolMissingError(
            "ExifTool wurde nicht gefunden. Lege exiftool(.exe) in ./bin/ ab "
            "oder installiere es ueber den Paketmanager (apt install libimage-exiftool-perl)."
        )
    helper = exiftool.ExifToolHelper(executable=binary)
    helper.run()
    try:
        yield helper
    finally:
        helper.terminate()


def _matches_field(key: str, field: str) -> bool:
    """Check if an exiftool key represents the requested field.

    ExifTool returns keys with group prefixes that vary (e.g. "XMP:Description"
    vs "XMP-dc:Description"). We compare the suffix after the last colon
    case-insensitively but require an exact match, not endswith.
    """
    key_suffix = key.rsplit(":", 1)[-1].lower()
    field_suffix = field.rsplit(":", 1)[-1].lower()
    return key_suffix == field_suffix


def read_alt_fields(path: Path) -> dict[str, str]:
    """Return non-empty alt-text-related fields currently set on the file."""
    tag_args = [f"-{field}" for field in METADATA_FIELDS]
    with exif_helper() as helper:
        metadata = helper.execute_json(*tag_args, str(path))
    if not metadata:
        return {}
    record = metadata[0]
    found: dict[str, str] = {}
    for field in METADATA_FIELDS:
        for key, value in record.items():
            if value and _matches_field(key, field):
                found[field] = str(value)
                break
    return found


def has_existing_alt(path: Path) -> bool:
    return bool(read_alt_fields(path))


def write_alt_text(
    path: Path,
    alt_text: str,
    *,
    force: bool = False,
    backup: bool = True,
    dry_run: bool = False,
) -> dict[str, str]:
    """Write alt text into the three configured metadata fields.

    Returns a dict {field: written_value} for fields that were actually written.
    """
    if dry_run:
        return {field: alt_text for field in METADATA_FIELDS}

    if not force:
        existing = read_alt_fields(path)
        if existing:
            return {}

    tags = {
        "IPTC:Caption-Abstract": alt_text,
        "XMP-dc:Description": alt_text,
        "XMP-iptc4xmpCore:AltTextAccessibility": alt_text,
    }

    params = []
    if not backup:
        params.append("-overwrite_original")

    with exif_helper() as helper:
        helper.set_tags([str(path)], tags=tags, params=params)
    return tags


def stats_for_folder(paths: list[Path]) -> dict[str, int]:
    counts = {"total": len(paths), "with_alt": 0, "without_alt": 0, "errors": 0}
    if not paths:
        return counts
    tag_args = [f"-{field}" for field in METADATA_FIELDS]
    with exif_helper() as helper:
        metadata = helper.execute_json(*tag_args, *[str(p) for p in paths])
    for record in metadata:
        if "ExifTool:Error" in record:
            counts["errors"] += 1
            continue
        has_alt = any(
            value
            for key, value in record.items()
            if any(_matches_field(key, field) for field in METADATA_FIELDS)
        )
        if has_alt:
            counts["with_alt"] += 1
        else:
            counts["without_alt"] += 1
    return counts
