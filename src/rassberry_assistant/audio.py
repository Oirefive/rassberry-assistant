from __future__ import annotations

import math
import queue
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import IO


def pcm_rms(chunk: bytes) -> float:
    samples = memoryview(chunk).cast("h")
    if not samples:
        return 0.0
    total = 0
    for sample in samples:
        total += sample * sample
    return math.sqrt(total / len(samples))


class AudioInputStream:
    def __init__(
        self,
        device: str,
        sample_rate: int,
        channels: int,
        chunk_ms: int,
    ) -> None:
        self.device = device
        self.chunk_bytes = sample_rate * channels * 2 * chunk_ms // 1000
        self._queue: queue.Queue[bytes] = queue.Queue(maxsize=128)
        self._stop_event = threading.Event()
        try:
            self._process = subprocess.Popen(
                self._build_command(sample_rate, channels),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
            )
        except OSError as exc:
            raise RuntimeError(f"Unable to start audio input for device: {device}") from exc
        time.sleep(0.05)
        if self._process.poll() is not None:
            error_text = ""
            if self._process.stderr is not None:
                error_text = self._process.stderr.read().decode("utf-8", errors="replace").strip()
            raise RuntimeError(error_text or f"Audio input device is unavailable: {device}")
        self._thread = threading.Thread(target=self._reader, daemon=True)
        self._thread.start()

    def _build_command(self, sample_rate: int, channels: int) -> list[str]:
        if self.device in {"pipewire", "pipewire-default"}:
            return [
                "pw-record",
                "--rate",
                str(sample_rate),
                "--channels",
                str(channels),
                "--format",
                "s16",
                "--raw",
                "-",
            ]
        if self.device.startswith("pipewire:"):
            target = self.device.split(":", 1)[1]
            command = [
                "pw-record",
                "--rate",
                str(sample_rate),
                "--channels",
                str(channels),
                "--format",
                "s16",
                "--raw",
            ]
            if target:
                command.extend(["--target", target])
            command.append("-")
            return command
        return [
            "arecord",
            "-q",
            "-D",
            self.device,
            "-f",
            "S16_LE",
            "-r",
            str(sample_rate),
            "-c",
            str(channels),
            "-t",
            "raw",
        ]

    def _reader(self) -> None:
        assert self._process.stdout is not None
        while not self._stop_event.is_set():
            chunk = self._process.stdout.read(self.chunk_bytes)
            if not chunk:
                break
            try:
                self._queue.put(chunk, timeout=0.5)
            except queue.Full:
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    pass
                try:
                    self._queue.put_nowait(chunk)
                except queue.Full:
                    pass

    def read(self, timeout: float = 1.0) -> bytes | None:
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def drain(self, seconds: float = 0.0) -> None:
        deadline = time.monotonic() + max(seconds, 0.0)
        while time.monotonic() < deadline:
            self.read(timeout=0.05)
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                return

    def close(self) -> None:
        self._stop_event.set()
        if self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._process.kill()
        self._thread.join(timeout=1)


class NetworkMicStream:
    def __init__(self, sample_rate: int, channels: int, chunk_ms: int) -> None:
        self.device = "network-mic"
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_ms = chunk_ms
        self.chunk_bytes = sample_rate * channels * 2 * chunk_ms // 1000
        self._queue: queue.Queue[bytes] = queue.Queue(maxsize=256)
        self._buffer = bytearray()
        self._lock = threading.Lock()
        self._last_chunk_at = 0.0
        self._last_seen_at = 0.0
        self._last_client = ""

    def push_chunk(self, chunk: bytes, client_name: str = "") -> None:
        if not chunk:
            return
        with self._lock:
            self._buffer.extend(chunk)
            self._last_chunk_at = time.monotonic()
            self._last_seen_at = time.time()
            if client_name:
                self._last_client = client_name
            while len(self._buffer) >= self.chunk_bytes:
                frame = bytes(self._buffer[: self.chunk_bytes])
                del self._buffer[: self.chunk_bytes]
                self._enqueue(frame)

    def read(self, timeout: float = 1.0) -> bytes | None:
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def drain(self, seconds: float = 0.0) -> None:
        deadline = time.monotonic() + max(seconds, 0.0)
        while time.monotonic() < deadline:
            self.read(timeout=0.05)
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
        with self._lock:
            self._buffer.clear()

    def close(self) -> None:
        self.drain(0.0)

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            last_chunk_at = self._last_chunk_at
            last_seen_at = self._last_seen_at
            last_client = self._last_client
        connected = (time.monotonic() - last_chunk_at) < 3.0 if last_chunk_at else False
        return {
            "connected": connected,
            "last_client": last_client,
            "last_seen": (
                datetime.fromtimestamp(last_seen_at, timezone.utc).isoformat()
                if last_seen_at
                else None
            ),
        }

    def _enqueue(self, chunk: bytes) -> None:
        try:
            self._queue.put(chunk, timeout=0.2)
        except queue.Full:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._queue.put_nowait(chunk)
            except queue.Full:
                pass


