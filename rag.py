"""YouTube Topic-RAG core.
Pipeline: download -> transcript (captions | Whisper) -> semantic chunking -> index
-> query rewrite -> hybrid retrieval (dense+BM25, RRF) -> cross-encoder rerank
-> corrective grading -> segment merge + ffmpeg clip -> grounded structured answer
-> claim verification (drop unsupported points).
"""
import contextvars
import copy
import os
import re
import json
import time
import shutil
import subprocess
import uuid
from pathlib import Path

import numpy as np
from dotenv import load_dotenv

load_dotenv()


def _refresh_windows_path():
    """Windows: tools installed by winget (ffmpeg, deno) land on PATH only for NEW sessions.
    Merge the registry PATH + known winget dirs so they work without reopening the terminal."""
    if os.name != "nt":
        return
    dirs = []
    try:
        import winreg
        for root, sub in ((winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
                          (winreg.HKEY_CURRENT_USER, "Environment")):
            try:
                with winreg.OpenKey(root, sub) as k:
                    dirs += os.path.expandvars(winreg.QueryValueEx(k, "Path")[0]).split(";")
            except OSError:
                pass
    except ImportError:
        pass
    import glob
    la, home = os.getenv("LOCALAPPDATA", ""), os.path.expanduser("~")
    dirs += [os.path.join(la, "Microsoft", "WinGet", "Links"), os.path.join(home, ".deno", "bin")]
    dirs += glob.glob(os.path.join(la, "Microsoft", "WinGet", "Packages", "Gyan.FFmpeg*", "*", "bin"))
    dirs += glob.glob(os.path.join(la, "Microsoft", "WinGet", "Packages", "DenoLand.Deno*"))
    cur = os.environ.get("PATH", "").split(";")
    add = [d for d in dirs if d and os.path.isdir(d) and d not in cur]
    if add:
        os.environ["PATH"] = ";".join(cur + add)


_refresh_windows_path()
DATA = Path(os.getenv("DATA_DIR", "data"))
LIBRARY = Path(os.getenv("LIBRARY_DIR", "library"))  # pre-built indexes baked into the deploy
for _d in ("videos", "index", "clips"):
    (DATA / _d).mkdir(parents=True, exist_ok=True)
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".opus"}
SUB_EXT = {".srt", ".vtt"}


def env(k, d=""):
    return os.getenv(k, d)


MODES = ("dense", "bm25", "hybrid", "hybrid+rerank")
_S = contextvars.ContextVar("rag_stats", default=None)  # per-request counters (LLM/embedding usage)


def _stat(key, n=1):
    st = _S.get()
    if st is not None:
        st[key] = st.get(key, 0) + n


def sync_library():
    """Copy pre-built indexes (library/index) into the runtime data dir (free hosts have ephemeral disk)."""
    src, n = LIBRARY / "index", 0
    if src.exists():
        for f in src.glob("*"):
            dst = DATA / "index" / f.name
            if not dst.exists():
                shutil.copy(f, dst)
                n += 1
    return n


# ------------------------------------------------------------------ helpers
def extract_video_id(s):
    s = s.strip()
    m = re.search(r"(?:v=|youtu\.be/|shorts/|embed/)([A-Za-z0-9_-]{11})", s)
    if m:
        return m.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", s):
        return s
    raise ValueError("Invalid YouTube URL / video id")


