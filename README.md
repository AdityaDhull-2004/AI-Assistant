# AI Assistant

A fast, **voice- and text-controlled desktop assistant for Windows** with a native GUI.
It uses **free cloud LLMs** for speed and a **local model as a private, unlimited fallback**, so it
can both **answer online questions** and **act on your PC** — open/close apps, manage files,
control the system, search the web, check the weather, and more.

<p align="center"><i>Type or talk → it understands → it acts → it replies (and speaks).</i></p>

---

## Features

- **Triple-redundant brain** with automatic failover:
  1. **Groq** (Llama 3.3 70B) — primary, extremely fast, free tier
  2. **Google Gemini** (2.5 Flash) — cloud fallback, free tier
  3. **Local Ollama** (Qwen3 4B) — last-resort fallback: free, **unlimited**, fully private
- **Native desktop UI** (PySide6): chat bubbles, streaming replies, mic button, system tray.
- **Voice + text:** type or talk; replies are spoken with a natural Piper voice.
- **27 tools** across:
  - **Online:** web search, read/summarize a web page, weather
  - **Apps & windows:** open / close apps, focus / minimize / maximize / list windows
  - **Files:** read, write, delete (single or by pattern), copy, move, rename, search, create folders, list directories
  - **System:** volume, brightness, media keys, battery, system info, lock / sleep / restart / shutdown
- **Safety first:** risky actions (delete, overwrite, move, shell, power-off) require confirmation; every action is logged.
- **Privacy-aware:** microphone audio is transcribed **locally**; you choose what the assistant processes.

## How it works

```
 Voice ─► (local Whisper STT) ─┐
                               ├─► LLM:  Groq ─► Gemini ─► local Ollama   (streaming + tool-calling)
 Text  ───────────────────────┘                 │
                                                 ▼
                            tools (online + local desktop actions)
                                                 │
                                                 ▼
                              reply streamed to the UI + spoken (Piper)
```

## Quick start

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env      # then paste your free API keys into .env
.venv\Scripts\python.exe run.py
```

Get free API keys (no credit card):
- **Groq:** https://console.groq.com  → API Keys → Create
- **Gemini:** https://aistudio.google.com/apikey

**Full step-by-step instructions (including the optional local fallback and voice): see [SETUP.md](SETUP.md).**

## Usage

Press **Mic** and speak, or type a command. Examples:
- *"What's the weather in Mumbai?"*
- *"Search the web for the latest on \<topic\> and summarize it."*
- *"Open Calculator."* · *"Close Chrome."*
- *"Create a file on my desktop called notes.txt that says hello."*
- *"Set the volume to 30."* · *"Set brightness to 60."*
- *"Find all PDFs in my downloads."*

Risky actions pop a **Yes/No** confirmation. Close the window to quit.

## Project structure

```
app/
  config.py   # API keys, models, paths (loads .env)
  llm.py      # Groq + Gemini + Ollama client (streaming, tool-calling, failover)
  agent.py    # the think -> act -> observe loop
  tools.py    # all 27 tools + safety + audit log
  stt.py      # speech-to-text (local Whisper, optional cloud)
  tts.py      # text-to-speech (Piper + Windows fallback)
  audio.py    # microphone capture
  main.py     # PySide6 desktop UI
run.py        # entry point
requirements.txt
.env.example  # copy to .env and add your keys
```

## Privacy

- Your **microphone audio never leaves your PC** (speech is transcribed locally).
- The assistant only sends to the cloud LLM the **text of your request** and **the data a task needs**
  (e.g. a file's contents *only if* you ask it to read/summarize that file). It never scans or uploads your system.
- For fully offline/private operation, the **local Ollama** model can handle requests with nothing leaving your machine.
- API keys live in `.env`, which is git-ignored.

## Notes

- Built and tuned on Windows 11 (Intel i7-1260P, 16 GB RAM, integrated GPU).
- Free API tiers have rate limits (generous for personal use); the assistant fails over automatically.
- Some paths in `app/config.py` are machine-specific — adjust if you relocate the project (see SETUP.md).
