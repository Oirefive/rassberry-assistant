import sys
import unittest
from pathlib import Path
from types import ModuleType
from itertools import count
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

if "vosk" not in sys.modules:
    fake_vosk = ModuleType("vosk")
    fake_vosk.KaldiRecognizer = object
    fake_vosk.Model = object
    sys.modules["vosk"] = fake_vosk

from rassberry_assistant.actions import ActionResult
from rassberry_assistant.assistant import VoiceAssistant
from rassberry_assistant.config import (
    AssistantConfig,
    AudioConfig,
    ConversationConfig,
    DashboardConfig,
    LLMConfig,
    ListenConfig,
    TTSConfig,
    VoicePackConfig,
    WakeConfig,
)
from rassberry_assistant.router import CommandDefinition, CommandMatch


class DummyPlayer:
    def play_file(self, path):  # pragma: no cover - not used
        return True


class DummyRouter:
    def find_best_match(self, transcript):  # pragma: no cover - not used
        return None


class DummyExecutor:
    def execute(self, match, transcript):  # pragma: no cover - not used
        raise NotImplementedError


class DummyVoicePack:
    def select(self, selectors):
        return None


class DummyTTS:
    def speak(self, text):
        return True


class DummyLLM:
    def __init__(self):
        self.reset_calls = 0

    def reset_history(self):
        self.reset_calls += 1


class DummyRecognizer:
    def __init__(self, transcript: str):
        self.transcript = transcript
        self.transcribe_calls = []
        self.accepted_chunks = []
        self.wake_phrases = []
        self.reset_calls = 0

    def transcribe(self, chunks):
        self.transcribe_calls.append(chunks)
        return self.transcript

    def set_wake_phrases(self, wake_phrases):
        self.wake_phrases = list(wake_phrases)
        self.reset_calls += 1

    def new_streaming_transcriber(self):
        return self

    def accept_chunk(self, chunk):
        self.accepted_chunks.append(chunk)
        return False

    def partial_text(self):
        return ""

    def final_text(self):
        return self.transcript


class DummyInputStream:
    def __init__(self, chunks):
        self.chunks = list(chunks)

    def read(self, timeout=1.0):
        if not self.chunks:
            return None
        return self.chunks.pop(0)

    def drain(self, seconds=0.0):
        return None


class DummyExecutorWithResult:
    def __init__(self, result):
        self.result = result

    def execute(self, match, transcript):
        return self.result


