"""Central configuration. Loads API keys from .env and defines models/paths."""
import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

# Keep model caches on E:
os.environ.setdefault("HF_HOME", r"E:\Claude\caches\hf")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

# ---- API keys (from .env; never hard-code) ----
GROQ_API_KEY   = os.getenv("GROQ_API_KEY", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

# ---- Providers (both via OpenAI-compatible API) ----
GROQ_BASE_URL   = "https://api.groq.com/openai/v1"
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
GROQ_MODEL      = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GEMINI_MODEL    = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")  # 2.5-flash has free quota (2.0 does not)

# ---- Local fallback brain (Ollama) - free, unlimited, private ----
OLLAMA_BASE_URL = "http://127.0.0.1:11434/v1"
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3-fast")


def ollama_available(timeout=1.5):
    import socket
    try:
        s = socket.create_connection(("127.0.0.1", 11434), timeout=timeout)
        s.close()
        return True
    except Exception:
        return False


# ---- Speech-to-text ----
GROQ_STT_MODEL   = "whisper-large-v3-turbo"   # fast cloud STT (only if PREFER_CLOUD_STT=True)
LOCAL_STT_MODEL  = "base.en"                   # local STT (default, keeps your voice on-device)
PREFER_CLOUD_STT = False                        # PRIVACY: transcribe voice locally, never upload audio

# ---- Text-to-speech (Piper, local) ----
PIPER_EXE   = r"E:\Claude\tools\piper\piper.exe"
PIPER_VOICE = str(ROOT / "models" / "piper" / "en_US-amy-medium.onnx")
PIPER_OUT   = r"E:\Claude\caches\tts_out.wav"

# ---- Audio capture ----
SAMPLE_RATE   = 16000
SILENCE_MS    = 900
MAX_SECONDS   = 20
START_TIMEOUT = 7
RMS_THRESHOLD = 0.012

AUDIT_LOG = str(ROOT / "assistant.log")


def providers_configured():
    names = []
    if GROQ_API_KEY:
        names.append("Groq")
    if GEMINI_API_KEY:
        names.append("Gemini")
    if ollama_available():
        names.append("Local (Ollama)")
    return names
