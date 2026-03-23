const STATE_POLL_MS = 250;
const SYSTEM_POLL_MS = 3000;
const TARGET_RATE = 16000;
const GITHUB_AVATAR_URL = "https://github.com/Oirefive.png?size=160";
const activePhases = new Set([
  "listening",
  "recording",
  "transcribing",
  "processing",
  "routing",
  "executing",
  "thinking",
  "speaking",
  "followup",
]);

const nodes = {
  navItems: Array.from(document.querySelectorAll("[data-view-target]")),
  views: Array.from(document.querySelectorAll("[data-view]")),
  assistantName: document.getElementById("assistantName"),
  phasePill: document.getElementById("phasePill"),
  phaseMessage: document.getElementById("phaseMessage"),
  statusText: document.getElementById("statusText"),
  statusSubtext: document.getElementById("statusSubtext"),
  liveTranscriptLine: document.getElementById("liveTranscriptLine"),
  transcriptText: document.getElementById("transcriptText"),
  partialTranscriptText: document.getElementById("partialTranscriptText"),
  replyText: document.getElementById("replyText"),
  commandId: document.getElementById("commandId"),
  successValue: document.getElementById("successValue"),
  updatedAt: document.getElementById("updatedAt"),
  inputLevelValue: document.getElementById("inputLevelValue"),
  speechStateValue: document.getElementById("speechStateValue"),
  silenceValue: document.getElementById("silenceValue"),
  cpuValue: document.getElementById("cpuValue"),
  cpuFill: document.getElementById("cpuFill"),
  memoryValue: document.getElementById("memoryValue"),
  memoryFill: document.getElementById("memoryFill"),
  memoryFootprint: document.getElementById("memoryFootprint"),
  levelFill: document.getElementById("levelFill"),
  llmModelBadge: document.getElementById("llmModelBadge"),
  chatMessages: document.getElementById("chatMessages"),
  chatForm: document.getElementById("chatForm"),
  chatInput: document.getElementById("chatInput"),
  chatSubmit: document.getElementById("chatSubmit"),
  formModeLabel: document.getElementById("formModeLabel"),
  commandIdInput: document.getElementById("commandIdInput"),
  phrasesInput: document.getElementById("phrasesInput"),
  actionTypeSelect: document.getElementById("actionTypeSelect"),
  actionValueInput: document.getElementById("actionValueInput"),
  httpFields: document.getElementById("httpFields"),
  actionMethodSelect: document.getElementById("actionMethodSelect"),
  headersInput: document.getElementById("headersInput"),
  jsonInput: document.getElementById("jsonInput"),
  audioModeSelect: document.getElementById("audioModeSelect"),
  ttsFields: document.getElementById("ttsFields"),
  ttsTextInput: document.getElementById("ttsTextInput"),
  wavFields: document.getElementById("wavFields"),
  audioFileSelect: document.getElementById("audioFileSelect"),
  audioFileInput: document.getElementById("audioFileInput"),
  audioFileHint: document.getElementById("audioFileHint"),
  disabledInput: document.getElementById("disabledInput"),
  resetCommandBtn: document.getElementById("resetCommandBtn"),
  saveCommandBtn: document.getElementById("saveCommandBtn"),
  commandSearch: document.getElementById("commandSearch"),
  commandList: document.getElementById("commandList"),
  systemInputDevice: document.getElementById("systemInputDevice"),
  systemOutputDevice: document.getElementById("systemOutputDevice"),
  systemInputSelect: document.getElementById("systemInputSelect"),
  systemOutputSelect: document.getElementById("systemOutputSelect"),
  systemTriggerInput: document.getElementById("systemTriggerInput"),
  systemTtsEngineSelect: document.getElementById("systemTtsEngineSelect"),
  systemTtsEngineBadge: document.getElementById("systemTtsEngineBadge"),
  systemTtsVoiceInput: document.getElementById("systemTtsVoiceInput"),
  systemTtsVoiceGroup: document.getElementById("systemTtsVoiceGroup"),
  systemTtsRateInput: document.getElementById("systemTtsRateInput"),
  systemTtsPitchInput: document.getElementById("systemTtsPitchInput"),
  systemTtsVolumeInput: document.getElementById("systemTtsVolumeInput"),
  systemTtsModelSelect: document.getElementById("systemTtsModelSelect"),
  systemTtsModelGroup: document.getElementById("systemTtsModelGroup"),
  systemTtsTestInput: document.getElementById("systemTtsTestInput"),
  systemTtsUploadInput: document.getElementById("systemTtsUploadInput"),
  refreshAudioDevicesBtn: document.getElementById("refreshAudioDevicesBtn"),
  saveAudioDevicesBtn: document.getElementById("saveAudioDevicesBtn"),
  saveTriggerBtn: document.getElementById("saveTriggerBtn"),
  saveTtsBtn: document.getElementById("saveTtsBtn"),
  testTtsBtn: document.getElementById("testTtsBtn"),
  uploadTtsBtn: document.getElementById("uploadTtsBtn"),
  systemAudioHint: document.getElementById("systemAudioHint"),
  systemTriggerHint: document.getElementById("systemTriggerHint"),
  systemTtsHint: document.getElementById("systemTtsHint"),
  systemTtsTestHint: document.getElementById("systemTtsTestHint"),
  systemTtsUploadHint: document.getElementById("systemTtsUploadHint"),
  networkMicPanel: document.getElementById("networkMicPanel"),
  systemNetworkMicHost: document.getElementById("systemNetworkMicHost"),
  systemNetworkMicUrl: document.getElementById("systemNetworkMicUrl"),
  systemNetworkMicState: document.getElementById("systemNetworkMicState"),
  systemNetworkMicClient: document.getElementById("systemNetworkMicClient"),
  browserMicState: document.getElementById("browserMicState"),
  browserMicLevelFill: document.getElementById("browserMicLevelFill"),
  browserMicLevelValue: document.getElementById("browserMicLevelValue"),
  copyNetworkMicUrlBtn: document.getElementById("copyNetworkMicUrlBtn"),
  openNetworkMicUrlBtn: document.getElementById("openNetworkMicUrlBtn"),
  startBrowserMicBtn: document.getElementById("startBrowserMicBtn"),
  stopBrowserMicBtn: document.getElementById("stopBrowserMicBtn"),
  systemModel: document.getElementById("systemModel"),
  systemCpuText: document.getElementById("systemCpuText"),
  systemCpuFill: document.getElementById("systemCpuFill"),
  systemRamText: document.getElementById("systemRamText"),
  systemRamFill: document.getElementById("systemRamFill"),
  systemLlmStatus: document.getElementById("systemLlmStatus"),
  networkLabel: document.getElementById("networkLabel"),
};

