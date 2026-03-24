from __future__ import annotations

from collections import deque
import logging
import re
import time
from pathlib import Path

import requests

from .actions import ActionExecutor
from .audio import AudioInputStream, AudioPlayer, NetworkMicStream, create_input_stream, pcm_rms
from .config import AssistantConfig
from .dashboard import AssistantDashboard
from .llm import ChatClient
from .router import CommandMatch, CommandRouter
from .stt import VoskRecognizer
from .tts import FallbackTTS, PiperTTS, RhVoiceTTS, TTSPlaybackHandle, build_tts
from .utils import normalize_text, prepare_tts_text
from .voicepack import VoicePack


class VoiceAssistant:
    _WAKE_ALIAS_HINTS = {
        "джервис",
        "джарис",
        "жарвис",
        "джарвес",
        "джордж",
    }
    _INLINE_LOW_SIGNAL_WORDS = {
        "как",
        "что",
        "кто",
        "где",
        "когда",
        "почему",
        "зачем",
        "какой",
        "какая",
        "какие",
        "какую",
        "который",
        "которая",
        "которые",
        "которую",
        "сколько",
    }
    SESSION_STOP_PHRASES = {
        "стоп",
        "отмена",
        "отбой",
        "хватит",
        "замолчи",
        "стоп диалог",
        "стоп разговор",
    }
    _SPOKEN_REPLY_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")

    def __init__(
        self,
        config: AssistantConfig,
        input_stream: AudioInputStream | None,
        player: AudioPlayer,
        recognizer: VoskRecognizer | None,
        router: CommandRouter,
        executor: ActionExecutor,
        voice_pack: VoicePack,
        tts: RhVoiceTTS | PiperTTS | FallbackTTS,
        llm: ChatClient | None,
        dashboard: AssistantDashboard | None = None,
        network_mic_stream: NetworkMicStream | None = None,
    ) -> None:
        self.config = config
        self.input_stream = input_stream
        self.player = player
        self.recognizer = recognizer
        self.router = router
        self.executor = executor
        self.voice_pack = voice_pack
        self.tts = tts
        self.llm = llm
        self.dashboard = dashboard
        self.network_mic_stream = network_mic_stream
        self._running = True
        self._last_wake_at = 0.0
        self._restart_requested = False
        self._stop_requested = False
        self._last_meter_update_at = 0.0
        self._ambient_rms = 0.0
        self._ambient_samples = 0
        self._last_record_detected_speech = False

    def _display_assistant_name(self) -> str:
        name = " ".join(str(self.config.assistant_name or "").split()).strip()
        if name:
            return name
        wake_phrase = self._primary_wake_phrase()
        return wake_phrase[:1].upper() + wake_phrase[1:] if wake_phrase else "Ассистент"

    def _primary_wake_phrase(self) -> str:
        for phrase in self.config.wake.phrases:
            normalized = normalize_text(phrase)
            if normalized:
                return normalized
        return "джарвис"

    def _idle_message(self, prefix: str | None = None) -> str:
        message = f'Жду слово активации: "{self._display_assistant_name()}".'
        if prefix:
            return f"{prefix} {message}"
        return message

    def reconfigure_trigger(
        self,
        *,
        trigger_phrase: str,
        assistant_name: str | None = None,
    ) -> dict[str, str]:
        normalized_trigger = normalize_text(trigger_phrase)
        if not normalized_trigger:
            raise ValueError("trigger_phrase is required")
        display_name = " ".join(str(assistant_name or "").split()).strip() or normalized_trigger
        self.config.wake.phrases = [normalized_trigger]
        self.config.assistant_name = display_name
        if self.recognizer:
            if hasattr(self.recognizer, "set_wake_phrases"):
                self.recognizer.set_wake_phrases([normalized_trigger])
            else:  # pragma: no cover - compatibility path
                self.recognizer.wake_phrases = [normalized_trigger]
                if hasattr(self.recognizer, "reset_wake"):
                    self.recognizer.reset_wake()
        if hasattr(self.executor, "assistant_name"):
            self.executor.assistant_name = display_name
        if self.dashboard:
            self.dashboard.set_identity(
                assistant_name=display_name,
                page_title=display_name,
                wake_phrase=normalized_trigger,
            )
        self._last_wake_at = time.monotonic()
        self._reset_conversation_context()
        self._update_dashboard(
            phase="idle",
            status_text="Ожидание",
            message=self._idle_message("Триггер обновлён."),
            transcript="",
            partial_transcript="",
            reply_text="",
            command_id="",
            input_level=0,
            speech_active=False,
            speech_timeout_ms=None,
            success=True,
        )
        return {
            "assistant_name": display_name,
            "wake_phrase": normalized_trigger,
        }

    def run(self) -> None:
        if not self.input_stream or not self.recognizer:
            raise RuntimeError("run() requires live audio input and recognizer")

        logging.info("Ассистент запущен")
        self._update_dashboard(phase="idle", status_text="Ожидание", message=self._idle_message())
        if self._play_event("startup"):
            self._settle_input(self.config.conversation.post_response_guard_seconds)

        while self._running:
            detected, inline_transcript = self._wait_for_wake()
            if not detected:
                continue
            self._run_conversation_session(initial_transcript=inline_transcript)

    def stop(self) -> None:
        self._running = False

    def reconfigure_audio(
        self,
        *,
        input_device: str | None = None,
        output_device: str | None = None,
    ) -> dict[str, str]:
        next_input = str(input_device or self.config.audio.input_device).strip()
        next_output = str(output_device or self.config.audio.output_device).strip()
        if not next_input:
            raise ValueError("input_device is required")
        if not next_output:
            raise ValueError("output_device is required")

        new_stream = None
        if next_input != self.config.audio.input_device and self.recognizer is not None:
            new_stream = create_input_stream(
                device=next_input,
                sample_rate=self.config.audio.sample_rate,
                channels=self.config.audio.channels,
                chunk_ms=self.config.audio.chunk_ms,
                network_mic_stream=self.network_mic_stream,
            )

        new_player = self.player
        new_tts = self.tts
        if next_output != self.config.audio.output_device:
            new_player = AudioPlayer(next_output)
            new_tts = build_tts(new_player, self.config.tts)

        self.player = new_player
        self.tts = new_tts
        self.config.audio.output_device = next_output

        if new_stream is not None:
            old_stream = self.input_stream
            self.input_stream = new_stream
            self.config.audio.input_device = next_input
            if old_stream:
                old_stream.close()
        else:
            self.config.audio.input_device = next_input

        self._ambient_rms = 0.0
        self._ambient_samples = 0
        self._last_meter_update_at = 0.0
        self._last_wake_at = time.monotonic()
        self._update_dashboard(
            phase="idle",
            status_text="Ожидание",
            message=self._idle_message("Аудио перенастроено."),
            transcript="",
            partial_transcript="",
            reply_text="",
            command_id="",
            input_level=0,
            speech_active=False,
            speech_timeout_ms=None,
            success=True,
        )
        return {
            "input_device": self.config.audio.input_device,
            "output_device": self.config.audio.output_device,
        }

    def reconfigure_tts(
        self,
        *,
        engine: str | None = None,
        voice: str | None = None,
        rate: int | None = None,
        pitch: int | None = None,
        volume: int | None = None,
        piper_model_path: Path | None = None,
        piper_config_path: Path | None = None,
    ) -> dict[str, str | int]:
        if engine:
            self.config.tts.engine = str(engine).strip().lower()
        if voice is not None:
            self.config.tts.voice = str(voice).strip() or self.config.tts.voice
        if rate is not None:
            self.config.tts.rate = int(rate)
        if pitch is not None:
            self.config.tts.pitch = int(pitch)
        if volume is not None:
            self.config.tts.volume = int(volume)
        if piper_model_path is not None:
            self.config.tts.piper_model_path = piper_model_path.resolve()
        if piper_config_path is not None:
            self.config.tts.piper_config_path = piper_config_path.resolve()

        self.tts = build_tts(self.player, self.config.tts)
        self._last_wake_at = time.monotonic()
        self._update_dashboard(
            phase="idle",
            status_text="Ожидание",
            message=self._idle_message("TTS перенастроен."),
            transcript="",
            partial_transcript="",
            reply_text="",
            command_id="",
            input_level=0,
            speech_active=False,
            speech_timeout_ms=None,
            success=True,
        )
        return {
            "engine": self.config.tts.engine,
            "voice": self.config.tts.voice,
            "rate": self.config.tts.rate,
            "pitch": self.config.tts.pitch,
            "volume": self.config.tts.volume,
            "piper_model_path": str(self.config.tts.piper_model_path),
        }

    def preview_tts(self, text: str) -> bool:
        self._restart_requested = False
        self._stop_requested = False
        delivered = self._speak_text(text)
        if delivered and not self._should_abort_response():
            self._settle_input(self.config.conversation.post_response_guard_seconds)
        self._last_wake_at = time.monotonic()
        return delivered and not self._should_abort_response()

    def process_transcript(self, transcript: str) -> None:
        match = self.router.find_best_match(transcript)
        if match:
            self._handle_known_command(transcript, match)
        else:
            self._handle_llm(transcript)

    def _run_conversation_session(self, initial_transcript: str | None = None) -> None:
        turns = 0
        pending_transcript = normalize_text(initial_transcript) if initial_transcript else None
        while self._running:
            if pending_transcript is not None:
                transcript = pending_transcript
                pending_transcript = None
            else:
                timeout = (
                    self.config.listen.pre_speech_timeout
                    if turns == 0
                    else self.config.conversation.followup_timeout
                )
                transcript = self._record_command(pre_speech_timeout=timeout)
            if not transcript:
                if turns == 0:
                    if self._last_record_detected_speech:
                        logging.info("Команда после активации не распознана")
                        self._update_dashboard(
                            phase="missed",
                            status_text="Не расслышал",
                            message="Команду не расслышал.",
                            transcript="",
                            reply_text="Не расслышал команду.",
                            success=False,
                        )
                        delivered = self._play_event("not_heard")
                        if not delivered:
                            delivered = self._speak_text("Не расслышал команду.")
                        if delivered:
                            self._settle_input(self.config.conversation.post_response_guard_seconds)
                    else:
                        logging.info("После активации тишина, возвращаюсь в ожидание без голосового ответа")
                else:
                    logging.info("Диалоговая сессия завершена по таймауту")
                self._update_dashboard(
                    phase="idle",
                    status_text="Ожидание",
                    message=self._idle_message(),
                )
                return

            wake_restart, transcript = self._extract_embedded_wake(transcript)
            if wake_restart:
                logging.info("Wake word повторен внутри сессии, сбрасываю контекст диалога")
                self._reset_conversation_context()
                self._update_dashboard(
                    phase="listening",
                    status_text="Слушаю",
                    message="Сессия перезапущена. Жду новую команду.",
                    transcript="",
                    reply_text="",
                    command_id="",
                )
                turns = 0
                if self._is_stop_phrase(transcript):
                    self._stop_interaction_silently()
                    return
                self._play_event("wake_ack")
                self._settle_input(self.config.conversation.post_wake_guard_seconds)
                if not transcript:
                    continue

            if self._is_stop_phrase(transcript):
                logging.info("Диалоговая сессия остановлена голосовой командой")
                self._stop_interaction_silently()
                return

            logging.info("Распознана команда: %s", transcript)
            self._update_dashboard(
                phase="routing",
                status_text="Маршрутизирую",
                message="Определяю, это команда или вопрос.",
                transcript=transcript,
            )
            self.process_transcript(transcript)

            if self._stop_requested:
                logging.info("Диалог завершён жёсткой остановкой")
                self._stop_requested = False
                return

            if self._restart_requested:
                logging.info("Диалог прерван новым wake word, начинаю новую команду")
                self._restart_requested = False
                self._update_dashboard(
                    phase="listening",
                    status_text="Слушаю",
                    message="Прервал ответ. Жду новую команду.",
                    transcript="",
                    reply_text="",
                    command_id="",
                )
                turns = 0
                continue

            turns += 1
            if not self._running:
                return
            if not self.config.conversation.enabled:
                self._update_dashboard(
                    phase="idle",
                    status_text="Ожидание",
                    message=self._idle_message(),
                )
                return
            if turns >= self.config.conversation.max_turns:
                logging.info("Диалоговая сессия завершена по лимиту ходов")
                self._update_dashboard(
                    phase="idle",
                    status_text="Ожидание",
                    message=self._idle_message(),
                )
                return
            self._update_dashboard(
                phase="followup",
                status_text="Жду уточнение",
                message="Можете продолжить диалог без повторного wake word.",
            )

    def _wait_for_wake(self) -> tuple[bool, str | None]:
        assert self.input_stream is not None
        assert self.recognizer is not None

        recent_chunks: deque[bytes] = deque(
            maxlen=max(8, int(3200 / max(self.config.audio.chunk_ms, 1)))
        )
        wake_probe_streak = 0
        last_probe_at = 0.0
        preview_text = ""
        last_preview_at = 0.0

        while self._running:
            chunk = self.input_stream.read(timeout=1.0)
            now = time.monotonic()
            if not chunk:
                self._update_input_telemetry(
                    phase="idle",
                    status_text="Ожидание",
                    message=self._idle_message(),
                    rms=0.0,
                    speech_active=False,
                    speech_timeout_ms=None,
                    partial_transcript="",
                )
                preview_text = ""
                continue
            rms = pcm_rms(chunk)
            if self._ambient_samples == 0:
                self._update_ambient_rms(rms)
            speech_threshold = self._speech_rms_threshold()
            wake_threshold = self._wake_rms_threshold()
            speech_active = rms >= speech_threshold
            if rms < speech_threshold:
                self._update_ambient_rms(rms)
            self._update_input_telemetry(
                phase="idle",
                status_text="Ожидание",
                message=self._idle_message(),
                rms=rms,
                speech_active=speech_active,
                speech_timeout_ms=None,
                partial_transcript=preview_text if speech_active else "",
            )
            recent_chunks.append(chunk)
            if speech_active and now - last_preview_at >= self.config.wake.preview_refresh_seconds:
                last_preview_at = now
                preview_text = self._transcribe_recent_audio(list(recent_chunks))
                self._update_input_telemetry(
                    phase="idle",
                    status_text="Ожидание",
                    message=self._idle_message(),
                    rms=rms,
                    speech_active=True,
                    speech_timeout_ms=None,
                    partial_transcript=preview_text,
                    force=True,
                )
            if time.monotonic() - self._last_wake_at < self.config.wake.cooldown_seconds:
                continue
            if rms < wake_threshold:
                wake_probe_streak = 0
                if not speech_active:
                    preview_text = ""
                continue
            wake_probe_streak += 1
            if self.recognizer.wake_detected(chunk):
                preview_override = preview_text if self._should_use_preview_for_wake(preview_text) else None
                wake_confirmed, inline_transcript = self._resolve_wake_from_recent_audio(
                    list(recent_chunks),
                    transcript=preview_override,
                )
                if wake_confirmed:
                    return self._begin_wake_session(inline_transcript)
                continue
            if (
                wake_probe_streak >= self.config.wake.probe_streak_chunks
                and now - last_probe_at >= self.config.wake.probe_interval_seconds
            ):
                last_probe_at = now
                preview_override = preview_text if self._should_use_preview_for_wake(preview_text) else None
                wake_confirmed, inline_transcript = self._resolve_wake_from_recent_audio(
                    list(recent_chunks),
                    transcript=preview_override,
                )
                if wake_confirmed:
                    return self._begin_wake_session(inline_transcript)
        return False, None

    def _record_command(self, pre_speech_timeout: float | None = None) -> str | None:
        assert self.input_stream is not None
        assert self.recognizer is not None

        self._last_record_detected_speech = False
        deadline = time.monotonic() + (
            pre_speech_timeout
            if pre_speech_timeout is not None
            else self.config.listen.pre_speech_timeout
        )
        speech_started = False
        speech_started_at = 0.0
        silence_started_at = 0.0
        loud_streak = 0
        chunks: list[bytes] = []
        stream = None
        last_partial = ""
        recent_chunks: deque[bytes] = deque(
            maxlen=max(
                1,
                int(
                    max(self.config.listen.preroll_ms, self.config.audio.chunk_ms)
                    / max(self.config.audio.chunk_ms, 1)
                )
                + max(self.config.listen.start_speech_chunks - 1, 0),
            )
        )

        while self._running:
            chunk = self.input_stream.read(timeout=0.5)
            now = time.monotonic()
            if chunk is None:
                if speech_started:
                    if silence_started_at == 0.0:
                        silence_started_at = now
                    silence_left_ms = max(
                        0,
                        int(
                            (
                                self.config.listen.silence_timeout
                                - (now - silence_started_at)
                            )
                            * 1000
                        ),
                    )
                    self._update_input_telemetry(
                        phase="recording",
                        status_text="Слушаю",
                        message="Записываю команду.",
                        speech_active=False,
                        speech_timeout_ms=silence_left_ms,
                        partial_transcript=last_partial,
                        rms=0.0,
                    )
                    if now - silence_started_at >= self.config.listen.silence_timeout:
                        if now - speech_started_at < self.config.listen.min_speech_seconds:
                            speech_started = False
                            speech_started_at = 0.0
                            silence_started_at = 0.0
                            loud_streak = 0
                            chunks = []
                            stream = None
                            last_partial = ""
                            recent_chunks.clear()
                        else:
                            break
                    elif now - speech_started_at >= self.config.listen.max_record_seconds:
                        break
                else:
                    self._update_input_telemetry(
                        phase="listening",
                        status_text="Жду фразу",
                        message="Говорите команду.",
                        speech_active=False,
                        speech_timeout_ms=None,
                        partial_transcript="",
                        rms=0.0,
                    )
                if not speech_started and now >= deadline:
                    return None
                continue

            rms = pcm_rms(chunk)
            if self._ambient_samples == 0:
                self._update_ambient_rms(rms)
            speech_threshold = self._speech_rms_threshold()
            is_loud = rms >= speech_threshold
            recent_chunks.append(chunk)
            if not speech_started and not is_loud:
                self._update_ambient_rms(rms)
            if is_loud:
                self._last_record_detected_speech = True

            if speech_started:
                silence_left_ms = (
                    int(self.config.listen.silence_timeout * 1000)
                    if silence_started_at == 0.0
                    else max(
                        0,
                        int(
                            (
                                self.config.listen.silence_timeout
                                - (now - silence_started_at)
                            )
                            * 1000
                        ),
                    )
                )
                self._update_input_telemetry(
                    phase="recording",
                    status_text="Слушаю",
                    message="Записываю команду.",
                    speech_active=is_loud,
                    speech_timeout_ms=silence_left_ms,
                    partial_transcript=last_partial,
                    rms=rms,
                )
            else:
                self._update_input_telemetry(
                    phase="listening",
                    status_text="Жду фразу",
                    message="Говорите команду.",
                    speech_active=is_loud,
                    speech_timeout_ms=None,
                    partial_transcript="",
                    rms=rms,
                )

            if not speech_started:
                if now >= deadline:
                    return None
                if is_loud:
                    loud_streak += 1
                else:
                    loud_streak = 0
                if loud_streak < self.config.listen.start_speech_chunks:
                    continue
                speech_started = True
                speech_started_at = now
                chunks = list(recent_chunks)
                stream = self.recognizer.new_streaming_transcriber()
                for buffered_chunk in chunks:
                    stream.accept_chunk(buffered_chunk)
                last_partial = stream.partial_text()
                self._update_dashboard(
                    phase="recording",
                    status_text="Слушаю",
                    message="Записываю команду.",
                    partial_transcript=last_partial,
                    input_level=self._input_level_percent(
                        rms, speech_threshold
                    ),
                    speech_active=True,
                    speech_timeout_ms=int(self.config.listen.silence_timeout * 1000),
                )
                continue

            chunks.append(chunk)
            if stream:
                stream.accept_chunk(chunk)
                partial = stream.partial_text()
                if partial:
                    last_partial = partial
            if is_loud:
                loud_streak = self.config.listen.start_speech_chunks
                silence_started_at = 0.0
            elif silence_started_at == 0.0:
                silence_started_at = now
            elif now - silence_started_at >= self.config.listen.silence_timeout:
                if now - speech_started_at < self.config.listen.min_speech_seconds:
                    speech_started = False
                    speech_started_at = 0.0
                    silence_started_at = 0.0
                    loud_streak = 0
                    chunks = []
                    stream = None
                    last_partial = ""
                    recent_chunks.clear()
                    recent_chunks.append(chunk)
                    continue
                break

            if now - speech_started_at >= self.config.listen.max_record_seconds:
                break

        if not chunks:
            return None

        self._update_dashboard(
            phase="transcribing",
            status_text="Распознаю",
            message="Преобразую речь в текст.",
            partial_transcript=last_partial,
            input_level=0,
            speech_active=False,
            speech_timeout_ms=None,
        )
        transcript = stream.final_text() if stream else self.recognizer.transcribe(chunks)
        return transcript or None

    @staticmethod
    def _input_level_percent(rms: float, threshold: int) -> int:
        baseline = max(float(threshold) * 2.0, 1.0)
        return max(0, min(100, int((float(rms) / baseline) * 100)))

    def _update_ambient_rms(self, rms: float) -> None:
        if self._ambient_samples == 0:
            self._ambient_rms = max(0.0, float(rms))
            self._ambient_samples = 1
            return
        if rms <= 0:
            return
        alpha = self.config.listen.ambient_rms_smoothing
        self._ambient_rms = ((1.0 - alpha) * self._ambient_rms) + (alpha * float(rms))
        self._ambient_samples += 1

    def _speech_rms_threshold(self) -> int:
        if self._ambient_samples == 0:
            return self.config.listen.speech_rms_threshold
        dynamic = int(
            (self._ambient_rms * self.config.listen.speech_dynamic_multiplier)
            + self.config.listen.speech_dynamic_margin
        )
        return max(self.config.listen.speech_rms_threshold, dynamic)

    def _wake_rms_threshold(self) -> int:
        if self._ambient_samples == 0:
            return self.config.wake.min_rms_threshold
        dynamic = int(
            (self._ambient_rms * self.config.wake.dynamic_multiplier)
            + self.config.wake.dynamic_margin
        )
        return max(self.config.wake.min_rms_threshold, dynamic)

    def _handle_known_command(self, transcript: str, match: CommandMatch) -> None:
        self._update_dashboard(
            phase="executing",
            status_text="Выполняю",
            message="Исполняю команду.",
            transcript=transcript,
            command_id=match.command.command_id,
            success=None,
        )
        if match.command.action.get("announce_before"):
            self._play_event("execute")
            if self._should_abort_response():
                return
        self._drain_input()

        try:
            result = self.executor.execute(match, transcript)
        except Exception as exc:  # pragma: no cover - runtime guard
            logging.exception("Ошибка выполнения действия: %s", exc)
            self._update_dashboard(
                phase="error",
                status_text="Ошибка",
                message="Команда завершилась ошибкой.",
                success=False,
            )
            delivered = self._play_event("error")
            if not delivered:
                delivered = self._speak_text("Команда сломалась об реальность. Проверьте логи.")
            if delivered and not self._should_abort_response():
                self._settle_input(self.config.conversation.post_response_guard_seconds)
            return

        delivered = False
        if result.audio_path:
            delivered = self._play_configured_audio(result.audio_path)
            if self._should_abort_response():
                return

        if not delivered and result.voice_selectors:
            delivered = self._play_selectors(result.voice_selectors)
            if self._should_abort_response():
                return

        if not delivered and result.speech_text:
            delivered = self._speak_text(result.speech_text)
            if self._should_abort_response():
                return

        if (
            not delivered
            and result.success
            and self.config.voice_pack.auto_match_commands
            and self.voice_pack.is_available()
        ):
            entry = self.voice_pack.find_best_for_text(
                transcript,
                self.config.voice_pack.auto_match_min_score,
            )
            if entry:
                delivered = self._play_audio_path(entry.path) == "played"
                if self._should_abort_response():
                    return

        if not delivered:
            fallback_event = "done" if result.success else "error"
            if not self._play_event(fallback_event):
                delivered = self._speak_text("Готово." if result.success else "Не вышло.")
            else:
                delivered = True
            if self._should_abort_response():
                return

        if delivered:
            self._settle_input(self.config.conversation.post_response_guard_seconds)
        self._update_dashboard(
            phase="done" if result.success else "error",
            status_text="Готово" if result.success else "Ошибка",
            message="Команда выполнена." if result.success else "Команда завершилась ошибкой.",
            reply_text=result.speech_text or "",
            command_id=match.command.command_id,
            success=result.success,
        )

        if result.should_exit:
            self.stop()

    def _handle_llm(self, transcript: str) -> None:
        self._update_dashboard(
            phase="thinking",
            status_text="Думаю",
            message="Отправил запрос в нейросеть.",
            transcript=transcript,
            command_id="llm",
            success=None,
        )
        self._play_event("llm")
        if self._should_abort_response():
            return
        self._drain_input()

        if not self.llm:
            self._update_dashboard(
                phase="error",
                status_text="Ошибка",
                message="Нейросеть сейчас недоступна.",
                success=False,
            )
            delivered = self._play_event("error")
            if not delivered:
                delivered = self._speak_text("Нейросеть сейчас недоступна.")
            if delivered and not self._should_abort_response():
                self._settle_input(self.config.conversation.post_response_guard_seconds)
            return

        try:
            answer = self.llm.chat(transcript)
        except requests.RequestException as exc:
            logging.exception("Ошибка запроса к нейросети: %s", exc)
            self._update_dashboard(
                phase="error",
                status_text="Ошибка",
                message="Не получилось достучаться до нейросети.",
                success=False,
            )
            delivered = self._play_event("error")
            if not delivered:
                delivered = self._speak_text("До нейросети не достучался.")
            if delivered and not self._should_abort_response():
                self._settle_input(self.config.conversation.post_response_guard_seconds)
            return
        except Exception as exc:  # pragma: no cover - runtime guard
            logging.exception("Ошибка ответа модели: %s", exc)
            self._update_dashboard(
                phase="error",
                status_text="Ошибка",
                message="Нейросеть не вернула ответ.",
                success=False,
            )
            delivered = self._play_event("error")
            if not delivered:
                delivered = self._speak_text("Модель задумалась и не вернулась.")
            if delivered and not self._should_abort_response():
                self._settle_input(self.config.conversation.post_response_guard_seconds)
            return

        if not answer.strip():
            self._update_dashboard(
                phase="error",
                status_text="Пустой ответ",
                message="Нейросеть вернула пустой ответ.",
                success=False,
            )
            delivered = self._play_event("error")
            if not delivered:
                delivered = self._speak_text("Модель ответила пустотой. Бывает.")
            if delivered and not self._should_abort_response():
                self._settle_input(self.config.conversation.post_response_guard_seconds)
            return

        answer = self._prepare_spoken_reply(answer)
        if self._speak_text(answer) and not self._should_abort_response():
            self._settle_input(self.config.conversation.post_response_guard_seconds)
        if self._should_abort_response():
            return
        self._update_dashboard(
            phase="done",
            status_text="Ответил",
            message="Нейросеть ответила.",
            reply_text=answer,
            command_id="llm",
            success=True,
        )

    def _play_event(self, event_name: str) -> bool:
        selectors = self.config.voice_pack.event_map.get(event_name) or []
        return self._play_selectors(selectors)

    def _play_selectors(self, selectors: list[str] | str) -> bool:
        entry = self.voice_pack.select(selectors)
        if not entry:
            return False
        return self._play_audio_path(entry.path) == "played"

    def _play_configured_audio(self, audio_path: str) -> bool:
        if not audio_path:
            return False
        path = Path(audio_path).expanduser()
        if not path.is_absolute():
            path = (self.config.project_root / path).resolve()
        return self._play_audio_path(path) == "played"

    def _drain_input(self) -> None:
        if not self.input_stream:
            return
        self.input_stream.drain(self.config.listen.discard_after_playback_ms / 1000)

    def _settle_input(self, seconds: float) -> None:
        if not self.input_stream:
            return
        self.input_stream.drain((self.config.listen.discard_after_playback_ms / 1000) + seconds)

    def _extract_embedded_wake(self, transcript: str) -> tuple[bool, str]:
        normalized = normalize_text(transcript)
        wake_phrases = {normalize_text(phrase) for phrase in self.config.wake.phrases if normalize_text(phrase)}
        if "джарвис" in wake_phrases:
            wake_phrases.update(self._WAKE_ALIAS_HINTS)
        for normalized_phrase in sorted(wake_phrases, key=len, reverse=True):
            if not normalized_phrase:
                continue
            if normalized == normalized_phrase:
                return True, ""
            prefix = normalized_phrase + " "
            if normalized.startswith(prefix):
                return True, normalized[len(prefix) :].strip()
        return False, normalized

    def _transcribe_recent_audio(self, chunks: list[bytes]) -> str:
        if not chunks or not self.recognizer:
            return ""
        return normalize_text(self.recognizer.transcribe(chunks))

    def _resolve_wake_from_recent_audio(
        self,
        chunks: list[bytes],
        transcript: str | None = None,
    ) -> tuple[bool, str | None]:
        if not chunks and not transcript:
            return False, None

        transcript = normalize_text(transcript) if transcript is not None else self._transcribe_recent_audio(chunks)
        if not transcript:
            return False, None

        wake_found, payload = self._extract_embedded_wake(transcript)
        if not wake_found:
            logging.info("Отфильтровано ложное срабатывание wake: %s", transcript)
            return False, None

        return True, payload or None

    def _should_accept_inline_transcript(self, transcript: str | None) -> bool:
        normalized = normalize_text(transcript or "")
        if not normalized:
            return False
        if self._is_stop_phrase(normalized):
            return True
        words = normalized.split()
        if len(words) >= 2:
            return True
        word = words[0]
        if word in self._INLINE_LOW_SIGNAL_WORDS:
            return False
        return len(word) >= 6

    def _should_use_preview_for_wake(self, transcript: str | None) -> bool:
        normalized = normalize_text(transcript or "")
        if not normalized:
            return False
        wake_found, payload = self._extract_embedded_wake(normalized)
        if not wake_found:
            return False
        return self._should_accept_inline_transcript(payload)

    def _begin_wake_session(self, inline_transcript: str | None) -> tuple[bool, str | None]:
        self._last_wake_at = time.monotonic()
        self._restart_requested = False
        self._stop_requested = False
        self._reset_conversation_context()
        logging.info("Обнаружено слово активации")
        self._update_dashboard(
            phase="listening",
            status_text="Слушаю",
            message="Жду команду.",
            transcript="",
            reply_text="",
            command_id="",
        )
        if self._should_accept_inline_transcript(inline_transcript):
            logging.info("Команда захвачена вместе с wake word: %s", inline_transcript)
            return True, inline_transcript
        if inline_transcript:
            logging.info("Отбросил сомнительный inline transcript после wake: %s", inline_transcript)
        self._play_event("wake_ack")
        self._settle_input(self.config.conversation.post_wake_guard_seconds)
        return True, None

    def _is_stop_phrase(self, transcript: str) -> bool:
        return normalize_text(transcript) in self.SESSION_STOP_PHRASES

    def _should_abort_response(self) -> bool:
        return self._restart_requested or self._stop_requested

    def _stop_interaction_silently(self) -> None:
        self._restart_requested = False
        self._stop_requested = True
        self._last_wake_at = time.monotonic()
        self._reset_conversation_context()
        self._update_dashboard(
            phase="idle",
            status_text="Ожидание",
            message=self._idle_message("Диалог остановлен."),
            transcript="",
            partial_transcript="",
            reply_text="",
            command_id="",
            success=True,
        )

    def _acknowledge_session_stop(self) -> None:
        delivered = self._play_selectors(
            ["я поняла снова", "сейчас", "подожди", "Принято", "Сделано", "Есть"]
        )
        if not delivered:
            delivered = self._speak_text("Остановился.")
        if delivered and not self._restart_requested:
            self._settle_input(self.config.conversation.post_response_guard_seconds)
        self._update_dashboard(
            phase="idle",
            status_text="Ожидание",
            message=self._idle_message("Диалог остановлен."),
            transcript="",
            reply_text="Остановился.",
            command_id="",
            success=True,
        )

    def _reset_conversation_context(self) -> None:
        if self.llm:
            self.llm.reset_history()

    def _prepare_spoken_reply(self, text: str) -> str:
        normalized = " ".join(text.split()).strip()
        if not normalized:
            return ""
        parts = self._SPOKEN_REPLY_SPLIT_RE.split(normalized)
        if len(parts) > 2:
            normalized = " ".join(parts[:2]).strip()
        if len(normalized) <= 220:
            return normalized
        cutoff = normalized.rfind(" ", 0, 220)
        if cutoff < 80:
            cutoff = 220
        return normalized[:cutoff].rstrip(" ,;:-")

    def _speak_text(self, text: str) -> bool:
        spoken_text = prepare_tts_text(text)
        if not spoken_text:
            return False
        self._update_dashboard(
            phase="speaking",
            status_text="Говорю",
            message="Озвучиваю ответ.",
            reply_text=text,
        )
        try:
            playback = self.tts.start_playback(spoken_text)
        except Exception as exc:  # pragma: no cover - runtime guard
            logging.exception("Сбой TTS: %s", exc)
            return False
        if not playback:
            return False
        try:
            return self._monitor_playback(playback) == "played"
        finally:
            playback.cleanup()

    def _update_input_telemetry(
        self,
        *,
        phase: str,
        status_text: str,
        message: str,
        rms: float,
        speech_active: bool,
        speech_timeout_ms: int | None,
        partial_transcript: str = "",
        force: bool = False,
    ) -> None:
        now = time.monotonic()
        if not force and now - self._last_meter_update_at < 0.08:
            return
        self._last_meter_update_at = now
        self._update_dashboard(
            phase=phase,
            status_text=status_text,
            message=message,
            partial_transcript=partial_transcript,
            input_level=self._input_level_percent(rms, self._speech_rms_threshold()),
            speech_active=speech_active,
            speech_timeout_ms=speech_timeout_ms,
        )

    def _play_audio_path(self, path: Path, delete_after: bool = False) -> str:
        try:
            if not self.input_stream or not self.recognizer:
                return "played" if self.player.play_file(path) else "missing"

            process = self.player.start_file(path)
            if not process:
                return "missing"
            return self._monitor_playback(TTSPlaybackHandle(process=process))
        finally:
            if delete_after:
                path.unlink(missing_ok=True)

    def _monitor_playback(self, playback: TTSPlaybackHandle) -> str:
        process = playback.process
        recent_chunks: deque[bytes] = deque(
            maxlen=max(8, int(3200 / max(self.config.audio.chunk_ms, 1)))
        )
        wake_probe_streak = 0
        last_probe_at = 0.0
        interrupt_guard_until = (
            time.monotonic() + self.config.conversation.playback_interrupt_guard_seconds
        )

        while process.poll() is None:
            if not self.input_stream or not self.recognizer:
                break
            chunk = self.input_stream.read(timeout=0.1)
            if not chunk:
                continue
            recent_chunks.append(chunk)
            if time.monotonic() < interrupt_guard_until:
                continue
            rms = pcm_rms(chunk)
            if rms < self._wake_rms_threshold():
                wake_probe_streak = 0
                continue
            wake_probe_streak += 1
            should_probe = self.recognizer.wake_detected(chunk)
            now = time.monotonic()
            if (
                not should_probe
                and wake_probe_streak >= self.config.wake.probe_streak_chunks
                and now - last_probe_at >= self.config.wake.probe_interval_seconds
            ):
                should_probe = True
                last_probe_at = now
            if not should_probe:
                continue
            wake_confirmed, payload = self._resolve_wake_from_recent_audio(list(recent_chunks))
            if not wake_confirmed:
                continue
            logging.info("Wake word обнаружен во время воспроизведения, прерываю ответ")
            self.player.stop_process(process)
            for extra_process in playback.extra_processes:
                self.player.stop_process(extra_process)
            self._last_wake_at = now
            if payload and self._is_stop_phrase(payload):
                logging.info("Получена команда жёсткой остановки во время воспроизведения")
                self._stop_interaction_silently()
                return "stopped"
            self._restart_requested = True
            self._stop_requested = False
            self._reset_conversation_context()
            self._update_dashboard(
                phase="listening",
                status_text="Слушаю",
                message="Ответ прерван. Жду новую команду.",
                transcript="",
                command_id="",
            )
            return "interrupted"

        return "played" if process.wait() == 0 else "missing"

    def _update_dashboard(self, **kwargs: object) -> None:
        phase = kwargs.get("phase")
        if phase not in {"idle", "listening", "recording", "transcribing"}:
            kwargs.setdefault("partial_transcript", "")
            kwargs.setdefault("input_level", 0)
            kwargs.setdefault("speech_active", False)
            kwargs.setdefault("speech_timeout_ms", None)
        if self.dashboard:
            self.dashboard.update(**kwargs)
