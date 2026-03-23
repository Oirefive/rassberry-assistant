from __future__ import annotations

import json
from pathlib import Path

from vosk import KaldiRecognizer, Model

from .utils import normalize_text


def _extract_text(payload: str, key: str) -> str:
    try:
        return (json.loads(payload) or {}).get(key, "")
    except json.JSONDecodeError:
        return ""


def wake_text_matches(text: str, wake_phrases: list[str]) -> bool:
    normalized = normalize_text(text)
    if not normalized:
        return False
    return any(phrase and normalized == phrase for phrase in wake_phrases)


class StreamingTranscriber:
    def __init__(self, model: Model, sample_rate: int) -> None:
        self._recognizer = KaldiRecognizer(model, sample_rate)
        self._recognizer.SetWords(False)

    def accept_chunk(self, chunk: bytes) -> bool:
        return self._recognizer.AcceptWaveform(chunk)

    def partial_text(self) -> str:
        return normalize_text(_extract_text(self._recognizer.PartialResult(), "partial"))

    def final_text(self) -> str:
        return normalize_text(_extract_text(self._recognizer.FinalResult(), "text"))


class VoskRecognizer:
    def __init__(self, model_path: Path, sample_rate: int, wake_phrases: list[str]) -> None:
        self.model = Model(str(model_path))
        self.sample_rate = sample_rate
        self.wake_phrases = [normalize_text(item) for item in wake_phrases]
        self._wake_recognizer = self._new_wake_recognizer()

    def set_wake_phrases(self, wake_phrases: list[str]) -> None:
        self.wake_phrases = [normalize_text(item) for item in wake_phrases if normalize_text(item)]
        self.reset_wake()

    def _new_wake_recognizer(self) -> KaldiRecognizer:
        grammar = json.dumps(self.wake_phrases, ensure_ascii=False)
        recognizer = KaldiRecognizer(self.model, self.sample_rate, grammar)
        recognizer.SetWords(False)
        return recognizer

    def reset_wake(self) -> None:
        self._wake_recognizer = self._new_wake_recognizer()

    def new_streaming_transcriber(self) -> StreamingTranscriber:
        return StreamingTranscriber(self.model, self.sample_rate)

    def wake_detected(self, chunk: bytes) -> bool:
        if self._wake_recognizer.AcceptWaveform(chunk):
            text = _extract_text(self._wake_recognizer.Result(), "text")
            recognized = wake_text_matches(text, self.wake_phrases)
        else:
            recognized = False
        if recognized:
            self.reset_wake()
        return recognized

    def transcribe(self, chunks: list[bytes]) -> str:
        recognizer = self.new_streaming_transcriber()
        for chunk in chunks:
            recognizer.accept_chunk(chunk)
        return recognizer.final_text()