const appState = {
  commands: [],
  audioFiles: [],
  commandMap: new Map(),
  lastStateHash: "",
  systemInfo: {},
  formMode: "new",
  editingId: null,
  editingEditable: true,
  chatMessages: [],
  audioDraft: { dirty: false, input: "", output: "" },
  triggerDraft: { dirty: false, value: "" },
  ttsDraft: { dirty: false, engine: "", voice: "", rate: "", pitch: "", volume: "", model: "" },
  runtimeMetrics: { cpuPercent: null, memoryPercent: null, memoryUsedMb: null, memoryTotalMb: null },
  telemetry: {
    input: { current: 0, target: 0 },
    cpu: { current: 0, target: 0 },
    memory: { current: 0, target: 0 },
    browserMic: { current: 0, target: 0 },
  },
  browserMic: {
    running: false,
    audioContext: null,
    mediaStream: null,
    sourceNode: null,
    processorNode: null,
    uploadQueue: [],
    uploading: false,
  },
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function textOrFallback(value, fallback) {
  const text = String(value ?? "").trim();
  return text || fallback;
}

function clampPercent(value) {
  return Math.max(0, Math.min(100, Number(value || 0)));
}

function resolveDeviceLabel(devices, deviceId) {
  const wanted = String(deviceId || "").trim();
  if (!wanted) {
    return "";
  }
  const match = Array.isArray(devices)
    ? devices.find((device) => String(device.id || "").trim() === wanted)
    : null;
  return match ? textOrFallback(match.label, wanted) : wanted;
}

function populateDeviceSelect(node, devices, selectedValue, emptyLabel) {
  if (!node) {
    return;
  }
  const options = [];
  if (!Array.isArray(devices) || !devices.length) {
    options.push(`<option value="">${escapeHtml(emptyLabel)}</option>`);
  } else {
    devices.forEach((device) => {
      const value = String(device.id || "").trim();
      const selected = value === String(selectedValue || "").trim() ? " selected" : "";
      const backend = String(device.backend || "").trim().toUpperCase();
      const availability = device.available === false ? " unavailable" : "";
      const suffix = backend ? ` [${backend}]` : "";
      options.push(
        `<option value="${escapeHtml(value)}"${selected}>${escapeHtml(textOrFallback(device.label, value) + suffix + availability)}</option>`,
      );
    });
  }
  node.innerHTML = options.join("");
  if (selectedValue) {
    node.value = selectedValue;
  }
}

function populateTtsModelSelect(models, selectedValue) {
  if (!nodes.systemTtsModelSelect) {
    return;
  }
  const options = ['<option value="">Выберите Piper модель</option>'];
  if (Array.isArray(models)) {
    models.forEach((model) => {
      const value = textOrFallback(model.path, "");
      if (!value) {
        return;
      }
      const selected = value === String(selectedValue || "").trim() ? " selected" : "";
      const currentSuffix = model.current ? " [active]" : "";
      const details = model.details ? ` (${model.details})` : "";
      options.push(
        `<option value="${escapeHtml(value)}"${selected}>${escapeHtml(textOrFallback(model.label, value) + details + currentSuffix)}</option>`,
      );
    });
  }
  nodes.systemTtsModelSelect.innerHTML = options.join("");
  if (selectedValue) {
    nodes.systemTtsModelSelect.value = selectedValue;
  }
}

function populateRhvoiceVoiceSelect(voices, selectedValue) {
  if (!nodes.systemTtsVoiceInput) {
    return;
  }
  const options = [];
  const values = Array.isArray(voices) ? [...voices] : [];
  const selected = textOrFallback(selectedValue, "");
  if (selected && !values.includes(selected)) {
    values.unshift(selected);
  }
  if (!values.length) {
    options.push('<option value="">Голоса не найдены</option>');
  } else {
    values.forEach((voice) => {
      const isSelected = voice === selected ? " selected" : "";
      options.push(`<option value="${escapeHtml(voice)}"${isSelected}>${escapeHtml(voice)}</option>`);
    });
  }
  nodes.systemTtsVoiceInput.innerHTML = options.join("");
  if (selected) {
    nodes.systemTtsVoiceInput.value = selected;
  }
}

function formatTime(value) {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) {
    return String(value);
  }
  return date.toLocaleTimeString("ru-RU");
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    cache: "no-store",
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });
  const raw = await response.text();
  let body = null;
  if (raw) {
    try {
      body = JSON.parse(raw);
    } catch {
      body = raw;
    }
  }
  if (!response.ok) {
    const message =
      (body && typeof body === "object" && (body.message || body.error)) ||
      (typeof body === "string" && body.trim()) ||
      `HTTP ${response.status}`;
    throw new Error(message);
  }
  return body;
}

