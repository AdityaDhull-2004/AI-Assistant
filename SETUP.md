# Setup Guide

A complete, beginner-friendly guide to getting the AI Assistant running on a fresh Windows PC.
Allow ~15 minutes. Everything here is free.

---

## 1. Prerequisites

| Requirement | Notes |
|---|---|
| **Windows 10/11** | The app uses Windows-specific features (apps, volume, windows). |
| **Python 3.12+** | Download from https://www.python.org/downloads/ — during install, tick **"Add Python to PATH"**. |
| **Git** (optional) | To clone the repo. Or just download the ZIP from GitHub. |
| **A microphone & speakers** | Only if you want voice. Text works without them. |

Optional (for the best experience — both free, set up later in this guide):
- **Ollama** — the local, unlimited, private fallback brain.
- **Piper** — a natural-sounding offline voice (otherwise the built-in Windows voice is used).

---

## 2. Get the project

**Option A — clone with Git:**
```powershell
git clone https://github.com/AdityaDhull-2004/AI-Assistant.git
cd AI-Assistant
```

**Option B — download ZIP:** on the GitHub page click **Code → Download ZIP**, extract it, and open a
PowerShell window inside the extracted folder.

---

## 3. Create the environment and install dependencies

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```
This creates an isolated environment and installs everything the app needs. (PySide6 is the biggest
download, ~100 MB; give it a minute.)

---

## 4. Get your free API keys

You need at least **one**. Groq is recommended as the fast primary; Gemini is a great free fallback.

### Groq (fast, recommended)
1. Go to **https://console.groq.com** and sign in (Google / GitHub / email).
2. Open **API Keys** in the left sidebar → **Create API Key** → name it → **Copy** it (starts with `gsk_`).

### Google Gemini (fallback)
1. Go to **https://aistudio.google.com/apikey** and sign in with a Google account.
2. Click **Create API key** → pick/create a project → **Copy** the key.
   *(Both `AIza...` and `AQ....` formats are valid.)*

> **Cost:** Both are **free tiers** — you are **never charged** unless you explicitly add billing.
> The only limit is rate (requests per minute/day), which is generous for personal use. If you hit a
> limit, the assistant automatically falls back to the next provider.

---

## 5. Configure your keys

Copy the template and edit it:
```powershell
copy .env.example .env
notepad .env
```
Paste your keys (no quotes, no trailing spaces):
```
GROQ_API_KEY=gsk_your_key_here
GEMINI_API_KEY=your_gemini_key_here
```
`.env` is git-ignored — your keys never get uploaded.

---

## 6. (Optional) Local fallback brain — Ollama

Gives you an **unlimited, fully-private** fallback that works even with no internet / when cloud limits hit.

1. Install Ollama from **https://ollama.com/download** (it auto-starts in the background).
2. Pull the model used by the app:
   ```powershell
   ollama pull hf.co/unsloth/Qwen3-4B-Instruct-2507-GGUF:Q4_K_M
   ollama cp hf.co/unsloth/Qwen3-4B-Instruct-2507-GGUF:Q4_K_M qwen3-fast
   ```
   *(To store models on another drive, set the `OLLAMA_MODELS` environment variable to a folder there.)*

The app detects Ollama automatically. If it isn't installed, the app simply skips this fallback.

---

## 7. (Optional) Natural voice — Piper

Without Piper, replies use the built-in Windows voice (works fine, just more robotic).

1. Download the Piper Windows binary from https://github.com/rhasspy/piper/releases and unzip it.
2. Download a voice, e.g. `en_US-amy-medium.onnx` **and** `en_US-amy-medium.onnx.json` from
   https://huggingface.co/rhasspy/piper-voices (under `en/en_US/amy/medium/`).
3. Put the two voice files in `models/piper/` inside the project.
4. Open `app/config.py` and set `PIPER_EXE` to the path of your `piper.exe`.

---

## 8. Run it

```powershell
.venv\Scripts\python.exe run.py
```
(or double-click `run.bat`). A dark chat window opens. The status bar shows which providers are active.

- **Type** a command and press Enter, **or** click **Mic** and speak.
- Replies stream in and are spoken aloud (toggle **"Speak replies"**).
- **Risky actions** (delete/overwrite/move/shell/power) show a **Yes/No** dialog.
- **To quit:** close the window (the X).

---

## 9. Things to try

- *"What's the weather in \<city\>?"*
- *"Search the web for \<topic\> and summarize the top results."*
- *"Open Notepad."* · *"Close Calculator."*
- *"Create a file on my desktop called todo.txt with my shopping list: milk, eggs, bread."*
- *"Set the volume to 25."* · *"Lock my screen."*
- *"Find all the PDFs in my Downloads folder."*

---

## 10. Troubleshooting

| Problem | Fix |
|---|---|
| **"No API keys found"** | Make sure `.env` exists (not `.env.example`) and has a key. Restart the app. |
| **429 / rate limit** | You hit a free-tier limit; it auto-fails over. Wait ~30s, or add a second provider / Ollama. |
| **Gemini 429 with `limit: 0`** | Use model `gemini-2.5-flash` (already the default) — older models have no free quota. |
| **No speech detected** | Check Windows **Settings → Privacy → Microphone** is on; make sure the mic isn't muted. |
| **Robotic voice** | Set up Piper (Section 7) for a natural voice. |
| **Ctrl+C won't stop it** | GUI apps ignore Ctrl+C — just close the window, or use the tray icon's Quit. |
| **Wrong file paths** | The app resolves Desktop/Documents/etc. automatically (incl. OneDrive). Paths in `app/config.py` are machine-specific. |

---

## 11. Privacy summary

- **Microphone audio stays on your PC** (transcribed locally with Whisper).
- The cloud LLM only receives your **request text** and **data a specific task needs** (e.g. a file's
  contents *only* when you ask it to read that file). The app never scans or bulk-uploads your files.
- For zero-cloud operation, rely on the **local Ollama** model.
- Keep your `.env` private; it is git-ignored by default.
