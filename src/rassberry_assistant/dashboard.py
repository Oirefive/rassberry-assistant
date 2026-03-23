from __future__ import annotations

import json
import logging
import mimetypes
import socket
import ssl
import subprocess
import time
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock, Thread
from typing import Any, Callable
from urllib.parse import parse_qs, unquote, urlparse

from .config import DashboardConfig


_UNSET = object()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AssistantDashboard:
    _STATE_FLUSH_INTERVAL_SECONDS = 0.45

    def __init__(self, config: DashboardConfig, assistant_name: str, project_root: Path) -> None:
        self.config = config
        self.assistant_name = assistant_name
        self.project_root = project_root
        self.web_root = (project_root / "web").resolve()
        self._lock = Lock()
        self._server: ThreadingHTTPServer | None = None
        self._thread: Thread | None = None
        self._https_server: ThreadingHTTPServer | None = None
        self._https_thread: Thread | None = None
        self._system_metrics: dict[str, Any] = self._empty_system_metrics()
        self._system_metrics_updated_at = 0.0
        self._cpu_sample: tuple[int, int] | None = None
        self._last_state_flush_at = 0.0
        self._chat_client: Any = None
        self._command_store: Any = None
        self._reload_commands_callback: Callable[[], None] | None = None
        self._system_controller: Any = None
        self._network_mic: Any = None
        self._local_ip = self._resolve_local_ip()
        self._https_available = False
        self._system_info: dict[str, Any] = {}
        self._state: dict[str, Any] = {
            "assistant_name": assistant_name,
            "page_title": config.page_title,
            "phase": "idle",
            "status_text": "Ожидание",
            "message": f'Жду слово активации: "{assistant_name}".',
            "transcript": "",
            "partial_transcript": "",
            "reply_text": "",
            "command_id": "",
            "success": None,
            "input_level": 0,
            "speech_active": False,
            "speech_timeout_ms": None,
            "updated_at": _now_iso(),
        }
        self._write_locked(force=True)

    def start(self) -> None:
        if not self.config.enabled:
            return
        if self._server:
            return

        dashboard = self

        class DashboardHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                path = urlparse(self.path).path
                if path in {"/", "/index.html"}:
                    self._serve_file(dashboard.web_root / "index.html", "text/html; charset=utf-8")
                    return
                if path in {"/mic", "/mic.html"}:
                    self._serve_file(dashboard.web_root / "mic.html", "text/html; charset=utf-8")
                    return
                if path == "/dashboard.css":
                    self._serve_file(dashboard.web_root / "dashboard.css", "text/css; charset=utf-8")
                    return
                if path == "/mic.css":
                    self._serve_file(dashboard.web_root / "mic.css", "text/css; charset=utf-8")
                    return
                if path == "/dashboard.js":
                    self._serve_file(
                        dashboard.web_root / "dashboard.js",
                        "application/javascript; charset=utf-8",
                    )
                    return
                if path == "/mic.js":
                    self._serve_file(
                        dashboard.web_root / "mic.js",
                        "application/javascript; charset=utf-8",
                    )
                    return
                if path == "/api/state":
                    self._serve_json(dashboard.snapshot())
                    return
                if path == "/api/system":
                    self._serve_json(dashboard.system_info())
                    return
                if path == "/api/mic/status":
                    if not dashboard._network_mic:
                        self.send_error(HTTPStatus.SERVICE_UNAVAILABLE, "network mic is unavailable")
                        return
                    self._serve_json(dashboard._network_mic_payload())
                    return
                if path == "/api/commands":
                    if not dashboard._command_store:
                        self.send_error(HTTPStatus.SERVICE_UNAVAILABLE)
                        return
                    self._serve_json(
                        {
                            "commands": dashboard._command_store.list_commands(),
                            "audio_files": dashboard._command_store.list_audio_files(),
                        }
                    )
                    return
                if path == "/healthz":
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", "text/plain; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(b"ok")
                    return
                if path == "/media/idle":
                    self._serve_file(dashboard.config.idle_video)
                    return
                if path == "/media/active":
                    self._serve_file(dashboard.config.active_video)
                    return
                if path == "/media/logo":
                    self._serve_file(dashboard.config.logo_path)
                    return
                self.send_error(HTTPStatus.NOT_FOUND)

            def do_POST(self) -> None:  # noqa: N802
                path = urlparse(self.path).path
                if path == "/api/mic/chunk":
                    if not dashboard._network_mic:
                        self.send_error(HTTPStatus.SERVICE_UNAVAILABLE, "network mic is unavailable")
                        return
                    length = int(self.headers.get("Content-Length", "0") or "0")
                    raw = self.rfile.read(length) if length > 0 else b""
                    source = parse_qs(urlparse(self.path).query).get("source", ["browser"])[0]
                    dashboard._network_mic.push_chunk(raw, client_name=str(source or "browser"))
                    self.send_response(HTTPStatus.NO_CONTENT)
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    return
                if path == "/api/chat":
                    try:
                        payload = self._read_json()
                    except ValueError as exc:
                        self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
                        return
                    user_text = str(payload.get("message") or "").strip()
                    if not user_text:
                        self.send_error(HTTPStatus.BAD_REQUEST, "message is required")
                        return
                    if not dashboard._chat_client:
                        self.send_error(HTTPStatus.SERVICE_UNAVAILABLE, "llm is not configured")
                        return
                    reply = dashboard._chat_client.chat(user_text)
                    self._serve_json({"reply": reply})
                    return
                if path == "/api/system/audio":
                    if not dashboard._system_controller:
                        self.send_error(HTTPStatus.SERVICE_UNAVAILABLE, "system control is unavailable")
                        return
                    try:
                        payload = self._read_json()
                        dashboard._system_controller.apply_audio_settings(
                            input_device=str(payload.get("input_device") or "").strip() or None,
                            output_device=str(payload.get("output_device") or "").strip() or None,
                        )
                    except ValueError as exc:
                        self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
                        return
                    except RuntimeError as exc:
                        self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
                        return
                    self._serve_json(dashboard.system_info())
                    return
                if path == "/api/system/assistant":
                    if not dashboard._system_controller:
                        self.send_error(HTTPStatus.SERVICE_UNAVAILABLE, "system control is unavailable")
                        return
                    try:
                        payload = self._read_json()
                        dashboard._system_controller.apply_assistant_settings(
                            trigger_phrase=str(payload.get("trigger_phrase") or "").strip() or None,
                        )
                    except ValueError as exc:
                        self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
                        return
                    except RuntimeError as exc:
                        self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
                        return
                    self._serve_json(dashboard.system_info())
                    return
                if path == "/api/system/tts":
                    if not dashboard._system_controller:
                        self.send_error(HTTPStatus.SERVICE_UNAVAILABLE, "system control is unavailable")
                        return
                    try:
                        payload = self._read_json()
                        dashboard._system_controller.apply_tts_settings(
                            engine=str(payload.get("engine") or "").strip() or None,
                            voice=str(payload.get("voice") or "").strip() or None,
                            rate=payload.get("rate"),
                            pitch=payload.get("pitch"),
                            volume=payload.get("volume"),
                            piper_model=str(payload.get("piper_model") or "").strip() or None,
                        )
                    except ValueError as exc:
                        self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
                        return
                    except RuntimeError as exc:
                        self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
                        return
                    self._serve_json(dashboard.system_info())
                    return
                if path == "/api/system/tts/test":
                    if not dashboard._system_controller:
                        self.send_error(HTTPStatus.SERVICE_UNAVAILABLE, "system control is unavailable")
                        return
                    try:
                        payload = self._read_json()
                        dashboard._system_controller.preview_tts(str(payload.get("text") or "").strip())
                    except ValueError as exc:
                        self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
                        return
                    except RuntimeError as exc:
                        self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
                        return
                    self._serve_json(dashboard.system_info())
                    return
                if path == "/api/system/tts/upload":
                    if not dashboard._system_controller:
                        self.send_error(HTTPStatus.SERVICE_UNAVAILABLE, "system control is unavailable")
                        return
                    try:
                        payload = self._read_json()
                        files = payload.get("files")
                        if not isinstance(files, list) or not files:
                            raise ValueError("files are required")
                        result = dashboard._system_controller.upload_tts_files(files)
                    except ValueError as exc:
                        self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
                        return
                    except RuntimeError as exc:
                        self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
                        return
                    self._serve_json(result, status=HTTPStatus.CREATED)
                    return
                if path == "/api/commands":
                    if not dashboard._command_store:
                        self.send_error(HTTPStatus.SERVICE_UNAVAILABLE)
                        return
                    try:
                        payload = self._read_json()
                        command = dashboard._command_store.save_custom_command(payload)
                    except ValueError as exc:
                        self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
                        return
                    dashboard.reload_commands()
                    self._serve_json(command, status=HTTPStatus.CREATED)
                    return
                if path == "/api/audio/upload":
                    if not dashboard._command_store:
                        self.send_error(HTTPStatus.SERVICE_UNAVAILABLE)
                        return
                    try:
                        payload = self._read_json()
                    except ValueError as exc:
                        self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
                        return
                    file_name = str(payload.get("file_name") or "").strip()
                    content_base64 = str(payload.get("content_base64") or "").strip()
                    if not file_name or not content_base64:
                        self.send_error(HTTPStatus.BAD_REQUEST, "file_name and content_base64 are required")
                        return
                    saved_path = dashboard._command_store.upload_audio(
                        file_name=file_name,
                        content_base64=content_base64,
                        command_id=str(payload.get("command_id") or "").strip() or None,
                    )
                    self._serve_json(
                        {
                            "path": saved_path,
                            "audio_files": dashboard._command_store.list_audio_files(),
                        },
                        status=HTTPStatus.CREATED,
                    )
                    return
                self.send_error(HTTPStatus.NOT_FOUND)

            def do_DELETE(self) -> None:  # noqa: N802
                path = urlparse(self.path).path
                if not path.startswith("/api/commands/"):
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                if not dashboard._command_store:
                    self.send_error(HTTPStatus.SERVICE_UNAVAILABLE)
                    return
                command_id = unquote(path.rsplit("/", 1)[-1]).strip()
                if not command_id:
                    self.send_error(HTTPStatus.BAD_REQUEST)
                    return
                deleted = dashboard._command_store.delete_custom_command(command_id)
                if not deleted:
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                dashboard.reload_commands()
                self._serve_json({"deleted": True, "id": command_id})

            def log_message(self, format: str, *args: object) -> None:
                return

            def _serve_file(self, path: Path, content_type: str | None = None) -> None:
                if not path.exists() or not path.is_file():
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                payload = path.read_bytes()
                media_type = content_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", media_type)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def _read_json(self) -> dict[str, Any]:
                length = int(self.headers.get("Content-Length", "0") or "0")
                raw = self.rfile.read(length) if length > 0 else b"{}"
                try:
                    payload = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    raise ValueError("invalid json payload") from None
                if not isinstance(payload, dict):
                    raise ValueError("json object expected")
                return payload

            def _serve_json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        try:
            self._server = ThreadingHTTPServer((self.config.host, self.config.port), DashboardHandler)
        except OSError as exc:
            logging.warning("Не удалось поднять dashboard на %s:%s: %s", self.config.host, self.config.port, exc)
            return
        self._thread = Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        logging.info("Dashboard доступен на http://%s:%s", self.config.host, self.config.port)
        if self.config.https_enabled:
            self._start_https_server(DashboardHandler)

    def stop(self) -> None:
        with self._lock:
            self._write_locked(force=True)
        if self._server:
            self._server.shutdown()
            self._server.server_close()
        if self._thread:
            self._thread.join(timeout=2)
        if self._https_server:
            self._https_server.shutdown()
            self._https_server.server_close()
        if self._https_thread:
            self._https_thread.join(timeout=2)
        self._server = None
        self._thread = None
        self._https_server = None
        self._https_thread = None
        self._https_available = False

    def attach_control_plane(
        self,
        *,
        chat_client: Any = None,
        command_store: Any = None,
        reload_commands_callback: Callable[[], None] | None = None,
        system_controller: Any = None,
        network_mic: Any = None,
        system_info: dict[str, Any] | None = None,
    ) -> None:
        self._chat_client = chat_client
        self._command_store = command_store
        self._reload_commands_callback = reload_commands_callback
        self._system_controller = system_controller
        self._network_mic = network_mic
        self._system_info = dict(system_info or {})

    def set_identity(
        self,
        *,
        assistant_name: str,
        page_title: str | None = None,
        wake_phrase: str | None = None,
    ) -> None:
        with self._lock:
            clean_name = str(assistant_name or "").strip() or self.assistant_name
            self.assistant_name = clean_name
            self._state["assistant_name"] = clean_name
            self._system_info["assistant_name"] = clean_name
            if page_title is not None:
                clean_title = str(page_title or "").strip() or clean_name
                self.config.page_title = clean_title
                self._state["page_title"] = clean_title
                self._system_info["page_title"] = clean_title
            if wake_phrase is not None:
                self._system_info["wake_phrase"] = str(wake_phrase or "").strip()
            self._state["updated_at"] = _now_iso()
            self._write_locked(force=True)

    def reload_commands(self) -> None:
        if self._reload_commands_callback:
            self._reload_commands_callback()

    def system_info(self) -> dict[str, Any]:
        with self._lock:
            payload = dict(self._system_info)
            metrics = self._read_system_metrics_locked()
        if self._system_controller:
            payload = self._system_controller.snapshot(payload)
        payload.update(metrics)
        payload.update(self._network_mic_payload())
        return payload

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            state = dict(self._state)
            state.update(self._read_system_metrics_locked())
            return state

    def update(
        self,
        *,
        phase: str | None = None,
        status_text: str | None = None,
        message: str | None = None,
        transcript: str | None = None,
        partial_transcript: str | None = None,
        reply_text: str | None = None,
        command_id: str | None = None,
        input_level: int | None = None,
        speech_active: bool | None = None,
        speech_timeout_ms: object = _UNSET,
        success: object = _UNSET,
    ) -> None:
        with self._lock:
            if phase is not None:
                self._state["phase"] = phase
            if status_text is not None:
                self._state["status_text"] = status_text
            if message is not None:
                self._state["message"] = message
            if transcript is not None:
                self._state["transcript"] = transcript
            if partial_transcript is not None:
                self._state["partial_transcript"] = partial_transcript
            if reply_text is not None:
                self._state["reply_text"] = reply_text
            if command_id is not None:
                self._state["command_id"] = command_id
            if input_level is not None:
                self._state["input_level"] = max(0, min(100, int(input_level)))
            if speech_active is not None:
                self._state["speech_active"] = bool(speech_active)
            if speech_timeout_ms is not _UNSET:
                self._state["speech_timeout_ms"] = (
                    None if speech_timeout_ms is None else max(0, int(speech_timeout_ms))
                )
            if success is not _UNSET:
                self._state["success"] = success
            self._state["updated_at"] = _now_iso()
            should_force_flush = bool(
                phase is not None
                or status_text is not None
                or message is not None
                or transcript is not None
                or reply_text is not None
                or command_id is not None
                or success is not _UNSET
            )
            self._write_locked(force=should_force_flush)

    def _write_locked(self, *, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_state_flush_at < self._STATE_FLUSH_INTERVAL_SECONDS:
            return
        self.config.state_file.write_text(
            json.dumps(self._state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._last_state_flush_at = now

    @staticmethod
    def _empty_system_metrics() -> dict[str, Any]:
        return {
            "cpu_percent": None,
            "memory_percent": None,
            "memory_used_mb": None,
            "memory_total_mb": None,
        }

    def _read_system_metrics_locked(self) -> dict[str, Any]:
        now = time.monotonic()
        if now - self._system_metrics_updated_at < 0.25:
            return dict(self._system_metrics)

        metrics = self._empty_system_metrics()
        metrics.update(self._read_memory_metrics())
        metrics["cpu_percent"] = self._read_cpu_percent()
        self._system_metrics = metrics
        self._system_metrics_updated_at = now
        return dict(metrics)

    def _read_cpu_percent(self) -> int | None:
        stat_path = Path("/proc/stat")
        if not stat_path.exists():
            return None
        try:
            fields = stat_path.read_text(encoding="utf-8").splitlines()[0].split()[1:]
            values = [int(field) for field in fields]
        except (IndexError, OSError, ValueError):
            return self._system_metrics.get("cpu_percent")

        total = sum(values)
        idle = values[3] + (values[4] if len(values) > 4 else 0)
        previous = self._cpu_sample
        self._cpu_sample = (total, idle)
        if previous is None:
            return self._system_metrics.get("cpu_percent", 0)

        total_delta = total - previous[0]
        idle_delta = idle - previous[1]
        if total_delta <= 0:
            return self._system_metrics.get("cpu_percent", 0)
        usage = 100.0 * (1.0 - (idle_delta / total_delta))
        return max(0, min(100, int(round(usage))))

    @staticmethod
    def _read_memory_metrics() -> dict[str, Any]:
        meminfo_path = Path("/proc/meminfo")
        if not meminfo_path.exists():
            return {}
        try:
            parsed: dict[str, int] = {}
            for line in meminfo_path.read_text(encoding="utf-8").splitlines():
                key, raw_value = line.split(":", 1)
                parsed[key] = int(raw_value.strip().split()[0])
        except (OSError, ValueError):
            return {}

        total_kb = parsed.get("MemTotal")
        available_kb = parsed.get("MemAvailable")
        if not total_kb or not available_kb:
            return {}

        used_kb = max(0, total_kb - available_kb)
        return {
            "memory_percent": max(0, min(100, int(round((used_kb / total_kb) * 100)))),
            "memory_used_mb": int(round(used_kb / 1024)),
            "memory_total_mb": int(round(total_kb / 1024)),
        }

    def _start_https_server(self, handler_cls: type[BaseHTTPRequestHandler]) -> None:
        try:
            if not self._ensure_tls_cert():
                return
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(
                certfile=str(self.config.tls_cert_file),
                keyfile=str(self.config.tls_key_file),
            )
            self._https_server = ThreadingHTTPServer((self.config.host, self.config.https_port), handler_cls)
            self._https_server.socket = context.wrap_socket(self._https_server.socket, server_side=True)
            self._https_thread = Thread(target=self._https_server.serve_forever, daemon=True)
            self._https_thread.start()
            self._https_available = True
            logging.info("Dashboard HTTPS доступен на https://%s:%s", self._local_ip, self.config.https_port)
        except OSError as exc:
            self._https_available = False
            logging.warning(
                "Не удалось поднять HTTPS dashboard на %s:%s: %s",
                self.config.host,
                self.config.https_port,
                exc,
            )

    def _ensure_tls_cert(self) -> bool:
        if self.config.tls_cert_file.exists() and self.config.tls_key_file.exists():
            return True
        host_name = socket.gethostname() or "raspberrypi"
        completed = subprocess.run(
            [
                "openssl",
                "req",
                "-x509",
                "-nodes",
                "-newkey",
                "rsa:2048",
                "-keyout",
                str(self.config.tls_key_file),
                "-out",
                str(self.config.tls_cert_file),
                "-days",
                "365",
                "-subj",
                f"/CN={host_name}",
                "-addext",
                f"subjectAltName=DNS:{host_name},IP:{self._local_ip}",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if completed.returncode != 0:
            logging.warning("Не удалось сгенерировать TLS сертификат для Wi-Fi микрофона.")
            return False
        return self.config.tls_cert_file.exists() and self.config.tls_key_file.exists()

    def _network_mic_payload(self) -> dict[str, Any]:
        payload = {
            "network_mic_url": self._public_url(path="/#system"),
            "network_mic_capture_url": self._public_url(path="/api/mic/chunk"),
            "dashboard_url": self._public_url(path="/"),
            "network_mic_host": self._local_ip,
            "network_mic_connected": False,
            "network_mic_last_seen": None,
            "network_mic_client": "",
            "network_mic_secure": self._https_available,
        }
        if self._network_mic:
            snapshot = self._network_mic.snapshot()
            payload["network_mic_connected"] = bool(snapshot.get("connected"))
            payload["network_mic_last_seen"] = snapshot.get("last_seen")
            payload["network_mic_client"] = snapshot.get("last_client") or ""
        return payload

    def _public_url(self, *, path: str = "/") -> str:
        scheme = "https" if self._https_available else "http"
        port = self.config.https_port if self._https_available else self.config.port
        return f"{scheme}://{self._local_ip}:{port}{path}"

    @staticmethod
    def _resolve_local_ip() -> str:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.connect(("8.8.8.8", 80))
                host = sock.getsockname()[0]
                if host and not host.startswith("127."):
                    return host
        except OSError:
            pass
        try:
            host = socket.gethostbyname(socket.gethostname())
            if host and not host.startswith("127."):
                return host
        except OSError:
            pass
        return "raspberrypi.local"
