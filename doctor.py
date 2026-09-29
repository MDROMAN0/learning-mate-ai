"""Pre-demo checklist:  python doctor.py [youtube-video-id]
Checks everything a LIVE demo on your own PC depends on and tells you how to fix what fails."""
import importlib.util
import re
import shutil
import sys

import rag


def line(state, name, hint=""):
    print({"ok": "✅", "warn": "⚠️ ", "bad": "❌"}[state], name, ("→ " + hint) if hint and state != "ok" else "")
    return state


def check(name, fn, hint, warn_only=False):
    try:
        detail = fn()
        return line("ok", f"{name}{(' — ' + str(detail)) if detail else ''}")
    except Exception as e:
        return line("warn" if warn_only else "bad", f"{name}: {str(e)[:110]}", hint)


def _need(cond, msg):
    if not cond:
        raise RuntimeError(msg)


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    test_id = argv[0] if argv else "jNQXAC9IVRw"  # first-ever YouTube video; has captions
    res = []
    res.append(check("ffmpeg", lambda: _need(shutil.which("ffmpeg"), "not found") or shutil.which("ffmpeg"),
                     "Windows: winget install ffmpeg"))
    res.append(check("deno (JS runtime yt-dlp needs for YouTube)", lambda: _need(shutil.which("deno"), "not on PATH") or shutil.which("deno"),
                     "Windows: winget install DenoLand.Deno (then reopen the terminal). Without it downloads may fail → use YT_DOWNLOAD=0", warn_only=True))

    def ytdlp():
        import yt_dlp
        return yt_dlp.version.__version__
    res.append(check("yt-dlp", ytdlp, 'pip install -U "yt-dlp[default]"'))
    res.append(check("yt-dlp-ejs (challenge solver scripts)",
                     lambda: _need(importlib.util.find_spec("yt_dlp_ejs"), "module not found"),
                     'pip install -U "yt-dlp[default]"  (ignore if yt-dlp -v shows the solver works)', warn_only=True))
    def captions():
        segs = rag.fetch_captions(test_id)
        _need(segs, "none returned")
        return f"{len(segs)} segments"
    res.append(check("captions from your IP", captions,
                     "YouTube may be blocking this network → try a mobile hotspot; or use the Chrome extension / pre-indexed library"))
    def title():
        t = rag.fetch_title(test_id)
        _need(t != test_id, "title lookup failed")
        return t
    res.append(check("video title (oEmbed)", title, "network problem?", warn_only=True))

    def metadata():
        import yt_dlp
        with yt_dlp.YoutubeDL({"quiet": True, "skip_download": True}) as y:
            return y.extract_info(f"https://www.youtube.com/watch?v={test_id}", download=False).get("title")
    res.append(check("yt-dlp can read YouTube", metadata,
                     "install Deno + update yt-dlp; else set YT_DOWNLOAD=0 (captions + embedded player, no clip files)", warn_only=True))
    def model_name():
        m, u = rag.env("LLM_MODEL", "gpt-4o-mini"), rag.env("LLM_BASE_URL")
        _need(not ("generativelanguage" in u and re.match(r"gemini-(1|2)\.", m)),
              f"{m} is a legacy Gemini model (new projects can't use 2.5; 2.0 is shut down)")
        return m
    res.append(check("LLM model name is current", model_name,
                     "set LLM_MODEL=gemini-3.5-flash (or gemini-3.5-flash-lite; on this free-tier key 3.8-flash returned 429 quota) — see ai.google.dev/gemini-api/docs/deprecations"))
    res.append(check("LLM API", lambda: _need(rag.llm("Reply with exactly: ok", "ping", max_tokens=5).strip(), "empty reply") or rag.env("LLM_MODEL", "gpt-4o-mini"),
                     "set LLM_API_KEY / LLM_BASE_URL / LLM_MODEL in .env"))
    res.append(check("embeddings", lambda: f"{rag.emb_id()} dim={rag.embed(['ping']).shape[1]}",
                     "EMB_PROVIDER/EMB_API_MODEL wrong, or key/quota problem"))
    if rag.env("ASR_PROVIDER", "local") == "sarvam":
        res.append(check("SARVAM_API_KEY set", lambda: _need(rag.env("SARVAM_API_KEY"), "missing"), "add SARVAM_API_KEY"))
    res.append(check("library (backup videos)", lambda: f"{len(rag.list_library())} indexed" if rag.list_library() else _need(False, "empty"),
                     "index 2-3 videos beforehand: python prepare.py <url> — your live-demo safety net", warn_only=True))
    bad, warn = res.count("bad"), res.count("warn")
    print(f"\n{'READY' if not bad else 'NOT READY'} — {bad} failed, {warn} warnings")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
