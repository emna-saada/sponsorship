"use strict";

const LANG_NAMES = { en: "English", fr: "French", ar: "Arabic" };
const TARGETS = { en: ["fr", "ar"], fr: ["ar", "en"] };

const $ = (id) => document.getElementById(id);
const startBtn = $("start");
const micSel = $("mic");
const levelFill = $("level-fill");
const listening = $("listening");
const feed = $("feed");
const banner = $("banner");
const serverStatus = $("server-status");

let ws = null;
let status = null;
let audio = null; // { ctx, stream, node, source }
let running = false;
let speaking = false;
let processing = false;
const entries = new Map(); // id -> { ts, lang, text, translations, el }

// ---------- WebSocket ----------
function connect() {
  ws = new WebSocket(`ws://${location.host}/ws`);
  ws.binaryType = "arraybuffer";
  ws.onopen = () => setPill("Connected", "ok");
  ws.onmessage = (ev) => handle(JSON.parse(ev.data));
  ws.onclose = () => {
    setPill("Server disconnected - retrying…", "err");
    startBtn.disabled = true;
    if (running) stop();
    setTimeout(connect, 2000);
  };
}

function handle(msg) {
  switch (msg.type) {
    case "status": return onStatus(msg);
    case "vad":
      if ("speaking" in msg) speaking = msg.speaking;
      if ("processing" in msg) processing = msg.processing;
      return updateListening();
    case "segment": return addEntry(msg);
    case "translation": return fillTranslation(msg);
    case "error":
      if (msg.id && entries.has(msg.id)) return failTranslation(msg.id, msg.message);
      return showBanner(msg.message);
  }
}

function onStatus(s) {
  status = s;
  if (s.load_error) {
    setPill("Speech model failed", "err");
    showBanner(s.load_error);
    startBtn.disabled = true;
    return;
  }
  if (!s.model_ready) {
    setPill(`Loading Whisper "${s.whisper}"… (first run downloads the model)`, "warn");
    startBtn.disabled = true;
    return;
  }
  startBtn.disabled = false;
  if (!s.api_key) {
    setPill(`Whisper ${s.whisper} · ${s.device} · no API key`, "warn");
    showBanner("Missing API key: copy .env.example to .env, set ANTHROPIC_API_KEY, then restart. Transcription works, translation won't.", "warn");
  } else {
    setPill(`Whisper ${s.whisper} · ${s.device} · ${s.claude_model}`, "ok");
  }
}

function setPill(text, cls) {
  serverStatus.textContent = text;
  serverStatus.className = "pill " + (cls || "");
}

function showBanner(text, kind) {
  banner.textContent = text;
  banner.className = "banner" + (kind ? " " + kind : "");
  banner.hidden = false;
}
function hideBanner() { banner.hidden = true; }

// ---------- Microphone ----------
async function listMics() {
  if (!navigator.mediaDevices?.enumerateDevices) return;
  const devices = await navigator.mediaDevices.enumerateDevices();
  const current = micSel.value;
  micSel.innerHTML = '<option value="">Default microphone</option>';
  devices.filter((d) => d.kind === "audioinput" && d.deviceId !== "default").forEach((d, i) => {
    const o = document.createElement("option");
    o.value = d.deviceId;
    o.textContent = d.label || `Microphone ${i + 1}`;
    micSel.appendChild(o);
  });
  if ([...micSel.options].some((o) => o.value === current)) micSel.value = current;
}

async function start() {
  if (!navigator.mediaDevices?.getUserMedia) {
    showBanner("This browser can't access the microphone. Open http://localhost:8000 in Chrome, Edge or Firefox.");
    return;
  }
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        deviceId: micSel.value ? { exact: micSel.value } : undefined,
        channelCount: 1,
        echoCancellation: false, // the call audio IS what we want to hear
        noiseSuppression: true,
        autoGainControl: true,
      },
    });
  } catch (e) {
    if (e.name === "NotAllowedError" || e.name === "SecurityError") {
      showBanner("Microphone permission denied. Click the lock/camera icon in the address bar, allow the microphone, then press Start again.");
    } else if (e.name === "NotFoundError" || e.name === "OverconstrainedError") {
      showBanner("No microphone found (or the selected one was unplugged). Check the device and pick it in the Microphone list.");
    } else if (e.name === "NotReadableError") {
      showBanner("The microphone is busy or blocked by another app/Windows privacy settings.");
    } else {
      showBanner(`Could not open the microphone: ${e.message || e.name}`);
    }
    return;
  }
  hideBanner();
  if (status && !status.api_key) onStatus(status);
  await listMics(); // labels become available after permission is granted

  const ctx = new AudioContext();
  await ctx.audioWorklet.addModule("/static/pcm-worklet.js");
  const source = ctx.createMediaStreamSource(stream);
  const node = new AudioWorkletNode(ctx, "pcm-capture", { processorOptions: { chunkSize: 4000 } });
  node.port.onmessage = ({ data }) => {
    if (ws?.readyState === WebSocket.OPEN) ws.send(data.pcm);
    const pct = Math.min(100, Math.sqrt(data.rms) * 180);
    levelFill.style.width = pct + "%";
  };
  source.connect(node);
  // Not connected to ctx.destination: we don't want to play the mic back.
  audio = { ctx, stream, node, source };

  ws.send(JSON.stringify({ type: "start" }));
  running = true;
  startBtn.textContent = "Stop";
  startBtn.classList.add("running");
  micSel.disabled = true;
  updateListening();
}