function normalizedHashView() {
  const raw = String(window.location.hash || "").replace(/^#/, "").trim().toLowerCase();
  return ["chat", "commands", "system"].includes(raw) ? raw : "chat";
}

function setView(viewName, { updateHash = true } = {}) {
  nodes.navItems.forEach((node) => {
    node.classList.toggle("is-active", node.dataset.viewTarget === viewName);
  });
  nodes.views.forEach((node) => {
    node.classList.toggle("is-active", node.dataset.view === viewName);
  });
  if (updateHash && normalizedHashView() !== viewName) {
    window.history.replaceState(null, "", `#${viewName}`);
  }
}

function updateTtsFields() {
  const engine = textOrFallback(nodes.systemTtsEngineSelect?.value, "rhvoice");
  const usePiper = engine === "piper";
  nodes.systemTtsEngineBadge.textContent = usePiper ? "piper" : "rhvoice";
  nodes.systemTtsVoiceGroup.classList.toggle("is-hidden", usePiper);
  nodes.systemTtsModelGroup.classList.toggle("is-hidden", !usePiper);
  nodes.systemTtsVoiceInput.disabled = usePiper;
  nodes.systemTtsModelSelect.disabled = !usePiper;
}

function selectedInputDevice() {
  if (appState.audioDraft.dirty && textOrFallback(appState.audioDraft.input, "")) {
    return textOrFallback(appState.audioDraft.input, "");
  }
  return textOrFallback(appState.systemInfo.input_device, "");
}

function currentAssistantInitial() {
  return textOrFallback(appState.systemInfo.assistant_name, "Ассистент").trim().charAt(0).toUpperCase() || "A";
}

function updateBrowserMicUi() {
  const wantsNetworkMic = selectedInputDevice() === "network-mic";
  const secureUrl = textOrFallback(appState.systemInfo.network_mic_url, "");
  const remoteConnected = Boolean(appState.systemInfo.network_mic_connected);
  const secureContext = window.isSecureContext;
  const browserMicRunning = appState.browserMic.running;

  nodes.startBrowserMicBtn.disabled = !wantsNetworkMic || !secureContext || browserMicRunning;
  nodes.stopBrowserMicBtn.disabled = !browserMicRunning;
  nodes.copyNetworkMicUrlBtn.disabled = !secureUrl;
  nodes.openNetworkMicUrlBtn.disabled = !secureUrl;

  if (browserMicRunning) {
    nodes.browserMicState.textContent = "streaming";
  } else if (remoteConnected) {
    nodes.browserMicState.textContent = "remote";
  } else if (wantsNetworkMic) {
    nodes.browserMicState.textContent = secureContext ? "ready" : "secure";
  } else {
    nodes.browserMicState.textContent = "inactive";
  }
}

function applySystemInfo(systemInfo) {
  appState.systemInfo = systemInfo || {};
  const inputDevices = Array.isArray(systemInfo.audio_inputs) ? systemInfo.audio_inputs : [];
  const outputDevices = Array.isArray(systemInfo.audio_outputs) ? systemInfo.audio_outputs : [];
  const ttsModels = Array.isArray(systemInfo.tts_piper_models) ? systemInfo.tts_piper_models : [];
  const rhvoiceVoices = Array.isArray(systemInfo.tts_rhvoice_voices) ? systemInfo.tts_rhvoice_voices : [];
  const inputDeviceValue = textOrFallback(systemInfo.input_device, "");
  const outputDeviceValue = textOrFallback(systemInfo.output_device, "");
  const wakePhraseValue = textOrFallback(systemInfo.wake_phrase, "");
  const ttsEngineValue = textOrFallback(systemInfo.tts_engine, "rhvoice");
  const ttsVoiceValue = textOrFallback(systemInfo.tts_voice, rhvoiceVoices[0] || "");
  const ttsRateValue = String(systemInfo.tts_rate ?? "");
  const ttsPitchValue = String(systemInfo.tts_pitch ?? "");
  const ttsVolumeValue = String(systemInfo.tts_volume ?? "");
  const ttsModelValue = textOrFallback(systemInfo.tts_piper_model, "");

  const selectedInput = appState.audioDraft.dirty
    ? textOrFallback(appState.audioDraft.input, inputDeviceValue)
    : inputDeviceValue;
  const selectedOutput = appState.audioDraft.dirty
    ? textOrFallback(appState.audioDraft.output, outputDeviceValue)
    : outputDeviceValue;
  const selectedTrigger = appState.triggerDraft.dirty
    ? textOrFallback(appState.triggerDraft.value, wakePhraseValue)
    : wakePhraseValue;
  const selectedTtsEngine = appState.ttsDraft.dirty
    ? textOrFallback(appState.ttsDraft.engine, ttsEngineValue)
    : ttsEngineValue;
  const selectedTtsVoice = appState.ttsDraft.dirty
    ? textOrFallback(appState.ttsDraft.voice, ttsVoiceValue)
    : ttsVoiceValue;
  const selectedTtsRate = appState.ttsDraft.dirty
    ? String(appState.ttsDraft.rate !== "" ? appState.ttsDraft.rate : ttsRateValue)
    : ttsRateValue;
  const selectedTtsPitch = appState.ttsDraft.dirty
    ? String(appState.ttsDraft.pitch !== "" ? appState.ttsDraft.pitch : ttsPitchValue)
    : ttsPitchValue;
  const selectedTtsVolume = appState.ttsDraft.dirty
    ? String(appState.ttsDraft.volume !== "" ? appState.ttsDraft.volume : ttsVolumeValue)
    : ttsVolumeValue;
  const selectedTtsModel = appState.ttsDraft.dirty
    ? textOrFallback(appState.ttsDraft.model, ttsModelValue)
    : ttsModelValue;

  if (document.activeElement !== nodes.systemTriggerInput) {
    nodes.systemTriggerInput.value = selectedTrigger;
  }
  if (document.activeElement !== nodes.systemTtsRateInput) {
    nodes.systemTtsRateInput.value = selectedTtsRate;
  }
  if (document.activeElement !== nodes.systemTtsPitchInput) {
    nodes.systemTtsPitchInput.value = selectedTtsPitch;
  }
  if (document.activeElement !== nodes.systemTtsVolumeInput) {
    nodes.systemTtsVolumeInput.value = selectedTtsVolume;
  }
  nodes.systemTtsEngineSelect.value = selectedTtsEngine;

  populateDeviceSelect(nodes.systemInputSelect, inputDevices, selectedInput, "Микрофоны не найдены");
  populateDeviceSelect(nodes.systemOutputSelect, outputDevices, selectedOutput, "Выходы не найдены");
  populateTtsModelSelect(ttsModels, selectedTtsModel);
  populateRhvoiceVoiceSelect(rhvoiceVoices, selectedTtsVoice);
  updateTtsFields();

  nodes.systemInputDevice.textContent = textOrFallback(resolveDeviceLabel(inputDevices, inputDeviceValue), "Не задано");
  nodes.systemOutputDevice.textContent = textOrFallback(resolveDeviceLabel(outputDevices, outputDeviceValue), "Не задано");
  nodes.systemModel.textContent = textOrFallback(systemInfo.llm_model, "LLM отключена");
  nodes.systemLlmStatus.textContent = systemInfo.llm_enabled ? "подключена" : "выключена";
  nodes.llmModelBadge.textContent = systemInfo.llm_enabled ? textOrFallback(systemInfo.llm_model, "OpenRouter") : "LLM off";

  nodes.systemTriggerHint.textContent =
    textOrFallback(systemInfo.assistant_error, "") ||
    textOrFallback(systemInfo.assistant_message, "") ||
    (selectedTrigger
      ? `Текущий триггер: ${selectedTrigger}. Ассистент ждёт именно эту фразу.`
      : "Задайте фразу активации, иначе он будет изображать мебель.");
  nodes.systemTriggerHint.classList.toggle("is-danger", Boolean(systemInfo.assistant_error));

  const networkMicHost = textOrFallback(systemInfo.network_mic_host, "");
  const networkMicUrl = textOrFallback(systemInfo.network_mic_url, "");
  const networkMicClient = textOrFallback(systemInfo.network_mic_client, "");
  const wantsNetworkMic = selectedInput === "network-mic";
  const remoteConnected = Boolean(systemInfo.network_mic_connected);
  nodes.systemNetworkMicHost.textContent = networkMicHost || "IP пока не определён";
  nodes.systemNetworkMicUrl.textContent = networkMicUrl || "URL пока не готов";
  nodes.systemNetworkMicClient.textContent = networkMicClient || "пока пусто";
  nodes.systemNetworkMicState.textContent =
    textOrFallback(systemInfo.audio_error, "") ||
    (appState.browserMic.running
      ? "Браузерный микрофон активен и стримит звук на Raspberry."
      : remoteConnected
        ? `Удалённый микрофон подключён${networkMicClient ? `: ${networkMicClient}` : ""}.`
        : !wantsNetworkMic
          ? 'Выберите вход "Телефон / браузер по Wi‑Fi", затем нажмите "Применить".'
          : !systemInfo.network_mic_secure
            ? "HTTPS ещё не поднялся, а браузеры без secure context ведут себя как капризные принцессы."
            : window.isSecureContext
              ? "На этой же странице можно включить микрофон хоть с Android, хоть с Windows."
              : `Откройте secure-версию страницы: ${networkMicUrl || "https URL пока не готов"}`);
  nodes.systemNetworkMicState.classList.toggle("is-danger", Boolean(systemInfo.audio_error));
  nodes.systemAudioHint.textContent =
    textOrFallback(systemInfo.audio_error, "") ||
    textOrFallback(systemInfo.audio_message, "") ||
    (wantsNetworkMic
      ? "Wi‑Fi микрофон можно запускать прямо из этого раздела."
      : "Выберите устройства и примените, если звуковой маршрут опять ушёл в астрал.");
  nodes.systemAudioHint.classList.toggle("is-danger", Boolean(systemInfo.audio_error));

  const ttsHint = textOrFallback(systemInfo.tts_error, "") || textOrFallback(systemInfo.tts_message, "");
  if (ttsHint) {
    nodes.systemTtsHint.textContent = ttsHint;
  } else if (selectedTtsEngine === "piper") {
    nodes.systemTtsHint.textContent = selectedTtsModel
      ? `Активная Piper модель: ${selectedTtsModel}.`
      : "Для Piper сначала выберите модель.";
  } else {
    nodes.systemTtsHint.textContent = `Активный RHVoice голос: ${selectedTtsVoice || "не задан"}. Применяется без рестарта сервиса.`;
  }
  nodes.systemTtsHint.classList.toggle("is-danger", Boolean(systemInfo.tts_error));
  nodes.systemTtsUploadHint.textContent = textOrFallback(systemInfo.tts_root, "Каталог TTS недоступен.");
  nodes.networkLabel.textContent = "В сети";
  updateBrowserMicUi();
}

function setTelemetryTarget(name, value) {
  if (!appState.telemetry[name]) {
    return;
  }
  appState.telemetry[name].target = clampPercent(value);
}

function setFillWidth(node, value) {
  if (!node) {
    return;
  }
  node.style.width = `${clampPercent(value)}%`;
}

function animateTelemetry() {
  const step = (metricName, node, textNode, formatter) => {
    const metric = appState.telemetry[metricName];
    const delta = metric.target - metric.current;
    metric.current = Math.abs(delta) < 0.15 ? metric.target : metric.current + delta * 0.18;
    setFillWidth(node, metric.current);
    if (textNode) {
      textNode.textContent = formatter(Math.round(metric.current));
    }
  };

  step("input", nodes.levelFill, nodes.inputLevelValue, (value) => `${value}%`);
  step("cpu", nodes.cpuFill, nodes.cpuValue, (value) => `${value}%`);
  step("memory", nodes.memoryFill, nodes.memoryValue, (value) => `${value}%`);
  step("browserMic", nodes.browserMicLevelFill, nodes.browserMicLevelValue, (value) => `${value}%`);

  setFillWidth(nodes.systemCpuFill, appState.telemetry.cpu.current);
  setFillWidth(nodes.systemRamFill, appState.telemetry.memory.current);
  nodes.systemCpuText.textContent =
    appState.runtimeMetrics.cpuPercent == null ? "-" : `${Math.round(appState.telemetry.cpu.current)}%`;
  nodes.systemRamText.textContent =
    appState.runtimeMetrics.memoryPercent == null
      ? "-"
      : `${Math.round(appState.telemetry.memory.current)}% (${Number(appState.runtimeMetrics.memoryUsedMb || 0)} / ${Number(appState.runtimeMetrics.memoryTotalMb || 0)} MB)`;

  window.requestAnimationFrame(animateTelemetry);
}

function applyRuntimeState(state) {
  const hash = JSON.stringify(state);
  if (hash === appState.lastStateHash) {
    return;
  }
  appState.lastStateHash = hash;

  document.body.dataset.phase = state.phase || "idle";
  document.title = textOrFallback(state.page_title, "Ассистент");

  nodes.assistantName.textContent = textOrFallback(state.assistant_name, "Ассистент");
  nodes.phasePill.textContent = textOrFallback(state.status_text, "ОЖИДАНИЕ").toUpperCase();
  nodes.phaseMessage.textContent = textOrFallback(state.message, "Жду слово активации.");
  nodes.statusText.textContent = textOrFallback(state.status_text, "Ожидание");
  nodes.statusSubtext.textContent = textOrFallback(state.message, "Жду слово активации.");

  const liveLine = textOrFallback(
    state.partial_transcript,
    activePhases.has(state.phase) ? state.transcript : "",
  );
  nodes.liveTranscriptLine.textContent = textOrFallback(liveLine, state.speech_active ? "Слушаю..." : "Пока тишина.");
  nodes.transcriptText.textContent = textOrFallback(state.transcript, "Пока пусто.");
  nodes.partialTranscriptText.textContent = textOrFallback(state.partial_transcript, "Пока тишина.");
  nodes.replyText.textContent = textOrFallback(state.reply_text, "Пока без ответа.");
  nodes.commandId.textContent = textOrFallback(state.command_id, "system");
  nodes.speechStateValue.textContent = state.speech_active ? "речь" : "тишина";
  nodes.silenceValue.textContent =
    state.speech_timeout_ms == null ? "-" : `${(Number(state.speech_timeout_ms) / 1000).toFixed(1)}s`;
  nodes.updatedAt.textContent = formatTime(state.updated_at);

  setTelemetryTarget("input", state.input_level);
  setTelemetryTarget("cpu", state.cpu_percent);
  setTelemetryTarget("memory", state.memory_percent);
  appState.runtimeMetrics.cpuPercent = state.cpu_percent;
  appState.runtimeMetrics.memoryPercent = state.memory_percent;
  appState.runtimeMetrics.memoryUsedMb = state.memory_used_mb;
  appState.runtimeMetrics.memoryTotalMb = state.memory_total_mb;
  nodes.memoryFootprint.textContent =
    state.memory_used_mb == null || state.memory_total_mb == null
      ? "-"
      : `${Number(state.memory_used_mb)} / ${Number(state.memory_total_mb)} MB`;

  if (state.success === true) {
    nodes.successValue.textContent = "ok";
  } else if (state.success === false) {
    nodes.successValue.textContent = "error";
  } else {
    nodes.successValue.textContent = "n/a";
  }
}

function renderChatMessages() {
  if (!appState.chatMessages.length) {
    nodes.chatMessages.innerHTML = `
      <div class="chat-empty">
        Здесь можно проверить нейросеть текстом и не ждать, пока микрофон снова устроит драму.
      </div>
    `;
    return;
  }

  nodes.chatMessages.innerHTML = appState.chatMessages
    .map((message) => {
      const isUser = message.role === "user";
      const avatar = isUser
        ? `<div class="chat-avatar"><img src="${GITHUB_AVATAR_URL}" alt="User avatar" /></div>`
        : `<div class="chat-avatar">${escapeHtml(currentAssistantInitial())}</div>`;
      return `
        <article class="chat-message ${isUser ? "is-user" : "is-assistant"}">
          ${avatar}
          <div class="chat-bubble">${escapeHtml(message.text)}</div>
        </article>
      `;
    })
    .join("");
  nodes.chatMessages.scrollTop = nodes.chatMessages.scrollHeight;
}

function pushChatMessage(role, text) {
  appState.chatMessages.push({ role, text: String(text || "").trim() });
  if (appState.chatMessages.length > 24) {
    appState.chatMessages = appState.chatMessages.slice(-24);
  }
  renderChatMessages();
}

function updateActionFields() {
  const actionType = nodes.actionTypeSelect.value;
  const isHttp = actionType === "http";
  const isSpeak = actionType === "speak";
  nodes.httpFields.classList.toggle("is-hidden", !isHttp);
  nodes.actionValueInput.disabled = isSpeak;
  nodes.actionValueInput.classList.toggle("is-disabled", isSpeak);

  if (isHttp) {
    nodes.actionValueInput.placeholder = "URL webhook или HTTP endpoint";
  } else if (isSpeak) {
    nodes.actionValueInput.placeholder = "Для режима только ответа действие не требуется";
  } else {
    nodes.actionValueInput.placeholder = "Shell-команда, путь к программе или скрипту";
  }
}

function updateAudioFields() {
  const audioMode = nodes.audioModeSelect.value;
  nodes.ttsFields.classList.toggle("is-hidden", audioMode !== "tts");
  nodes.wavFields.classList.toggle("is-hidden", audioMode !== "wav");
}

function populateAudioOptions(selectedPath = "") {
  const options = ['<option value="">Выберите WAV из хранилища</option>'];
  appState.audioFiles.forEach((file) => {
    const selected = file.path === selectedPath ? " selected" : "";
    options.push(`<option value="${escapeHtml(file.path)}"${selected}>${escapeHtml(file.name)}</option>`);
  });
  nodes.audioFileSelect.innerHTML = options.join("");
}

function commandSummary(command) {
  const phrases = Array.isArray(command.phrases) ? command.phrases.join(", ") : "";
  if (command.action_type === "http") {
    return `${command.action_method || "POST"} ${command.action_value || ""}`.trim();
  }
  if (command.action_type === "shell") {
    return textOrFallback(command.action_value, "shell");
  }
  return phrases ? "Только озвучка по триггеру" : "Команда без действия";
}

function commandAudioSummary(command) {
  if (command.audio_mode === "wav") {
    return textOrFallback(command.audio_file, "WAV");
  }
  if (command.audio_mode === "tts") {
    return textOrFallback(command.tts_text, "TTS");
  }
  return "без аудио";
}

function renderCommandList() {
  const query = nodes.commandSearch.value.trim().toLowerCase();
  const filtered = appState.commands.filter((command) => {
    if (!query) {
      return true;
    }
    const haystack = [
      command.id,
      ...(command.phrases || []),
      command.action_value,
      command.tts_text,
      command.audio_file,
    ]
      .join(" ")
      .toLowerCase();
    return haystack.includes(query);
  });

  if (!filtered.length) {
    nodes.commandList.innerHTML = `
      <div class="command-empty">
        Здесь пусто. Добавьте первую команду и перестаньте мучить YAML руками.
      </div>
    `;
    return;
  }

  nodes.commandList.innerHTML = filtered
    .map((command) => {
      const phrases = Array.isArray(command.phrases) ? command.phrases.join(", ") : "";
      const editableClass = command.editable ? "is-editable" : "is-readonly";
      return `
        <article class="command-card ${editableClass}" data-command-id="${escapeHtml(command.id)}">
          <div class="command-card-head">
            <div>
              <div class="command-card-title">${escapeHtml(command.id)}</div>
              <div class="command-card-meta">
                <span class="badge ${command.source === "core" ? "is-core" : "is-custom"}">${escapeHtml(command.source)}</span>
                <span class="badge ${command.disabled ? "is-danger" : "is-ok"}">${command.disabled ? "disabled" : "active"}</span>
              </div>
            </div>
            <div class="command-card-actions">
              <button class="ghost-button small-button" type="button" data-action="edit" data-command-id="${escapeHtml(command.id)}">
                ${command.editable ? "Изменить" : "Шаблон"}
              </button>
              ${
                command.editable
                  ? `<button class="ghost-button small-button danger-button" type="button" data-action="delete" data-command-id="${escapeHtml(command.id)}">Удалить</button>`
                  : ""
              }
            </div>
          </div>
          <div class="command-card-body">
            <div class="command-row"><span class="command-row-label">Фразы</span><span class="command-row-value">${escapeHtml(phrases || "—")}</span></div>
            <div class="command-row"><span class="command-row-label">Действие</span><span class="command-row-value">${escapeHtml(commandSummary(command))}</span></div>
            <div class="command-row"><span class="command-row-label">Ответ</span><span class="command-row-value">${escapeHtml(commandAudioSummary(command))}</span></div>
          </div>
        </article>
      `;
    })
    .join("");
}

function resetCommandForm() {
  appState.formMode = "new";
  appState.editingId = null;
  appState.editingEditable = true;
  nodes.formModeLabel.textContent = "new";
  nodes.commandIdInput.value = "";
  nodes.phrasesInput.value = "";
  nodes.actionTypeSelect.value = "speak";
  nodes.actionValueInput.value = "";
  nodes.actionMethodSelect.value = "POST";
  nodes.headersInput.value = "";
  nodes.jsonInput.value = "";
  nodes.audioModeSelect.value = "tts";
  nodes.ttsTextInput.value = "";
  nodes.audioFileSelect.value = "";
  nodes.audioFileInput.value = "";
  nodes.audioFileHint.textContent = "Загружайте WAV. Файл будет сохранён прямо на Raspberry.";
  nodes.disabledInput.checked = false;
  nodes.saveCommandBtn.textContent = "Сохранить";
  updateActionFields();
  updateAudioFields();
}

function fillCommandForm(command) {
  const useAsTemplate = !command.editable;
  appState.formMode = useAsTemplate ? "template" : "edit";
  appState.editingId = useAsTemplate ? null : command.id;
  appState.editingEditable = Boolean(command.editable);

  nodes.formModeLabel.textContent = useAsTemplate ? "template" : "edit";
  nodes.commandIdInput.value = useAsTemplate ? `${command.id}-copy` : command.id;
  nodes.phrasesInput.value = (command.phrases || []).join("\n");
  nodes.actionTypeSelect.value = command.action_type || "speak";
  nodes.actionValueInput.value = command.action_value || "";
  nodes.actionMethodSelect.value = command.action_method || "POST";
  nodes.headersInput.value = command.headers_text || "";
  nodes.jsonInput.value = command.json_text || "";
  nodes.audioModeSelect.value = command.audio_mode || "tts";
  nodes.ttsTextInput.value = command.tts_text || "";
  populateAudioOptions(command.audio_file || "");
  nodes.disabledInput.checked = Boolean(command.disabled);
  nodes.audioFileInput.value = "";
  nodes.audioFileHint.textContent = useAsTemplate
    ? "Это системная команда. Вы редактируете её как шаблон для новой пользовательской."
    : "Редактируйте и сохраняйте. WAV остаётся на Raspberry.";
  nodes.saveCommandBtn.textContent = useAsTemplate ? "Сохранить копию" : "Сохранить";
  updateActionFields();
  updateAudioFields();
}

function collectCommandPayload(audioFilePath = "") {
  const actionType = nodes.actionTypeSelect.value;
  const audioMode = nodes.audioModeSelect.value;
  const phrases = nodes.phrasesInput.value
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);

  if (!phrases.length) {
    throw new Error("Нужен хотя бы один голосовой триггер.");
  }
  if ((actionType === "shell" || actionType === "http") && !nodes.actionValueInput.value.trim()) {
    throw new Error("Для выбранного действия нужно заполнить команду или URL.");
  }
  if (audioMode === "tts" && !nodes.ttsTextInput.value.trim()) {
    throw new Error("Для TTS нужен текст ответа.");
  }
  if (audioMode === "wav" && !audioFilePath) {
    throw new Error("Сначала выберите или загрузите WAV.");
  }

  return {
    id: nodes.commandIdInput.value.trim(),
    phrases: phrases.join("\n"),
    action_type: actionType,
    action_value: nodes.actionValueInput.value.trim(),
    action_method: nodes.actionMethodSelect.value,
    headers_text: nodes.headersInput.value.trim(),
    json_text: nodes.jsonInput.value.trim(),
    audio_mode: audioMode,
    tts_text: nodes.ttsTextInput.value.trim(),
    audio_file: audioFilePath,
    disabled: nodes.disabledInput.checked,
  };
}

function readFileAsBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result || "");
      const [, base64] = result.split(",", 2);
      resolve(base64 || "");
    };
    reader.onerror = () => reject(new Error("Не удалось прочитать файл."));
    reader.readAsDataURL(file);
  });
}

async function uploadPendingAudio() {
  const file = nodes.audioFileInput.files?.[0];
  if (!file) {
    return nodes.audioFileSelect.value;
  }
  if (!file.name.toLowerCase().endsWith(".wav")) {
    throw new Error("Поддерживается только WAV. MP3 и прочий зоопарк здесь не нужен.");
  }

  nodes.audioFileHint.textContent = "Загружаю WAV на Raspberry...";
  const contentBase64 = await readFileAsBase64(file);
  const commandIdHint =
    nodes.commandIdInput.value.trim() ||
    nodes.phrasesInput.value.split(/\r?\n/).find((item) => item.trim()) ||
    "custom-audio";

  const payload = await fetchJson("/api/audio/upload", {
    method: "POST",
    body: JSON.stringify({
      file_name: file.name,
      content_base64: contentBase64,
      command_id: commandIdHint,
    }),
  });

  appState.audioFiles = Array.isArray(payload.audio_files) ? payload.audio_files : appState.audioFiles;
  populateAudioOptions(payload.path || "");
  nodes.audioFileInput.value = "";
  nodes.audioFileHint.textContent = `Файл загружен: ${file.name}`;
  return payload.path || "";
}

