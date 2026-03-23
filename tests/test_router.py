import unittest
import sys
from pathlib import Path
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from rassberry_assistant.router import CommandDefinition, CommandRouter


class RouterTests(unittest.TestCase):
    def test_exact_phrase_match(self) -> None:
        router = CommandRouter(
            [
                CommandDefinition(
                    command_id="time_now",
                    phrases=["который час"],
                    action={"type": "speak", "text": "ok"},
                )
            ]
        )
        match = router.find_best_match("Который час?")
        self.assertIsNotNone(match)
        self.assertEqual(match.command.command_id, "time_now")

    def test_regex_match(self) -> None:
        router = CommandRouter(
            [
                CommandDefinition(
                    command_id="reminder",
                    regex=[r"напомни (?P<task>.+)"],
                    action={"type": "speak", "text": "ok"},
                )
            ]
        )
        match = router.find_best_match("напомни купить молоко")
        self.assertIsNotNone(match)
        self.assertEqual(match.captures["task"], "купить молоко")

    def test_pc_launch_command_matches_polite_form_and_alias(self) -> None:
        from rassberry_assistant.router import load_commands

        payload = yaml.safe_load((PROJECT_ROOT / "config" / "commands.yaml").read_text(encoding="utf-8"))
        self.assertIn("commands", payload)

        router = CommandRouter(load_commands(PROJECT_ROOT / "config" / "commands.yaml"))
        match = router.find_best_match("откройте олега")
        self.assertIsNotNone(match)
        self.assertEqual(match.command.command_id, "pc_launch_known_app")


if __name__ == "__main__":
    unittest.main()
