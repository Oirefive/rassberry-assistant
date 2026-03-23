from __future__ import annotations

import argparse
import logging
from pathlib import Path

from vosk import SetLogLevel

from .actions import ActionExecutor
from .assistant import VoiceAssistant
from .audio import NetworkMicStream, AudioPlayer, create_input_stream
from .command_store import CommandStore
from .config import load_assistant_config
from .dashboard import AssistantDashboard
from .env import load_env_file
from .llm import ChatClient
from .router import CommandRouter
from .stt import VoskRecognizer
from .system_control import SystemControlPlane
from .tts import build_tts
from .voicepack import VoicePack


def configure_logging(level: str, log_file: Path) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Локальный голосовой ассистент для Raspberry Pi")
    parser.add_argument("--config", default="config/assistant.yaml", help="Путь к основному конфигу")
    parser.add_argument("--commands", default="config/commands.yaml", help="Путь к конфигу команд")
    parser.add_argument(
        "--custom-commands",
        default="config/custom_commands.yaml",
        help="Путь к пользовательским командам",
    )
    parser.add_argument("--project-root", default=".", help="Корень проекта")
    parser.add_argument("--text", help="Прогнать одну текстовую команду без микрофона")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    project_root = Path(args.project_root).resolve()
    load_env_file(project_root / ".env")

    config_path = (project_root / args.config).resolve()
    commands_path = (project_root / args.commands).resolve()
    custom_commands_path = (project_root / args.custom_commands).resolve()

    config = load_assistant_config(config_path, project_root)
    configure_logging(config.log_level, config.log_file)
    SetLogLevel(-1)

    if not config.stt_model_path.exists():
        raise FileNotFoundError(
            f"Vosk модель не найдена: {config.stt_model_path}. Сначала запустите scripts/install_pi.sh"
        )

    voice_pack = VoicePack(config.voice_pack.root)
    command_store = CommandStore(project_root, commands_path, custom_commands_path)
    commands = command_store.load_router_commands()
    router = CommandRouter(commands)
    executor = ActionExecutor(config.assistant_name)
    dashboard = AssistantDashboard(config.dashboard, config.assistant_name, project_root)
    system_controller = SystemControlPlane(config_path, config)
    network_mic_stream = NetworkMicStream(
        sample_rate=config.audio.sample_rate,
        channels=config.audio.channels,
        chunk_ms=config.audio.chunk_ms,
    )

    player = AudioPlayer(config.audio.output_device)
    tts = build_tts(player, config.tts)

    llm = (
        ChatClient(
            api_url=config.llm.api_url,
            api_key=config.llm.api_key,
            model=config.llm.model,
            system_prompt=config.llm.system_prompt,
            timeout_seconds=config.llm.timeout_seconds,
            max_history_messages=config.llm.max_history_messages,
            http_referer=config.llm.http_referer,
            app_title=config.llm.app_title,
            options=config.llm.options,
            primer_messages=config.llm.primer_messages,
        )
        if config.llm.enabled and config.llm.api_key
        else None
    )
    if llm:
        try:
            llm.warm_up()
        except Exception as exc:  # pragma: no cover - startup guard
            logging.warning("Не удалось проверить внешнюю нейросеть: %s", exc)
    elif config.llm.enabled:
        logging.warning("OpenRouter API key is not configured; chat and LLM fallback are disabled.")

    def reload_router_commands() -> None:
        router.replace_commands(command_store.load_router_commands())

    dashboard.attach_control_plane(
        chat_client=llm,
        command_store=command_store,
        reload_commands_callback=reload_router_commands,
        system_controller=system_controller,
        network_mic=network_mic_stream,
        system_info={
            "assistant_name": config.assistant_name,
            "llm_enabled": bool(llm),
            "llm_model": config.llm.model,
        },
    )
    dashboard.start()

    input_stream = None
    recognizer = None
    if not args.text:
        input_stream = create_input_stream(
            device=config.audio.input_device,
            sample_rate=config.audio.sample_rate,
            channels=config.audio.channels,
            chunk_ms=config.audio.chunk_ms,
            network_mic_stream=network_mic_stream,
        )
        recognizer = VoskRecognizer(
            model_path=config.stt_model_path,
            sample_rate=config.audio.sample_rate,
            wake_phrases=config.wake.phrases,
        )

    assistant = VoiceAssistant(
        config=config,
        input_stream=input_stream,
        player=player,
        recognizer=recognizer,
        router=router,
        executor=executor,
        voice_pack=voice_pack,
        tts=tts,
        llm=llm,
        dashboard=dashboard,
        network_mic_stream=network_mic_stream,
    )
    system_controller.attach_assistant(assistant)

    try:
        if args.text:
            assistant.process_transcript(args.text)
        else:
            assistant.run()
    finally:
        dashboard.stop()
        if input_stream:
            input_stream.close()


if __name__ == "__main__":
    main()
