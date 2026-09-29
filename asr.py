"""ASR providers: local faster-whisper, or Sarvam (Bangla-first API). Returns [{start,end,text}]."""
import glob
import os
import subprocess
import tempfile
import time


def transcribe_media(path, provider=None):
    provider = provider or os.getenv("ASR_PROVIDER", "local")
    if provider == "sarvam":
        return _sarvam(path)
    return _local(path)


def _local(path):
    from faster_whisper import WhisperModel
    model = WhisperModel(os.getenv("WHISPER_MODEL", "small"), device="auto", compute_type="auto")
    lang = os.getenv("ASR_LANG") or None
    if lang and "-" in lang:  # allow bn-IN style
        lang = lang.split("-")[0]
    if lang == "unknown":
        lang = None
    segs, _ = model.transcribe(str(path), language=lang, vad_filter=True, beam_size=5)
    return [{"start": s.start, "end": s.end, "text": s.text.strip()} for s in segs]


def _sarvam(path, chunk=None):
    """Sarvam REST accepts <=30s per request -> split with ffmpeg into short WAV chunks."""
    import httpx
    chunk = chunk or int(os.getenv("ASR_CHUNK_SEC", "25"))
    key = os.environ["SARVAM_API_KEY"]
    model = os.getenv("SARVAM_MODEL", "saaras:v3")
    lang = os.getenv("ASR_LANG") or "bn-IN"
    segs = []
    with tempfile.TemporaryDirectory() as d:
        subprocess.run(["ffmpeg", "-y", "-i", str(path), "-vn", "-ac", "1", "-ar", "16000",
                        "-f", "segment", "-segment_time", str(chunk), "-c:a", "pcm_s16le",
                        f"{d}/c_%05d.wav"], check=True, capture_output=True)
        for i, f in enumerate(sorted(glob.glob(f"{d}/c_*.wav"))):
            data = {"language_code": lang, "model": model}
            if model.startswith("saaras"):
                data["mode"] = "transcribe"
            r = None
            for attempt in range(4):
                with open(f, "rb") as fh:
                    r = httpx.post("https://api.sarvam.ai/speech-to-text",
                                   headers={"api-subscription-key": key},
                                   files={"file": (os.path.basename(f), fh, "audio/wav")},
                                   data=data, timeout=120)
                if r.status_code == 429:
                    time.sleep(2 ** attempt * 2)
                    continue
                r.raise_for_status()
                break
            else:
                r.raise_for_status()
            text = (r.json().get("transcript") or "").strip()
            if text:
                segs.append({"start": i * chunk, "end": (i + 1) * chunk, "text": text})
    return segs
