import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from rassberry_assistant.tts import PiperTTS, RhVoiceTTS


class TTSTests(unittest.TestCase):
    def test_piper_resolve_command_uses_virtualenv_bin(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bin_dir = Path(temp_dir) / "bin"
            bin_dir.mkdir(parents=True, exist_ok=True)
            piper_bin = bin_dir / "piper"
            piper_bin.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")

            with (
                patch("rassberry_assistant.tts.shutil.which", return_value=None),
                patch("rassberry_assistant.tts.sys.executable", str(bin_dir / "python")),
            ):
                resolved = PiperTTS._resolve_command()

        self.assertEqual(resolved, [str(piper_bin)])

    def test_rhvoice_render_to_file_requires_real_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            tts = RhVoiceTTS(
                player=MagicMock(),
                voice="aleksandr-hq",
                rate=-6,
                pitch=-28,
                volume=100,
                temp_dir=Path(temp_dir),
            )
            completed = SimpleNamespace(returncode=0)
            with patch("rassberry_assistant.tts.subprocess.run", return_value=completed):
                rendered = tts.render_to_file("Проверка")

        self.assertIsNone(rendered)


if __name__ == "__main__":
    unittest.main()
