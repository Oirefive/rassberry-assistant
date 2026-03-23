# Rassberry Assistant

Локальный голосовой ассистент для Raspberry Pi с wake word, локальными командами, web dashboard, STT/TTS и fallback через OpenRouter.

Репозиторий приведён в безопасный вид для публичного GitHub:
- без паролей и токенов;
- без пользовательских `wav`, видео и личных путей;
- без runtime-мусора, логов, временных скриптов и скачанных моделей.

## Возможности

- wake word и короткая голосовая сессия;
- локальные команды из `config/commands.yaml`;
- fallback в LLM через OpenRouter;
- локальный TTS через Piper или RHVoice;
- dashboard по HTTP/HTTPS;
- Windows bridge для запуска приложений;
- сетевой микрофон из браузера по Wi-Fi.

## Что не хранится в репозитории

В публичную репу специально не входят:
- `assets/voice_pack/` с пользовательской озвучкой;
- тяжёлые dashboard-медиафайлы;
- `models/` и `tts/piper/` со скачанными моделями;
- `.env`, `runtime/`, `logs/`, `.tools/`, сертификаты и временные архивы.

Это добро создаётся или докидывается локально.

## Структура

- [src/rassberry_assistant](C:\Users\MementoMori\Desktop\rassberry\src\rassberry_assistant) — основной код ассистента
- [config/assistant.yaml](C:\Users\MementoMori\Desktop\rassberry\config\assistant.yaml) — главный конфиг
- [config/commands.yaml](C:\Users\MementoMori\Desktop\rassberry\config\commands.yaml) — локальные команды
- [config/windows_agent.json](C:\Users\MementoMori\Desktop\rassberry\config\windows_agent.json) — пример конфига Windows bridge
- [scripts/install_pi.sh](C:\Users\MementoMori\Desktop\rassberry\scripts\install_pi.sh) — установка на Raspberry Pi
- [scripts/deploy_to_pi.py](C:\Users\MementoMori\Desktop\rassberry\scripts\deploy_to_pi.py) — деплой по SSH
- [scripts/download_tts_models.py](C:\Users\MementoMori\Desktop\rassberry\scripts\download_tts_models.py) — загрузка каталога Piper
- [scripts/windows_agent.py](C:\Users\MementoMori\Desktop\rassberry\scripts\windows_agent.py) — локальный Windows HTTP bridge
- [systemd/rassberry-assistant.service](C:\Users\MementoMori\Desktop\rassberry\systemd\rassberry-assistant.service) — unit для systemd

## Быстрый старт

### 1. Установка локально

```powershell
git clone https://github.com/<your-github>/rassberry-assistant.git
cd rassberry-assistant
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -e .
```

### 2. Настройка `.env`

```powershell
Copy-Item .env.example .env
```

Заполни в `.env`:
- `OPENROUTER_API_KEY`
- `WINDOWS_AGENT_TOKEN`
- `HOME_ASSISTANT_TOKEN`

Нормальный токен для Windows bridge:

```powershell
python -c "import secrets; print(secrets.token_hex(24))"
```

### 3. Загрузка TTS-моделей

```powershell
python scripts/download_tts_models.py
```

### 4. Пользовательские ассеты

Если нужны свои `wav` и dashboard-медиа, добавь локально:
- `assets/voice_pack/wake_ack.wav`
- `assets/dashboard/idle.mp4`
- `assets/dashboard/active.mp4`
- `assets/dashboard/logo.png`

Подсказки лежат в:
- [assets/voice_pack/README.md](C:\Users\MementoMori\Desktop\rassberry\assets\voice_pack\README.md)
- [assets/dashboard/README.md](C:\Users\MementoMori\Desktop\rassberry\assets\dashboard\README.md)

### 5. Проверка

```powershell
python -m unittest discover -s tests
python -m compileall src tests
```

## Установка на Raspberry Pi

```bash
cd /home/pi
git clone https://github.com/<your-github>/rassberry-assistant.git
cd rassberry-assistant
cp .env.example .env
nano .env
bash scripts/install_pi.sh --app-dir /home/pi/rassberry-assistant --user pi
```

После установки:

```bash
sudo systemctl status rassberry-assistant
sudo journalctl -u rassberry-assistant -f
```

Dashboard по умолчанию:
- `http://<raspberry-ip>:8765`
- `https://<raspberry-ip>:9443`

## Windows bridge

Windows agent запускает белый список приложений по HTTP.

Особенности:
- токен в [config/windows_agent.json](C:\Users\MementoMori\Desktop\rassberry\config\windows_agent.json) надо заменить;
- пути можно задавать через `%APPDATA%`, `%ProgramFiles%`, `%ProgramFiles(x86)%`, `%USERPROFILE%`;
- установка есть в [scripts/install_windows_agent.ps1](C:\Users\MementoMori\Desktop\rassberry\scripts\install_windows_agent.ps1).

Запуск:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/install_windows_agent.ps1
```

## Публичная гигиена

- не коммить `.env`;
- не коммить реальные токены и пароли;
- не коммить `runtime/`, `logs/`, `models/`, `.tools/`;
- не коммить личные `wav`, видео и приватные медиа;
- перед пушем прогонять `python -m unittest discover -s tests`.

## Источники

- [Piper](https://github.com/rhasspy/piper)
- [Vosk](https://alphacephei.com/vosk/)
- [OpenRouter](https://openrouter.ai/)
