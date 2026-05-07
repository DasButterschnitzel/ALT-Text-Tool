"""Ollama calls and prompt construction for BITV-compliant alt texts."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import ollama

from .config import (
    CONFIDENCE_THRESHOLD,
    DEFAULT_MODEL,
    LOW_CONFIDENCE_PHRASES,
    MAX_ALT_TEXT_LENGTH,
    ollama_host,
)
from .image_utils import encode_base64, load_and_resize


SYSTEM_PROMPT_DE = """Du bist Experte fuer barrierefreie Bildbeschreibungen nach BITV 2.0 und WCAG 2.1.

Deine Aufgabe: Generiere einen Alt-Text fuer das Bild, der:
- Maximal 125 Zeichen lang ist
- Das Wesentliche beschreibt, was zu sehen ist
- KEINE Phrasen wie "Bild von", "Foto zeigt", "Auf dem Bild ist" enthaelt
- Konkret und sachlich ist, keine Spekulationen
- Wenn Text im Bild zu sehen ist, diesen wenn relevant kurz erwaehnt
- Personen werden allgemein beschrieben (Anzahl, Taetigkeit, Setting), keine Identifikationsversuche - ausser Namen wurden vom Nutzer explizit angegeben (siehe unten)

Zusaetzlicher Kontext zum Bild: {batch_context}
{people_block}
Gib deine Antwort EXAKT in diesem JSON-Format aus, ohne Markdown-Codebloecke:
{{"alt_text": "...", "confidence": 8, "reasoning": "kurze Begruendung der Confidence in einem Satz"}}

Confidence-Skala:
- 9-10: Bild eindeutig erkennbar, Beschreibung praezise
- 7-8: Bild gut erkennbar, kleinere Unsicherheiten
- 4-6: Bild teilweise unklar, Beschreibung koennte daneben liegen
- 1-3: Sehr unsicher, manuelle Pruefung noetig
"""

SYSTEM_PROMPT_EN = """You are an expert in accessible image descriptions according to BITV 2.0 and WCAG 2.1.

Your task: generate an alt text for the image that:
- Is at most 125 characters long
- Describes the essential content
- Contains NO phrases like "image of", "photo shows", "the picture depicts"
- Is concrete and factual, no speculation
- Briefly mentions text in the image when relevant
- Describes people generally (count, activity, setting), no identification attempts - unless names are explicitly provided by the user below

Additional context: {batch_context}
{people_block}
Return your answer EXACTLY in this JSON format, no markdown code blocks:
{{"alt_text": "...", "confidence": 8, "reasoning": "short justification in one sentence"}}

