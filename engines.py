"""AI engines: free API providers (and your own open-source Ollama) that the site rotates through.

The owner adds free keys in the "AI engines" panel. Every LLM call walks the enabled engines in order;
when one hits its free limit (429) or fails, the next one answers. Short "judge" jobs (rewrite, relevance
check, verify) can go to a fast engine first, so the main engine's free quota is kept for answers.
Everything here is free: no paid plan, no card. Keys are stored in the app database, lightly encrypted
with SECRET_KEY, and never sent back to the browser (only the last 4 characters)."""
import hashlib
import json
import os
import time

import auth

# id -> provider info. All speak the OpenAI chat API. Models can be changed in the panel.
CATALOG = {
    "groq": {"name": "Groq", "base": "https://api.groq.com/openai/v1", "model": "openai/gpt-oss-120b",
             "fast": "llama-3.1-8b-instant", "key_url": "https://console.groq.com/keys",
             "limits": "Free: ~30 requests/min, ~1,000/day per model", "fast_first": True},
    "gemini": {"name": "Google Gemini", "base": "https://generativelanguage.googleapis.com/v1beta/openai/",
               "model": "gemini-3.5-flash", "fast": "gemini-3.5-flash-lite", "key_url": "https://aistudio.google.com/apikey",
               "limits": "Free tier: limits per model per minute and per day"},
    "mistral": {"name": "Mistral", "base": "https://api.mistral.ai/v1", "model": "mistral-small-latest",
                "fast": "ministral-8b-latest", "key_url": "https://console.mistral.ai/api-keys",
                "limits": "Free 'Experiment' plan (allows Mistral to train on your data)"},
    "openrouter": {"name": "OpenRouter (free models)", "base": "https://openrouter.ai/api/v1",
                   "model": "openai/gpt-oss-120b:free", "fast": "meta-llama/llama-3.3-70b-instruct:free",
                   "key_url": "https://openrouter.ai/keys", "limits": "Free ':free' models: ~20/min, 50/day"},
    "nvidia": {"name": "NVIDIA NIM", "base": "https://integrate.api.nvidia.com/v1", "model": "meta/llama-3.3-70b-instruct",
               "fast": "meta/llama-3.1-8b-instruct", "key_url": "https://build.nvidia.com",
               "limits": "Free for prototyping: up to ~40 requests/min"},
    "cloudflare": {"name": "Cloudflare Workers AI", "base": "https://api.cloudflare.com/client/v4/accounts/{account}/ai/v1",
                   "model": "@cf/meta/llama-3.3-70b-instruct-fp8-fast", "fast": "@cf/meta/llama-3.1-8b-instruct",
                   "key_url": "https://dash.cloudflare.com/profile/api-tokens", "needs_account": True,
                   "limits": "Free: 10,000 'neurons' per day", "fast_first": True},
    "ollama": {"name": "My PC (Ollama, open-source)", "base": "http://localhost:11434/v1", "model": "qwen2.5:7b",
               "fast": "qwen2.5:3b", "key_url": "https://ollama.com/download", "local": True,
               "limits": "No limit - runs on your own computer"},
}
DEFAULT_ORDER = ["gemini", "groq", "mistral", "openrouter", "nvidia", "cloudflare", "ollama"]
_CACHE = {"t": 0, "v": None}


# ------------------------------------------------------------ storage (app database)
def _stream(n):
    seed = hashlib.sha256(auth._secret() + b"engines").digest()
    out = b""
    while len(out) < n:
        seed = hashlib.sha256(seed).digest()
        out += seed
    return out[:n]


def _enc(s):
    b = s.encode()
    return bytes(x ^ y for x, y in zip(b, _stream(len(b)))).hex()


def _dec(h):
    try:
        b = bytes.fromhex(h)
        return bytes(x ^ y for x, y in zip(b, _stream(len(b)))).decode()
    except Exception:
        return ""


def load():
    if time.time() - _CACHE["t"] < 10 and _CACHE["v"] is not None:
        return _CACHE["v"]
    cfg = {"order": list(DEFAULT_ORDER), "providers": {}}
    try:
        with auth._LOCK, auth._conn() as c:
            r = c.execute("SELECT v FROM settings WHERE k=?", ("engines",)).fetchone()
        if r:
            cfg.update(json.loads(r["v"]))
    except Exception:
        pass
    cfg["order"] = [p for p in cfg["order"] if p in CATALOG] + [p for p in DEFAULT_ORDER if p not in cfg["order"]]
    _CACHE.update(t=time.time(), v=cfg)
    return cfg


def _save(cfg):
    raw = json.dumps(cfg)
    with auth._LOCK, auth._conn() as c:
        if c.execute("SELECT k FROM settings WHERE k=?", ("engines",)).fetchone():
            c.execute("UPDATE settings SET v=? WHERE k=?", (raw, "engines"))
        else:
            c.execute("INSERT INTO settings(k, v) VALUES(?, ?)", ("engines", raw))
    _CACHE.update(t=0, v=None)


def _conf(pid, p):
    """Effective settings of one provider (catalog defaults + what the owner saved)."""
    c = CATALOG[pid]
    base = (p.get("base") or c["base"]).strip()
    if c.get("needs_account"):
        base = base.replace("{account}", (p.get("account") or "").strip())
    return {"base": base.rstrip("/") + ("/" if base.endswith("/") else ""), "key": _dec(p.get("key", "")) if p.get("key") else "",
            "model": (p.get("model") or c["model"]).strip(), "fast": (p.get("fast") or c["fast"]).strip()}


def ready(pid, p):
    c = CATALOG[pid]
    if not p.get("enabled"):
        return False
    if c.get("local"):
        return True
    if c.get("needs_account") and not (p.get("account") or "").strip():
        return False
    return bool(p.get("key"))


