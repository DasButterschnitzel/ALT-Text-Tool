"""Unit tests for prompt construction and JSON parsing."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from alttext.vision import (
    VisionClient,
    _apply_confidence_heuristic,
    _extract_json,
    _truncate,
    build_system_prompt,
)


def test_build_system_prompt_de_includes_context():
    prompt = build_system_prompt("de", "Aktionstag")
    assert "BITV 2.0" in prompt
    assert "Aktionstag" in prompt


def test_build_system_prompt_de_default_context():
    prompt = build_system_prompt("de", None)
    assert "keiner" in prompt


def test_build_system_prompt_en():
    prompt = build_system_prompt("en", None)
    assert "WCAG" in prompt
    assert "none" in prompt


def test_build_system_prompt_with_single_person_de():
    prompt = build_system_prompt("de", None, people=["Buergermeister Mueller"])
    assert "Buergermeister Mueller" in prompt
    assert "DARFST" in prompt


def test_build_system_prompt_with_multiple_people_de():
    prompt = build_system_prompt("de", "Aktionstag", people=["Mueller", "Schmidt", "Weber"])
    assert "links nach rechts" in prompt
    assert "Mueller, Schmidt, Weber" in prompt
    assert "Aktionstag" in prompt


def test_build_system_prompt_without_people_omits_block():
    prompt = build_system_prompt("de", None, people=None)
    assert "Personen-Vorgabe" not in prompt
    prompt2 = build_system_prompt("de", None, people=[])
    assert "Personen-Vorgabe" not in prompt2


def test_extract_json_clean():
    raw = '{"alt_text": "Hund auf Wiese", "confidence": 9, "reasoning": "klar"}'
    assert _extract_json(raw)["alt_text"] == "Hund auf Wiese"


def test_extract_json_with_codeblock():
    raw = '```json\n{"alt_text": "X", "confidence": 5, "reasoning": "y"}\n```'
    parsed = _extract_json(raw)
    assert parsed["confidence"] == 5


def test_extract_json_inside_text():
    raw = 'Ich antworte: {"alt_text": "Foo", "confidence": 7, "reasoning": "z"} Ende.'
    assert _extract_json(raw)["alt_text"] == "Foo"


def test_extract_json_invalid():
    assert _extract_json("nichts hier") is None


def test_apply_confidence_heuristic_lowers_for_hedge():
    assert _apply_confidence_heuristic("Möglicherweise ein Hund", "klar", 9) == 6


def test_apply_confidence_heuristic_keeps_high():
    assert _apply_confidence_heuristic("Hund auf Wiese", "klar", 9) == 9


def test_truncate_short():
    assert _truncate("kurz") == "kurz"


def test_truncate_long_breaks_at_space():
    text = "a" * 130
    out = _truncate(text)
    assert len(out) <= 125


def test_describe_parses_response():
    client = VisionClient.__new__(VisionClient)
    client.model = "qwen2.5vl:7b"
    client._client = MagicMock()
    client._client.chat.return_value = {
        "message": {
            "content": '{"alt_text": "Mann am Rednerpult", "confidence": 8, "reasoning": "klar"}'
        }
    }
    with patch("alttext.vision.load_and_resize", return_value=b"x"):
        result = client.describe(
            image_path=__import__("pathlib").Path("/tmp/x.jpg"),
            lang="de",
            batch_context=None,
        )
    assert result.alt_text == "Mann am Rednerpult"
    assert result.confidence == 8
    assert result.needs_review is False


def test_describe_invalid_then_raises():
    client = VisionClient.__new__(VisionClient)
    client.model = "qwen2.5vl:7b"
    client._client = MagicMock()
    client._client.chat.return_value = {"message": {"content": "kein JSON"}}
    with patch("alttext.vision.load_and_resize", return_value=b"x"):
        with pytest.raises(ValueError):
            client.describe(
                image_path=__import__("pathlib").Path("/tmp/x.jpg"),
                lang="de",
                batch_context=None,
                retries=1,
            )
