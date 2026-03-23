import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from rassberry_assistant.audio import AudioInputStream, AudioPlayer


class AudioTests(unittest.TestCase):
    def test_pipewire_default_input_command(self) -> None:
        stream = AudioInputStream.__new__(AudioInputStream)
        stream.device = "pipewire-default"
        command = stream._build_command(16000, 1)
        self.assertEqual(
            command,
            ["pw-record", "--rate", "16000", "--channels", "1", "--format", "s16", "--raw", "-"],
        )

    def test_pipewire_target_input_command(self) -> None:
        stream = AudioInputStream.__new__(AudioInputStream)
        stream.device = "pipewire:81"
        command = stream._build_command(16000, 1)
        self.assertEqual(
            command,
            ["pw-record", "--rate", "16000", "--channels", "1", "--format", "s16", "--raw", "--target", "81", "-"],
        )

    def test_pipewire_default_command(self) -> None:
        player = AudioPlayer("pipewire-default")
        command = player._build_command(Path("/tmp/test.wav"))
        self.assertEqual(command, ["pw-play", "/tmp/test.wav"])

    def test_pipewire_target_command(self) -> None:
        player = AudioPlayer("pipewire:VK Capsula Neo-0B0B")
        command = player._build_command(Path("/tmp/test.wav"))
        self.assertEqual(command, ["pw-play", "--target", "VK Capsula Neo-0B0B", "/tmp/test.wav"])


if __name__ == "__main__":
    unittest.main()