def fmt(t):
    t = int(t)
    h, r = divmod(t, 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def yt_link(vid, start):
    return f"https://www.youtube.com/watch?v={vid}&t={int(start)}s"


# NOTE: \w+ breaks Bangla words (vowel signs are not \w), so split on separators instead.
def tokenize(text):
    return re.findall(r'[^\s.,;:!?"\'()\[\]{}।|\-–—/]+', text.lower())


def parse_json(txt):
    txt = re.sub(r"^```(?:json)?|```$", "", (txt or "").strip(), flags=re.M).strip()
    try:
        return json.loads(txt)
    except Exception:
        m = re.search(r"\{.*\}", txt, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
    return None


# ---------------------------------------------------------------------- LLM
_client = None


def llm(system, user, temperature=0.1, max_tokens=1500):
    """Any OpenAI-compatible API (OpenAI, Gemini, Groq, OpenRouter...) via env vars."""
    global _client
    if _client is None:
        from openai import OpenAI
        _client = OpenAI(api_key=os.environ["LLM_API_KEY"],
                         base_url=os.getenv("LLM_BASE_URL") or None, max_retries=1, timeout=90)
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    gem = "generativelanguage" in env("LLM_BASE_URL")
    models = [os.getenv("LLM_MODEL", "gpt-4o-mini")]
    # Free-tier quotas are per model (e.g. 15 requests/min each), so on 429/503 rotate through a pool.
    fbs = os.getenv("LLM_FALLBACK_MODELS", DEFAULT_GEMINI_FALLBACKS if gem else "")
    models += [m.strip() for m in fbs.split(",") if m.strip() and m.strip() not in models]
    rounds = int(env("LLM_BUSY_ROUNDS", "4"))
    for rnd in range(rounds):
        try:
            return _llm_try(models, msgs, temperature, max_tokens, gem)
        except _AllBusy as e:
            if rnd == rounds - 1:
                raise e.last
            _stat("llm_waits")
            time.sleep(min(e.wait, 65))   # every model rate-limited: wait out the per-minute window


DEFAULT_GEMINI_FALLBACKS = "gemini-3.5-flash-lite,gemini-3-flash-preview,gemini-flash-lite-latest"


class _AllBusy(Exception):
    def __init__(self, last, wait):
        super().__init__(str(last))
        self.last, self.wait = last, wait


_COOL = {}  # model -> time until which it is rate-limited (skip it instead of wasting a round-trip)


def _llm_try(models, msgs, temperature, max_tokens, gem):
    wait = None
    t = time.time()
    ready = [m for m in models if _COOL.get(m, 0) <= t]
    models = ready + [m for m in models if m not in ready]   # cooling models last, as a final resort
    for i, m in enumerate(models):
        kw = dict(model=m, messages=msgs, temperature=temperature, max_tokens=max_tokens)
        # Gemini 3.x "thinks" by default and thinking tokens eat max_tokens -> empty replies.
        # Measured (Sep 2026, free tier): flash + reasoning_effort=none -> ~2s and a real answer;
        # flash-lite rejects "none" (400) but doesn't need it. LLM_REASONING=low|medium for harder answers.
        effort = env("LLM_REASONING", "none") if gem else ""
        if gem and "lite" in m and effort == "none":
            effort = ""
        if effort:
            kw["reasoning_effort"] = effort
            if effort != "none":
                kw["max_tokens"] = max_tokens + 2048
        try:
            try:
                r = _client.chat.completions.create(**kw)
            except Exception as e:
                if getattr(e, "status_code", None) != 400 or "reasoning_effort" not in kw:
                    raise
                kw.pop("reasoning_effort"); kw["max_tokens"] = max_tokens + 2048
                r = _client.chat.completions.create(**kw)
            if not (r.choices[0].message.content or "").strip() and r.choices[0].finish_reason == "length":
                kw.pop("reasoning_effort", None); kw["max_tokens"] = kw["max_tokens"] + 2048
                r = _client.chat.completions.create(**kw)   # thinking ate the budget: once more, bigger
            break
        except Exception as e:
            code = getattr(e, "status_code", None)
            if code not in (404, 429, 500, 502, 503, 504):
                raise
            mw = re.search(r"retryDelay'?\"?:\s*'?\"?(\d+)", str(e))
            d = float(mw.group(1)) + 1 if mw else 20.0
            wait = d if wait is None else min(wait, d)
            if code == 429:
                _COOL[m] = time.time() + max(d, 30)
            _stat("llm_fallbacks")
            if i == len(models) - 1:
                raise _AllBusy(e, wait)
    out = r.choices[0].message.content or ""
    _stat("llm_calls")
    _stat("llm_in_chars", sum(len(x["content"]) for x in msgs))
    _stat("llm_out_chars", len(out))
    return out


# --------------------------------------------------------- embeddings/rerank
_emb = None
_embc = None
_rr = None


def emb_model():
    m = env("EMB_API_MODEL")
    if m:
        return m
    return "gemini-embedding-001" if "generativelanguage" in env("LLM_BASE_URL") else "text-embedding-3-small"


def emb_id():
    if env("EMB_PROVIDER", "api") == "local":
        return "local:" + env("EMB_MODEL", "intfloat/multilingual-e5-small")
    return "api:" + emb_model()


def embed(texts, kind="passage", batch=32):
    """EMB_PROVIDER=api (default, light: fits 512MB hosts) | local (sentence-transformers)."""
    texts = [t[:6000] for t in texts]
    if not texts:
        return np.zeros((0, 1), dtype="float32")
    _stat("embed_calls")
    _stat("embed_texts", len(texts))
    if env("EMB_PROVIDER", "api") == "local":
        global _emb
        if _emb is None:
            from sentence_transformers import SentenceTransformer
            _emb = SentenceTransformer(env("EMB_MODEL", "intfloat/multilingual-e5-small"))
        pref = "query: " if kind == "query" else "passage: "
        v = _emb.encode([pref + t for t in texts], normalize_embeddings=True,
                        batch_size=batch, show_progress_bar=False)
        return np.asarray(v, dtype="float32")
    global _embc
    if _embc is None:
        from openai import OpenAI
        _embc = OpenAI(api_key=env("EMB_API_KEY") or os.environ["LLM_API_KEY"],
                       base_url=env("EMB_BASE_URL") or env("LLM_BASE_URL") or None)
    todo = [t for t in dict.fromkeys(texts) if not (kind == "query" and (emb_model(), t) in _QCACHE)]
    got = {}
    for i in range(0, len(todo), batch):
        for attempt in range(5):
            try:
                r = _embc.embeddings.create(model=emb_model(), input=todo[i:i + batch])
                got.update({t: d.embedding for t, d in zip(todo[i:i + batch], r.data)})
                break
            except Exception as e:
                if attempt == 4 or "PerDay" in str(e):   # daily free quota gone: fail fast, caller degrades
                    raise
                time.sleep(2 ** attempt)
    if kind == "query":
        for t, e in got.items():
            if len(_QCACHE) > 5000:
                _QCACHE.clear()
            _QCACHE[(emb_model(), t)] = e
        got = {t: got.get(t) or _QCACHE[(emb_model(), t)] for t in texts}
    v = np.asarray([got[t] for t in texts], dtype="float32")
    return v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-9)


_QCACHE = {}  # query-embedding cache: same question / rewritten query -> no extra embedding call


def rerank_scores(query, texts):
    """RERANK_PROVIDER=cross-encoder (local model)."""
    global _rr
    if _rr is None:
        from sentence_transformers import CrossEncoder
        _rr = CrossEncoder(env("RERANK_MODEL", "BAAI/bge-reranker-v2-m3"), max_length=512)
    return list(map(float, _rr.predict([(query, t) for t in texts])))


def rerank_llm(question, texts):
    """RERANK_PROVIDER=llm (default): listwise rerank with the LLM, no local model needed."""
    ev = "\n\n".join(f"[{i}] {t[:500]}" for i, t in enumerate(texts))
    out = parse_json(llm("You rank transcript passages by how directly they explain the topic.",
                         f"Topic: {question}\n\n{ev}\n\nReturn JSON: {{\"order\": [passage indices, "
                         "most relevant first]}}", max_tokens=200))
    order = [i for i in (out or {}).get("order", []) if isinstance(i, int) and 0 <= i < len(texts)]
    rank = {i: p for p, i in enumerate(order)}
    return [float(len(texts) - rank[i]) if i in rank else 0.0 for i in range(len(texts))]


# ------------------------------------------------------- download/transcript
def download_video(vid):
    out = DATA / "videos" / f"{vid}.mp4"
    if find_media(vid):
        return find_media(vid), vid
    import yt_dlp
    opts = {
        "format": "bv*[height<=480]+ba/b[height<=480]/b",
        "merge_output_format": "mp4",
        "outtmpl": str(DATA / "videos" / f"{vid}.%(ext)s"),
        "quiet": True, "noprogress": True,
    }
    if env("YT_COOKIES_FROM_BROWSER"):  # last resort for "Sign in to confirm you're not a bot"
        opts["cookiesfrombrowser"] = (env("YT_COOKIES_FROM_BROWSER"),)
    with yt_dlp.YoutubeDL(opts) as y:
        info = y.extract_info(f"https://www.youtube.com/watch?v={vid}", download=True)
    if not out.exists():
        raise RuntimeError("yt-dlp finished but mp4 not found (ffmpeg installed?)")
    return out, info.get("title", vid)


def fetch_title(vid):
    """Video title via YouTube oEmbed (no download needed); falls back to the id."""
    try:
        import httpx
        r = httpx.get("https://www.youtube.com/oembed", timeout=8,
                      params={"url": f"https://www.youtube.com/watch?v={vid}", "format": "json"})
        return r.json().get("title") or vid if r.status_code == 200 else vid
    except Exception:
        return vid


def fetch_captions(vid, langs=("bn", "en", "hi")):
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        try:  # v1.x
            tr = YouTubeTranscriptApi().fetch(vid, languages=list(langs))
            return [{"start": s.start, "end": s.start + s.duration, "text": s.text} for s in tr]
        except AttributeError:  # v0.6.x
            tr = YouTubeTranscriptApi.get_transcript(vid, languages=list(langs))
            return [{"start": t["start"], "end": t["start"] + t["duration"], "text": t["text"]}
                    for t in tr]
    except Exception:
        return None


def transcribe(video_path):
    import asr
    return asr.transcribe_media(video_path)


_SUB_T = re.compile(r"(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{1,3})\s*-->\s*(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{1,3})")


def _sec(h, m, s, ms):
    return int(h or 0) * 3600 + int(m) * 60 + int(s) + int(ms.ljust(3, "0")) / 1000


def parse_subtitles(text):
    """SRT / VTT -> segments."""
    segs, lines, i = [], text.replace("\r", "").split("\n"), 0
    while i < len(lines):
        m = _SUB_T.search(lines[i])
        if not m:
            i += 1
            continue
        g = m.groups()
        s0, e0 = _sec(*g[:4]), _sec(*g[4:])
        i += 1
        buf = []
        while i < len(lines) and lines[i].strip():
            buf.append(re.sub(r"<[^>]+>", "", lines[i]).strip())
            i += 1
        if buf:
            segs.append({"start": s0, "end": e0, "text": " ".join(buf)})
    return segs


def find_media(vid):
    for p in sorted((DATA / "videos").glob(f"{vid}.*")):
        if p.suffix not in (".part", ".ytdl"):
            return p
    return None


def clean_segments(segs):
    out = []
    for s in sorted(segs, key=lambda x: x["start"]):
        t = re.sub(r"\[[^\]]*\]", "", s["text"]).replace("\n", " ").strip()
        if not t:
            continue
        e = s["end"] if s["end"] > s["start"] else s["start"] + 1.0
        out.append({"start": float(s["start"]), "end": float(e), "text": t})
    return out


# -------------------------------------------------------- semantic chunking
def make_chunk(cur):
    return {"start": cur[0]["start"], "end": cur[-1]["end"],
            "text": " ".join(s["text"] for s in cur),
            "segs": [[s["start"], s["text"]] for s in cur]}


def lexical_vectors(texts):
    """TF-IDF vectors (no model/API): topic-shift signal that works for Bangla and English."""
    toks = [tokenize(t) for t in texts]
    n = len(texts)
    df = {}
    for t in toks:
        for w in set(t):
            df[w] = df.get(w, 0) + 1
    vocab = [w for w, c in sorted(df.items(), key=lambda x: -x[1])
             if c >= 2 and (n < 6 or c <= 0.5 * n)][:6000]
    idx = {w: i for i, w in enumerate(vocab)}
    M = np.zeros((n, max(len(vocab), 1)), dtype="float32")
    for r, t in enumerate(toks):
        for w in t:
            if w in idx:
                M[r, idx[w]] += np.log(1 + n / df[w])
    return M / (np.linalg.norm(M, axis=1, keepdims=True) + 1e-9)


def segment_vectors(texts, signal=None):
    signal = signal or env("CHUNK_SIGNAL", "lexical")
    return embed(texts, "passage") if signal == "embedding" else lexical_vectors(texts)


def semantic_chunks(segs, min_dur=20.0, max_dur=90.0, w=3, k=0.5, info=None, signal=None):
    """Split where adjacent windows of the transcript stop being similar (topic shift).
    info (dict) is filled with the similarity curve/threshold/boundaries for the RAG Lab visualiser."""
    n = len(segs)
    if n == 0:
        return []
    E = segment_vectors([s["text"] for s in segs], signal)
    sims = []
    for i in range(n - 1):
        a = E[max(0, i - w + 1): i + 1].mean(0)
        b = E[i + 1: i + 1 + w].mean(0)
        sims.append(float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9)))
    thr = (float(np.mean(sims)) - k * float(np.std(sims))) if sims else 0.0
    chunks, cur, bounds = [], [], []
    for i, s in enumerate(segs):
        cur.append(s)
        dur = s["end"] - cur[0]["start"]
        boundary = i < n - 1 and ((sims[i] < thr and dur >= min_dur) or dur >= max_dur)
        if boundary or i == n - 1:
            chunks.append(make_chunk(cur))
            bounds.append(i)
            cur = []
    if info is not None:
        info.update(signal=signal or env("CHUNK_SIGNAL", "lexical"), thr=round(thr, 4), k=k, window=w,
                    min_dur=min_dur, max_dur=max_dur, sims=[round(x, 3) for x in sims],
                    t=[round(segs[i + 1]["start"], 1) for i in range(n - 1)], boundaries=bounds)
    return chunks


