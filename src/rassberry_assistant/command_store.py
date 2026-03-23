from __future__ import annotations

import base64
import re
from pathlib import Path
from typing import Any

import yaml

from .router import CommandDefinition, load_commands
from .utils import ensure_directory


class CommandStore:
    def __init__(self, project_root: Path, core_commands_path: Path, custom_commands_path: Path) -> None:
        self.project_root = project_root
        self.core_commands_path = core_commands_path
        self.custom_commands_path = custom_commands_path
        self.custom_audio_root = project_root / "assets" / "custom_audio"
        ensure_directory(self.custom_audio_root)
        self._ensure_custom_file()

    def list_commands(self) -> list[dict[str, Any]]:
        commands: list[dict[str, Any]] = []
        for source, path in (("core", self.core_commands_path), ("custom", self.custom_commands_path)):
            payload = self._load_yaml(path)
            for raw in payload.get("commands") or []:
                commands.append(self._serialize_command(raw, source))
        return commands

    def list_audio_files(self) -> list[dict[str, str]]:
        files: list[dict[str, str]] = []
        for path in sorted(self.custom_audio_root.glob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(self.project_root).as_posix()
            files.append({"name": path.name, "path": relative})
        return files

    def save_custom_command(self, payload: dict[str, Any]) -> dict[str, Any]:
        commands_payload = self._load_yaml(self.custom_commands_path)
        commands = list(commands_payload.get("commands") or [])
        command_id = self._resolve_command_id(payload)
        raw_command = self._build_command_payload(command_id, payload)

        replaced = False
        for index, existing in enumerate(commands):
            if existing.get("id") == command_id:
                commands[index] = raw_command
                replaced = True
                break
        if not replaced:
            commands.append(raw_command)

        commands_payload["commands"] = commands
        self._write_yaml(self.custom_commands_path, commands_payload)
        return self._serialize_command(raw_command, "custom")

    def delete_custom_command(self, command_id: str) -> bool:
        commands_payload = self._load_yaml(self.custom_commands_path)
        commands = list(commands_payload.get("commands") or [])
        filtered = [item for item in commands if item.get("id") != command_id]
        if len(filtered) == len(commands):
            return False
        commands_payload["commands"] = filtered
        self._write_yaml(self.custom_commands_path, commands_payload)
        return True

    def upload_audio(self, file_name: str, content_base64: str, command_id: str | None = None) -> str:
        stem = self._slugify(command_id or Path(file_name).stem or "audio")
        suffix = Path(file_name).suffix.lower()
        if suffix != ".wav":
            suffix = ".wav"
        target = self.custom_audio_root / f"{stem}{suffix}"
        binary = base64.b64decode(content_base64)
        target.write_bytes(binary)
        return target.relative_to(self.project_root).as_posix()

    def load_router_commands(self) -> list[CommandDefinition]:
        commands = load_commands(self.core_commands_path)
        if self.custom_commands_path.exists():
            commands.extend(load_commands(self.custom_commands_path))
        return commands

    def _ensure_custom_file(self) -> None:
        if self.custom_commands_path.exists():
            return
        ensure_directory(self.custom_commands_path.parent)
        self._write_yaml(self.custom_commands_path, {"commands": []})

    @staticmethod
    def _load_yaml(path: Path) -> dict[str, Any]:
        if not path.exists():
            return {"commands": []}
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {"commands": []}

    @staticmethod
    def _write_yaml(path: Path, payload: dict[str, Any]) -> None:
        path.write_text(
            yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, width=120),
            encoding="utf-8",
        )

    def _resolve_command_id(self, payload: dict[str, Any]) -> str:
        raw_id = str(payload.get("id") or "").strip()
        if raw_id:
            return self._slugify(raw_id)

        phrases = self._split_lines(payload.get("phrases"))
        if phrases:
            return self._slugify(phrases[0])
        return self._slugify("custom-command")

    @staticmethod
    def _split_lines(value: Any) -> list[str]:
        lines = str(value or "").splitlines()
        return [line.strip() for line in lines if line.strip()]

    def _build_command_payload(self, command_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        action_type = str(payload.get("action_type") or "speak").strip().lower()
        action_value = str(payload.get("action_value") or "").strip()
        action_method = str(payload.get("action_method") or "POST").strip().upper()
        disabled = bool(payload.get("disabled", False))
        threshold = float(payload.get("threshold") or 0.84)
        audio_mode = str(payload.get("audio_mode") or "tts").strip().lower()
        audio_file = str(payload.get("audio_file") or "").strip()
        tts_text = str(payload.get("tts_text") or "").strip()
        phrases = self._split_lines(payload.get("phrases"))

        action: dict[str, Any] = {"type": action_type}
        if action_type == "http":
            action["method"] = action_method
            action["url"] = action_value
            headers_text = str(payload.get("headers_text") or "").strip()
            json_text = str(payload.get("json_text") or "").strip()
            if headers_text:
                try:
                    action["headers"] = yaml.safe_load(headers_text) or {}
                except yaml.YAMLError as exc:
                    raise ValueError("Invalid YAML in HTTP headers.") from exc
            if json_text:
                try:
                    action["json"] = yaml.safe_load(json_text) or {}
                except yaml.YAMLError as exc:
                    raise ValueError("Invalid YAML in JSON body.") from exc
        elif action_type == "shell":
            action["type"] = "shell"
            action["command"] = action_value
        else:
            action["type"] = "speak"

        if audio_mode == "tts" and tts_text:
            action["ok_text" if action_type in {"shell", "http"} else "text"] = tts_text
        elif audio_mode == "wav" and audio_file:
            action["ok_audio_file" if action_type in {"shell", "http"} else "audio_file"] = audio_file

        return {
            "id": command_id,
            "phrases": phrases,
            "threshold": threshold,
            "disabled": disabled,
            "action": action,
        }

    def _serialize_command(self, raw: dict[str, Any], source: str) -> dict[str, Any]:
        action = raw.get("action") or {}
        audio_file = str(action.get("ok_audio_file") or action.get("audio_file") or "").strip()
        tts_text = str(action.get("ok_text") or action.get("text") or "").strip()
        audio_mode = "none"
        if audio_file:
            audio_mode = "wav"
        elif tts_text:
            audio_mode = "tts"
        return {
            "id": raw.get("id", ""),
            "source": source,
            "editable": source == "custom",
            "phrases": raw.get("phrases") or [],
            "regex": raw.get("regex") or [],
            "threshold": float(raw.get("threshold", 0.84)),
            "disabled": bool(raw.get("disabled", False)),
            "action_type": action.get("type", "speak"),
            "action_value": action.get("command") or action.get("url") or "",
            "action_method": action.get("method", "POST"),
            "headers_text": self._dump_yaml_fragment(action.get("headers")),
            "json_text": self._dump_yaml_fragment(action.get("json")),
            "audio_mode": audio_mode,
            "audio_file": audio_file,
            "tts_text": tts_text,
        }

    @staticmethod
    def _dump_yaml_fragment(value: Any) -> str:
        if value in (None, "", {}, []):
            return ""
        return yaml.safe_dump(value, allow_unicode=True, sort_keys=False, width=120).strip()

    @staticmethod
    def _slugify(value: str) -> str:
        normalized = value.strip().lower()
        normalized = re.sub(r"[^0-9a-zа-яё_-]+", "-", normalized, flags=re.IGNORECASE)
        normalized = normalized.strip("-_")
        if not normalized:
            return "custom-command"
        if normalized[0].isdigit():
            normalized = f"cmd-{normalized}"
        return normalized[:80]
