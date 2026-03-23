from __future__ import annotations

import argparse
from difflib import SequenceMatcher
import json
import logging
import os
import re
import subprocess
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


def normalize_text(text: str) -> str:
    cleaned = text.lower().replace("ё", "е")
    cleaned = re.sub(r"[^\w\s]+", " ", cleaned, flags=re.UNICODE)
    cleaned = re.sub(r"\s+", " ", cleaned, flags=re.UNICODE)
    return cleaned.strip()


def load_config(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _expand_path_value(value: str) -> str:
    return os.path.expanduser(os.path.expandvars(value))


class WindowsAgent:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.token = str(config["token"])
        self.apps = config.get("apps") or {}

    def authenticate(self, headers) -> bool:
        return headers.get("X-Assistant-Token", "") == self.token

    def list_apps(self) -> list[dict[str, Any]]:
        result = []
        for app_id, app in self.apps.items():
            result.append(
                {
                    "id": app_id,
                    "label": app.get("label", app_id),
                    "aliases": app.get("aliases") or [],
                }
            )
        return result

    def resolve_app(self, query: str | None = None, app_id: str | None = None) -> tuple[str, dict[str, Any]] | None:
        if app_id:
            app = self.apps.get(app_id)
            if app:
                return app_id, app

        normalized = normalize_text(query or "")
        if not normalized:
            return None

        best_match = None
        best_score = 0.0
        for candidate_id, app in self.apps.items():
            aliases = [candidate_id, app.get("label", "")]
            aliases.extend(app.get("aliases") or [])
            normalized_aliases = [normalize_text(alias) for alias in aliases if alias]
            if any(alias == normalized for alias in normalized_aliases):
                return candidate_id, app
            if any(alias and (alias in normalized or normalized in alias) for alias in normalized_aliases):
                return candidate_id, app
            for alias in normalized_aliases:
                if not alias:
                    continue
                score = SequenceMatcher(None, normalized, alias).ratio()
                if score > best_score:
                    best_score = score
                    best_match = (candidate_id, app)
        if best_match and best_score >= 0.66:
            return best_match
        return None

    def launch(self, query: str | None = None, app_id: str | None = None) -> tuple[int, dict[str, Any]]:
        resolved = self.resolve_app(query=query, app_id=app_id)
        if not resolved:
            return HTTPStatus.NOT_FOUND, {
                "ok": False,
                "message": "Не нашёл такое приложение в белом списке.",
            }

        resolved_id, app = resolved
        command = [_expand_path_value(str(part)) for part in (app.get("command") or [])]
        if not command:
            return HTTPStatus.BAD_REQUEST, {
                "ok": False,
                "message": "Для этого приложения не задана команда запуска.",
            }
        cwd = app.get("cwd") or None
        if isinstance(cwd, str) and cwd:
            cwd = _expand_path_value(cwd)

        creationflags = 0
        if os.name == "nt":
            creationflags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
                subprocess, "CREATE_NEW_PROCESS_GROUP", 0
            )

        try:
            subprocess.Popen(
                command,
                cwd=cwd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
            )
        except FileNotFoundError:
            return HTTPStatus.NOT_FOUND, {
                "ok": False,
                "message": "Приложение не найдено на этом компьютере.",
            }
        except OSError as exc:
            return HTTPStatus.INTERNAL_SERVER_ERROR, {
                "ok": False,
                "message": f"Не удалось запустить приложение: {exc}",
            }

        label = str(app.get("label") or resolved_id)
        return HTTPStatus.OK, {
            "ok": True,
            "app_id": resolved_id,
            "label": label,
            "voice_selector": app.get("voice_selector", ""),
            "message": f"Запускаю {label}.",
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Local Windows command bridge for the Raspberry assistant")
    parser.add_argument("--config", default=str(Path(__file__).resolve().parents[1] / "config" / "windows_agent.json"))
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config_path = Path(args.config).resolve()
    config = load_config(config_path)
    agent = WindowsAgent(config)

    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s",
    )

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/healthz":
                self._write_json(HTTPStatus.OK, {"ok": True})
                return
            if self.path == "/api/apps":
                if not agent.authenticate(self.headers):
                    self._write_json(HTTPStatus.UNAUTHORIZED, {"ok": False, "message": "Unauthorized"})
                    return
                self._write_json(HTTPStatus.OK, {"ok": True, "apps": agent.list_apps()})
                return
            self._write_json(HTTPStatus.NOT_FOUND, {"ok": False, "message": "Not found"})

        def do_POST(self) -> None:  # noqa: N802
            if not agent.authenticate(self.headers):
                self._write_json(HTTPStatus.UNAUTHORIZED, {"ok": False, "message": "Unauthorized"})
                return

            payload = self._read_json()
            if self.path == "/api/launch":
                status, body = agent.launch(
                    query=(payload or {}).get("query"),
                    app_id=(payload or {}).get("app_id"),
                )
                self._write_json(status, body)
                return

            self._write_json(HTTPStatus.NOT_FOUND, {"ok": False, "message": "Not found"})

        def log_message(self, fmt: str, *args: object) -> None:
            logging.info("%s - %s", self.client_address[0], fmt % args)

        def _read_json(self) -> dict[str, Any] | None:
            length = int(self.headers.get("Content-Length", "0") or "0")
            if length <= 0:
                return None
            raw = self.rfile.read(length)
            if not raw:
                return None
            return json.loads(raw.decode("utf-8"))

        def _write_json(self, status: int, payload: dict[str, Any]) -> None:
            encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    bind_host = str(config.get("bind_host", "0.0.0.0"))
    port = int(config.get("port", 8766))
    server = ThreadingHTTPServer((bind_host, port), Handler)
    logging.info("Windows agent listening on http://%s:%s", bind_host, port)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
