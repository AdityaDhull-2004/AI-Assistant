"""Text-to-speech: Piper (local neural voice) with Windows SAPI fallback."""
import os
import subprocess
import winsound

from . import config

_enabled = True


def set_enabled(on: bool):
    global _enabled
    _enabled = bool(on)


def is_enabled():
    return _enabled


def _windows(text):
    import pyttsx3
    eng = pyttsx3.init()
    eng.setProperty("rate", 180)
    eng.say(text)
    eng.runAndWait()
    eng.stop()


def speak(text):
    if not _enabled or not text:
        return
    if os.path.exists(config.PIPER_EXE) and os.path.exists(config.PIPER_VOICE):
        try:
            subprocess.run(
                [config.PIPER_EXE, "-m", config.PIPER_VOICE, "-f", config.PIPER_OUT],
                input=text.encode("utf-8"),
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True,
            )
            winsound.PlaySound(config.PIPER_OUT, winsound.SND_FILENAME)
            return
        except Exception as e:
            print(f"[tts] piper failed ({e}); using Windows voice")
    try:
        _windows(text)
    except Exception as e:
        print(f"[tts] failed: {e}")