def enrich(chunks, title):
    """Contextual enrichment: 1-line 'what is this passage about' prepended for indexing."""
    for c in chunks:
        try:
            c["ctx"] = llm("You label transcript passages.",
                           f"Video title: {title}\nPassage: {c['text'][:1200]}\n"
                           "Write ONE short line (max 25 words) saying what topic this passage "
                           "covers inside the video. Same language as the passage.",
                           max_tokens=80).strip()
        except Exception:
            c["ctx"] = ""


def index_text(c):
    return f"{c.get('ctx', '')} {c['text']}".strip()


# ------------------------------------------------------------------- index
class VideoIndex:
    def __init__(self, meta, chunks, E, extra=None):
        from rank_bm25 import BM25Okapi
        self.meta, self.chunks, self.E, self.extra = meta, chunks, E, extra or {}
        self.bm25 = BM25Okapi([tokenize(index_text(c)) or ["_"] for c in chunks])


_cache = {}
sync_library()


def index_exists(vid):
    return (DATA / "index" / f"{vid}.json").exists()


def save_index(vid, meta, chunks, E, extra=None):
    (DATA / "index" / f"{vid}.json").write_text(
        json.dumps({"meta": meta, "chunks": chunks, "extra": extra or {}}, ensure_ascii=False), encoding="utf-8")
    np.save(DATA / "index" / f"{vid}.npy", E)
    _cache.pop(vid, None)


