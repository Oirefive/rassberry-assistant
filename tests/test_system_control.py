import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from rassberry_assistant.config import load_assistant_config
from rassberry_assistant.system_control import (
    SystemControlPlane,
    list_rhvoice_voices,
    parse_alsa_hardware_devices,
    parse_pipewire_sources,
    parse_pipewire_sinks,
)


class DummyAssistant:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.tts_calls: list[dict[str, object]] = []
        self.preview_calls: list[str] = []

    def reconfigure_trigger(self, *, trigger_phrase: str, assistant_name: str | None = None) -> None:
        self.calls.append((trigger_phrase, str(assistant_name or "")))

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
    ) -> None:
        self.tts_calls.append(
            {
                "engine": engine,
                "voice": voice,
                "rate": rate,
                "pitch": pitch,
                "volume": volume,
                "piper_model_path": str(piper_model_path) if piper_model_path else "",
                "piper_config_path": str(piper_config_path) if piper_config_path else "",
            }
        )

    def preview_tts(self, text: str) -> bool:
        self.preview_calls.append(text)
        return True


class SystemControlTests(unittest.TestCase):
    def test_list_rhvoice_voices_returns_fallback_when_dirs_missing(self) -> None:
        voices = list_rhvoice_voices()
        self.assertIn("anna", voices)
        self.assertIn("mikhail", voices)

    def test_parse_alsa_hardware_devices_builds_plughw_ids(self) -> None:
        raw_text = """
**** List of CAPTURE Hardware Devices ****
card 2: Microphone [USB Microphone], device 0: USB Audio [USB Audio]
  Subdevices: 1/1
"""
        devices = parse_alsa_hardware_devices(raw_text, io_kind="input")

        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0]["id"], "plughw:CARD=Microphone,DEV=0")
        self.assertEqual(devices[0]["label"], "USB Microphone / USB Audio")
        self.assertEqual(devices[0]["backend"], "alsa")

    def test_parse_pipewire_sinks_reads_ids(self) -> None:
        raw_text = """
Audio
 ├─ Sinks:
 │  * 51. VK Capsula Neo-0B0B [vol: 1.00]
 │    54. HDMI Output [vol: 0.40]
"""
        devices = parse_pipewire_sinks(raw_text)

        self.assertEqual([device["id"] for device in devices], ["pipewire:51", "pipewire:54"])
        self.assertEqual(devices[0]["label"], "VK Capsula Neo-0B0B")
        self.assertTrue(devices[0]["default"])

    def test_parse_pipewire_sources_reads_ids(self) -> None:
        raw_text = """
Audio
 ├─ Sources:
 │  * 81. Infinix NOTE 50 Pro [vol: 1.00]
 │    82. USB Microphone [vol: 0.40]
"""
        devices = parse_pipewire_sources(raw_text)

        self.assertEqual([device["id"] for device in devices], ["pipewire:81", "pipewire:82"])
        self.assertEqual(devices[0]["label"], "Infinix NOTE 50 Pro")
        self.assertTrue(devices[0]["default"])

    def test_apply_audio_settings_updates_yaml_and_runtime_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config_dir = root / "config"
            config_dir.mkdir(parents=True, exist_ok=True)
            config_path = config_dir / "assistant.yaml"
            config_path.write_text(
                "\n".join(
                    [
                        'assistant_name: "Джарвис"',
                        'log_level: "INFO"',
                        'audio:',
                        '  input_device: "default"',
                        '  output_device: "pipewire-default"',
                        'dashboard:',
                        '  enabled: false',
                        'tts:',
                        '  engine: "rhvoice"',
                        'llm:',
                        '  enabled: false',
                    ]
                ),
                encoding="utf-8",
            )
            config = load_assistant_config(config_path, root)
            control = SystemControlPlane(config_path, config)

            payload = control.apply_audio_settings(
                input_device="plughw:CARD=Microphone,DEV=0",
                output_device="default",
            )

            stored = config_path.read_text(encoding="utf-8")
            self.assertIn('input_device: plughw:CARD=Microphone,DEV=0', stored)
            self.assertIn('output_device: default', stored)
            self.assertEqual(config.audio.input_device, "plughw:CARD=Microphone,DEV=0")
            self.assertEqual(config.audio.output_device, "default")
            self.assertEqual(payload["input_device"], "plughw:CARD=Microphone,DEV=0")
            self.assertEqual(payload["output_device"], "default")

    def test_apply_assistant_settings_updates_yaml_and_runtime_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config_dir = root / "config"
            config_dir.mkdir(parents=True, exist_ok=True)
            config_path = config_dir / "assistant.yaml"
            config_path.write_text(
                "\n".join(
                    [
                        'assistant_name: "Джарвис"',
                        'log_level: "INFO"',
                        'wake:',
                        '  phrases:',
                        '    - "джарвис"',
                        'audio:',
                        '  input_device: "default"',
                        '  output_device: "pipewire-default"',
                        'dashboard:',
                        '  enabled: false',
                        'tts:',
                        '  engine: "rhvoice"',
                        'llm:',
                        '  enabled: false',
                    ]
                ),
                encoding="utf-8",
            )
            config = load_assistant_config(config_path, root)
            control = SystemControlPlane(config_path, config)
            assistant = DummyAssistant()
            control.attach_assistant(assistant)

            payload = control.apply_assistant_settings(trigger_phrase="Эй Вега")

            stored = config_path.read_text(encoding="utf-8")
            self.assertIn('assistant_name: Эй Вега', stored)
            self.assertIn('- эй вега', stored)
            self.assertEqual(config.assistant_name, "Эй Вега")
            self.assertEqual(config.wake.phrases, ["эй вега"])
            self.assertEqual(payload["assistant_name"], "Эй Вега")
            self.assertEqual(payload["wake_phrase"], "эй вега")
            self.assertEqual(assistant.calls, [("эй вега", "Эй Вега")])

    def test_apply_tts_settings_updates_yaml_and_runtime_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config_dir = root / "config"
            tts_dir = root / "tts" / "curated"
            config_dir.mkdir(parents=True, exist_ok=True)
            tts_dir.mkdir(parents=True, exist_ok=True)
            (tts_dir / "voice.onnx").write_bytes(b"onnx")
            (tts_dir / "voice.onnx.json").write_text("{}", encoding="utf-8")
            config_path = config_dir / "assistant.yaml"
            config_path.write_text(
                "\n".join(
                    [
                        'assistant_name: "Джарвис"',
                        'log_level: "INFO"',
                        'audio:',
                        '  input_device: "default"',
                        '  output_device: "pipewire-default"',
                        'dashboard:',
                        '  enabled: false',
                        'tts:',
                        '  engine: "rhvoice"',
                        '  voice: "mikhail"',
                        '  piper_model_path: "tts/curated/voice.onnx"',
                        '  piper_config_path: "tts/curated/voice.onnx.json"',
                        'llm:',
                        '  enabled: false',
                    ]
                ),
                encoding="utf-8",
            )
            config = load_assistant_config(config_path, root)
            control = SystemControlPlane(config_path, config)
            assistant = DummyAssistant()
            control.attach_assistant(assistant)

            payload = control.apply_tts_settings(
                engine="piper",
                voice="anna",
                rate=-8,
                pitch=-18,
                volume=95,
                piper_model="tts/curated/voice.onnx",
            )

            stored = config_path.read_text(encoding="utf-8")
            self.assertIn("engine: piper", stored)
            self.assertIn("voice: anna", stored)
            self.assertIn("piper_model_path: tts/curated/voice.onnx", stored)
            self.assertEqual(config.tts.engine, "piper")
            self.assertEqual(config.tts.voice, "anna")
            self.assertEqual(payload["tts_engine"], "piper")
            self.assertEqual(payload["tts_voice"], "anna")
            self.assertEqual(payload["tts_piper_model"], "tts/curated/voice.onnx")
            self.assertEqual(len(assistant.tts_calls), 1)

    def test_upload_tts_files_saves_files_into_project_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config_dir = root / "config"
            config_dir.mkdir(parents=True, exist_ok=True)
            config_path = config_dir / "assistant.yaml"
            config_path.write_text(
                "\n".join(
                    [
                        'assistant_name: "Джарвис"',
                        'log_level: "INFO"',
                        'audio:',
                        '  input_device: "default"',
                        '  output_device: "pipewire-default"',
                        'dashboard:',
                        '  enabled: false',
                        'tts:',
                        '  engine: "rhvoice"',
                        'llm:',
                        '  enabled: false',
                    ]
                ),
                encoding="utf-8",
            )
            config = load_assistant_config(config_path, root)
            control = SystemControlPlane(config_path, config)

            payload = control.upload_tts_files(
                [
                    {"file_name": "voice.onnx", "content_base64": "b25ueA=="},
                    {"file_name": "voice.onnx.json", "content_base64": "e30="},
                ]
            )

            self.assertEqual(len(payload["uploaded_files"]), 2)
            self.assertTrue((root / "tts" / "custom" / "voice.onnx").exists())
            self.assertTrue((root / "tts" / "custom" / "voice.onnx.json").exists())

    def test_preview_tts_uses_attached_assistant(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config_dir = root / "config"
            config_dir.mkdir(parents=True, exist_ok=True)
            config_path = config_dir / "assistant.yaml"
            config_path.write_text(
                "\n".join(
                    [
                        'assistant_name: "Джарвис"',
                        'log_level: "INFO"',
                        'audio:',
                        '  input_device: "default"',
                        '  output_device: "pipewire-default"',
                        'dashboard:',
                        '  enabled: false',
                        'tts:',
                        '  engine: "rhvoice"',
                        'llm:',
                        '  enabled: false',
                    ]
                ),
                encoding="utf-8",
            )
            config = load_assistant_config(config_path, root)
            control = SystemControlPlane(config_path, config)
            assistant = DummyAssistant()
            control.attach_assistant(assistant)

            payload = control.preview_tts("Проверка")

            self.assertEqual(assistant.preview_calls, ["Проверка"])
            self.assertEqual(payload["tts_message"], "Тестовая фраза озвучена.")

    def test_apply_tts_settings_allows_piper_without_manual_voice(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config_dir = root / "config"
            tts_dir = root / "tts" / "curated"
            config_dir.mkdir(parents=True, exist_ok=True)
            tts_dir.mkdir(parents=True, exist_ok=True)
            (tts_dir / "voice.onnx").write_bytes(b"onnx")
            (tts_dir / "voice.onnx.json").write_text("{}", encoding="utf-8")
            config_path = config_dir / "assistant.yaml"
            config_path.write_text(
                "\n".join(
                    [
                        'assistant_name: "Джарвис"',
                        'log_level: "INFO"',
                        'audio:',
                        '  input_device: "default"',
                        '  output_device: "pipewire-default"',
                        'dashboard:',
                        '  enabled: false',
                        'tts:',
                        '  engine: "rhvoice"',
                        '  voice: ""',
                        '  piper_model_path: "tts/curated/voice.onnx"',
                        '  piper_config_path: "tts/curated/voice.onnx.json"',
                        'llm:',
                        '  enabled: false',
                    ]
                ),
                encoding="utf-8",
            )
            config = load_assistant_config(config_path, root)
            control = SystemControlPlane(config_path, config)
            assistant = DummyAssistant()
            control.attach_assistant(assistant)

            with patch("rassberry_assistant.system_control.list_rhvoice_voices", return_value=["anna", "mikhail"]):
                payload = control.apply_tts_settings(
                    engine="piper",
                    voice="",
                    rate=-8,
                    pitch=-18,
                    volume=95,
                    piper_model="tts/curated/voice.onnx",
                )

            self.assertEqual(payload["tts_engine"], "piper")
            self.assertEqual(payload["tts_voice"], "anna")
            self.assertEqual(config.tts.voice, "anna")


if __name__ == "__main__":
    unittest.main()