# ------------------------------------------------------------ used by rag.llm()
def providers(fast=False):
    """(tag, base, key, model, fast_model) for every enabled engine, in the owner's order.
    For short judge jobs, engines marked fast_first move to the front."""
    cfg = load()
    out = []
    for pid in cfg["order"]:
        p = cfg["providers"].get(pid) or {}
        if not ready(pid, p):
            continue
        e = _conf(pid, p)
        out.append(("E_" + pid + "_", e["base"], e["key"] or "ollama", e["model"], e["fast"]))
    if fast:
        out.sort(key=lambda t: 0 if CATALOG[t[0][2:-1]].get("fast_first") else 1)
    return out


def name_of(tag):
    pid = tag[2:-1] if tag.startswith("E_") else ""
    return CATALOG[pid]["name"] if pid in CATALOG else ""


# ------------------------------------------------------------ panel API
def is_admin(request):
    """Who may change keys: the PC owner running it locally, the admin key, ADMIN_EMAILS, or (if not set)
    the first account ever made on this site."""
    # "running on this PC": the browser itself opened localhost AND the connection is from this machine.
    # (Behind a host like Render the proxy also connects from 127.0.0.1, so the address alone is not enough.)
    host = request.client.host if request.client else ""
    site = (request.url.hostname or "").lower()
    if (host in ("127.0.0.1", "::1") and site in ("localhost", "127.0.0.1", "::1")
            and not request.headers.get("x-forwarded-for") and not request.headers.get("x-forwarded-host")):
        return True
    pw = os.getenv("APP_PASSWORD")
    if pw and request.headers.get("x-app-key") == pw:
        return True
    u = getattr(request.state, "user", None)
    if not u or u.get("email", "").endswith("@guest.learningmate.app"):
        return False
    admins = [x.strip().lower() for x in os.getenv("ADMIN_EMAILS", "").split(",") if x.strip()]
    return (u.get("email", "").lower() in admins) if admins else u.get("id") == 1


def public_view(admin):
    cfg = load()
    out = []
    for pid in cfg["order"]:
        c, p = CATALOG[pid], cfg["providers"].get(pid) or {}
        key = _dec(p["key"]) if p.get("key") else ""
        out.append({"id": pid, "name": c["name"], "enabled": bool(p.get("enabled")), "ready": ready(pid, p),
                    "has_key": bool(key), "key_hint": ("…" + key[-4:]) if key and admin else "",
                    "model": p.get("model") or c["model"], "fast": p.get("fast") or c["fast"],
                    "base": (p.get("base") or c["base"]) if admin else "", "account": (p.get("account") or "") if admin else "",
                    "default_model": c["model"], "default_fast": c["fast"], "default_base": c["base"],
                    "key_url": c["key_url"], "limits": c["limits"], "local": bool(c.get("local")),
                    "needs_account": bool(c.get("needs_account")), "fast_first": bool(c.get("fast_first")),
                    "last": p.get("last") or None})
    return out


def update(body):
    cfg = load()
    cfg = {"order": list(cfg["order"]), "providers": {k: dict(v) for k, v in cfg["providers"].items()}}
    order = [p for p in body.get("order") or [] if p in CATALOG]
    if order:
        cfg["order"] = order + [p for p in DEFAULT_ORDER if p not in order]
    for pid, v in (body.get("providers") or {}).items():
        if pid not in CATALOG or not isinstance(v, dict):
            continue
        p = cfg["providers"].setdefault(pid, {})
        for f in ("enabled",):
            if f in v:
                p[f] = bool(v[f])
        for f in ("model", "fast", "base", "account"):
            if f in v:
                p[f] = str(v[f] or "").strip()[:300]
        if v.get("clear_key"):
            p.pop("key", None)
        elif str(v.get("key") or "").strip():
            p["key"] = _enc(str(v["key"]).strip()[:400])
            p.setdefault("enabled", True)
    _save(cfg)
    return public_view(True)


def test(pid):
    """One tiny real call, so the owner sees at once whether the key / model / URL works."""
    cfg = load()
    p = cfg["providers"].get(pid) or {}
    if pid not in CATALOG:
        raise ValueError("unknown engine")
    c = CATALOG[pid]
    if not c.get("local") and not p.get("key"):
        raise ValueError("add a key first")
    e = _conf(pid, p)
    from openai import OpenAI
    cl = OpenAI(api_key=e["key"] or "ollama", base_url=e["base"], timeout=25, max_retries=0)
    res = {}
    for role, model in (("model", e["model"]), ("fast", e["fast"])):
        t0 = time.perf_counter()
        try:
            r = cl.chat.completions.create(model=model, max_tokens=12, temperature=0,
                                           messages=[{"role": "user", "content": "Reply with the single word: ok"}])
            res[role] = {"ok": True, "ms": round((time.perf_counter() - t0) * 1000),
                         "reply": (r.choices[0].message.content or "").strip()[:40]}
        except Exception as ex:
            code = getattr(ex, "status_code", None)
            msg = {401: "wrong key", 403: "key not allowed", 404: "model not found - check the model name",
                   429: "free limit reached right now (it will reset)"}.get(code)
            if not msg:
                msg = ("can't reach it - is Ollama running on this PC?" if c.get("local") else
                       "can't reach the service - check the internet / URL") if "Connection" in type(ex).__name__ + str(ex)[:40] else str(ex)[:160]
            res[role] = {"ok": False, "ms": round((time.perf_counter() - t0) * 1000), "error": msg}
    p = cfg["providers"].setdefault(pid, {})
    p["last"] = {"t": time.time(), "ok": res["model"]["ok"] or res["fast"]["ok"],
                 "ms": res["model"].get("ms"), "error": res["model"].get("error")}
    _save(cfg)
    return res
