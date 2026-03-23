from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from rassberry_assistant.voicepack import VoicePack  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import WAV voice pack into the project")
    parser.add_argument("source", help="Source directory with WAV files")
    parser.add_argument(
        "--destination",
        default=str(PROJECT_ROOT / "assets" / "voice_pack"),
        help="Destination directory inside the project",
    )
    return parser.parse_args()


def copy_tree(source: Path, destination: Path) -> None:
    for path in source.rglob("*"):
        relative = path.relative_to(source)
        target = destination / relative
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)


def main() -> None:
    args = parse_args()
    source = Path(args.source).resolve()
    destination = Path(args.destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)

    copy_tree(source, destination)

    manifest_path = destination / "manifest.json"
    VoicePack(destination).export_manifest(manifest_path)
    print(f"Imported voice pack to {destination}")
    print(f"Manifest written to {manifest_path}")


if __name__ == "__main__":
    main()
