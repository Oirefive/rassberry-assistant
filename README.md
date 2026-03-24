# Rassberry Assistant

Локальный голосовой ассистент для Raspberry Pi: wake word, локальные команды, web dashboard, STT/TTS, Wi‑Fi микрофон и fallback в OpenRouter.

Репозиторий приведён в безопасный вид для публичного GitHub:
- без реальных токенов и паролей;
- без пользовательских `wav`, видео и личных путей;
- без runtime-мусора, логов, сертификатов и скачанных моделей.

## Возможности

- wake word и короткая голосовая сессия;
- локальные команды из `config/commands.yaml`;
- fallback в LLM через OpenRouter;
- локальный TTS через Piper или RHVoice;
- dashboard по HTTP/HTTPS;
- Windows bridge для запуска приложений;
- сетевой микрофон из браузера по Wi‑Fi.

## Что не хранится в репозитории

В публичную репу специально не входят:
- `assets/voice_pack/` с пользовательской озвучкой;
- тяжёлые dashboard-медиафайлы;
- `models/` и `tts/piper/` со скачанными моделями;
- `.env`, `runtime/`, `logs/`, `.tools/`, сертификаты и временные архивы.

Это добро создаётся или докидывается локально.

## Структура

- [src/rassberry_assistant](src/rassberry_assistant) — основной код ассистента
- [config/assistant.yaml](config/assistant.yaml) — главный конфиг
- [config/commands.yaml](config/commands.yaml) — локальные команды
- [config/windows_agent.json](config/windows_agent.json) — пример конфига Windows bridge
- [scripts/install_pi.sh](scripts/install_pi.sh) — установка на Raspberry Pi
- [scripts/deploy_to_pi.py](scripts/deploy_to_pi.py) — деплой по SSH
- [scripts/download_tts_models.py](scripts/download_tts_models.py) — загрузка каталога Piper
- [scripts/windows_agent.py](scripts/windows_agent.py) — локальный Windows HTTP bridge
- [systemd/rassberry-assistant.service](systemd/rassberry-assistant.service) — unit для systemd

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
- [assets/voice_pack/README.md](assets/voice_pack/README.md)
- [assets/dashboard/README.md](assets/dashboard/README.md)

### 5. Проверка

```powershell
python -m unittest discover -s tests
python -m compileall src tests
```

## Микрофон

Менять источник микрофона можно двумя путями:
- через `Система` в web dashboard;
- руками в `audio.input_device` в [config/assistant.yaml](config/assistant.yaml).

Что выбирать и зачем:

| Вариант | Где менять | Когда использовать | Плюсы | Минусы |
| --- | --- | --- | --- | --- |
| USB-микрофон | `Система` или `audio.input_device` | Основной вариант для ассистента | Лучшая скорость триггера, меньше ложных срабатываний, нормальная речь | Нужно отдельное железо |
| Wi‑Fi микрофон из браузера | `Система` -> сетевой микрофон | Телефон или ноутбук как временный микрофон | Универсально, работает и с Android, и с Windows | Выше задержка, зависит от сети |
| Bluetooth микрофон в колонке | `Система` -> Bluetooth source | Только если ничего лучше нет | Удобно без проводов | HFP/HSP режет качество речи, триггер срабатывает хуже |

Практический порядок по качеству:
1. USB-микрофон.
2. Wi‑Fi микрофон.
3. Bluetooth hands-free в колонке.

Если ассистент слышит тебя плохо, в первую очередь проверь:
- правильный ли выбран `input_device`;
- не слишком ли шумный сам микрофон;
- не сидишь ли ты на Bluetooth, который любит калечить звук сильнее, чем обычно калечат обещания в рекламе.

## Как ускорить триггер

Основные настройки скорости сидят в [config/assistant.yaml](config/assistant.yaml):
- `audio.chunk_ms` — размер аудиочанка;
- `wake.preview_refresh_seconds` — как часто обновлять короткое live-распознавание;
- `wake.probe_streak_chunks` и `wake.probe_interval_seconds` — как быстро делать повторную проверку wake word;
- `listen.preroll_ms` и `listen.start_speech_chunks` — насколько быстро захватывать фразу после активации.

Быстрее не всегда значит лучше:
- меньший `chunk_ms` ускоряет отклик, но повышает нагрузку;
- слишком маленькие пороги увеличивают ложные срабатывания;
- Bluetooth почти всегда ухудшает скорость и качество wake word.

Если нужна реакция “как у колонки”, сначала нормализуй микрофон, а уже потом крути магические числа. Иначе получишь очень бодрого идиота.

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
- токен в [config/windows_agent.json](config/windows_agent.json) надо заменить;
- пути можно задавать через `%APPDATA%`, `%ProgramFiles%`, `%ProgramFiles(x86)%`, `%USERPROFILE%`;
- установка есть в [scripts/install_windows_agent.ps1](scripts/install_windows_agent.ps1).

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
