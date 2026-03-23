from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from typing import Any

import requests

from .router import CommandMatch
from .utils import render_template


@dataclass(slots=True)
class ActionResult:
    success: bool
    speech_text: str | None = None
    voice_selectors: list[str] = field(default_factory=list)
    audio_path: str | None = None
    should_exit: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


class ActionExecutor:
    def __init__(self, assistant_name: str) -> None:
        self.assistant_name = assistant_name

    @staticmethod
    def _flatten_payload(prefix: str, value: Any, target: dict[str, Any]) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                clean_key = re.sub(r"[^0-9a-zA-Z_]+", "_", str(key)).strip("_").lower()
                next_prefix = f"{prefix}_{clean_key}" if clean_key else prefix
                if next_prefix:
                    ActionExecutor._flatten_payload(next_prefix, item, target)
            return
        if isinstance(value, list):
            for index, item in enumerate(value):
                ActionExecutor._flatten_payload(f"{prefix}_{index}", item, target)
            return
        if prefix:
            target[prefix] = value

    def _base_context(self, transcript: str, captures: dict[str, str]) -> dict[str, Any]:
        context: dict[str, Any] = {
            "assistant_name": self.assistant_name,
            "transcript": transcript,
        }
        context.update(captures)
        context.update({f"env_{key}": value for key, value in os.environ.items()})
        return context

    def execute(self, match: CommandMatch, transcript: str) -> ActionResult:
        action = match.command.action
        action_type = action.get("type", "speak")
        context = self._base_context(transcript, match.captures)

        if action_type == "shell":
            return self._run_shell(action, context)
        if action_type == "http":
            return self._run_http(action, context)
        if action_type == "play_voice":
            selectors = action.get("voice") or action.get("voice_selectors") or []
            selectors = selectors if isinstance(selectors, list) else [selectors]
            return ActionResult(success=True, voice_selectors=selectors)
        if action_type == "assistant.exit":
            speech_text = render_template(action.get("ok_text"), context)
            selectors = action.get("ok_voice") or []
            audio_path = render_template(action.get("ok_audio_file"), context)
            selectors = selectors if isinstance(selectors, list) else [selectors]
            return ActionResult(
                success=True,
                speech_text=speech_text,
                voice_selectors=selectors,
                audio_path=audio_path or None,
                should_exit=True,
            )

        speech_text = render_template(action.get("text"), context)
        selectors = action.get("voice") or []
        audio_path = render_template(action.get("audio_file"), context)
        selectors = selectors if isinstance(selectors, list) else [selectors]
        return ActionResult(
            success=True,
            speech_text=speech_text,
            voice_selectors=selectors,
            audio_path=audio_path or None,
        )

    def _run_shell(self, action: dict[str, Any], context: dict[str, Any]) -> ActionResult:
        command = render_template(action["command"], context)
        timeout = int(action.get("timeout_seconds", 30))
        completed = subprocess.run(
            command,
            shell=True,
            executable="/bin/bash",
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

        result_context = dict(context)
        result_context.update(
            {
                "stdout": completed.stdout.strip(),
                "stderr": completed.stderr.strip(),
                "returncode": completed.returncode,
            }
        )

        if completed.returncode == 0:
            speech_text = render_template(action.get("ok_text"), result_context)
            selectors = action.get("ok_voice") or []
            audio_path = render_template(action.get("ok_audio_file"), result_context)
            selectors = selectors if isinstance(selectors, list) else [selectors]
            return ActionResult(
                success=True,
                speech_text=speech_text,
                voice_selectors=selectors,
                audio_path=audio_path or None,
                metadata=result_context,
            )

        speech_text = render_template(
            action.get("error_text") or "Команда завершилась с ошибкой.",
            result_context,
        )
        selectors = action.get("error_voice") or []
        audio_path = render_template(action.get("error_audio_file"), result_context)
        selectors = selectors if isinstance(selectors, list) else [selectors]
        return ActionResult(
            success=False,
            speech_text=speech_text,
            voice_selectors=selectors,
            audio_path=audio_path or None,
            metadata=result_context,
        )

    def _run_http(self, action: dict[str, Any], context: dict[str, Any]) -> ActionResult:
        method = str(action.get("method", "POST")).upper()
        url = render_template(action["url"], context)
        timeout = int(action.get("timeout_seconds", 15))
        headers = render_template(action.get("headers") or {}, context)
        json_payload = render_template(action.get("json"), context)
        data_payload = render_template(action.get("data"), context)

        response = requests.request(
            method,
            url,
            headers=headers,
            json=json_payload,
            data=data_payload,
            timeout=timeout,
        )

        result_context = dict(context)
        result_context.update(
            {
                "status_code": response.status_code,
                "response_text": response.text.strip(),
            }
        )
        try:
            response_payload = response.json()
        except ValueError:
            response_payload = None
        if response_payload is not None:
            result_context["response_json"] = response_payload
            self._flatten_payload("json", response_payload, result_context)

        if 200 <= response.status_code < 300:
            speech_text = render_template(action.get("ok_text"), result_context)
            selectors = action.get("ok_voice") or []
            audio_path = render_template(action.get("ok_audio_file"), result_context)
            selectors = selectors if isinstance(selectors, list) else [selectors]
            return ActionResult(
                success=True,
                speech_text=speech_text,
                voice_selectors=selectors,
                audio_path=audio_path or None,
                metadata=result_context,
            )

        speech_text = render_template(
            action.get("error_text") or "Удаленный сервис вернул ошибку.",
            result_context,
        )
        selectors = action.get("error_voice") or []
        audio_path = render_template(action.get("error_audio_file"), result_context)
        selectors = selectors if isinstance(selectors, list) else [selectors]
        return ActionResult(
            success=False,
            speech_text=speech_text,
            voice_selectors=selectors,
            audio_path=audio_path or None,
            metadata=result_context,
        )
