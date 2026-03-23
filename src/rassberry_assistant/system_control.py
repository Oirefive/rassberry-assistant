from __future__ import annotations

import logging
import os
import re
import shutil
import socket
import subprocess
import time
from pathlib import Path
from threading import Lock
from typing import Any

import yaml

from .audio import AudioPlayer
from .config import AssistantConfig
from .tts import build_tts
from .tts_library import TTSLibrary
from .utils import normalize_text


_ALSA_DEVICE_RE = re.compile(
    r"card\s+(?P<card_num>\d+):\s*(?P<card_key>[^\[]+)\[(?P<card_label>[^\]]+)\],\s*"
    r"device\s+(?P<device_num>\d+):\s*(?P<device_key>[^\[]+)\[(?P<device_label>[^\]]+)\]",
    flags=re.IGNORECASE,
)
_PIPEWIRE_LINE_RE = re.compile(
    r"^(?P<default>\*\s+)?(?P<node_id>\d+)\.\s+(?P<label>.+?)(?:\s+\[(?:vol|mute):.*)?$"
)
_TREE_PREFIX_RE = re.compile(r"^[\s\|\u2502\u251c\u2514\u2500\u252c\u2534\u253c]+")


def _run_text(command: list[str]) -> str:
    try:
        completed = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError:
        return ""
    if completed.returncode != 0:
        return ""
    return completed.stdout


