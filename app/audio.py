"""Microphone capture with simple voice-activity (silence) detection."""
import time
import queue
import wave
import numpy as np
import sounddevice as sd

from . import config


def record_until_silence():
    """Record from the default mic until the user pauses. Returns float32 mono audio or None."""
    q = queue.Queue()
    block_ms = 30
    blocksize = int(config.SAMPLE_RATE * block_ms / 1000)
    needed_silence = int(config.SILENCE_MS / block_ms)

    def cb(indata, frames, t, status):
        q.put(indata.copy())

    frames, started, silent = [], False, 0
    with sd.InputStream(samplerate=config.SAMPLE_RATE, channels=1, dtype="float32",
                        blocksize=blocksize, callback=cb):
        start = time.time()
        while True:
            try:
                block = q.get(timeout=0.2)
            except queue.Empty:
                block = None
            if block is None:
                if not started and time.time() - start > config.START_TIMEOUT:
                    return None
                continue
            rms = float(np.sqrt(np.mean(block ** 2)))
            if not started:
                if rms > config.RMS_THRESHOLD:
                    started = True
                    frames.append(block)
                elif time.time() - start > config.START_TIMEOUT:
                    return None
            else:
                frames.append(block)
                silent = silent + 1 if rms < config.RMS_THRESHOLD else 0
                if silent >= needed_silence:
                    break
                if sum(len(f) for f in frames) / config.SAMPLE_RATE > config.MAX_SECONDS:
                    break
    if not frames:
        return None
    return np.concatenate(frames).flatten().astype(np.float32)


def save_wav(path, audio, samplerate=None):
    sr = samplerate or config.SAMPLE_RATE
    pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