function stop() {
  running = false;
  if (audio) {
    audio.node.port.onmessage = null;
    audio.source.disconnect();
    audio.stream.getTracks().forEach((t) => t.stop());
    audio.ctx.close();
    audio = null;
  }
  if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "stop" }));
  startBtn.textContent = "Start";
  startBtn.classList.remove("running");
  micSel.disabled = false;
  levelFill.style.width = "0";
  speaking = false;
  updateListening();
}

function updateListening() {
  const show = (running && speaking) || processing;
  listening.hidden = !show;
  listening.classList.toggle("processing", processing && !speaking);
  listening.lastChild.textContent = speaking ? "listening…" : "transcribing…";
}

// ---------- Feed ----------
function nearBottom() {
  return feed.scrollHeight - feed.scrollTop - feed.clientHeight < 120;
}
function scrollDown(stick) {
  if (stick) feed.scrollTop = feed.scrollHeight;
}

function el(tag, attrs = {}, text) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (text !== undefined) e.textContent = text;
  return e;
}

function addEntry(msg) {
  const stick = nearBottom();
  $("empty")?.remove();
  const box = el("article", { class: "entry" });
  const meta = el("div", { class: "meta" });
  meta.append(el("span", {}, msg.ts), el("span", { class: `tag ${msg.lang}` }, msg.lang.toUpperCase()));
  const timing = el("span", { class: "timing" });
  meta.append(timing);
  const original = el("div", { class: "original", lang: msg.lang }, msg.text);
  const tr = el("div", { class: "tr" });
  box.append(meta, original, tr);
  feed.append(box);

  const entry = { ts: msg.ts, lang: msg.lang, text: msg.text, translations: null, box, meta, original, tr, timing };
  entries.set(msg.id, entry);
  renderTranslations(entry, null);
  scrollDown(stick);
}

function renderTranslations(entry, translations, error) {
  entry.tr.innerHTML = "";
  for (const lang of TARGETS[entry.lang]) {
    const rtl = lang === "ar";
    const cls = `t ${lang}` + (error ? " error" : translations ? "" : " pending");
    const box = el("div", { class: cls, lang, dir: rtl ? "rtl" : "ltr" });
    box.append(el("label", {}, LANG_NAMES[lang]));
    const text = error ? error : translations ? translations[lang] : "translating…";
    box.append(el("div", { class: "txt" }, text));
    entry.tr.append(box);
  }
}

function fillTranslation(msg) {
  const entry = entries.get(msg.id);
  if (!entry) return;
  const stick = nearBottom();
  if (msg.source_lang !== entry.lang) {
    // Claude read the text and corrected Whisper's language guess.
    entry.lang = msg.source_lang;
    const tag = entry.meta.querySelector(".tag");
    tag.className = `tag ${entry.lang}`;
    tag.textContent = entry.lang.toUpperCase();
    entry.original.lang = entry.lang;
  }
  entry.translations = msg.translations;
  renderTranslations(entry, msg.translations);
  entry.timing.textContent = `${(msg.total_ms / 1000).toFixed(1)}s`;
  scrollDown(stick);
}

function failTranslation(id, message) {
  const entry = entries.get(id);
  renderTranslations(entry, null, message);
  if (/API key/i.test(message)) showBanner(message);
}

function clearFeed() {
  entries.clear();
  feed.innerHTML = "";
  const empty = el("div", { id: "empty", class: "empty" });
  empty.append(el("p", {}, "Transcript cleared."));
  feed.append(empty);
}

function exportTranscript() {
  if (!entries.size) {
    showBanner("Nothing to export yet.", "warn");
    setTimeout(hideBanner, 2500);
    return;
  }
  const lines = [`Live Call Translator - transcript ${new Date().toLocaleString()}`, ""];
  for (const e of entries.values()) {
    lines.push(`[${e.ts}] ${e.lang.toUpperCase()} (${LANG_NAMES[e.lang]}): ${e.text}`);
    for (const lang of TARGETS[e.lang]) {
      const t = e.translations ? e.translations[lang] : "(not translated)";
      lines.push(`    ${LANG_NAMES[lang]}: ${t}`);
    }
    lines.push("");
  }
  // BOM so Notepad opens the Arabic text as UTF-8.
  const blob = new Blob(["﻿" + lines.join("\r\n")], { type: "text/plain;charset=utf-8" });
  const a = el("a", { href: URL.createObjectURL(blob) });
  const d = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  a.download = `call-transcript-${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}-${pad(d.getHours())}${pad(d.getMinutes())}.txt`;
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

// ---------- Wiring ----------
startBtn.onclick = () => (running ? stop() : start());
$("clear").onclick = clearFeed;
$("export").onclick = exportTranscript;
navigator.mediaDevices?.addEventListener?.("devicechange", listMics);
listMics();
connect();