class AudioPlayer:
    def __init__(self, device: str) -> None:
        self.device = device

    def play_file(self, path: Path) -> bool:
        if not path.exists():
            return False
        process = self.start_file(path)
        if not process:
            return False
        return process.wait() == 0

    def start_file(self, path: Path) -> subprocess.Popen[bytes] | None:
        if not path.exists():
            return None
        command = self._build_command(path)
        return subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def start_raw_stream(
        self,
        sample_rate: int,
        channels: int,
        sample_format: str = "s16",
        stdin_source: IO[bytes] | int | None = subprocess.PIPE,
    ) -> subprocess.Popen[bytes]:
        command = self._build_raw_command(sample_rate, channels, sample_format)
        return subprocess.Popen(
            command,
            stdin=stdin_source,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    @staticmethod
    def stop_process(process: subprocess.Popen[bytes]) -> None:
        if process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            process.kill()

    def _build_command(self, path: Path) -> list[str]:
        file_path = path.as_posix()
        if self.device in {"pipewire", "pipewire-default"}:
            return ["pw-play", file_path]
        if self.device.startswith("pipewire:"):
            target = self.device.split(":", 1)[1]
            if target:
                return ["pw-play", "--target", target, file_path]
            return ["pw-play", file_path]
        return ["aplay", "-q", "-D", self.device, file_path]

    def _build_raw_command(self, sample_rate: int, channels: int, sample_format: str) -> list[str]:
        if sample_format != "s16":
            raise ValueError(f"Unsupported raw sample format: {sample_format}")

        if self.device in {"pipewire", "pipewire-default"}:
            return [
                "pw-play",
                "--raw",
                "--rate",
                str(sample_rate),
                "--channels",
                str(channels),
                "--format",
                sample_format,
                "-",
            ]
        if self.device.startswith("pipewire:"):
            target = self.device.split(":", 1)[1]
            command = [
                "pw-play",
                "--raw",
                "--rate",
                str(sample_rate),
                "--channels",
                str(channels),
                "--format",
                sample_format,
            ]
            if target:
                command.extend(["--target", target])
            command.append("-")
            return command
        return [
            "aplay",
            "-q",
            "-D",
            self.device,
            "-t",
            "raw",
            "-f",
            "S16_LE",
            "-r",
            str(sample_rate),
            "-c",
            str(channels),
            "-",
        ]


def is_network_input_device(device: str) -> bool:
    normalized = str(device or "").strip().lower()
    return normalized in {"network-mic", "browser-mic", "wifi-mic"}


def create_input_stream(
    device: str,
    sample_rate: int,
    channels: int,
    chunk_ms: int,
    *,
    network_mic_stream: NetworkMicStream | None = None,
) -> AudioInputStream | NetworkMicStream:
    if is_network_input_device(device):
        if network_mic_stream is not None:
            return network_mic_stream
        return NetworkMicStream(sample_rate=sample_rate, channels=channels, chunk_ms=chunk_ms)
    return AudioInputStream(
        device=device,
        sample_rate=sample_rate,
        channels=channels,
        chunk_ms=chunk_ms,
    )
