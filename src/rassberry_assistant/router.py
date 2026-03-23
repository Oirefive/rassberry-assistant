from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import yaml

from .utils import normalize_text


@dataclass(slots=True)
class CommandDefinition:
    command_id: str
    phrases: list[str] = field(default_factory=list)
    regex: list[str] = field(default_factory=list)
    threshold: float = 0.84
    action: dict[str, Any] = field(default_factory=dict)
    disabled: bool = False


@dataclass(slots=True)
class CommandMatch:
    command: CommandDefinition
    score: float
    captures: dict[str, str] = field(default_factory=dict)


def load_commands(path: Path) -> list[CommandDefinition]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    commands: list[CommandDefinition] = []
    for raw in payload.get("commands") or []:
        commands.append(
            CommandDefinition(
                command_id=raw["id"],
                phrases=raw.get("phrases") or [],
                regex=raw.get("regex") or [],
                threshold=float(raw.get("threshold", 0.84)),
                action=raw.get("action") or {},
                disabled=bool(raw.get("disabled", False)),
            )
        )
    return commands


def _phrase_score(text: str, phrase: str) -> float:
    normalized_phrase = normalize_text(phrase)
    if not normalized_phrase:
        return 0.0
    if text == normalized_phrase:
        return 1.0
    if normalized_phrase in text:
        length_score = len(normalized_phrase) / max(len(text), 1)
        return min(0.98, 0.82 + length_score * 0.18)
    if text in normalized_phrase:
        return 0.75
    return SequenceMatcher(None, text, normalized_phrase).ratio()


class CommandRouter:
    def __init__(self, commands: list[CommandDefinition]) -> None:
        self.commands = commands

    def replace_commands(self, commands: list[CommandDefinition]) -> None:
        self.commands = commands

    def find_best_match(self, transcript: str) -> CommandMatch | None:
        normalized = normalize_text(transcript)
        if not normalized:
            return None

        best_match: CommandMatch | None = None
        for command in self.commands:
            if command.disabled:
                continue

            command_best_score = 0.0
            command_captures: dict[str, str] = {}

            for pattern in command.regex:
                match = re.search(pattern, normalized)
                if match:
                    command_best_score = 1.0
                    command_captures = {
                        key: value for key, value in match.groupdict().items() if value is not None
                    }
                    break

            if command_best_score < 1.0:
                for phrase in command.phrases:
                    score = _phrase_score(normalized, phrase)
                    if score > command_best_score:
                        command_best_score = score

            if command_best_score < command.threshold:
                continue

            if not best_match or command_best_score > best_match.score:
                best_match = CommandMatch(
                    command=command,
                    score=command_best_score,
                    captures=command_captures,
                )
        return best_match