def load_index(vid):
    if vid in _cache:
        return _cache[vid]
    p = DATA / "index" / f"{vid}.json"
    if not p.exists():
        raise FileNotFoundError(f"video {vid} is not indexed yet")
    d = json.loads(p.read_text(encoding="utf-8"))
    got = d["meta"].get("emb_id")
    if got and got != emb_id():
        raise RuntimeError(f"index built with {got} but current embedding config is {emb_id()} "
                           "(re-index, or set EMB_* env to match)")
    _cache[vid] = VideoIndex(d["meta"], d["chunks"], np.load(DATA / "index" / f"{vid}.npy"), d.get("extra"))
    return _cache[vid]


YT_BLOCK_MSG = ("YouTube blocked this server (cloud IPs are blocked) or has no captions. Use: "
                "(1) Chrome extension, (2) Add-video tab: upload video/audio/.srt, or "
                "(3) index locally with prepare.py and put it in library/.")


def build_index_from_segments(vid, title, segs, source, media=None, kind="youtube",
                              progress=lambda m: None, media_url=None):
    segs = clean_segments(segs)
    if not segs:
        raise RuntimeError("Empty transcript")
    progress("Chunking...")
    cinfo = {}
    chunks = semantic_chunks(segs, info=cinfo)
    if env("ENRICH", "0") == "1":
        progress("Contextual enrichment (LLM)...")
        enrich(chunks, title)
    progress("Embedding...")
    E = embed([index_text(c) for c in chunks], "passage")
    meta = {"video_id": vid, "title": title, "source": source, "kind": kind,
            "n_chunks": len(chunks), "has_video": media is not None, "media_url": media_url,
            "duration": segs[-1]["end"], "emb_id": emb_id()}
    save_index(vid, meta, chunks, E, {"chunking": cinfo})
    return meta


def build_index(url, force_asr=False, progress=lambda m: None):
    vid = extract_video_id(url)
    if index_exists(vid):
        return load_index(vid).meta
    if env("YT_LIVE", "1") == "0":
        raise RuntimeError(YT_BLOCK_MSG)
    path, title = None, vid
    # Default: NO download - read captions straight from YouTube and play segments in the embedded player.
    # YT_DOWNLOAD=1 also downloads the mp4 (only needed for clip files / ASR on caption-less videos).
    if env("YT_DOWNLOAD", "0") == "1" or force_asr:
        progress("Downloading video...")
        try:
            path, title = download_video(vid)
        except Exception as e:
            m = str(e)
            hint = (" [yt-dlp needs Deno + yt-dlp[default]; see docs/LIVE_DEMO.md]"
                    if re.search(r"JavaScript|Sign in|bot|challenge", m, re.I) else "")
            progress(f"Download failed ({m[:80]}){hint}; continuing with captions only (no clip files)")
    if path is None:
        title = fetch_title(vid)
    progress("Fetching captions...")
    segs = None if force_asr else fetch_captions(vid)
    source = "captions"
    if not segs:
        if path is None:
            if env("YT_DOWNLOAD", "0") != "1":
                raise RuntimeError("এই video-তে caption পাওয়া যায়নি / no captions found for this video. "
                                   "Caption আছে এমন video বেছে নাও, অথবা audio/.srt upload করো (বা YT_DOWNLOAD=1 + ASR)।")
            raise RuntimeError(YT_BLOCK_MSG)
        progress("Transcribing (ASR)...")
        segs = transcribe(path)
        source = env("ASR_PROVIDER", "local")
    return build_index_from_segments(vid, title, segs, source, path, "youtube", progress)


