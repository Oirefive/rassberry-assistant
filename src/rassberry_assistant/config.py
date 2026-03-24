from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .llm import DEFAULT_JARVIS_PRIMER_MESSAGES, DEFAULT_JARVIS_SYSTEM_PROMPT
from .utils import ensure_directory, normalize_text


@dataclass(slots=True)
class AudioConfig:
    input_device: str = "default"
    output_device: str = "default"
    sample_rate: int = 16000
    channels: int = 1
    chunk_ms: int = 60


@dataclass(slots=True)
class WakeConfig:
    phrases: list[str] = field(default_factory=lambda: ["джарвис"])
    cooldown_seconds: float = 2.0
    min_rms_threshold: int = 920
    dynamic_margin: int = 200
    dynamic_multiplier: float = 1.6
    preview_refresh_seconds: float = 0.18
    probe_streak_chunks: int = 2
    probe_interval_seconds: float = 0.18


@dataclass(slots=True)
class ListenConfig:
    pre_speech_timeout: float = 4.0
    silence_timeout: float = 0.28
    max_record_seconds: float = 12.0
    speech_rms_threshold: int = 430
    speech_dynamic_margin: int = 90
    speech_dynamic_multiplier: float = 1.25
    ambient_rms_smoothing: float = 0.08
    preroll_ms: int = 240
    start_speech_chunks: int = 2
    min_speech_seconds: float = 0.18
    discard_after_playback_ms: int = 180


@dataclass(slots=True)
class ConversationConfig:
    enabled: bool = True
    followup_timeout: float = 6.0
    max_turns: int = 6
    post_wake_guard_seconds: float = 0.04
    post_response_guard_seconds: float = 0.45
    playback_interrupt_guard_seconds: float = 0.45


@dataclass(slots=True)
class VoicePackConfig:
    root: Path
    event_map: dict[str, list[str]] = field(default_factory=dict)
    auto_match_commands: bool = True
    auto_match_min_score: float = 0.74


@dataclass(slots=True)
class TTSConfig:
    engine: str = "rhvoice"
    voice: str = "mikhail"
    rate: int = -12
    pitch: int = -32
    volume: int = 100
    temp_dir: Path = Path("/tmp/rassberry-assistant")
    piper_model_path: Path = Path("models/piper/ru_RU-ruslan-medium.onnx")
    piper_config_path: Path = Path("models/piper/ru_RU-ruslan-medium.onnx.json")
    piper_length_scale: float = 0.78
    piper_noise_scale: float = 0.72
    piper_noise_w_scale: float = 0.82
    piper_sentence_silence: float = 0.03
    piper_volume: float = 1.05


@dataclass(slots=True)
class DashboardConfig:
    enabled: bool = True
    host: str = "0.0.0.0"
    port: int = 8765
    https_enabled: bool = True
    https_port: int = 9443
    page_title: str = "JARVIS"
    idle_video: Path = Path("assets/dashboard/jarvis-core.mp4")
    active_video: Path = Path("assets/dashboard/jarvis-active2.mp4")
    logo_path: Path = Path("assets/dashboard/jarvis-logo.png")
    state_file: Path = Path("runtime/dashboard/state.json")
    tls_cert_file: Path = Path("runtime/dashboard/cert.pem")
    tls_key_file: Path = Path("runtime/dashboard/key.pem")


@dataclass(slots=True)
class LLMConfig:
    enabled: bool = True
    api_url: str = "https://openrouter.ai/api/v1/chat/completions"
    api_key: str = ""
    model: str = "openai/gpt-4o"
    timeout_seconds: int = 90
    max_history_messages: int = 8
    http_referer: str = "https://jarvismax.app"
    app_title: str = "JARVIS MAX"
    options: dict[str, Any] = field(
        default_factory=lambda: {
            "temperature": 0.85,
            "max_tokens": 512,
        }
    )
    system_prompt: str = DEFAULT_JARVIS_SYSTEM_PROMPT
    primer_messages: list[dict[str, str]] = field(default_factory=lambda: list(DEFAULT_JARVIS_PRIMER_MESSAGES))


@dataclass(slots=True)
class AssistantConfig:
    project_root: Path
    assistant_name: str
    log_level: str
    log_file: Path
    stt_model_path: Path
    audio: AudioConfig
    wake: WakeConfig
    listen: ListenConfig
    conversation: ConversationConfig
    voice_pack: VoicePackConfig
    tts: TTSConfig
    dashboard: DashboardConfig
    llm: LLMConfig


def _load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _resolve_path(project_root: Path, value: str | None, default: str) -> Path:
    raw = value or default
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = project_root / path
    return path.resolve()


def _display_name_from_trigger(raw_value: str | None, fallback: str = "Джарвис") -> str:
    compact = " ".join(str(raw_value or "").split()).strip()
    if not compact:
        compact = fallback
    if compact and compact == compact.lower():
        return compact[:1].upper() + compact[1:]
    return compact


