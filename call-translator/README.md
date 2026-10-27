# Live Call Translator

A local web app that listens to a phone call on speaker through your PC microphone,
transcribes it, and shows live translations:

- **English** speech → **French** + **Arabic**
- **French** speech → **Arabic** + **English**

Speech recognition runs **locally** with [faster-whisper](https://github.com/SYSTRAN/faster-whisper).
Only the transcribed text is sent to the Claude API (`claude-haiku-5-5`) for translation.
The server listens on `127.0.0.1` only, so it isn't reachable from your network.

## Setup (Windows)

1. Install **Python 3.11 or newer** from <https://www.python.org/downloads/>
   (tick **"Add python.exe to PATH"** in the installer).
2. Get an Anthropic API key at <https://platform.claude.com/> → API Keys.
3. Double-click **`start.bat`**. The first run:
   - creates a virtual environment in `.venv` and installs `requirements.txt` (a few minutes),
   - creates `.env` from `.env.example` and opens it in Notepad. Paste your key after
     `ANTHROPIC_API_KEY=`, save, close Notepad.
4. The browser opens <http://localhost:8000>. The first start also downloads the Whisper
   model (~500 MB for `small`), so wait until the status pill turns green.

After that, just double-click `start.bat` whenever you need it. Close the console window to stop.

### Mac / Linux

```bash
./start.sh
```
Same steps: it creates `.venv`, installs packages, creates `.env`, then opens the browser.

### Manual setup (any OS)

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows  (Mac/Linux: source .venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env          # Mac/Linux: cp .env.example .env  — then add your key
python -m app.server            # then open http://localhost:8000
```

## Using it

1. Put the phone on speaker next to the PC.
2. Pick the microphone in the dropdown (names appear after you allow mic access once).
3. Press **Start** and allow microphone access. The level meter should move when people talk.
4. Each time a speaker pauses (~0.6 s), an entry appears: time, **EN/FR** tag, the original
   text, then the two translations (Arabic is right-to-left). The time on the right of each
   entry is how long it took from the end of the sentence to the translation.
5. **Export transcript** downloads a `.txt` with the originals and all translations.
   **Clear** empties the feed.

## Settings (`.env`)

| Variable | Default | Meaning |
|---|---|---|
| `ANTHROPIC_API_KEY` | – | Required for translation. Never commit `.env`. |
| `CLAUDE_MODEL` | `claude-haiku-5-5` | Translation model. |
| `WHISPER_MODEL` | `small` | `medium` is more accurate but ~2–3× slower (use with a GPU). |
| `WHISPER_DEVICE` | `auto` | `auto` uses an NVIDIA GPU (CUDA, float16) if available, else CPU (int8). |
| `SILENCE_MS` | `600` | Pause that ends a sentence. |
| `MAX_SEGMENT_S` | `10` | Long monologues are cut at the best pause before this length. |
| `VAD_THRESHOLD` | `0.5` | Raise to `0.6`–`0.7` if background noise triggers entries. |
| `PORT` | `8000` | Web page port. |

Restart the app after editing `.env`.

### GPU (optional)

With an NVIDIA GPU, faster-whisper also needs the CUDA 12 cuBLAS and cuDNN 9 libraries. The
simplest way on Windows is:

```bat
.venv\Scripts\pip install nvidia-cublas-cu12 nvidia-cudnn-cu12
```

If the GPU libraries are missing, the app logs a warning and falls back to the CPU automatically.

## How it works

```
Browser (getUserMedia → AudioWorklet: mono, 16 kHz, 250 ms Int16 chunks)
   │  WebSocket /ws
   ▼
Segmenter (Silero VAD)  ── cut at 600 ms pause or 10 s
   ▼
Whisper: detect language (restricted to en/fr) → transcribe
   ▼  filter silence / noise / hallucinations ("Thanks for watching", repeated lines…)
Claude: one request per segment → {"source_lang", "translations": {...}}
   ▼
Browser feed (transcript appears first, translations fill in a moment later)
```

- `app/segmenter.py` – live VAD segmentation
- `app/transcriber.py` – Whisper, language restriction, hallucination filters
- `app/translator.py` – Claude request (structured JSON output) and error messages
- `app/server.py` – FastAPI app, WebSocket, pipeline
- `static/` – the page (`index.html`, `app.js`, `style.css`, `pcm-worklet.js`)

## Testing with audio files

Record a short English and a short French clip (any format), then:

```bash
.venv\Scripts\activate
python -m tests.try_samples english.wav french.m4a
```

It runs the same pipeline as the live app and prints the detected language, text,
translations and timings.

## Troubleshooting

- **"Microphone permission denied"** – click the icon at the left of the address bar, allow the
  microphone, press Start again. On Windows also check *Settings → Privacy & security → Microphone*.
- **"Missing API key"** – `.env` must contain `ANTHROPIC_API_KEY=sk-ant-...`; restart after editing.
- **Nothing appears** – check the level meter moves; try another microphone in the list; move the
  phone closer; lower `VAD_THRESHOLD`.
- **Slow (> 4 s)** – stay on `WHISPER_MODEL=small` on CPU; `medium` needs a GPU for live use.
- **Wrong language tag** – short utterances ("OK", "Oui") are hard to identify; Claude corrects
  the tag when it can tell from the text.