def build_index_from_upload(path, title, progress=lambda m: None, youtube_url=None):
    """Own video/audio (ASR) or .srt/.vtt (optionally paired with a YouTube URL -> embedded player)."""
    path = Path(path)
    ext = path.suffix.lower()
    if ext in SUB_EXT:
        segs = parse_subtitles(path.read_text(encoding="utf-8", errors="ignore"))
        vid = extract_video_id(youtube_url) if youtube_url else "up_" + uuid.uuid4().hex[:8]
        return build_index_from_segments(vid, title, segs, "subtitle", None,
                                         "youtube" if youtube_url else "upload", progress)
    vid = "up_" + uuid.uuid4().hex[:8]
    final = DATA / "videos" / f"{vid}{ext}"
    shutil.move(str(path), final)
    progress("Transcribing (ASR)...")
    segs = transcribe(final)
    return build_index_from_segments(vid, title, segs, env("ASR_PROVIDER", "local"), final,
                                     "upload", progress, "/media/" + final.name)


def list_library():
    out = []
    for p in sorted((DATA / "index").glob("*.json")):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8"))["meta"])
        except Exception:
            pass
    return out


# ----------------------------------------------------------------- retrieval
def trim_chunk(c, t):
    """Progress-aware: hide everything after time t (spoiler-free)."""
    if t is None or c["end"] <= t:
        return c
    keep = [s for s in c["segs"] if s[0] < t]
    if not keep:
        return None
    return {**c, "segs": keep, "text": " ".join(s[1] for s in keep), "end": min(c["end"], t)}


def _row(ix, i, **kw):
    c = ix.chunks[i]
    return {"idx": i, "start": c["start"], "end": c["end"], **kw}


def retrieve(ix, queries, question, k=8, max_time=None, mode="hybrid+rerank", pool=20, dbg=None):
    """mode: dense | bm25 | hybrid | hybrid+rerank. dbg (dict) collects every stage for the RAG Lab."""
    if isinstance(queries, str):
        queries = [queries]
    allowed = [i for i, c in enumerate(ix.chunks) if max_time is None or c["start"] < max_time]
    if not allowed:
        return []
    rankings = []
    qvecs = None
    if mode in ("dense", "hybrid", "hybrid+rerank"):
        try:
            qvecs = embed(queries, "query")
        except Exception as e:   # embedding quota/outage: degrade to BM25 instead of failing the question
            _stat("dense_failed")
            if dbg is not None:
                dbg["dense_error"] = str(e)[:160]
            if mode == "dense":
                raise
    if qvecs is not None:
        for q, qv in zip(queries, qvecs):
            sc = ix.E @ qv
            rankings.append(sorted(allowed, key=lambda i: -sc[i]))
            if dbg is not None:
                dbg.setdefault("rankings", []).append({"kind": "dense", "query": q, "top": [
                    _row(ix, i, score=round(float(sc[i]), 4)) for i in rankings[-1][:6]]})
    if mode in ("bm25", "hybrid", "hybrid+rerank"):
        for q in queries:
            sc = ix.bm25.get_scores(tokenize(q))
            rankings.append([i for i in sorted(allowed, key=lambda i: -sc[i]) if sc[i] > 0])
            if dbg is not None:
                dbg.setdefault("rankings", []).append({"kind": "bm25", "query": q, "top": [
                    _row(ix, i, score=round(float(sc[i]), 3)) for i in rankings[-1][:6]]})
    fused = {}
    for r in rankings:
        for rank, i in enumerate(r):  # Reciprocal Rank Fusion
            fused[i] = fused.get(i, 0.0) + 1.0 / (60 + rank)
    order = sorted(fused, key=lambda i: -fused[i])[:pool]
    trimmed = {i: trim_chunk(ix.chunks[i], max_time) for i in order}
    order = [i for i in order if trimmed[i]]
    if dbg is not None:
        dbg["fused"] = [_row(ix, i, rrf=round(fused[i], 5)) for i in order[:10]]
    prov = env("RERANK_PROVIDER", "llm")  # llm | cross-encoder | none
    if mode == "hybrid+rerank" and prov != "none" and len(order) > 1:
        before = list(order)
        head = order[:12] if prov == "llm" else order
        txt = [trimmed[i]["text"] for i in head]
        sc = rerank_llm(question, txt) if prov == "llm" else rerank_scores(question, txt)
        head = [head[j] for j in sorted(range(len(head)), key=lambda j: -sc[j])]
        order = head + order[len(head):]
        if dbg is not None:
            dbg["rerank"] = {"provider": prov, "before": before[:10], "after": order[:10]}
    if dbg is not None:
        dbg["final"] = order[:k]
    return [{**trimmed[i], "idx": i, "score": 1.0 / (1 + pos)}
            for pos, i in enumerate(order[:k])]