Confidence scale:
- 9-10: image clearly recognisable, description precise
- 7-8: image well recognisable, minor uncertainties
- 4-6: image partially unclear, description may be off
- 1-3: very uncertain, manual review needed
"""


@dataclass
class VisionResult:
    alt_text: str
    confidence: int
    reasoning: str
    raw: str
    needs_review: bool


def build_system_prompt(
    lang: str,
    batch_context: str | None,
    people: list[str] | None = None,
) -> str:
    template = SYSTEM_PROMPT_DE if lang == "de" else SYSTEM_PROMPT_EN
    context_value = batch_context.strip() if batch_context else ("keiner" if lang == "de" else "none")
    if people:
        if lang == "de":
            if len(people) == 1:
                people_line = (
                    f"Personen-Vorgabe (vom Nutzer): {people[0]}. "
                    "Du DARFST diesen Namen im Alt-Text nennen, wenn er ins Beschreibung passt."
                )
            else:
                listed = ", ".join(people)
                people_line = (
                    f"Personen-Vorgabe (vom Nutzer, von links nach rechts): {listed}. "
                    "Du DARFST diese Namen im Alt-Text nennen, in der angegebenen Reihenfolge."
                )
        else:
            if len(people) == 1:
                people_line = (
                    f"Person identification (provided by user): {people[0]}. "
                    "You MAY use this name in the alt text where appropriate."
                )
            else:
                listed = ", ".join(people)
                people_line = (
                    f"Person identification (provided by user, left to right): {listed}. "
                    "You MAY use these names in the alt text in this order."
                )
        people_block = people_line + "\n"
    else:
        people_block = ""
    return template.format(batch_context=context_value, people_block=people_block)


def _extract_json(raw: str) -> dict[str, Any] | None:
    """Find the first JSON object in the model output."""
    # Strip possible code fences
    cleaned = re.sub(r"```(?:json)?", "", raw).replace("```", "").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def _apply_confidence_heuristic(alt_text: str, reasoning: str, confidence: int) -> int:
    """Lower confidence if hedge phrases appear in alt text or reasoning."""
    haystack = f"{alt_text} {reasoning}".lower()
    for phrase in LOW_CONFIDENCE_PHRASES:
        if phrase in haystack:
            return min(confidence, CONFIDENCE_THRESHOLD - 1)
    return confidence


def _truncate(text: str, limit: int = MAX_ALT_TEXT_LENGTH) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rsplit(" ", 1)[0]
    return (cut or text[: limit - 1]).rstrip() + "…"


class VisionClient:
    """Thin wrapper around the Ollama Python SDK."""

    def __init__(self, model: str = DEFAULT_MODEL, host: str | None = None) -> None:
        self.model = model
        self._client = ollama.Client(host=host or ollama_host())

    def check_available(self) -> tuple[bool, str]:
        """Return (ok, message) describing Ollama and model availability."""
        try:
            response = self._client.list()
        except Exception as exc:  # pragma: no cover - depends on runtime
            return False, f"Ollama nicht erreichbar unter {ollama_host()}: {exc}"
        models = response.get("models", []) if isinstance(response, dict) else getattr(response, "models", [])
        names: list[str] = []
        for entry in models:
            if isinstance(entry, dict):
                names.append(entry.get("name") or entry.get("model") or "")
            else:
                names.append(getattr(entry, "name", "") or getattr(entry, "model", ""))
        names = [n for n in names if n]
        requested_base = self.model.split(":", 1)[0]
        for installed in names:
            installed_base = installed.split(":", 1)[0]
            if installed == self.model or installed_base == requested_base:
                return True, f"Modell {self.model} ist installiert (gefunden als {installed})."
        installed_list = ", ".join(names) if names else "keine"
        return False, (
            f"Modell {self.model} fehlt. Installiere es mit: ollama pull {self.model}. "
            f"Installierte Modelle: {installed_list}."
        )

    def describe(
        self,
        image_path: Path,
        lang: str,
        batch_context: str | None,
        retries: int = 1,
        people: list[str] | None = None,
    ) -> VisionResult:
        image_bytes = load_and_resize(image_path)
        encoded = encode_base64(image_bytes)
        system_prompt = build_system_prompt(lang, batch_context, people=people)

        last_raw = ""
        for attempt in range(retries + 1):
            response = self._client.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": (
                            "Beschreibe dieses Bild." if lang == "de" else "Describe this image."
                        ),
                        "images": [encoded],
                    },
                ],
                options={"temperature": 0.2},
            )
            raw = (
                response["message"]["content"]
                if isinstance(response, dict)
                else response.message.content
            )
            last_raw = raw or ""
            data = _extract_json(last_raw)
            if data and "alt_text" in data:
                alt_text = _truncate(str(data.get("alt_text", "")))
                reasoning = str(data.get("reasoning", "")).strip()
                try:
                    confidence = int(data.get("confidence", 0))
                except (TypeError, ValueError):
                    confidence = 0
                confidence = max(1, min(10, confidence))
                confidence = _apply_confidence_heuristic(alt_text, reasoning, confidence)
                return VisionResult(
                    alt_text=alt_text,
                    confidence=confidence,
                    reasoning=reasoning,
                    raw=last_raw,
                    needs_review=confidence < CONFIDENCE_THRESHOLD,
                )

        raise ValueError(f"Modell-Antwort war kein gueltiges JSON: {last_raw[:200]}")
