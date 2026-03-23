#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/home/pi/rassberry-assistant"
APP_USER="pi"
INSTALL_SERVICE="1"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --app-dir)
      APP_DIR="$2"
      shift 2
      ;;
    --user)
      APP_USER="$2"
      shift 2
      ;;
    --skip-service)
      INSTALL_SERVICE="0"
      shift 1
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [[ ! -d "$APP_DIR" ]]; then
  echo "Project directory not found: $APP_DIR" >&2
  exit 1
fi

if [[ "$(id -u)" -eq 0 ]]; then
  SUDO=""
else
  SUDO="sudo"
fi

APP_UID="$(id -u "$APP_USER")"

if [[ -f "$APP_DIR/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$APP_DIR/.env"
  set +a
fi

$SUDO apt-get update
$SUDO apt-get install -y python3-venv python3-pip curl unzip alsa-utils

if [[ ! -f "$APP_DIR/.env" ]]; then
  cp "$APP_DIR/.env.example" "$APP_DIR/.env"
fi

if [[ -z "${OPENROUTER_API_KEY:-}" ]]; then
  echo "Warning: OPENROUTER_API_KEY is empty in $APP_DIR/.env. Chat fallback will stay disabled." >&2
fi

python3 -m venv "$APP_DIR/.venv"
# shellcheck disable=SC1091
source "$APP_DIR/.venv/bin/activate"
python -m pip install --upgrade pip
python -m pip install -r "$APP_DIR/requirements.txt"
python -m pip install -e "$APP_DIR"

mkdir -p "$APP_DIR/models"
if [[ ! -d "$APP_DIR/models/vosk-model-small-ru-0.22" ]]; then
  MODEL_ARCHIVE="$APP_DIR/models/vosk-model-small-ru-0.22.zip"
  if [[ ! -f "$MODEL_ARCHIVE" ]]; then
    curl -L "https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip" -o "$MODEL_ARCHIVE"
  fi
  unzip -q -o "$MODEL_ARCHIVE" -d "$APP_DIR/models"
fi

mkdir -p "$APP_DIR/models/piper"
if [[ ! -f "$APP_DIR/models/piper/ru_RU-ruslan-medium.onnx" ]]; then
  curl -L "https://huggingface.co/rhasspy/piper-voices/resolve/main/ru/ru_RU/ruslan/medium/ru_RU-ruslan-medium.onnx?download=true" \
    -o "$APP_DIR/models/piper/ru_RU-ruslan-medium.onnx"
fi
if [[ ! -f "$APP_DIR/models/piper/ru_RU-ruslan-medium.onnx.json" ]]; then
  curl -L "https://huggingface.co/rhasspy/piper-voices/resolve/main/ru/ru_RU/ruslan/medium/ru_RU-ruslan-medium.onnx.json?download=true" \
    -o "$APP_DIR/models/piper/ru_RU-ruslan-medium.onnx.json"
fi

mkdir -p "$APP_DIR/logs" "$APP_DIR/runtime/tts"

if [[ "$(id -u)" -eq 0 ]]; then
  chown -R "$APP_USER:$APP_USER" "$APP_DIR"
fi

if [[ "$INSTALL_SERVICE" == "1" ]]; then
  SERVICE_FILE="/tmp/rassberry-assistant.service"
  sed \
    -e "s|__APP_DIR__|$APP_DIR|g" \
    -e "s|__APP_USER__|$APP_USER|g" \
    -e "s|__APP_UID__|$APP_UID|g" \
    "$APP_DIR/systemd/rassberry-assistant.service" > "$SERVICE_FILE"

  $SUDO cp "$SERVICE_FILE" /etc/systemd/system/rassberry-assistant.service
  $SUDO systemctl daemon-reload
  $SUDO systemctl enable rassberry-assistant.service
  $SUDO systemctl restart rassberry-assistant.service
fi

echo "Installation completed."