# ------------------------------------------------- query rewrite / grading
def rewrite_query(question, title, broader=False):
    qs = [question]
    try:
        extra = " Use broader, related terms and synonyms." if broader else ""
        out = parse_json(llm(
            "You rewrite search queries for transcript retrieval.",
            f"Video title: {title}\nUser question (Bangla, English or Banglish = Bangla typed in "
            f"Latin letters): {question}\nReturn JSON: {{\"queries\": [3 short search queries: one "
            f"in Bangla script, one in English, one with key technical terms], \"sub_questions\": "
            f"[0-3 simpler sub-questions ONLY if the question is complex, else []], \"hypothetical\": "
            f"\"1-2 sentence passage that would answer it, as a speaker would say it\"}}.{extra}",
            max_tokens=500))
        if out:
            qs += [q for q in out.get("queries", []) if isinstance(q, str)][:3]
            qs += [q for q in out.get("sub_questions", []) if isinstance(q, str)][:3]
            h = out.get("hypothetical")
            if isinstance(h, str) and h:
                qs.append(h)
    except Exception:
        pass
    seen, res = set(), []
    for q in qs:
        if q.strip() and q.lower() not in seen:
            seen.add(q.lower())
            res.append(q)
    return res


def grade_chunks(question, cands):
    """Corrective RAG: keep only passages that genuinely discuss the topic."""
    if not cands:
        return [], True
    ev = "\n\n".join(f"[{i}] ({fmt(c['start'])}-{fmt(c['end'])}) {c['text'][:800]}"
                     for i, c in enumerate(cands))
    out = parse_json(llm(
        "You are a strict relevance judge. A passage is relevant if it directly discusses or "
        "explains the asked topic OR a part the answer needs (e.g. for 'difference between A and B', "
        "a passage explaining A or B alone is relevant). Keyword overlap or a passing mention is NOT relevant. "
        "Passages are noisy auto-generated captions (often Bangla): English technical terms may appear "
        "in Bangla script or misspelled (e.g. 'ল্যান' = LAN, 'নরমাল ফর্ম' = normal form); judge by meaning.",
        f"Topic/question: {question}\n\nPassages:\n{ev}\n\n"
        "Return JSON: {\"relevant\": [indices of relevant passages]}", max_tokens=200))
    if not out or not isinstance(out.get("relevant"), list):
        return [], False
    idx = [i for i in out["relevant"] if isinstance(i, int) and 0 <= i < len(cands)]
    return [cands[i] for i in idx], True


# ---------------------------------------------------------- merge + clip
def merge_ranges(chunks, gap=10.0, pad_before=1.0, pad_after=1.5, max_len=300.0, max_time=None):
    iv = sorted((c["start"], c["end"], c.get("score", 0.0)) for c in chunks)
    merged = []
    for s, e, sc in iv:
        if merged and s - merged[-1][1] <= gap:
            merged[-1][1] = max(merged[-1][1], e)
            merged[-1][2] = max(merged[-1][2], sc)
        else:
            merged.append([s, e, sc])
    out = []
    for s, e, sc in merged:
        s = max(0.0, s - pad_before)
        e = min(e + pad_after, s + max_len)
        if max_time is not None:
            e = min(e, max_time)
        if e > s:
            out.append({"start": s, "end": e, "score": sc})
    return sorted(out, key=lambda r: -r["score"])


def cut_clip(vid, s, e):
    src = find_media(vid)
    if not src:
        raise FileNotFoundError("source media not available")
    audio = src.suffix.lower() in AUDIO_EXT
    name = f"{vid}_{int(s)}_{int(e)}" + (".m4a" if audio else ".mp4")
    out = DATA / "clips" / name
    if not out.exists():
        codec = ["-vn", "-c:a", "aac"] if audio else ["-c:v", "libx264", "-preset", "veryfast",
                                                     "-c:a", "aac", "-movflags", "+faststart"]
        subprocess.run(["ffmpeg", "-y", "-ss", f"{s:.2f}", "-i", str(src), "-t", f"{e - s:.2f}"]
                       + codec + [str(out)], check=True, capture_output=True)
    return name


# ------------------------------------------------- grounded answer + verify
ANSWER_SYS = (
    "You write study notes ONLY from the numbered evidence passages of a video transcript. "
    "Never use outside knowledge. Every point must cite the evidence numbers that support it. "
    "If the evidence does not answer the question, return empty sections. "
    "Answer language: if the question is Bangla or Banglish, write in Bangla script and keep "
    "English technical terms; otherwise write in the question's language.")


LEVELS = {"simple": "Explain very simply in short sentences, like to a beginner.",
          "exam": "Write concise exam-ready points and definitions.",
          "expert": "Be precise and technical; assume prior knowledge."}


def generate_answer(question, ev, level="simple"):
    text = "\n\n".join(f"[{i + 1}] ({fmt(c['start'])}-{fmt(c['end'])}) {c['text']}"
                       for i, c in enumerate(ev))
    out = parse_json(llm(
        ANSWER_SYS + " " + LEVELS.get(level, LEVELS["simple"]),
        f"Question: {question}\n\nEvidence:\n{text}\n\nReturn JSON exactly: "
        "{\"title\": str, \"summary\": str (2-3 sentences), \"sections\": [{\"heading\": str, "
        "\"points\": [{\"text\": str, \"cites\": [int]}]}]}", max_tokens=1800))
    if not out or not isinstance(out.get("sections"), list):
        return {"title": "", "summary": "", "sections": []}
    secs = []
    for sec in out["sections"]:           # real LLMs sometimes return bare strings / "1" cites
        if isinstance(sec, str):
            sec = {"heading": "", "points": [sec]}
        if not isinstance(sec, dict):
            continue
        pts = []
        for p in sec.get("points") or []:
            if isinstance(p, str):
                p = {"text": p, "cites": []}
            if not isinstance(p, dict) or not str(p.get("text", "")).strip():
                continue
            cites = p.get("cites") or []
            cites = cites if isinstance(cites, list) else [cites]
            p["cites"] = [int(c) for c in cites if str(c).strip().isdigit()]
            pts.append(p)
        secs.append({"heading": str(sec.get("heading", "")), "points": pts})
    out["sections"] = secs
    out.setdefault("title", "")
    out.setdefault("summary", "")
    return out


