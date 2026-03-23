from __future__ import annotations

import json
import random
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

from .utils import normalize_text


@dataclass(frozen=True, slots=True)
class VoiceEntry:
    path: Path
    relative_path: str
    stem: str
    normalized_stem: str


class VoicePack:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.entries = self._scan(root)

    @staticmethod
    def _scan(root: Path) -> list[VoiceEntry]:
        if not root.exists():
            return []

        entries: list[VoiceEntry] = []
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix.lower() != ".wav":
                continue
            entries.append(
                VoiceEntry(
                    path=path,
                    relative_path=path.relative_to(root).as_posix(),
                    stem=path.stem,
                    normalized_stem=normalize_text(path.stem),
                )
            )
        return entries

    def export_manifest(self, output_path: Path) -> None:
        payload = [
            {
                "relative_path": entry.relative_path,
                "stem": entry.stem,
                "normalized_stem": entry.normalized_stem,
            }
            for entry in self.entries
        ]
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def is_available(self) -> bool:
        return bool(self.entries)

    def _matches_selector(self, selector: str, entry: VoiceEntry) -> bool:
        normalized_selector = normalize_text(Path(selector).stem or selector)
        lowered_selector = selector.lower()
        if lowered_selector == entry.relative_path.lower():
            return True
        if lowered_selector == entry.path.name.lower():
            return True
        if normalized_selector and normalized_selector == entry.normalized_stem:
            return True
        return bool(normalized_selector and normalized_selector in entry.normalized_stem)

    def select(self, selectors: list[str] | str) -> VoiceEntry | None:
        if isinstance(selectors, str):
            selectors = [selectors]

        matches: list[VoiceEntry] = []
        for selector in selectors:
            matches.extend(entry for entry in self.entries if self._matches_selector(selector, entry))
            if matches:
                break

        if not matches:
            return None
        return random.choice(matches)

    def find_best_for_text(self, text: str, min_score: float) -> VoiceEntry | None:
        normalized = normalize_text(text)
        if not normalized:
            return None

        best_entry: VoiceEntry | None = None
        best_score = 0.0
        for entry in self.entries:
            if entry.normalized_stem == normalized:
                return entry
            if entry.normalized_stem in normalized or normalized in entry.normalized_stem:
                score = 0.96
            else:
                score = SequenceMatcher(None, normalized, entry.normalized_stem).ratio()
            if score > best_score:
                best_entry = entry
                best_score = score
        if best_score >= min_score:
            return best_entry
        return None
