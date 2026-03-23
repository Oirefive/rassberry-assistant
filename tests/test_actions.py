import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from rassberry_assistant.actions import ActionExecutor
from rassberry_assistant.router import CommandDefinition, CommandMatch


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


class ActionExecutorTests(unittest.TestCase):
    def test_http_action_flattens_json_response(self):
        executor = ActionExecutor("Джарвис")
        match = CommandMatch(
            command=CommandDefinition(
                command_id="ha",
                action={
                    "type": "http",
                    "method": "POST",
                    "url": "http://example.local/api",
                    "json": {"text": "включи свет"},
                    "ok_text": "{json_response_speech_plain_speech}",
                },
            ),
            score=1.0,
        )

        payload = {"response": {"speech": {"plain": {"speech": "Включаю свет."}}}}
        with patch("rassberry_assistant.actions.requests.request", return_value=FakeResponse(200, payload)):
            result = executor.execute(match, "включи свет")

        self.assertTrue(result.success)
        self.assertEqual(result.speech_text, "Включаю свет.")

    def test_shell_action_returns_configured_audio_path(self):
        executor = ActionExecutor("Джарвис")
        match = CommandMatch(
            command=CommandDefinition(
                command_id="open_browser",
                action={
                    "type": "shell",
                    "command": "echo ok",
                    "ok_audio_file": "assets/custom_audio/browser.wav",
                },
            ),
            score=1.0,
        )

        with patch("rassberry_assistant.actions.subprocess.run") as run_mock:
            run_mock.return_value.returncode = 0
            run_mock.return_value.stdout = ""
            run_mock.return_value.stderr = ""
            result = executor.execute(match, "открой браузер")

        self.assertTrue(result.success)
        self.assertEqual(result.audio_path, "assets/custom_audio/browser.wav")


if __name__ == "__main__":
    unittest.main()
