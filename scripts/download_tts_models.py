from __future__ import annotations

import argparse
import json
import time
import urllib.request
from pathlib import Path


VOICE_INDEX_URL = "https://huggingface.co/rhasspy/piper-voices/raw/main/voices.json"
VOICE_BASE_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main"

CURATED_MODELS = [
    "ru_RU-irina-medium",
    "ru_RU-ruslan-medium",
    "ru_RU-denis-medium",
    "ru_RU-dmitri-medium",
    "en_US-amy-medium",
    "en_US-kristin-medium",
    "en_US-lessac-high",
    "en_GB-jenny_dioco-medium",
    "fr_FR-siwis-medium",
    "it_IT-paola-medium",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download curated Piper TTS models into the local tts catalog")
    parser.add_argument("--project-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--target-dir", default="tts")
    return parser.parse_args()


def fetch_voice_index() -> dict[str, dict]:
    with urllib.request.urlopen(VOICE_INDEX_URL, timeout=60) as response:
        return json.load(response)


def download_file(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    last_error: Exception | None = None
    for attempt in range(1, 6):
        try:
            with urllib.request.urlopen(url, timeout=180) as response:
                destination.write_bytes(response.read())
            return
        except Exception as exc:  # pragma: no cover - network guard
            last_error = exc
            time.sleep(min(8, attempt * 1.5))
    assert last_error is not None
    raise last_error


def build_label(item: dict) -> str:
    language = (item.get("language") or {}).get("name_english", "")
    name = str(item.get("name") or "").replace("_", " ").strip().title()
    quality = str(item.get("quality") or "").strip()
    parts = [part for part in (name, language, quality) if part]
    return " • ".join(parts) if parts else "Piper voice"


def main() -> None:
    args = parse_args()
    project_root = Path(args.project_root).resolve()
    target_root = (project_root / args.target_dir).resolve()
    piper_root = target_root / "piper"
    piper_root.mkdir(parents=True, exist_ok=True)

    voice_index = fetch_voice_index()
    catalog_models: list[dict[str, str]] = []

    for key in CURATED_MODELS:
        item = voice_index.get(key)
        if not item:
            raise SystemExit(f"Voice not found in official Piper index: {key}")

        onnx_path = ""
        json_path = ""
        source_url = ""
        for relative_path in item.get("files", {}):
            file_name = Path(relative_path).name
            destination = piper_root / key / file_name
            if not destination.exists():
                download_file(f"{VOICE_BASE_URL}/{relative_path}", destination)
            if relative_path.endswith(".onnx"):
                onnx_path = destination.relative_to(project_root).as_posix()
                source_url = f"{VOICE_BASE_URL}/{relative_path}"
            elif relative_path.endswith(".onnx.json"):
                json_path = destination.relative_to(project_root).as_posix()

        if not onnx_path or not json_path:
            raise SystemExit(f"Voice is incomplete in official Piper index: {key}")

        catalog_models.append(
            {
                "key": key,
                "label": build_label(item),
                "voice_name": str(item.get("name") or ""),
                "language_code": str((item.get("language") or {}).get("code") or ""),
                "language_name": str((item.get("language") or {}).get("name_english") or ""),
                "quality": str(item.get("quality") or ""),
                "relative_model_path": onnx_path,
                "relative_config_path": json_path,
                "source_url": source_url,
            }
        )
        print(f"Downloaded {key}")

    catalog_path = target_root / "catalog.json"
    catalog_path.write_text(
        json.dumps({"provider": "piper", "models": catalog_models}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Catalog saved to {catalog_path}")


if __name__ == "__main__":
    main()