def verify_answer(ans, ev):
    """Claim-level verification (LLM as NLI judge): drop points the cited evidence doesn't support."""
    items = []
    for si, s in enumerate(ans["sections"]):
        for pi, p in enumerate(s.get("points", [])):
            cites = [c for c in p.get("cites", []) if isinstance(c, int) and 1 <= c <= len(ev)]
            items.append((si, pi, p.get("text", ""), cites))
    stats = {"claims_total": len(items), "claims_supported": 0, "verify": "ok", "claims": []}
    if not items:
        return ans, stats
    checkable = [it for it in items if it[3]]
    verdict = {}
    if checkable:
        blocks = "\n\n".join(
            f"Claim {j}: {t}\nEvidence: " + " ".join(ev[c - 1]["text"] for c in cites)
            for j, (_, _, t, cites) in enumerate(checkable))
        out = parse_json(llm(
            "You are a strict fact verifier. A claim is supported only if the evidence states it "
            "or directly implies it. The evidence is a noisy auto-generated caption transcript (often "
            "Bangla, English terms may be written in Bangla script or misspelled) and the claim may be a "
            "translation or paraphrase of it: judge meaning, not wording. Outside knowledge does not count.",
            f"{blocks}\n\nThere are exactly {len(checkable)} claims. Return JSON: {{\"results\": "
            f"[{len(checkable)} booleans true/false, one per claim, in order]}}",
            max_tokens=400))
        res = out.get("results") if out else None
        if isinstance(res, list):
            res = [(r.get("supported", r.get("verdict", r.get("result"))) if isinstance(r, dict) else r) for r in res]
            res = [(str(r).strip().lower() in ("true", "yes", "supported", "1")) if not isinstance(r, bool) else r for r in res]
        if isinstance(res, list) and len(res) == len(checkable):
            for (si, pi, _, _), ok in zip(checkable, res):
                verdict[(si, pi)] = bool(ok)
        else:
            stats["verify"] = "failed (kept all points, unverified)"
            for si, pi, _, _ in checkable:
                verdict[(si, pi)] = True
    new_sections = []
    for si, s in enumerate(ans["sections"]):
        pts = []
        for pi, p in enumerate(s.get("points", [])):
            if verdict.get((si, pi), False):
                p["cites"] = [c for c in p.get("cites", []) if isinstance(c, int) and 1 <= c <= len(ev)]
                pts.append(p)
        if pts:
            new_sections.append({"heading": s.get("heading", ""), "points": pts})
    stats["claims_supported"] = sum(len(s["points"]) for s in new_sections)
    for si, pi, t, cites in items:
        v = verdict.get((si, pi))
        stats["claims"].append({"text": t, "cites": cites, "verdict": (
            "no_citation" if not cites else ("supported" if v and stats["verify"] == "ok" else
                                             "unverified" if v else "unsupported"))})
    return {**ans, "sections": new_sections}, stats


# --------------------------------------------------------------------- ask
def ask(video, question, current_time=None, make_clip=True, mode="hybrid+rerank",
        use_rewrite=True, level="simple", use_grade=True, use_verify=True, debug=False):
    """Full pipeline. use_* flags exist for ablation; debug=True adds every intermediate stage to trace."""
    tok = _S.set({})
    try:
        out = _ask(video, question, current_time, make_clip, mode, use_rewrite, level, use_grade, use_verify, debug)
        out["trace"]["usage"] = dict(_S.get() or {})
        return out
    finally:
        _S.reset(tok)


def _ms(t0):
    return round((time.perf_counter() - t0) * 1000)