class AssistantTests(unittest.TestCase):
    def _make_assistant(self, llm=None):
        config = AssistantConfig(
            project_root=PROJECT_ROOT,
            assistant_name="Джарвис",
            log_level="INFO",
            log_file=PROJECT_ROOT / "logs" / "assistant.log",
            stt_model_path=PROJECT_ROOT / "models" / "dummy",
            audio=AudioConfig(),
            wake=WakeConfig(phrases=["джарвис"]),
            listen=ListenConfig(),
            conversation=ConversationConfig(),
            voice_pack=VoicePackConfig(root=PROJECT_ROOT / "assets" / "voice_pack"),
            tts=TTSConfig(),
            dashboard=DashboardConfig(enabled=False),
            llm=LLMConfig(),
        )
        return VoiceAssistant(
            config=config,
            input_stream=None,
            player=DummyPlayer(),
            recognizer=None,
            router=DummyRouter(),
            executor=DummyExecutor(),
            voice_pack=DummyVoicePack(),
            tts=DummyTTS(),
            llm=llm,
        )

    def test_extract_embedded_wake_phrase(self):
        assistant = self._make_assistant()
        restarted, text = assistant._extract_embedded_wake("Джарвис который час")
        self.assertTrue(restarted)
        self.assertEqual(text, "который час")

    def test_extract_embedded_wake_accepts_common_variant(self):
        assistant = self._make_assistant()
        assistant.config.wake.phrases = ["джарвис", "джервис", "джарис", "жарвис"]
        restarted, text = assistant._extract_embedded_wake("джервис который час")
        self.assertTrue(restarted)
        self.assertEqual(text, "который час")

    def test_extract_embedded_wake_accepts_logged_alias(self):
        assistant = self._make_assistant()
        restarted, text = assistant._extract_embedded_wake("джордж который час")
        self.assertTrue(restarted)
        self.assertEqual(text, "который час")

    def test_extract_embedded_wake_without_payload(self):
        assistant = self._make_assistant()
        restarted, text = assistant._extract_embedded_wake("джарвис")
        self.assertTrue(restarted)
        self.assertEqual(text, "")

    def test_stop_phrase_detected(self):
        assistant = self._make_assistant()
        self.assertTrue(assistant._is_stop_phrase("стоп"))
        self.assertTrue(assistant._is_stop_phrase("Замолчи"))

    def test_reset_conversation_context_clears_llm_history(self):
        llm = DummyLLM()
        assistant = self._make_assistant(llm=llm)
        assistant._reset_conversation_context()
        self.assertEqual(llm.reset_calls, 1)

    def test_reconfigure_trigger_updates_runtime_state(self):
        assistant = self._make_assistant()
        assistant.recognizer = DummyRecognizer("")
        assistant.executor.assistant_name = assistant.config.assistant_name

        payload = assistant.reconfigure_trigger(trigger_phrase="Эй Вега", assistant_name="Эй Вега")

        self.assertEqual(payload["assistant_name"], "Эй Вега")
        self.assertEqual(payload["wake_phrase"], "эй вега")
        self.assertEqual(assistant.config.assistant_name, "Эй Вега")
        self.assertEqual(assistant.config.wake.phrases, ["эй вега"])
        self.assertEqual(assistant.recognizer.wake_phrases, ["эй вега"])
        self.assertEqual(assistant.recognizer.reset_calls, 1)
        self.assertEqual(assistant.executor.assistant_name, "Эй Вега")

    def test_reconfigure_tts_updates_runtime_state(self):
        assistant = self._make_assistant()
        new_model = PROJECT_ROOT / "tts" / "dummy.onnx"
        new_config = PROJECT_ROOT / "tts" / "dummy.onnx.json"

        with patch("rassberry_assistant.assistant.build_tts", return_value=DummyTTS()) as mocked_build:
            payload = assistant.reconfigure_tts(
                engine="piper",
                voice="anna",
                rate=-6,
                pitch=-14,
                volume=90,
                piper_model_path=new_model,
                piper_config_path=new_config,
            )

        self.assertEqual(payload["engine"], "piper")
        self.assertEqual(payload["voice"], "anna")
        self.assertEqual(assistant.config.tts.engine, "piper")
        self.assertEqual(assistant.config.tts.voice, "anna")
        self.assertEqual(assistant.config.tts.rate, -6)
        self.assertEqual(assistant.config.tts.pitch, -14)
        self.assertEqual(assistant.config.tts.volume, 90)
        self.assertEqual(assistant.config.tts.piper_model_path, new_model)
        self.assertEqual(assistant.config.tts.piper_config_path, new_config)
        mocked_build.assert_called_once()

    def test_resolve_wake_from_recent_audio_extracts_inline_command(self):
        assistant = self._make_assistant()
        assistant.recognizer = DummyRecognizer("джарвис который час")
        detected, payload = assistant._resolve_wake_from_recent_audio([b"a"])
        self.assertTrue(detected)
        self.assertEqual(payload, "который час")

    def test_transcribe_recent_audio_normalizes_preview(self):
        assistant = self._make_assistant()
        assistant.recognizer = DummyRecognizer("  джарвис   открой   телеграм  ")
        preview = assistant._transcribe_recent_audio([b"a"])
        self.assertEqual(preview, "джарвис открой телеграм")

    def test_resolve_wake_uses_supplied_preview_transcript(self):
        assistant = self._make_assistant()
        assistant.recognizer = DummyRecognizer("не должен вызываться")
        detected, payload = assistant._resolve_wake_from_recent_audio(
            [],
            transcript="джарвис открой телеграм",
        )
        self.assertTrue(detected)
        self.assertEqual(payload, "открой телеграм")

    def test_resolve_wake_rejects_empty_preview(self):
        assistant = self._make_assistant()
        assistant.recognizer = DummyRecognizer("")
        detected, payload = assistant._resolve_wake_from_recent_audio([])
        self.assertFalse(detected)
        self.assertIsNone(payload)

    def test_should_not_use_preview_for_low_signal_inline_payload(self):
        assistant = self._make_assistant()
        self.assertFalse(assistant._should_use_preview_for_wake("джарвис как"))
        self.assertTrue(assistant._should_use_preview_for_wake("джарвис который час"))

    def test_resolve_wake_from_recent_audio_filters_false_positive(self):
        assistant = self._make_assistant()
        assistant.recognizer = DummyRecognizer("жалость какая погода")
        detected, payload = assistant._resolve_wake_from_recent_audio([b"a"])
        self.assertFalse(detected)
        self.assertIsNone(payload)

    def test_record_command_uses_preroll_after_confirmed_speech_start(self):
        assistant = self._make_assistant()
        assistant.config.audio = AudioConfig(chunk_ms=120)
        assistant.config.listen = ListenConfig(
            pre_speech_timeout=1.0,
            silence_timeout=0.2,
            max_record_seconds=5.0,
            speech_rms_threshold=100,
            preroll_ms=240,
            start_speech_chunks=2,
            min_speech_seconds=0.1,
        )
        quiet = (0).to_bytes(2, "little", signed=True) * 32
        loud = (500).to_bytes(2, "little", signed=True) * 32
        assistant.input_stream = DummyInputStream([quiet, loud, loud, quiet, quiet])
        assistant.recognizer = DummyRecognizer("команда")

        timer = count(0, 0.1)
        with patch("rassberry_assistant.assistant.time.monotonic", side_effect=lambda: next(timer)):
            transcript = assistant._record_command(pre_speech_timeout=1.0)

        self.assertEqual(transcript, "команда")
        self.assertEqual(len(assistant.recognizer.accepted_chunks), 5)

    def test_record_command_finishes_when_stream_goes_silent_after_speech(self):
        assistant = self._make_assistant()
        assistant.config.audio = AudioConfig(chunk_ms=120)
        assistant.config.listen = ListenConfig(
            pre_speech_timeout=1.0,
            silence_timeout=0.2,
            max_record_seconds=5.0,
            speech_rms_threshold=100,
            preroll_ms=240,
            start_speech_chunks=2,
            min_speech_seconds=0.1,
        )
        quiet = (0).to_bytes(2, "little", signed=True) * 32
        loud = (500).to_bytes(2, "little", signed=True) * 32
        assistant.input_stream = DummyInputStream([quiet, loud, loud])
        assistant.recognizer = DummyRecognizer("команда")

        timer = count(0, 0.1)
        with patch("rassberry_assistant.assistant.time.monotonic", side_effect=lambda: next(timer)):
            transcript = assistant._record_command(pre_speech_timeout=1.0)

        self.assertEqual(transcript, "команда")
        self.assertTrue(assistant._last_record_detected_speech)

    def test_record_command_timeout_on_silence_keeps_speech_flag_off(self):
        assistant = self._make_assistant()
        assistant.config.audio = AudioConfig(chunk_ms=120)
        assistant.config.listen = ListenConfig(
            pre_speech_timeout=0.3,
            silence_timeout=0.2,
            max_record_seconds=5.0,
            speech_rms_threshold=100,
            preroll_ms=240,
            start_speech_chunks=2,
            min_speech_seconds=0.1,
        )
        quiet = (0).to_bytes(2, "little", signed=True) * 32
        assistant.input_stream = DummyInputStream([quiet, quiet, quiet, quiet])
        assistant.recognizer = DummyRecognizer("")

        timer = count(0, 0.1)
        with patch("rassberry_assistant.assistant.time.monotonic", side_effect=lambda: next(timer)):
            transcript = assistant._record_command(pre_speech_timeout=0.3)

        self.assertIsNone(transcript)
        self.assertFalse(assistant._last_record_detected_speech)

    def test_dynamic_threshold_rises_with_ambient_noise(self):
        assistant = self._make_assistant()
        assistant._update_ambient_rms(500)
        self.assertGreater(assistant._speech_rms_threshold(), assistant.config.listen.speech_rms_threshold)
        self.assertGreater(assistant._wake_rms_threshold(), assistant.config.wake.min_rms_threshold)

    def test_handle_known_command_skips_execute_ack_by_default(self):
        assistant = self._make_assistant()
        assistant.executor = DummyExecutorWithResult(ActionResult(success=True, speech_text="готово"))

        events = []
        assistant._play_event = lambda name: events.append(name) or False
        assistant._drain_input = lambda: None
        assistant._speak_text = lambda text: True
        assistant._settle_input = lambda seconds: None
        assistant._update_dashboard = lambda **kwargs: None

        match = CommandMatch(
            command=CommandDefinition(command_id="test", action={}),
            score=1.0,
        )
        assistant._handle_known_command("команда", match)
        self.assertNotIn("execute", events)

    def test_handle_known_command_allows_opt_in_execute_ack(self):
        assistant = self._make_assistant()
        assistant.executor = DummyExecutorWithResult(ActionResult(success=True, speech_text="готово"))

        events = []
        assistant._play_event = lambda name: events.append(name) or False
        assistant._drain_input = lambda: None
        assistant._speak_text = lambda text: True
        assistant._settle_input = lambda seconds: None
        assistant._update_dashboard = lambda **kwargs: None

        match = CommandMatch(
            command=CommandDefinition(command_id="test", action={"announce_before": True}),
            score=1.0,
        )
        assistant._handle_known_command("команда", match)
        self.assertIn("execute", events)

    def test_stop_interaction_silently_sets_idle_state_without_reply(self):
        assistant = self._make_assistant()
        updates = []
        assistant.dashboard = type("Dash", (), {"update": lambda _, **kwargs: updates.append(kwargs)})()

        assistant._restart_requested = True
        assistant._stop_interaction_silently()

        self.assertFalse(assistant._restart_requested)
        self.assertTrue(assistant._stop_requested)
        self.assertEqual(updates[-1]["phase"], "idle")
        self.assertEqual(updates[-1]["reply_text"], "")

    def test_handle_known_command_does_not_fallback_after_hard_stop(self):
        assistant = self._make_assistant()
        assistant.executor = DummyExecutorWithResult(ActionResult(success=True, speech_text="готово"))

        events = []
        assistant._play_event = lambda name: events.append(name) or False
        assistant._play_selectors = lambda selectors: False
        assistant._drain_input = lambda: None
        assistant._settle_input = lambda seconds: None
        assistant._update_dashboard = lambda **kwargs: None

        def stop_during_speak(text):
            assistant._stop_requested = True
            return False

        assistant._speak_text = stop_during_speak

        match = CommandMatch(
            command=CommandDefinition(command_id="test", action={}),
            score=1.0,
        )
        assistant._handle_known_command("команда", match)
        self.assertEqual(events, [])


if __name__ == "__main__":
    unittest.main()
