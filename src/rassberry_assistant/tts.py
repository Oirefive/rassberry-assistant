from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from .audio import AudioPlayer
from .config import TTSConfig


@dataclass(slots=True)
class TTSPlaybackHandle:
    process: subprocess.Popen[bytes]
    extra_processes: list[subprocess.Popen[bytes]] = field(default_factory=list)
    temp_path: Path | None = None

    def cleanup(self) -> None:
        for proc in self.extra_processes:
            if proc.poll() is None:
                proc.terminate()
        if self.temp_path:
            self.temp_path.unlink(missing_ok=True)


class RhVoiceTTS:
    def __init__(
        self,
        player: AudioPlayer,
        voice: str,
        rate: int,
        pitch: int,
        volume: int,
        temp_dir: Path,
    ) -> None:
        self.player = player
        self.voice = voice
        self.rate = rate
        self.pitch = pitch
        self.volume = volume
        self.temp_dir = temp_dir

    def render_to_file(self, text: str) -> Path | None:
        phrase = text.strip()
        if not phrase:
            return None

        self.temp_dir.mkdir(parents=True, exist_ok=True)
        output_path = self.temp_dir / f"tts-{uuid.uuid4().hex}.wav"
        completed = subprocess.run(
            [
                "RHVoice-test",
                "-p",
                self.voice,
                "-r",
                str(self.rate),
                "-t",
                str(self.pitch),
                "-v",
                str(self.volume),
                "-o",
                str(output_path),
            ],
            input=phrase.encode("utf-8"),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            check=False,
        )
        if completed.returncode != 0 or not output_path.exists() or output_path.stat().st_size <= 0:
            output_path.unlink(missing_ok=True)
            return None
        return output_path

    def start_playback(self, text: str) -> TTSPlaybackHandle | None:
        output_path = self.render_to_file(text)
        if not output_path:
            return None
        process = self.player.start_file(output_path)
        if not process:
            output_path.unlink(missing_ok=True)
            return None
        return TTSPlaybackHandle(process=process, temp_path=output_path)


class PiperTTS:
    def __init__(
        self,
        player: AudioPlayer,
        model_path: Path,
        config_path: Path,
        length_scale: float,
        noise_scale: float,
        noise_w_scale: float,
        sentence_silence: float,
        volume: float,
    ) -> None:
        self.player = player
        self.model_path = model_path
        self.config_path = config_path
        self.length_scale = length_scale
        self.noise_scale = noise_scale
        self.noise_w_scale = noise_w_scale
        self.sentence_silence = sentence_silence
        self.volume = volume
        config = json.loads(config_path.read_text(encoding="utf-8"))
        self.sample_rate = int((config.get("audio") or {}).get("sample_rate", 22050))
        self.command = self._resolve_command()

    @staticmethod
    def _resolve_command() -> list[str] | None:
        for candidate in ("piper", "piper-tts"):
            resolved = shutil.which(candidate)
            if resolved:
                return [resolved]

        python_dirs = [Path(sys.executable).parent, Path(sys.executable).resolve().parent]
        seen: set[str] = set()
        for python_dir in python_dirs:
            key = str(python_dir)
            if key in seen:
                continue
            seen.add(key)
            for name in ("piper", "piper-tts"):
                candidate = python_dir / name
                if candidate.exists():
                    return [str(candidate)]
        return None

    def start_playback(self, text: str) -> TTSPlaybackHandle | None:
        phrase = text.strip()
        if (
            not phrase
            or not self.model_path.exists()
            or not self.config_path.exists()
            or not self.command
        ):
            return None

        try:
            piper_process = subprocess.Popen(
                [
                    *self.command,
                    "--model",
                    str(self.model_path),
                    "--config",
                    str(self.config_path),
                    "--output-raw",
                    "--length-scale",
                    str(self.length_scale),
                    "--noise-scale",
                    str(self.noise_scale),
                    "--noise-w-scale",
                    str(self.noise_w_scale),
                    "--sentence-silence",
                    str(self.sentence_silence),
                    "--volume",
                    str(self.volume),
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            return None

        assert piper_process.stdout is not None
        playback_process = self.player.start_raw_stream(
            sample_rate=self.sample_rate,
            channels=1,
            sample_format="s16",
            stdin_source=piper_process.stdout,
        )
        if not playback_process:
            piper_process.terminate()
            return None
        piper_process.stdout.close()

        assert piper_process.stdin is not None
        piper_process.stdin.write(phrase.encode("utf-8"))
        piper_process.stdin.close()

        # Some aarch64 builds manage to parse CLI args and then die instantly on synthesis.
        # Treat that as an unavailable engine so the caller can fall back to RHVoice instead
        # of pretending Piper is working while producing silence.
        time.sleep(0.08)
        piper_return_code = piper_process.poll()
        if piper_return_code not in (None, 0):
            AudioPlayer.stop_process(playback_process)
            return None

        return TTSPlaybackHandle(process=playback_process, extra_processes=[piper_process])


class FallbackTTS:
    def __init__(self, primary: PiperTTS | RhVoiceTTS, secondary: RhVoiceTTS | None = None) -> None:
        self.primary = primary
        self.secondary = secondary

    def start_playback(self, text: str) -> TTSPlaybackHandle | None:
        playback = self.primary.start_playback(text)
        if playback or not self.secondary:
            return playback
        return self.secondary.start_playback(text)


def build_tts(player: AudioPlayer, config: TTSConfig) -> RhVoiceTTS | PiperTTS | FallbackTTS:
    rhvoice = RhVoiceTTS(
        player=player,
        voice=config.voice,
        rate=config.rate,
        pitch=config.pitch,
        volume=config.volume,
        temp_dir=config.temp_dir,
    )
    piper = PiperTTS(
        player=player,
        model_path=config.piper_model_path,
        config_path=config.piper_config_path,
        length_scale=config.piper_length_scale,
        noise_scale=config.piper_noise_scale,
        noise_w_scale=config.piper_noise_w_scale,
        sentence_silence=config.piper_sentence_silence,
        volume=config.piper_volume,
    )

    engine = config.engine.strip().lower()
    if engine == "piper":
        return FallbackTTS(primary=piper, secondary=rhvoice)

    return FallbackTTS(primary=rhvoice, secondary=piper)
