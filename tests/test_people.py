"""Tests for the people annotation module."""
from __future__ import annotations

import json
from pathlib import Path

from alttext.people import (
    annotations_path,
    format_for_prompt,
    load_annotations,
    parse_names,
    save_annotations,
)


def test_parse_names_strips_and_filters():
    assert parse_names("Mueller,  Schmidt,  ,  Weber") == ["Mueller", "Schmidt", "Weber"]


def test_parse_names_empty():
    assert parse_names("") == []
    assert parse_names("   ,  , ") == []


def test_save_and_load_roundtrip(tmp_path: Path):
    annotations = {
        str(tmp_path / "a.jpg"): ["Buergermeister Mueller", "Vereinsvorsitzende Schmidt"],
        str(tmp_path / "b.jpg"): [],
    }
    save_annotations(tmp_path, annotations)
    loaded = load_annotations(tmp_path)
    assert loaded == annotations


def test_load_returns_empty_when_missing(tmp_path: Path):
    assert load_annotations(tmp_path) == {}


def test_load_handles_legacy_flat_dict(tmp_path: Path):
    target = annotations_path(tmp_path)
    target.write_text(
        json.dumps({str(tmp_path / "x.jpg"): ["Person A"]}, ensure_ascii=False),
        encoding="utf-8",
    )
    loaded = load_annotations(tmp_path)
    assert loaded == {str(tmp_path / "x.jpg"): ["Person A"]}


def test_load_handles_corrupted(tmp_path: Path):
    annotations_path(tmp_path).write_text("nicht json", encoding="utf-8")
    assert load_annotations(tmp_path) == {}


def test_format_for_prompt_single_de():
    out = format_for_prompt(["Buergermeister Mueller"], lang="de")
    assert "Buergermeister Mueller" in out
    assert "links nach rechts" not in out


def test_format_for_prompt_multi_de():
    out = format_for_prompt(["Mueller", "Schmidt", "Weber"], lang="de")
    assert "links nach rechts" in out
    assert "Mueller, Schmidt, Weber" in out


def test_format_for_prompt_empty():
    assert format_for_prompt([]) == ""


def test_format_for_prompt_en_multi():
    out = format_for_prompt(["A", "B"], lang="en")
    assert "left to right" in out
    assert "A, B" in out