def load_assistant_config(config_path: Path, project_root: Path) -> AssistantConfig:
    data = _load_yaml(config_path)

    audio = AudioConfig(**(data.get("audio") or {}))
    wake = WakeConfig(**(data.get("wake") or {}))
    listen = ListenConfig(**(data.get("listen") or {}))
    conversation = ConversationConfig(**(data.get("conversation") or {}))

    voice_pack_data = data.get("voice_pack") or {}
    voice_pack = VoicePackConfig(
        root=_resolve_path(project_root, voice_pack_data.get("root"), "assets/voice_pack"),
        event_map=voice_pack_data.get("event_map") or {},
        auto_match_commands=voice_pack_data.get("auto_match_commands", True),
        auto_match_min_score=float(voice_pack_data.get("auto_match_min_score", 0.74)),
    )

    tts_data = data.get("tts") or {}
    tts = TTSConfig(
        engine=str(tts_data.get("engine", "piper")),
        voice=os.environ.get("RHVOICE_VOICE", tts_data.get("voice", "mikhail")),
        rate=int(os.environ.get("RHVOICE_RATE", tts_data.get("rate", -12))),
        pitch=int(os.environ.get("RHVOICE_PITCH", tts_data.get("pitch", -32))),
        volume=int(os.environ.get("RHVOICE_VOLUME", tts_data.get("volume", 100))),
        temp_dir=_resolve_path(project_root, tts_data.get("temp_dir"), "runtime/tts"),
        piper_model_path=_resolve_path(
            project_root,
            tts_data.get("piper_model_path"),
            "models/piper/ru_RU-ruslan-medium.onnx",
        ),
        piper_config_path=_resolve_path(
            project_root,
            tts_data.get("piper_config_path"),
            "models/piper/ru_RU-ruslan-medium.onnx.json",
        ),
        piper_length_scale=float(tts_data.get("piper_length_scale", 0.84)),
        piper_noise_scale=float(tts_data.get("piper_noise_scale", 0.8)),
        piper_noise_w_scale=float(tts_data.get("piper_noise_w_scale", 0.9)),
        piper_sentence_silence=float(tts_data.get("piper_sentence_silence", 0.05)),
        piper_volume=float(tts_data.get("piper_volume", 1.0)),
    )

    dashboard_data = data.get("dashboard") or {}
    dashboard = DashboardConfig(
        enabled=bool(dashboard_data.get("enabled", True)),
        host=str(dashboard_data.get("host", "0.0.0.0")),
        port=int(dashboard_data.get("port", 8765)),
        https_enabled=bool(dashboard_data.get("https_enabled", True)),
        https_port=int(dashboard_data.get("https_port", 9443)),
        page_title=str(dashboard_data.get("page_title", "JARVIS")),
        idle_video=_resolve_path(
            project_root,
            dashboard_data.get("idle_video"),
            "assets/dashboard/jarvis-core.mp4",
        ),
        active_video=_resolve_path(
            project_root,
            dashboard_data.get("active_video"),
            "assets/dashboard/jarvis-active2.mp4",
        ),
        logo_path=_resolve_path(
            project_root,
            dashboard_data.get("logo_path"),
            "assets/dashboard/jarvis-logo.png",
        ),
        state_file=_resolve_path(
            project_root,
            dashboard_data.get("state_file"),
            "runtime/dashboard/state.json",
        ),
        tls_cert_file=_resolve_path(
            project_root,
            dashboard_data.get("tls_cert_file"),
            "runtime/dashboard/cert.pem",
        ),
        tls_key_file=_resolve_path(
            project_root,
            dashboard_data.get("tls_key_file"),
            "runtime/dashboard/key.pem",
        ),
    )

    llm_data = data.get("llm") or {}
    use_openrouter = bool(os.environ.get("OPENROUTER_API_KEY"))
    llm = LLMConfig(
        enabled=bool(llm_data.get("enabled", True)),
        api_url=os.environ.get(
            "OPENROUTER_API_URL",
            llm_data.get("api_url") or llm_data.get("host") or LLMConfig().api_url,
        ),
        api_key=os.environ.get("OPENROUTER_API_KEY", llm_data.get("api_key", "")),
        model=os.environ.get("OPENROUTER_MODEL", llm_data.get("model", LLMConfig().model)),
        timeout_seconds=int(llm_data.get("timeout_seconds", LLMConfig().timeout_seconds)),
        max_history_messages=int(llm_data.get("max_history_messages", LLMConfig().max_history_messages)),
        http_referer=str(llm_data.get("http_referer", LLMConfig().http_referer)),
        app_title=str(llm_data.get("app_title", LLMConfig().app_title)),
        options=dict(llm_data.get("options") or LLMConfig().options),
        system_prompt=(
            LLMConfig().system_prompt
            if use_openrouter
            else llm_data.get("system_prompt", LLMConfig().system_prompt)
        ),
        primer_messages=(
            list(LLMConfig().primer_messages)
            if use_openrouter
            else list(llm_data.get("primer_messages") or LLMConfig().primer_messages)
        ),
    )

    log_file = _resolve_path(project_root, data.get("log_file"), "logs/assistant.log")
    ensure_directory(log_file.parent)
    ensure_directory(tts.temp_dir)
    ensure_directory(dashboard.state_file.parent)
    ensure_directory(dashboard.tls_cert_file.parent)

    stt_model_path = _resolve_path(
        project_root,
        data.get("stt_model_path"),
        "models/vosk-model-small-ru-0.22",
    )

    primary_wake_phrase = next((normalize_text(item) for item in wake.phrases if normalize_text(item)), "джарвис")
    assistant_name = _display_name_from_trigger(
        data.get("assistant_name"),
        _display_name_from_trigger(primary_wake_phrase),
    )
    dashboard.page_title = assistant_name

    return AssistantConfig(
        project_root=project_root,
        assistant_name=assistant_name,
        log_level=(data.get("log_level") or "INFO").upper(),
        log_file=log_file,
        stt_model_path=stt_model_path,
        audio=audio,
        wake=wake,
        listen=listen,
        conversation=conversation,
        voice_pack=voice_pack,
        tts=tts,
        dashboard=dashboard,
        llm=llm,
    )