def _dedupe_devices(devices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for device in devices:
        device_id = str(device.get("id") or "").strip()
        if not device_id or device_id in seen:
            continue
        seen.add(device_id)
        result.append(device)
    return result


def _with_current_device(
    devices: list[dict[str, Any]],
    current_device: str,
    fallback_label: str,
) -> list[dict[str, Any]]:
    current = str(current_device or "").strip()
    if not current:
        return _dedupe_devices(devices)
    if any(str(device.get("id") or "").strip() == current for device in devices):
        return _dedupe_devices(devices)
    synthetic = {
        "id": current,
        "label": fallback_label,
        "backend": "custom",
        "available": False,
    }
    return _dedupe_devices([synthetic, *devices])


def _display_trigger_phrase(raw_phrase: str, normalized_phrase: str) -> str:
    compact = " ".join(str(raw_phrase or "").split()).strip() or normalized_phrase
    if compact and compact == compact.lower():
        return compact[:1].upper() + compact[1:]
    return compact or "Ассистент"


def parse_alsa_hardware_devices(raw_text: str, *, io_kind: str) -> list[dict[str, Any]]:
    devices: list[dict[str, Any]] = []
    for match in _ALSA_DEVICE_RE.finditer(raw_text):
        card_key = match.group("card_key").strip()
        card_label = match.group("card_label").strip()
        device_num = match.group("device_num").strip()
        device_label = match.group("device_label").strip()
        device_id = f"plughw:CARD={card_key},DEV={device_num}"
        pretty_io = "Microphone" if io_kind == "input" else "Output"
        devices.append(
            {
                "id": device_id,
                "label": f"{card_label} / {device_label}",
                "backend": "alsa",
                "available": True,
                "description": f"{pretty_io} via ALSA",
            }
        )
    return _dedupe_devices(devices)


def parse_pipewire_sinks(raw_text: str) -> list[dict[str, Any]]:
    return _parse_pipewire_audio_nodes(raw_text, section_name="sinks", io_kind="output")


def parse_pipewire_sources(raw_text: str) -> list[dict[str, Any]]:
    return _parse_pipewire_audio_nodes(raw_text, section_name="sources", io_kind="input")


def _parse_pipewire_audio_nodes(
    raw_text: str,
    *,
    section_name: str,
    io_kind: str,
) -> list[dict[str, Any]]:
    devices: list[dict[str, Any]] = []
    section = ""
    for line in raw_text.splitlines():
        normalized = _TREE_PREFIX_RE.sub("", line).strip()
        if not normalized:
            continue
        if normalized.endswith(":"):
            section = normalized[:-1].strip().lower()
            continue
        if section != section_name:
            continue
        match = _PIPEWIRE_LINE_RE.match(normalized)
        if not match:
            continue
        node_id = match.group("node_id").strip()
        label = match.group("label").strip()
        devices.append(
            {
                "id": f"pipewire:{node_id}",
                "label": label,
                "backend": "pipewire",
                "available": True,
                "default": bool(match.group("default")),
                "description": f"{io_kind.capitalize()} via PipeWire",
            }
        )
    return _dedupe_devices(devices)


def list_audio_input_devices(current_device: str) -> list[dict[str, Any]]:
    devices: list[dict[str, Any]] = [
        {
            "id": "network-mic",
            "label": "Телефон / браузер по Wi-Fi",
            "backend": "network",
            "available": True,
            "description": "Browser microphone over local network",
        }
    ]
    if shutil.which("pw-record"):
        devices.append(
            {
                "id": "pipewire-default",
                "label": "PipeWire default",
                "backend": "pipewire",
                "available": True,
                "default": True,
            }
        )
        devices.extend(parse_pipewire_sources(_run_text(["wpctl", "status"])))
    devices.append(
        {
            "id": "default",
            "label": "ALSA default",
            "backend": "alsa",
            "available": True,
        }
    )
    devices.extend(parse_alsa_hardware_devices(_run_text(["arecord", "-l"]), io_kind="input"))
    return _with_current_device(devices, current_device, f"{current_device} (configured)")


def list_audio_output_devices(current_device: str) -> list[dict[str, Any]]:
    devices: list[dict[str, Any]] = []
    if shutil.which("pw-play"):
        devices.append(
            {
                "id": "pipewire-default",
                "label": "PipeWire default",
                "backend": "pipewire",
                "available": True,
                "default": True,
            }
        )
    devices.extend(parse_pipewire_sinks(_run_text(["wpctl", "status"])))
    devices.extend(parse_alsa_hardware_devices(_run_text(["aplay", "-l"]), io_kind="output"))
    devices.append(
        {
            "id": "default",
            "label": "ALSA default",
            "backend": "alsa",
            "available": True,
        }
    )
    return _with_current_device(devices, current_device, f"{current_device} (configured)")


def list_rhvoice_voices() -> list[str]:
    candidates = [
        Path("/usr/share/RHVoice/voices"),
        Path("/usr/local/share/RHVoice/voices"),
        Path.home() / ".local" / "share" / "RHVoice" / "voices",
    ]
    voices: set[str] = set()
    for root in candidates:
        try:
            if not root.exists():
                continue
            for item in root.iterdir():
                if item.is_dir():
                    name = item.name.strip()
                    if name:
                        voices.add(name)
        except OSError:
            continue
    if voices:
        return sorted(voices)
    return [
        "anna",
        "arina",
        "elena",
        "irina",
        "mikhail",
        "pavel",
        "vitaliy-ng",
    ]


class SystemControlPlane:
    def __init__(self, config_path: Path, config: AssistantConfig) -> None:
        self.config_path = config_path
        self.config = config
        self._assistant: Any = None
        self._lock = Lock()
        self._audio_cache: dict[str, list[dict[str, Any]]] = {}
        self._audio_cache_updated_at = 0.0
        self._last_audio_message = ""
        self._last_audio_error = ""
        self._last_assistant_message = ""
        self._last_assistant_error = ""
        self._last_tts_message = ""
        self._last_tts_error = ""
        self._tts_library = TTSLibrary(config.project_root)
        self._tts_cache: dict[str, Any] = {}
        self._tts_cache_updated_at = 0.0
        self._rhvoice_cache: list[str] = []
        self._rhvoice_cache_updated_at = 0.0

    def attach_assistant(self, assistant: Any) -> None:
        self._assistant = assistant

    def snapshot(self, base: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = dict(base or {})
        audio_snapshot = self._audio_snapshot()
        payload.update(audio_snapshot)
        payload["input_device"] = self.config.audio.input_device
        payload["output_device"] = self.config.audio.output_device
        payload["audio_message"] = self._last_audio_message
        payload["audio_error"] = self._last_audio_error
        payload["assistant_message"] = self._last_assistant_message
        payload["assistant_error"] = self._last_assistant_error
        payload["assistant_name"] = self.config.assistant_name
        payload["wake_phrase"] = self._current_wake_phrase()
        payload.update(self._tts_snapshot())
        payload["tts_message"] = self._last_tts_message
        payload["tts_error"] = self._last_tts_error
        payload["input_device_available"] = any(
            device.get("id") == self.config.audio.input_device and device.get("available")
            for device in audio_snapshot["audio_inputs"]
        )
        payload["output_device_available"] = any(
            device.get("id") == self.config.audio.output_device and device.get("available")
            for device in audio_snapshot["audio_outputs"]
        )
        return payload

    @staticmethod
    def resolve_lan_ip() -> str:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.connect(("8.8.8.8", 80))
                host = sock.getsockname()[0]
                if host and not host.startswith("127."):
                    return host
        except OSError:
            pass
        try:
            host = socket.gethostbyname(socket.gethostname())
            if host and not host.startswith("127."):
                return host
        except OSError:
            pass
        return "raspberrypi.local"

    def apply_audio_settings(
        self,
        *,
        input_device: str | None = None,
        output_device: str | None = None,
    ) -> dict[str, Any]:
        new_input = str(input_device or self.config.audio.input_device).strip()
        new_output = str(output_device or self.config.audio.output_device).strip()
        if not new_input:
            raise ValueError("input_device is required")
        if not new_output:
            raise ValueError("output_device is required")

        changed_parts: list[str] = []
        current_input = self.config.audio.input_device
        current_output = self.config.audio.output_device

        with self._lock:
            try:
                if self._assistant:
                    self._assistant.reconfigure_audio(
                        input_device=new_input if new_input != current_input else None,
                        output_device=new_output if new_output != current_output else None,
                    )
                self._write_audio_settings(new_input, new_output)
            except Exception as exc:
                self._last_audio_error = str(exc) or "Failed to apply audio settings."
                self._last_audio_message = ""
                logging.exception("Failed to apply audio settings: %s", exc)
                raise

            if new_input != current_input:
                changed_parts.append("microphone")
            if new_output != current_output:
                changed_parts.append("output")

            self._last_audio_error = ""
            if changed_parts:
                self._last_audio_message = f"Applied: {', '.join(changed_parts)}."
            else:
                self._last_audio_message = "Audio routing is already set like this."
            self._audio_cache_updated_at = 0.0
            return self.snapshot()

    def apply_assistant_settings(
        self,
        *,
        trigger_phrase: str | None = None,
    ) -> dict[str, Any]:
        raw_trigger = " ".join(str(trigger_phrase or "").split()).strip()
        if not raw_trigger:
            raise ValueError("trigger_phrase is required")
        normalized_trigger = normalize_text(raw_trigger)
        if not normalized_trigger:
            raise ValueError("trigger_phrase is empty after normalization")
        display_name = _display_trigger_phrase(raw_trigger, normalized_trigger)

        with self._lock:
            try:
                if self._assistant:
                    self._assistant.reconfigure_trigger(
                        trigger_phrase=normalized_trigger,
                        assistant_name=display_name,
                    )
                self._write_assistant_settings(normalized_trigger, display_name)
            except Exception as exc:
                self._last_assistant_error = str(exc) or "Failed to apply trigger."
                self._last_assistant_message = ""
                logging.exception("Failed to apply assistant settings: %s", exc)
                raise

            self._last_assistant_error = ""
            self._last_assistant_message = f'Триггер обновлён: "{display_name}".'
            return self.snapshot()

    def apply_tts_settings(
        self,
        *,
        engine: str | None = None,
        voice: str | None = None,
        rate: int | str | None = None,
        pitch: int | str | None = None,
        volume: int | str | None = None,
        piper_model: str | None = None,
    ) -> dict[str, Any]:
        next_engine = str(engine or self.config.tts.engine).strip().lower()
        if next_engine not in {"rhvoice", "piper"}:
            raise ValueError("tts engine must be rhvoice or piper")

        available_voices = self._rhvoice_snapshot()
        next_voice = str(voice or self.config.tts.voice).strip()
        if not next_voice and available_voices:
            next_voice = available_voices[0]
        if next_engine == "rhvoice" and not next_voice:
            raise ValueError("tts voice is required")

        next_rate = int(rate if rate is not None else self.config.tts.rate)
        next_pitch = int(pitch if pitch is not None else self.config.tts.pitch)
        next_volume = int(volume if volume is not None else self.config.tts.volume)
        next_model_path = self.config.tts.piper_model_path
        next_config_path = self.config.tts.piper_config_path

        if piper_model or next_engine == "piper":
            selected_model = str(piper_model or self._relative_project_path(next_model_path)).strip()
            next_model_path, next_config_path = self._tts_library.resolve_piper_model(selected_model)

        with self._lock:
            try:
                if self._assistant and hasattr(self._assistant, "reconfigure_tts"):
                    self._assistant.reconfigure_tts(
                        engine=next_engine,
                        voice=next_voice,
                        rate=next_rate,
                        pitch=next_pitch,
                        volume=next_volume,
                        piper_model_path=next_model_path,
                        piper_config_path=next_config_path,
                    )
                self._write_tts_settings(
                    engine=next_engine,
                    voice=next_voice,
                    rate=next_rate,
                    pitch=next_pitch,
                    volume=next_volume,
                    piper_model_path=next_model_path,
                    piper_config_path=next_config_path,
                )
            except Exception as exc:
                self._last_tts_error = str(exc) or "Failed to apply TTS settings."
                self._last_tts_message = ""
                logging.exception("Failed to apply TTS settings: %s", exc)
                raise

            self._last_tts_error = ""
            if next_engine == "piper":
                self._last_tts_message = "Piper обновлён."
            else:
                self._last_tts_message = f'RHVoice обновлён: "{next_voice}".'
            self._tts_cache_updated_at = 0.0
            return self.snapshot()

    def preview_tts(self, text: str) -> dict[str, Any]:
        phrase = " ".join(str(text or "").split()).strip()
        if not phrase:
            raise ValueError("text is required")

        with self._lock:
            try:
                success = False
                if self._assistant and hasattr(self._assistant, "preview_tts"):
                    success = bool(self._assistant.preview_tts(phrase))
                else:
                    preview_player = AudioPlayer(self.config.audio.output_device)
                    preview_tts = build_tts(preview_player, self.config.tts)
                    playback = preview_tts.start_playback(phrase)
                    if playback:
                        try:
                            success = playback.process.wait() == 0
                        finally:
                            playback.cleanup()
                if not success:
                    raise RuntimeError("TTS preview failed.")
            except Exception as exc:
                self._last_tts_error = str(exc) or "Failed to preview TTS."
                self._last_tts_message = ""
                logging.exception("Failed to preview TTS: %s", exc)
                raise

            self._last_tts_error = ""
            self._last_tts_message = "Тестовая фраза озвучена."
            return self.snapshot()

    def upload_tts_files(self, files: list[dict[str, str]]) -> dict[str, Any]:
        with self._lock:
            try:
                uploaded = self._tts_library.upload_files(files)
            except Exception as exc:
                self._last_tts_error = str(exc) or "Failed to upload TTS files."
                self._last_tts_message = ""
                logging.exception("Failed to upload TTS files: %s", exc)
                raise

            self._last_tts_error = ""
            self._last_tts_message = f"Загружено файлов: {len(uploaded)}."
            self._tts_cache_updated_at = 0.0
            payload = self.snapshot()
            payload["uploaded_files"] = uploaded
            return payload

    def _audio_snapshot(self) -> dict[str, list[dict[str, Any]]]:
        now = time.monotonic()
        if now - self._audio_cache_updated_at < 3.0 and self._audio_cache:
            return {
                "audio_inputs": list(self._audio_cache.get("audio_inputs") or []),
                "audio_outputs": list(self._audio_cache.get("audio_outputs") or []),
            }

        snapshot = {
            "audio_inputs": list_audio_input_devices(self.config.audio.input_device),
            "audio_outputs": list_audio_output_devices(self.config.audio.output_device),
        }
        self._audio_cache = snapshot
        self._audio_cache_updated_at = now
        return {
            "audio_inputs": list(snapshot["audio_inputs"]),
            "audio_outputs": list(snapshot["audio_outputs"]),
        }

    def _write_audio_settings(self, input_device: str, output_device: str) -> None:
        payload = yaml.safe_load(self.config_path.read_text(encoding="utf-8")) or {}
        audio = payload.setdefault("audio", {})
        audio["input_device"] = input_device
        audio["output_device"] = output_device
        self.config.audio.input_device = input_device
        self.config.audio.output_device = output_device
        self.config_path.write_text(
            yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, width=120),
            encoding="utf-8",
        )

    def _write_assistant_settings(self, trigger_phrase: str, assistant_name: str) -> None:
        payload = yaml.safe_load(self.config_path.read_text(encoding="utf-8")) or {}
        payload["assistant_name"] = assistant_name
        wake = payload.setdefault("wake", {})
        wake["phrases"] = [trigger_phrase]
        dashboard = payload.setdefault("dashboard", {})
        dashboard["page_title"] = assistant_name
        self.config.assistant_name = assistant_name
        self.config.wake.phrases = [trigger_phrase]
        self.config.dashboard.page_title = assistant_name
        self.config_path.write_text(
            yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, width=120),
            encoding="utf-8",
        )

    def _write_tts_settings(
        self,
        *,
        engine: str,
        voice: str,
        rate: int,
        pitch: int,
        volume: int,
        piper_model_path: Path,
        piper_config_path: Path,
    ) -> None:
        payload = yaml.safe_load(self.config_path.read_text(encoding="utf-8")) or {}
        tts = payload.setdefault("tts", {})
        tts["engine"] = engine
        tts["voice"] = voice
        tts["rate"] = int(rate)
        tts["pitch"] = int(pitch)
        tts["volume"] = int(volume)
        tts["piper_model_path"] = self._relative_project_path(piper_model_path)
        tts["piper_config_path"] = self._relative_project_path(piper_config_path)
        self.config.tts.engine = engine
        self.config.tts.voice = voice
        self.config.tts.rate = int(rate)
        self.config.tts.pitch = int(pitch)
        self.config.tts.volume = int(volume)
        self.config.tts.piper_model_path = piper_model_path.resolve()
        self.config.tts.piper_config_path = piper_config_path.resolve()
        self.config_path.write_text(
            yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, width=120),
            encoding="utf-8",
        )

    def _current_wake_phrase(self) -> str:
        for phrase in self.config.wake.phrases:
            normalized = normalize_text(phrase)
            if normalized:
                return normalized
        return ""

    def _tts_snapshot(self) -> dict[str, Any]:
        now = time.monotonic()
        if self._tts_cache and now - self._tts_cache_updated_at < 8.0:
            return dict(self._tts_cache)
        current_model = self.config.tts.piper_model_path if self.config.tts.piper_model_path else None
        current_config = self.config.tts.piper_config_path if self.config.tts.piper_config_path else None
        rhvoice_voices = self._rhvoice_snapshot()
        payload = {
            "tts_engine": self.config.tts.engine,
            "tts_voice": self.config.tts.voice,
            "tts_rate": self.config.tts.rate,
            "tts_pitch": self.config.tts.pitch,
            "tts_volume": self.config.tts.volume,
            "tts_root": str(self._tts_library.root),
            "tts_piper_model": self._relative_project_path(current_model),
            "tts_rhvoice_voices": rhvoice_voices,
            "tts_piper_models": self._tts_library.list_piper_models(
                current_model_path=current_model,
                current_config_path=current_config,
            ),
        }
        self._tts_cache = dict(payload)
        self._tts_cache_updated_at = now
        return dict(payload)

    def _rhvoice_snapshot(self) -> list[str]:
        now = time.monotonic()
        if self._rhvoice_cache and now - self._rhvoice_cache_updated_at < 20.0:
            return list(self._rhvoice_cache)
        voices = list_rhvoice_voices()
        self._rhvoice_cache = list(voices)
        self._rhvoice_cache_updated_at = now
        return list(voices)

    def _relative_project_path(self, path: Path | None) -> str:
        if not path:
            return ""
        resolved = path.resolve()
        try:
            return resolved.relative_to(self.config.project_root).as_posix()
        except ValueError:
            try:
                return Path(os.path.relpath(resolved, self.config.project_root.resolve())).as_posix()
            except ValueError:
                return resolved.as_posix()
