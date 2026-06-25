"""Speech-to-text: Groq Whisper (cloud, fast) with local faster-whisper fallback."""
import os
import tempfile

from . import config, audio

_local_model = None


def _local(audio_arr):
    global _local_model
    from faster_whisper import WhisperModel
    if _local_model is None:
        _local_model = WhisperModel(config.LOCAL_STT_MODEL, device="cpu", compute_type="int8")
    segments, _ = _local_model.transcribe(audio_arr, language="en", beam_size=1)
    return "".join(s.text for s in segments).strip()


def _groq(audio_arr):
    from openai import OpenAI
    path = os.path.join(tempfile.gettempdir(), "stt_in.wav")
    audio.save_wav(path, audio_arr)
    client = OpenAI(api_key=config.GROQ_API_KEY, base_url=config.GROQ_BASE_URL)
    with open(path, "rb") as f:
        r = client.audio.transcriptions.create(model=config.GROQ_STT_MODEL, file=f)
    return (r.text or "").strip()


def transcribe(audio_arr):
    """Transcribe a float32 mono 16k array to text."""
    if audio_arr is None or len(audio_arr) == 0:
        return ""
    if config.PREFER_CLOUD_STT and config.GROQ_API_KEY:
        try:
            return _groq(audio_arr)
        except Exception as e:
            print(f"[stt] cloud failed ({e}); using local")
    return _local(audio_arr)


def warm_up():
    """Preload the local model so the first local transcription isn't slow."""
    if not (config.PREFER_CLOUD_STT and config.GROQ_API_KEY):
        try:
            _local(audio.np.zeros(1600, dtype="float32"))
        except Exception:
            pass