async function loadCommands() {
  const payload = await fetchJson("/api/commands", { headers: {} });
  appState.commands = Array.isArray(payload.commands) ? payload.commands : [];
  appState.audioFiles = Array.isArray(payload.audio_files) ? payload.audio_files : [];
  appState.commandMap = new Map(appState.commands.map((command) => [command.id, command]));
  populateAudioOptions(nodes.audioFileSelect.value);
  renderCommandList();
}

async function saveCommand() {
  nodes.saveCommandBtn.disabled = true;
  nodes.saveCommandBtn.textContent = "Сохраняю...";
  try {
    const audioFilePath = await uploadPendingAudio();
    const payload = collectCommandPayload(audioFilePath);
    const savedCommand = await fetchJson("/api/commands", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    await loadCommands();
    const freshCommand = appState.commandMap.get(savedCommand.id) || savedCommand;
    fillCommandForm(freshCommand);
    nodes.audioFileHint.textContent = "Команда сохранена. Raspberry пережила ещё один YAML.";
  } finally {
    nodes.saveCommandBtn.disabled = false;
    nodes.saveCommandBtn.textContent = appState.formMode === "template" ? "Сохранить копию" : "Сохранить";
  }
}

async function deleteCommand(commandId) {
  const command = appState.commandMap.get(commandId);
  if (!command || !command.editable) {
    return;
  }
  if (!window.confirm(`Удалить команду "${commandId}"?`)) {
    return;
  }
  await fetchJson(`/api/commands/${encodeURIComponent(commandId)}`, { method: "DELETE", headers: {} });
  if (appState.editingId === commandId) {
    resetCommandForm();
  }
  await loadCommands();
}

async function refreshState() {
  try {
    const state = await fetchJson("/api/state", { headers: {} });
    applyRuntimeState(state);
    nodes.networkLabel.textContent = "В сети";
  } catch (error) {
    document.body.dataset.phase = "error";
    nodes.phasePill.textContent = "OFFLINE";
    nodes.phaseMessage.textContent = "Нет связи с локальным API.";
    nodes.statusText.textContent = "Связь потеряна";
    nodes.statusSubtext.textContent = String(error.message || error);
    nodes.networkLabel.textContent = "Оффлайн";
  }
}

async function refreshSystem() {
  try {
    const systemInfo = await fetchJson("/api/system", { headers: {} });
    applySystemInfo(systemInfo);
  } catch (error) {
    nodes.systemLlmStatus.textContent = "ошибка";
    nodes.networkLabel.textContent = "Оффлайн";
    console.error(error);
  }
}

async function saveAudioSettings() {
  const inputDevice = textOrFallback(nodes.systemInputSelect.value, "");
  const outputDevice = textOrFallback(nodes.systemOutputSelect.value, "");
  if (!inputDevice || !outputDevice) {
    throw new Error("Сначала выберите и вход, и выход.");
  }

  nodes.saveAudioDevicesBtn.disabled = true;
  nodes.saveAudioDevicesBtn.textContent = "Применяю...";
  try {
    const systemInfo = await fetchJson("/api/system/audio", {
      method: "POST",
      body: JSON.stringify({
        input_device: inputDevice,
        output_device: outputDevice,
      }),
    });
    appState.audioDraft = {
      dirty: false,
      input: textOrFallback(systemInfo.input_device, inputDevice),
      output: textOrFallback(systemInfo.output_device, outputDevice),
    };
    applySystemInfo(systemInfo);
  } finally {
    nodes.saveAudioDevicesBtn.disabled = false;
    nodes.saveAudioDevicesBtn.textContent = "Применить";
  }
}

async function saveAssistantSettings() {
  const triggerPhrase = textOrFallback(nodes.systemTriggerInput.value, "");
  if (!triggerPhrase) {
    throw new Error("Сначала введите слово активации.");
  }

  nodes.saveTriggerBtn.disabled = true;
  nodes.saveTriggerBtn.textContent = "Сохраняю...";
  try {
    const systemInfo = await fetchJson("/api/system/assistant", {
      method: "POST",
      body: JSON.stringify({
        trigger_phrase: triggerPhrase,
      }),
    });
    appState.triggerDraft = {
      dirty: false,
      value: textOrFallback(systemInfo.wake_phrase, triggerPhrase),
    };
    applySystemInfo(systemInfo);
    await refreshState();
  } finally {
    nodes.saveTriggerBtn.disabled = false;
    nodes.saveTriggerBtn.textContent = "Сохранить триггер";
  }
}

function collectTtsPayload() {
  const engine = textOrFallback(nodes.systemTtsEngineSelect?.value, "rhvoice");
  const voice = textOrFallback(nodes.systemTtsVoiceInput?.value, "");
  const rate = Number(nodes.systemTtsRateInput?.value ?? 0);
  const pitch = Number(nodes.systemTtsPitchInput?.value ?? 0);
  const volume = Number(nodes.systemTtsVolumeInput?.value ?? 100);
  const piperModel = textOrFallback(nodes.systemTtsModelSelect?.value, "");
  return {
    engine,
    voice,
    rate,
    pitch,
    volume,
    piper_model: piperModel,
  };
}

async function saveTtsSettings() {
  const payload = collectTtsPayload();
  if (payload.engine === "rhvoice" && !payload.voice) {
    throw new Error("Выберите голос RHVoice.");
  }
  if (payload.engine === "piper" && !payload.piper_model) {
    throw new Error("Для Piper сначала выберите модель.");
  }

  nodes.saveTtsBtn.disabled = true;
  nodes.saveTtsBtn.textContent = "Сохраняю...";
  try {
    const systemInfo = await fetchJson("/api/system/tts", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    appState.ttsDraft = {
      dirty: false,
      engine: textOrFallback(systemInfo.tts_engine, payload.engine),
      voice: textOrFallback(systemInfo.tts_voice, payload.voice),
      rate: String(systemInfo.tts_rate ?? payload.rate),
      pitch: String(systemInfo.tts_pitch ?? payload.pitch),
      volume: String(systemInfo.tts_volume ?? payload.volume),
      model: textOrFallback(systemInfo.tts_piper_model, payload.piper_model),
    };
    applySystemInfo(systemInfo);
  } finally {
    nodes.saveTtsBtn.disabled = false;
    nodes.saveTtsBtn.textContent = "Сохранить TTS";
  }
}

async function testTts() {
  const text = textOrFallback(nodes.systemTtsTestInput?.value, "");
  if (!text) {
    throw new Error("Введите тестовый текст.");
  }
  await saveTtsSettings();
  nodes.testTtsBtn.disabled = true;
  nodes.testTtsBtn.textContent = "Озвучиваю...";
  try {
    const systemInfo = await fetchJson("/api/system/tts/test", {
      method: "POST",
      body: JSON.stringify({ text }),
    });
    nodes.systemTtsTestHint.textContent = textOrFallback(systemInfo.tts_message, "") || "Тест TTS выполнен.";
    nodes.systemTtsTestHint.classList.toggle("is-danger", Boolean(systemInfo.tts_error));
    applySystemInfo(systemInfo);
  } finally {
    nodes.testTtsBtn.disabled = false;
    nodes.testTtsBtn.textContent = "Проверить TTS";
  }
}

async function uploadTtsFiles() {
  const files = Array.from(nodes.systemTtsUploadInput?.files || []);
  if (!files.length) {
    throw new Error("Сначала выберите .onnx и .json файлы.");
  }
  const payloadFiles = [];
  for (const file of files) {
    const name = String(file.name || "").toLowerCase();
    if (!name.endsWith(".onnx") && !name.endsWith(".json")) {
      throw new Error("Поддерживаются только .onnx и .json файлы.");
    }
    payloadFiles.push({
      file_name: file.name,
      content_base64: await readFileAsBase64(file),
    });
  }

  nodes.uploadTtsBtn.disabled = true;
  nodes.uploadTtsBtn.textContent = "Загружаю...";
  try {
    const systemInfo = await fetchJson("/api/system/tts/upload", {
      method: "POST",
      body: JSON.stringify({ files: payloadFiles }),
    });
    nodes.systemTtsUploadInput.value = "";
    nodes.systemTtsUploadHint.textContent = Array.isArray(systemInfo.uploaded_files)
      ? `Загружено: ${systemInfo.uploaded_files.join(", ")}`
      : "Файлы загружены.";
    nodes.systemTtsUploadHint.classList.remove("is-danger");
    await refreshSystem();
  } finally {
    nodes.uploadTtsBtn.disabled = false;
    nodes.uploadTtsBtn.textContent = "Загрузить модель";
  }
}

async function handleChatSubmit(event) {
  event.preventDefault();
  const message = nodes.chatInput.value.trim();
  if (!message) {
    return;
  }

  pushChatMessage("user", message);
  nodes.chatInput.value = "";
  nodes.chatSubmit.disabled = true;
  nodes.chatSubmit.textContent = "Думаю...";
  try {
    const payload = await fetchJson("/api/chat", {
      method: "POST",
      body: JSON.stringify({ message }),
    });
    pushChatMessage("assistant", textOrFallback(payload.reply, "Нейросеть ответила пустотой. Редкий талант."));
  } catch (error) {
    pushChatMessage("assistant", `Ошибка: ${String(error.message || error)}`);
  } finally {
    nodes.chatSubmit.disabled = false;
    nodes.chatSubmit.textContent = "Отправить";
    nodes.chatInput.focus();
  }
}

function floatToLevel(channelData) {
  let peak = 0;
  for (let index = 0; index < channelData.length; index += 1) {
    peak = Math.max(peak, Math.abs(channelData[index]));
  }
  return Math.max(0, Math.min(100, Math.round(peak * 100)));
}

function downsampleToInt16(buffer, inputRate, outputRate) {
  if (outputRate >= inputRate) {
    const pcm = new Int16Array(buffer.length);
    for (let index = 0; index < buffer.length; index += 1) {
      const sample = Math.max(-1, Math.min(1, buffer[index]));
      pcm[index] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
    }
    return pcm;
  }

  const ratio = inputRate / outputRate;
  const newLength = Math.round(buffer.length / ratio);
  const result = new Int16Array(newLength);
  let offsetResult = 0;
  let offsetBuffer = 0;

  while (offsetResult < result.length) {
    const nextOffsetBuffer = Math.round((offsetResult + 1) * ratio);
    let accumulator = 0;
    let count = 0;
    for (let index = offsetBuffer; index < nextOffsetBuffer && index < buffer.length; index += 1) {
      accumulator += buffer[index];
      count += 1;
    }
    const sample = count ? accumulator / count : 0;
    const clamped = Math.max(-1, Math.min(1, sample));
    result[offsetResult] = clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff;
    offsetResult += 1;
    offsetBuffer = nextOffsetBuffer;
  }
  return result;
}

function browserMicSourceName() {
  const platform = navigator.userAgentData?.platform || navigator.platform || "browser";
  return String(platform).replace(/\s+/g, "-").toLowerCase();
}

async function flushBrowserMicQueue() {
  if (appState.browserMic.uploading || !appState.browserMic.uploadQueue.length) {
    return;
  }
  appState.browserMic.uploading = true;
  try {
    while (appState.browserMic.uploadQueue.length) {
      const chunk = appState.browserMic.uploadQueue.shift();
      await fetch(`/api/mic/chunk?source=${encodeURIComponent(browserMicSourceName())}`, {
        method: "POST",
        headers: { "Content-Type": "application/octet-stream" },
        body: chunk,
        cache: "no-store",
      });
    }
  } catch (error) {
    nodes.systemNetworkMicState.textContent = `Ошибка отправки микрофона: ${String(error.message || error)}`;
    nodes.systemNetworkMicState.classList.add("is-danger");
  } finally {
    appState.browserMic.uploading = false;
  }
}

async function startBrowserMic() {
  if (selectedInputDevice() !== "network-mic") {
    throw new Error('Сначала выберите вход "Телефон / браузер по Wi‑Fi" и нажмите "Применить".');
  }
  if (!window.isSecureContext) {
    throw new Error("Откройте secure-версию этой страницы. Обычный HTTP браузерный микрофон не даст.");
  }
  if (appState.browserMic.running) {
    return;
  }

  const mediaStream = await navigator.mediaDevices.getUserMedia({
    audio: {
      channelCount: 1,
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
    },
  });

  const audioContext = new AudioContext();
  const sourceNode = audioContext.createMediaStreamSource(mediaStream);
  const processorNode = audioContext.createScriptProcessor(2048, 1, 1);
  processorNode.onaudioprocess = (event) => {
    const channelData = event.inputBuffer.getChannelData(0);
    setTelemetryTarget("browserMic", floatToLevel(channelData));
    const pcm = downsampleToInt16(channelData, audioContext.sampleRate, TARGET_RATE);
    if (!pcm.length) {
      return;
    }
    appState.browserMic.uploadQueue.push(new Uint8Array(pcm.buffer).slice());
    if (appState.browserMic.uploadQueue.length > 12) {
      appState.browserMic.uploadQueue = appState.browserMic.uploadQueue.slice(-12);
    }
    void flushBrowserMicQueue();
  };

  sourceNode.connect(processorNode);
  processorNode.connect(audioContext.destination);

  appState.browserMic.mediaStream = mediaStream;
  appState.browserMic.audioContext = audioContext;
  appState.browserMic.sourceNode = sourceNode;
  appState.browserMic.processorNode = processorNode;
  appState.browserMic.running = true;
  nodes.systemNetworkMicState.textContent = "Браузерный микрофон активен. Говорите.";
  nodes.systemNetworkMicState.classList.remove("is-danger");
  updateBrowserMicUi();
}

function stopBrowserMic() {
  const mic = appState.browserMic;
  if (mic.processorNode) {
    mic.processorNode.disconnect();
    mic.processorNode.onaudioprocess = null;
    mic.processorNode = null;
  }
  if (mic.sourceNode) {
    mic.sourceNode.disconnect();
    mic.sourceNode = null;
  }
  if (mic.mediaStream) {
    mic.mediaStream.getTracks().forEach((track) => track.stop());
    mic.mediaStream = null;
  }
  if (mic.audioContext) {
    mic.audioContext.close().catch(() => {});
    mic.audioContext = null;
  }
  mic.uploadQueue = [];
  mic.uploading = false;
  mic.running = false;
  setTelemetryTarget("browserMic", 0);
  nodes.systemNetworkMicState.textContent = "Браузерный микрофон остановлен.";
  nodes.systemNetworkMicState.classList.remove("is-danger");
  updateBrowserMicUi();
}

async function copyNetworkMicUrl() {
  const url = textOrFallback(appState.systemInfo.network_mic_url, "");
  if (!url) {
    throw new Error("Secure URL пока не готов.");
  }
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(url);
  } else {
    window.prompt("Скопируйте URL вручную:", url);
  }
  nodes.systemNetworkMicState.textContent = "Secure URL скопирован.";
  nodes.systemNetworkMicState.classList.remove("is-danger");
}

function openNetworkMicUrl() {
  const url = textOrFallback(appState.systemInfo.network_mic_url, "");
  if (!url) {
    throw new Error("Secure URL пока не готов.");
  }
  window.open(url, "_blank", "noopener,noreferrer");
}

function bindEvents() {
  nodes.navItems.forEach((node) => {
    node.addEventListener("click", () => setView(node.dataset.viewTarget));
  });
  window.addEventListener("hashchange", () => setView(normalizedHashView(), { updateHash: false }));
  window.addEventListener("beforeunload", stopBrowserMic);

  nodes.chatForm.addEventListener("submit", handleChatSubmit);
  nodes.actionTypeSelect.addEventListener("change", updateActionFields);
  nodes.audioModeSelect.addEventListener("change", updateAudioFields);
  nodes.commandSearch.addEventListener("input", renderCommandList);

  nodes.systemInputSelect.addEventListener("change", () => {
    appState.audioDraft.dirty = true;
    appState.audioDraft.input = nodes.systemInputSelect.value;
    applySystemInfo(appState.systemInfo);
  });
  nodes.systemOutputSelect.addEventListener("change", () => {
    appState.audioDraft.dirty = true;
    appState.audioDraft.output = nodes.systemOutputSelect.value;
    applySystemInfo(appState.systemInfo);
  });
  nodes.systemTriggerInput.addEventListener("input", () => {
    appState.triggerDraft.dirty = true;
    appState.triggerDraft.value = nodes.systemTriggerInput.value;
  });
  nodes.systemTtsEngineSelect.addEventListener("change", () => {
    appState.ttsDraft.dirty = true;
    appState.ttsDraft.engine = nodes.systemTtsEngineSelect.value;
    updateTtsFields();
    applySystemInfo(appState.systemInfo);
  });
  nodes.systemTtsVoiceInput.addEventListener("change", () => {
    appState.ttsDraft.dirty = true;
    appState.ttsDraft.voice = nodes.systemTtsVoiceInput.value;
  });
  nodes.systemTtsRateInput.addEventListener("input", () => {
    appState.ttsDraft.dirty = true;
    appState.ttsDraft.rate = nodes.systemTtsRateInput.value;
  });
  nodes.systemTtsPitchInput.addEventListener("input", () => {
    appState.ttsDraft.dirty = true;
    appState.ttsDraft.pitch = nodes.systemTtsPitchInput.value;
  });
  nodes.systemTtsVolumeInput.addEventListener("input", () => {
    appState.ttsDraft.dirty = true;
    appState.ttsDraft.volume = nodes.systemTtsVolumeInput.value;
  });
  nodes.systemTtsModelSelect.addEventListener("change", () => {
    appState.ttsDraft.dirty = true;
    appState.ttsDraft.model = nodes.systemTtsModelSelect.value;
  });

  nodes.refreshAudioDevicesBtn.addEventListener("click", () => {
    refreshSystem().catch((error) => {
      nodes.systemAudioHint.textContent = String(error.message || error);
      nodes.systemAudioHint.classList.add("is-danger");
    });
  });
  nodes.saveAudioDevicesBtn.addEventListener("click", async () => {
    try {
      await saveAudioSettings();
    } catch (error) {
      nodes.systemAudioHint.textContent = String(error.message || error);
      nodes.systemAudioHint.classList.add("is-danger");
    }
  });
  nodes.saveTriggerBtn.addEventListener("click", async () => {
    try {
      await saveAssistantSettings();
    } catch (error) {
      nodes.systemTriggerHint.textContent = String(error.message || error);
      nodes.systemTriggerHint.classList.add("is-danger");
    }
  });
  nodes.saveTtsBtn.addEventListener("click", async () => {
    try {
      await saveTtsSettings();
    } catch (error) {
      nodes.systemTtsHint.textContent = String(error.message || error);
      nodes.systemTtsHint.classList.add("is-danger");
    }
  });
  nodes.testTtsBtn.addEventListener("click", async () => {
    try {
      await testTts();
    } catch (error) {
      nodes.systemTtsTestHint.textContent = String(error.message || error);
      nodes.systemTtsTestHint.classList.add("is-danger");
    }
  });
  nodes.uploadTtsBtn.addEventListener("click", async () => {
    try {
      await uploadTtsFiles();
    } catch (error) {
      nodes.systemTtsUploadHint.textContent = String(error.message || error);
      nodes.systemTtsUploadHint.classList.add("is-danger");
    }
  });
  nodes.copyNetworkMicUrlBtn.addEventListener("click", async () => {
    try {
      await copyNetworkMicUrl();
    } catch (error) {
      nodes.systemNetworkMicState.textContent = String(error.message || error);
      nodes.systemNetworkMicState.classList.add("is-danger");
    }
  });
  nodes.openNetworkMicUrlBtn.addEventListener("click", () => {
    try {
      openNetworkMicUrl();
    } catch (error) {
      nodes.systemNetworkMicState.textContent = String(error.message || error);
      nodes.systemNetworkMicState.classList.add("is-danger");
    }
  });
  nodes.startBrowserMicBtn.addEventListener("click", async () => {
    try {
      await startBrowserMic();
    } catch (error) {
      nodes.systemNetworkMicState.textContent = String(error.message || error);
      nodes.systemNetworkMicState.classList.add("is-danger");
    }
  });
  nodes.stopBrowserMicBtn.addEventListener("click", stopBrowserMic);

  nodes.resetCommandBtn.addEventListener("click", resetCommandForm);
  nodes.saveCommandBtn.addEventListener("click", async () => {
    try {
      await saveCommand();
    } catch (error) {
      nodes.audioFileHint.textContent = String(error.message || error);
    }
  });

  nodes.commandList.addEventListener("click", async (event) => {
    const target = event.target.closest("[data-action]");
    if (!target) {
      return;
    }
    const { action, commandId } = target.dataset;
    if (!commandId) {
      return;
    }
    if (action === "delete") {
      try {
        await deleteCommand(commandId);
      } catch (error) {
        nodes.audioFileHint.textContent = String(error.message || error);
      }
      return;
    }
    const command = appState.commandMap.get(commandId);
    if (command) {
      fillCommandForm(command);
      setView("commands");
    }
  });
}

async function boot() {
  bindEvents();
  resetCommandForm();
  renderChatMessages();
  setView(normalizedHashView(), { updateHash: false });
  animateTelemetry();

  await Promise.allSettled([refreshSystem(), loadCommands(), refreshState()]);
  window.setInterval(refreshState, STATE_POLL_MS);
  window.setInterval(refreshSystem, SYSTEM_POLL_MS);
}

boot().catch((error) => {
  console.error(error);
  nodes.networkLabel.textContent = "Ошибка";
});