def _ask(video, question, current_time, make_clip, mode, use_rewrite, level, use_grade, use_verify, debug):
    vid = extract_video_id(video)
    ix = load_index(vid)
    title = ix.meta.get("title", vid)
    trace = {"mode": mode, "current_time": current_time, "attempts": [], "timings_ms": {},
             "flags": {"rewrite": use_rewrite, "grade": use_grade, "verify": use_verify}}
    tm, dbg = trace["timings_ms"], ({"attempts": []} if debug else None)
    rel = []
    for attempt, (k, pool) in enumerate([(8, 20), (16, 40)]):
        t0 = time.perf_counter()
        queries = rewrite_query(question, title, broader=attempt > 0) if use_rewrite else [question]
        tm["rewrite"] = tm.get("rewrite", 0) + _ms(t0)
        d = {} if debug else None
        t0 = time.perf_counter()
        cands = retrieve(ix, queries, question, k=k, max_time=current_time, mode=mode, pool=pool, dbg=d)
        tm["retrieve"] = tm.get("retrieve", 0) + _ms(t0)
        t0 = time.perf_counter()
        if use_grade:
            rel, graded_ok = grade_chunks(question, cands)
        else:
            rel, graded_ok = cands[:5], True
        tm["grade"] = tm.get("grade", 0) + _ms(t0)
        trace["attempts"].append({"queries": queries, "candidates": len(cands),
                                  "relevant": len(rel), "grader_ok": graded_ok})
        if debug:
            keep = {c["idx"] for c in rel}
            d["graded"] = [{"idx": c["idx"], "start": c["start"], "end": c["end"], "relevant": c["idx"] in keep,
                            "preview": c["text"][:140]} for c in cands]
            d["queries"], d["k"], d["pool"] = queries, k, pool
            dbg["attempts"].append(d)
        if rel:
            break
    if not rel:
        where = f" (তোমার দেখা {fmt(current_time)} পর্যন্ত অংশে)" if current_time else ""
        if debug:
            trace["debug"] = dbg
        return {"found": False, "video_id": vid, "trace": trace,
                "message": f"এই topic এই video-তে পাওয়া যায়নি{where}."}
    ev = sorted(rel, key=lambda c: c["start"])[:8]
    t0 = time.perf_counter()
    ans = generate_answer(question, ev, level)
    tm["generate"] = _ms(t0)
    raw = copy.deepcopy(ans) if debug else None
    t0 = time.perf_counter()
    if use_verify:
        ans, stats = verify_answer(ans, ev)
    else:
        n = sum(len(s.get("points", [])) for s in ans["sections"])
        stats = {"claims_total": n, "claims_supported": n, "verify": "skipped", "claims": []}
    tm["verify"] = _ms(t0)
    trace.update(stats)
    refs = [{"n": i + 1, "start": c["start"], "end": c["end"], "url": yt_link(vid, c["start"]),
             "preview": c["text"][:160]} for i, c in enumerate(ev)]
    segments = []
    t0 = time.perf_counter()
    limit = min(current_time, ix.meta["duration"]) if current_time else ix.meta.get("duration")
    for r in merge_ranges(rel, max_time=limit)[:3]:
        seg = {"start": r["start"], "end": r["end"], "url": yt_link(vid, r["start"]), "clip": None}
        if make_clip and ix.meta.get("has_video"):
            try:
                seg["clip"] = "/clips/" + cut_clip(vid, r["start"], r["end"])
            except Exception as e:
                trace["clip_error"] = str(e)[:200]
        segments.append(seg)
    tm["merge_clip"] = _ms(t0)
    if debug:
        dbg["evidence"] = [{"n": i + 1, "start": c["start"], "end": c["end"], "text": c["text"][:400]}
                           for i, c in enumerate(ev)]
        dbg["answer_before_verify"] = raw
        trace["debug"] = dbg
    return {"found": True, "video_id": vid, "title": title, "kind": ix.meta.get("kind", "youtube"),
            "answer": ans if ans["sections"] else None,
            "note": None if ans["sections"] else "Topic আছে, কিন্তু নির্ভরযোগ্য (verified) answer বানানো যায়নি - clip দেখো।",
            "refs": refs, "segments": segments, "trace": trace}


# ------------------------------------------------------------- RAG Lab tools
def compare_modes(video, question, k=5, current_time=None, use_rewrite=False):
    """Same question through dense / bm25 / hybrid / hybrid+rerank -> shows what each stage adds."""
    tok = _S.set({})
    try:
        vid = extract_video_id(video)
        ix = load_index(vid)
        queries = rewrite_query(question, ix.meta.get("title", vid)) if use_rewrite else [question]
        out = {"video_id": vid, "queries": queries, "modes": {}}
        for m in MODES:
            t0 = time.perf_counter()
            r = retrieve(ix, queries, question, k=k, max_time=current_time, mode=m)
            out["modes"][m] = {"ms": _ms(t0), "results": [
                {"idx": c["idx"], "start": c["start"], "end": c["end"], "url": yt_link(vid, c["start"]),
                 "preview": c["text"][:140]} for c in r]}
        out["usage"] = dict(_S.get() or {})
        return out
    finally:
        _S.reset(tok)


def chunk_report(video):
    """Chunk list + topic-shift similarity curve (stored at index time; recomputed lexically for old indexes)."""
    vid = extract_video_id(video)
    ix = load_index(vid)
    info = ix.extra.get("chunking") if ix.extra else None
    if not info:
        flat = [{"start": s[0], "end": s[0] + 1.0, "text": s[1]} for c in ix.chunks for s in c["segs"]]
        info = {}
        semantic_chunks(flat, info=info, signal="lexical")
        info["recomputed"] = True
    return {"video_id": vid, "title": ix.meta.get("title", vid), "chunking": info, "chunks": [
        {"i": i, "start": c["start"], "end": c["end"], "n_segs": len(c["segs"]), "chars": len(c["text"]),
         "preview": c["text"][:120]} for i, c in enumerate(ix.chunks)]}


def topic_heat(video, question):
    """Where in the video does this topic live? Dense + BM25 relevance for EVERY chunk (1 embedding call,
    no LLM) -> the UI draws it as a heat-strip over the video timeline."""
    vid = extract_video_id(video)
    ix = load_index(vid)
    n = len(ix.chunks)
    if not n or not question.strip():
        return {"video_id": vid, "cells": []}
    b = np.asarray(ix.bm25.get_scores(tokenize(question)), dtype="float32")
    try:
        d = ix.E @ embed([question], "query")[0]
    except Exception:
        d = b

    def norm(x):
        lo, hi = float(np.min(x)), float(np.max(x))
        return (x - lo) / (hi - lo) if hi > lo else np.zeros_like(x)
    sc = 0.7 * norm(d) + 0.3 * norm(b)
    return {"video_id": vid, "duration": ix.meta.get("duration"),
            "cells": [{"start": c["start"], "end": c["end"], "score": round(float(sc[i]), 3)}
                      for i, c in enumerate(ix.chunks)]}


def transcript(video):
    """Chunked transcript for the interactive, searchable transcript panel."""
    vid = extract_video_id(video)
    ix = load_index(vid)
    return {"video_id": vid, "title": ix.meta.get("title", vid), "duration": ix.meta.get("duration"),
            "chunks": [{"i": i, "start": c["start"], "end": c["end"], "text": c["text"]}
                       for i, c in enumerate(ix.chunks)]}

