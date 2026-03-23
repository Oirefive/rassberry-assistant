from __future__ import annotations

import base64
import json
import os
import re
import time
from copy import deepcopy
from pathlib import Path
from typing import Any

from .utils import ensure_directory


_PIPER_MODEL_SUFFIX = ".onnx"
_PIPER_CONFIG_SUFFIX = ".onnx.json"
_SAFE_NAME_RE = re.compile(r"[^0-9A-Za-zА-Яа-яЁё._-]+")


class TTSLibrary:
    def __init__(self, project_root: Path, root: Path | None = None) -> None:
        self.project_root = project_root.resolve()
        self.root = (root or (self.project_root / "tts")).resolve()
        self.catalog_path = self.root / "catalog.json"
        self.custom_root = self.root / "custom"
        self._catalog_cache: dict[str, dict[str, Any]] = {}
        self._catalog_cache_mtime_ns: int | None = None
        self._model_cache: list[dict[str, Any]] = []
        self._model_cache_updated_at = 0.0
        ensure_directory(self.root)
        ensure_directory(self.custom_root)

    def list_piper_models(
        self,
        *,
        current_model_path: Path | None = None,
        current_config_path: Path | None = None,
    ) -> list[dict[str, Any]]:
        entries = self._base_model_entries()

        if current_model_path and current_model_path.exists():
            current_key = self._relative_to_project(current_model_path)
            if current_key not in entries:
                self._add_model_entry(
                    entries,
                    catalog,
                    current_model_path,
                    override_config_path=current_config_path,
                )

        current_relative = self._relative_to_project(current_model_path) if current_model_path else ""
        results = sorted(entries.values(), key=lambda item: item["label"].lower())
        for entry in results:
            entry["current"] = entry["path"] == current_relative
        return sorted(results, key=lambda item: (not item["current"], item["label"].lower()))

    def resolve_piper_model(self, model_id: str) -> tuple[Path, Path]:
        raw = str(model_id or "").strip()
        if not raw:
            raise ValueError("piper_model is required")

        model_path = Path(raw).expanduser()
        if not model_path.is_absolute():
            model_path = (self.project_root / model_path).resolve()
        config_path = Path(str(model_path) + ".json")

        if not model_path.exists():
            raise ValueError(f"Piper model not found: {raw}")
        if not config_path.exists():
            raise ValueError(f"Piper config not found for: {raw}")
        return model_path, config_path

    def upload_files(self, files: list[dict[str, str]]) -> list[str]:
        saved: list[str] = []
        for item in files:
            file_name = str(item.get("file_name") or "").strip()
            content_base64 = str(item.get("content_base64") or "").strip()
            if not file_name or not content_base64:
                raise ValueError("file_name and content_base64 are required")
            target = self.custom_root / self._sanitize_upload_name(file_name)
            binary = base64.b64decode(content_base64)
            target.write_bytes(binary)
            saved.append(self._relative_to_project(target))
        self.invalidate()
        return saved

    def invalidate(self) -> None:
        self._catalog_cache = {}
        self._catalog_cache_mtime_ns = None
        self._model_cache = []
        self._model_cache_updated_at = 0.0

    def _add_model_entry(
        self,
        entries: dict[str, dict[str, Any]],
        catalog: dict[str, dict[str, Any]],
        model_path: Path,
        *,
        override_config_path: Path | None = None,
    ) -> None:
        if not model_path.name.endswith(_PIPER_MODEL_SUFFIX):
            return

        relative_model = self._relative_to_project(model_path)
        config_path = override_config_path or Path(str(model_path) + ".json")
        relative_config = self._relative_to_project(config_path) if config_path.exists() else ""
        metadata = catalog.get(relative_model) or catalog.get(model_path.name) or {}
        label = str(metadata.get("label") or "").strip() or self._default_label(model_path)
        language_name = str(metadata.get("language_name") or "").strip()
        quality = str(metadata.get("quality") or "").strip()
        details = [part for part in (language_name, quality) if part]

        entries[relative_model] = {
            "id": relative_model,
            "path": relative_model,
            "config_path": relative_config,
            "label": label,
            "details": " • ".join(details),
            "voice_name": str(metadata.get("voice_name") or "").strip(),
            "language_code": str(metadata.get("language_code") or "").strip(),
            "language_name": language_name,
            "quality": quality,
            "source_url": str(metadata.get("source_url") or "").strip(),
            "size_mb": round(model_path.stat().st_size / 1024 / 1024, 1),
            "has_config": config_path.exists(),
            "current": False,
        }

    def _load_catalog(self) -> dict[str, dict[str, Any]]:
        current_mtime_ns = self.catalog_path.stat().st_mtime_ns if self.catalog_path.exists() else None
        if current_mtime_ns is not None and current_mtime_ns == self._catalog_cache_mtime_ns and self._catalog_cache:
            return self._catalog_cache
        if not self.catalog_path.exists():
            return {}
        try:
            raw = json.loads(self.catalog_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        items = raw.get("models") if isinstance(raw, dict) else None
        if not isinstance(items, list):
            return {}
        catalog: dict[str, dict[str, Any]] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            key = str(item.get("relative_model_path") or "").strip()
            if key:
                catalog[key] = dict(item)
            file_name = Path(key).name
            if file_name:
                catalog.setdefault(file_name, dict(item))
        self._catalog_cache = catalog
        self._catalog_cache_mtime_ns = current_mtime_ns
        return catalog

    def _base_model_entries(self) -> dict[str, dict[str, Any]]:
        now = time.monotonic()
        if self._model_cache and now - self._model_cache_updated_at < 12.0:
            return {item["path"]: deepcopy(item) for item in self._model_cache}

        catalog = self._load_catalog()
        entries: dict[str, dict[str, Any]] = {}
        for model_path in sorted(self.root.rglob(f"*{_PIPER_MODEL_SUFFIX}")):
            self._add_model_entry(entries, catalog, model_path)
        self._model_cache = [deepcopy(item) for item in entries.values()]
        self._model_cache_updated_at = now
        return {item["path"]: deepcopy(item) for item in self._model_cache}

    def _relative_to_project(self, path: Path | None) -> str:
        if not path:
            return ""
        resolved = path.resolve()
        try:
            return resolved.relative_to(self.project_root).as_posix()
        except ValueError:
            try:
                return Path(os.path.relpath(resolved, self.project_root)).as_posix()
            except ValueError:
                return resolved.as_posix()

    @staticmethod
    def _default_label(model_path: Path) -> str:
        return model_path.stem.replace("_", " ")

    @staticmethod
    def _sanitize_upload_name(file_name: str) -> str:
        raw_name = Path(file_name).name
        lower_name = raw_name.lower()
        if lower_name.endswith(_PIPER_CONFIG_SUFFIX):
            stem = raw_name[: -len(_PIPER_CONFIG_SUFFIX)]
            suffix = _PIPER_CONFIG_SUFFIX
        else:
            suffix = Path(raw_name).suffix.lower()
            stem = Path(raw_name).stem
        if suffix not in {_PIPER_MODEL_SUFFIX, ".json", _PIPER_CONFIG_SUFFIX}:
            raise ValueError("Only .onnx and .json files are supported for Piper uploads.")
        safe_stem = _SAFE_NAME_RE.sub("-", stem).strip("-._")
        if not safe_stem:
            safe_stem = "tts-model"
        return f"{safe_stem}{suffix}"
