# Live Call Translator

A local web app that listens to a phone call on speaker through your PC microphone,
transcribes it, and shows live translations:

- **English** speech → **French** + **Arabic**
- **French** speech → **Arabic** + **English**

**Free and fully offline:** speech recognition runs locally with
[faster-whisper](https://github.com/SYSTRAN/faster-whisper) and translation runs locally with
Meta's [NLLB-200](https://ai.meta.com/research/no-language-left-behind/) model. No account, no API
key, no cost, and the call audio never leaves your PC. (Optionally, you can switch translation
to the paid Claude API - see Settings.) The server listens on `127.0.0.1` only, so it isn't
reachable from your network.

## Setup (Windows)

1. Install **Python 3.11 or newer** from <https://www.python.org/downloads/>
   (tick **"Add python.exe to PATH"** in the installer).
2. Double-click **`start.bat`**. The first run creates a virtual environment in `.venv`
   and installs `requirements.txt` (a few minutes).
3. The browser opens <http://localhost:8000>. The first start also downloads the models
   (~500 MB Whisper `small` + ~650 MB NLLB 600M, once), so wait until the status pill turns green.

After that, just double-click `start.bat` whenever you need it. Close the console window to stop.

### Mac / Linux

```bash
./start.sh
```
Same steps: it creates `.venv`, installs packages, then opens the browser.

### Manual setup (any OS)

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows  (Mac/Linux: source .venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env          # Mac/Linux: cp .env.example .env
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
| `TRANSLATOR` | `local` | `local` = free offline NLLB. `claude` = paid Claude API (needs a key). |
| `NLLB_MODEL` | `osa911/nllb-200-distilled-600M-ct2-int8` | Use `OpenNMT/nllb-200-distilled-1.3B-ct2-int8` for slightly better translations (~2× slower on CPU, fine with a GPU). |
| `ANTHROPIC_API_KEY` | – | Only for `TRANSLATOR=claude` (also run `pip install anthropic`). Never commit `.env`. |
| `CLAUDE_MODEL` | `claude-haiku-5-5` | Only for `TRANSLATOR=claude`. |
| `WHISPER_MODEL` | `small` | `medium` is more accurate but ~2–3× slower (use with a GPU). |
| `WHISPER_DEVICE` | `auto` | `auto` uses an NVIDIA GPU (CUDA, float16) if available, else CPU (int8). |
| `SILENCE_MS` | `600` | Pause that ends a sentence. |
| `MAX_SEGMENT_S` | `10` | Long monologues are cut at the best pause before this length. |
| `VAD_THRESHOLD` | `0.5` | Raise to `0.6`–`0.7` if background noise triggers entries. |
| `PORT` | `8000` | Web page port. |

Restart the app after editing `.env`.

### GPU (optional)

With an NVIDIA GPU, Whisper and NLLB also need the CUDA 12 cuBLAS and cuDNN 9 libraries. The
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
Whisper: encode once → detect language (restricted to en/fr) → greedy decode
   ▼  filter silence / noise / hallucinations ("Thanks for watching", repeated lines…)
NLLB-200 (local) → {"source_lang", "translations": {...}}   (or Claude API if TRANSLATOR=claude)
   ▼
Browser feed (transcript appears first, translations fill in a moment later)
```

- `app/segmenter.py` – live VAD segmentation
- `app/transcriber.py` – Whisper, language restriction, hallucination filters
- `app/local_translator.py` – free offline NLLB-200 translation (default)
- `app/translator.py` – optional Claude API translation and error messages
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
- **"Missing API key"** – only with `TRANSLATOR=claude`. Set it back to `local` for free translation.
- **Nothing appears** – check the level meter moves; try another microphone in the list; move the
  phone closer; lower `VAD_THRESHOLD`.
- **Slow (> 4 s)** – stay on `WHISPER_MODEL=small` and the 600M NLLB model on CPU; `medium`
  and the 1.3B model need a GPU for live use.
- **Wrong language tag** – short utterances ("OK", "Oui") are hard to identify; Claude corrects
  the tag when it can tell from the text.

## Measured performance

Tested on a 4-core cloud CPU (no GPU) with synthetic English and French speech:

| Step | Time per sentence |
|---|---|
| Whisper `small` (speech → text) | 2.1–2.8 s |
| NLLB 600M (text → 2 languages) | 1.1–1.6 s |
| **Pause → translation on screen** (live, in the browser) | **~3.8–5.3 s** (the original text shows ~1.5 s earlier) |

That machine was also running the browser on the same 4 cores. A modern 6–8-core desktop CPU
should land around 3–4 s, and an NVIDIA GPU brings it under 2 s. Clear human speech transcribes
much better than the robotic test voice used here (which garbled some French words).

## License note

NLLB-200 models are released by Meta under CC-BY-NC 4.0: free for personal, non-commercial use.
