const TARGET_RATE = 16000;
const nodes = {
  levelFill: document.getElementById("levelFill"),
  statusText: document.getElementById("statusText"),
  serverText: document.getElementById("serverText"),
  secureHint: document.getElementById("secureHint"),
  startBtn: document.getElementById("startBtn"),
  stopBtn: document.getElementById("stopBtn"),
};

let audioContext = null;
let mediaStream = null;
let sourceNode = null;
let processorNode = null;
let uploadQueue = [];
let uploading = false;

function setStatus(text) {
  nodes.statusText.textContent = text;
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

async function flushUploadQueue() {
  if (uploading || !uploadQueue.length) {
    return;
  }
  uploading = true;
  try {
    while (uploadQueue.length) {
      const chunk = uploadQueue.shift();
      await fetch("/api/mic/chunk?source=phone-browser", {
        method: "POST",
        headers: { "Content-Type": "application/octet-stream" },
        body: chunk,
        cache: "no-store",
      });
    }
  } catch (error) {
    setStatus(`Ошибка отправки: ${String(error.message || error)}`);
  } finally {
    uploading = false;
  }
}

async function refreshStatus() {
  try {
    const response = await fetch("/api/mic/status", { cache: "no-store" });
    const payload = await response.json();
    nodes.serverText.textContent = payload.network_mic_url || window.location.href;
    if (!window.isSecureContext) {
      nodes.secureHint.textContent =
        "Откройте HTTPS-адрес. Без secure context браузер микрофон не отдаст, потому что стандарты решили поумничать.";
    }
  } catch (error) {
    nodes.serverText.textContent = String(error.message || error);
  }
}

async function startMic() {
  if (!window.isSecureContext) {
    setStatus("Откройте HTTPS-адрес этой страницы. На обычном HTTP браузер микрофон не даст.");
    return;
  }

  mediaStream = await navigator.mediaDevices.getUserMedia({
    audio: {
      channelCount: 1,
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
    },
  });

  audioContext = new AudioContext();
  sourceNode = audioContext.createMediaStreamSource(mediaStream);
  processorNode = audioContext.createScriptProcessor(2048, 1, 1);
  processorNode.onaudioprocess = (event) => {
    const channelData = event.inputBuffer.getChannelData(0);
    nodes.levelFill.style.width = `${floatToLevel(channelData)}%`;
    const pcm = downsampleToInt16(channelData, audioContext.sampleRate, TARGET_RATE);
    if (!pcm.length) {
      return;
    }
    uploadQueue.push(new Uint8Array(pcm.buffer).slice());
    if (uploadQueue.length > 12) {
      uploadQueue = uploadQueue.slice(-12);
    }
    void flushUploadQueue();
  };
  sourceNode.connect(processorNode);
  processorNode.connect(audioContext.destination);
  setStatus("Микрофон активен. Говорите.");
  nodes.startBtn.disabled = true;
  nodes.stopBtn.disabled = false;
}

function stopMic() {
  if (processorNode) {
    processorNode.disconnect();
    processorNode.onaudioprocess = null;
    processorNode = null;
  }
  if (sourceNode) {
    sourceNode.disconnect();
    sourceNode = null;
  }
  if (mediaStream) {
    mediaStream.getTracks().forEach((track) => track.stop());
    mediaStream = null;
  }
  if (audioContext) {
    audioContext.close().catch(() => {});
    audioContext = null;
  }
  uploadQueue = [];
  nodes.levelFill.style.width = "0%";
  setStatus("Микрофон остановлен.");
  nodes.startBtn.disabled = false;
  nodes.stopBtn.disabled = true;
}

nodes.startBtn.addEventListener("click", async () => {
  try {
    await startMic();
  } catch (error) {
    setStatus(`Не удалось включить микрофон: ${String(error.message || error)}`);
  }
});

nodes.stopBtn.addEventListener("click", stopMic);

window.setInterval(refreshStatus, 2000);
refreshStatus().catch(() => {});
