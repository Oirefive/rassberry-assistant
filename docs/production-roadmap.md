# Production Roadmap

Ниже два трека: быстрый рефактор поверх текущего проекта и нормальная production-пересборка.

## Быстрый рефактор без сноса

Цель: не ломать деплой и не менять стек целиком, а убрать самые заметные проблемы UX и задержек.

### Что оставить

- `systemd` сервис
- локальный `Ollama`
- текущий роутер команд
- dashboard
- локальное воспроизведение через PipeWire / ALSA

### Что изменить сразу

1. Убрать осмысленные `wav` из критического пути.
   Вместо голосовых `wake_ack` и `execute` использовать:
   - короткий beep при wake
   - короткий beep при ошибке
   - тишину перед локальной командой, если ответ и так будет озвучен

2. Перестать решать конец фразы по одному `RMS`.
   Нужен отдельный VAD-слой.
   В быстром треке допускается:
   - оставить текущий STT
   - добавить отдельное состояние `speech_detected`
   - показывать на dashboard, что речь еще идет

3. Добавить partial transcript в dashboard.
   Экран должен показывать не только итоговый текст, но и живую строку распознавания:
   - `partial_transcript`
   - индикатор уровня микрофона
   - индикатор `speech/no speech`
   - таймер до отправки фразы в распознавание

4. Разделить wake и командный режим в логике.
   После `Джарвис`:
   - короткий earcon
   - явное состояние `recording`
   - затем `transcribing`
   - затем `routing`
   - затем `thinking`, только если локальная команда не найдена

5. Ужать участие LLM.
   `LLM` должна вызываться только если:
   - нет локального совпадения
   - не найден regex/phrase match
   - это реально вопрос, а не команда устройству

### Что получится

- ассистент перестанет говорить бессмысленные pre-ack реплики
- на маленьком экране станет видно, слышит ли он речь прямо сейчас
- станет понятно, где он тупит: `wake`, `recording`, `transcribing` или `thinking`
- можно будет донастроить задержки и пороги по телеметрии, а не по гаданию

## Нормальная production-пересборка

Цель: переделать проект из demo-конвейера в стабильный голосовой рантайм.

### Новый стек

- Wake word: `openWakeWord`
- VAD: `Silero VAD`
- STT: `whisper.cpp`
- Router: локальный intent / command router
- LLM fallback: `Ollama`
- TTS: отдельный TTS worker
- Dashboard: отдельный web state API

### Почему именно так

- `openWakeWord` лучше подходит для постоянного wake-listening и умеет работать вместе с VAD
- `Silero VAD` должен решать, когда пользователь начал и закончил фразу
- `whisper.cpp` заметно лучше подходит для офлайн-русского распознавания, чем маленькая `Vosk` модель
- `Ollama` надо держать вне критического пути локальных команд
- `TTS` должен быть отдельным воркером, чтобы озвучка не мешала главному циклу ассистента

### Новая схема процесса

1. `audio-capture`
2. `wake-detector`
3. `vad-segmenter`
4. `stt-worker`
5. `router`
6. `command-executor`
7. `llm-fallback`
8. `tts-worker`
9. `dashboard-state-publisher`

Все модули общаются через короткие события состояния, а не через длинный монолитный цикл.

### Production-состояния dashboard

- `idle`
- `wake`
- `recording`
- `transcribing`
- `routing`
- `executing`
- `thinking`
- `speaking`
- `error`

### Production-метрики

- latency от wake до начала записи
- latency от конца речи до финального transcript
- latency от transcript до router decision
- latency от fallback до первого байта TTS
- false wake rate
- false reject rate
- средняя длительность реплики пользователя

## TTS стратегия

### Быстрый трек

Оставить `Piper`, но использовать его только как временный локальный TTS.
На текущей Raspberry с Python `3.13` это наименее конфликтный вариант.

### Production трек

#### Вариант A: Silero TTS

Рекомендуемый путь для женского голоса, если делаем новый runtime на Python `3.11`.

Почему:

- официальный офлайн TTS стек
- заявлен как natural-sounding
- работает на CPU
- есть русские голоса

Ограничение:

- на текущем Python `3.13` на Raspberry пакет `torch` не ставится, поэтому для `Silero TTS` нужен отдельный runtime

Практический вариант:

- отдельный `tts`-venv на Python `3.11`
- TTS вызывается через локальный HTTP / UNIX socket worker

#### Вариант B: Chatterbox Multilingual ONNX

Хороший кандидат на более живую речь, если выделить отдельный более тяжелый TTS-процесс.

Плюсы:

- MIT license
- есть русский язык
- ONNX inference
- голос звучит живее, чем типичный классический TTS

Минусы:

- тяжелее текущего Piper
- для Raspberry как единственного вычислителя это уже пограничная затея

### Что я бы выбрал

- если все остается строго на одной Raspberry: сначала довести UX и STT, а TTS временно оставить Piper
- если делаем уже production-уровень: `Silero TTS` в отдельном Python `3.11` runtime
- если позже появится mini PC или N100: перевести TTS и LLM туда, а Raspberry оставить как аудио-терминал и экран

## Практический порядок работ

### Этап 1. Быстрый рефактор

1. Убрать говорящие `wav` из wake / execute
2. Добавить partial transcript и VAD-индикатор в dashboard
3. Развести фазы `recording`, `transcribing`, `routing`
4. Подправить endpointing по телеметрии
5. Свести вызовы `LLM` к минимуму

### Этап 2. Production rebuild

1. Новый runtime c pinned Python `3.11`
2. Вынести wake, VAD и STT в отдельные компоненты
3. Перейти на `whisper.cpp`
4. Вынести `TTS` в отдельный воркер
5. Поднять нормальные метрики и health checks
6. Обновить `systemd` и installer под новый runtime

## Источники

- openWakeWord: https://github.com/dscripka/openWakeWord
- whisper.cpp: https://github.com/ggml-org/whisper.cpp
- Silero VAD / TTS repo: https://github.com/snakers4/silero-models
- Silero TTS docs: https://pytorch.org/hub/snakers4_silero-models_tts/
- Chatterbox Multilingual ONNX: https://huggingface.co/onnx-community/chatterbox-multilingual-ONNX
- Ollama qwen2.5:0.5b: https://ollama.com/library/qwen2.5:0.5b
