import sys
import tempfile
import unittest
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from rassberry_assistant.command_store import CommandStore


class CommandStoreTests(unittest.TestCase):
    def test_save_custom_tts_command_is_listed_as_editable(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            core_path = root / "config" / "commands.yaml"
            custom_path = root / "config" / "custom_commands.yaml"
            core_path.parent.mkdir(parents=True, exist_ok=True)
            core_path.write_text("commands: []\n", encoding="utf-8")

            store = CommandStore(root, core_path, custom_path)
            saved = store.save_custom_command(
                {
                    "id": "open-telegram",
                    "phrases": "открой телеграм\nзапусти телеграм",
                    "action_type": "shell",
                    "action_value": "telegram-desktop",
                    "audio_mode": "tts",
                    "tts_text": "Открываю телеграм, сэр.",
                }
            )

            commands = store.list_commands()
            self.assertEqual(saved["id"], "open-telegram")
            self.assertEqual(len(commands), 1)
            self.assertTrue(commands[0]["editable"])
            self.assertEqual(commands[0]["audio_mode"], "tts")
            self.assertEqual(commands[0]["tts_text"], "Открываю телеграм, сэр.")

    def test_save_response_only_command_uses_speak_action(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            core_path = root / "config" / "commands.yaml"
            custom_path = root / "config" / "custom_commands.yaml"
            core_path.parent.mkdir(parents=True, exist_ok=True)
            core_path.write_text("commands: []\n", encoding="utf-8")

            store = CommandStore(root, core_path, custom_path)
            store.save_custom_command(
                {
                    "phrases": "доброе утро",
                    "action_type": "speak",
                    "audio_mode": "tts",
                    "tts_text": "Доброе утро, сэр.",
                }
            )

            payload = yaml.safe_load(custom_path.read_text(encoding="utf-8"))
            command = payload["commands"][0]
            self.assertEqual(command["action"]["type"], "speak")
            self.assertEqual(command["action"]["text"], "Доброе утро, сэр.")

    def test_upload_audio_is_saved_inside_custom_audio_as_wav(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            core_path = root / "config" / "commands.yaml"
            custom_path = root / "config" / "custom_commands.yaml"
            core_path.parent.mkdir(parents=True, exist_ok=True)
            core_path.write_text("commands: []\n", encoding="utf-8")

            store = CommandStore(root, core_path, custom_path)
            relative_path = store.upload_audio(
                file_name="reply.mp3",
                content_base64="UklGRg==",
                command_id="voice-reply",
            )

            self.assertTrue(relative_path.endswith(".wav"))
            self.assertTrue((root / relative_path).exists())
            audio_files = store.list_audio_files()
            self.assertEqual(len(audio_files), 1)
            self.assertEqual(audio_files[0]["path"], relative_path)


if __name__ == "__main__":
    unittest.main()
