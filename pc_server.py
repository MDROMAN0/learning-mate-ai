"""Use this PC's Ollama as the AI engine for the ONLINE site (the site itself stays on Render).

Run it (start_pc_server.bat) and keep it running:
  1. a small gate on 127.0.0.1:11500 forwards only /v1/* to Ollama, and only with a secret key
  2. a free Cloudflare quick tunnel gives the gate a public https URL (no account needed)
  3. every 30 s it writes {url, key, models} + a heartbeat into the shared Postgres (DATABASE_URL)
The online site (rag._remote_provider) uses this PC while the heartbeat is fresh; when the PC is off
or Ollama stops, the heartbeat stops and the site falls back to Gemini automatically.
"""
import os
import re
import secrets
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
GATE_PORT = 11500
OLLAMA = "http://127.0.0.1:11434"


def load_env():
    p = HERE / ".env"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            m = re.match(r"\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.*)\s*$", line)
            if m and m.group(1) not in os.environ:
                os.environ[m.group(1)] = m.group(2).strip().strip('"')


load_env()
KEY = secrets.token_urlsafe(32)        # new secret every start; only the gate and the database know it
DB = os.getenv("DATABASE_URL", "")
MODEL = os.getenv("LLM_MODEL", "qwen2.5:7b")
FAST = os.getenv("LLM_FAST_MODEL", "llama3.2:3b")
ALLOWED = {m for m in (MODEL, FAST) if m}
# --- protection: the PC never takes more than it can handle (extra load goes to the site's backup) ---
MAX_ACTIVE = int(os.getenv("PC_MAX_ACTIVE", "2"))      # requests sent to Ollama at the same time
MAX_WAITING = int(os.getenv("PC_MAX_WAITING", "4"))    # more than this waiting -> "busy" (503)
MAX_PER_MIN = int(os.getenv("PC_MAX_PER_MIN", "60"))   # LLM calls per minute from the internet
GPU_MAX_C = int(os.getenv("PC_GPU_MAX_C", "80"))       # GPU hotter than this -> pause until it cools
RAM_MIN_FREE_GB = float(os.getenv("PC_RAM_MIN_FREE_GB", "3"))
STATE = {"hot": False, "low_ram": False, "gpu_c": None, "free_gb": None}


def health_watch():
    """Every 10 s: GPU temperature (nvidia-smi) and free RAM; sets STATE so the gate can refuse work."""
    import ctypes
    while True:
        try:
            out = subprocess.run(["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"],
                                 capture_output=True, text=True, timeout=10).stdout.strip().splitlines()
            c = int(out[0]) if out else None
            STATE["gpu_c"] = c
            if c is not None:                                   # hysteresis: stop at MAX, resume 8 C lower
                STATE["hot"] = c >= GPU_MAX_C or (STATE["hot"] and c > GPU_MAX_C - 8)
        except Exception:
            pass
        try:
            class MS(ctypes.Structure):
                _fields_ = [("l", ctypes.c_ulong), ("load", ctypes.c_ulong), ("total", ctypes.c_ulonglong),
                            ("avail", ctypes.c_ulonglong), ("tp", ctypes.c_ulonglong), ("ap", ctypes.c_ulonglong),
                            ("tv", ctypes.c_ulonglong), ("av", ctypes.c_ulonglong), ("ae", ctypes.c_ulonglong)]
            ms = MS(); ms.l = ctypes.sizeof(MS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms))
            STATE["free_gb"] = round(ms.avail / 2**30, 1)
            STATE["low_ram"] = STATE["free_gb"] < RAM_MIN_FREE_GB
        except Exception:
            pass
        time.sleep(10)


def gate():
    import httpx
    import uvicorn
    from fastapi import FastAPI, Request, Response

    import asyncio
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    client = httpx.AsyncClient(timeout=300)
    sem = asyncio.Semaphore(MAX_ACTIVE)
    q = {"waiting": 0, "minute": 0, "count": 0}

    @app.post("/v1/{path:path}")
    async def proxy(path: str, request: Request):
        if path != "chat/completions":          # only answering; nothing else is reachable
            return Response("not found", status_code=404)
        if not secrets.compare_digest(request.headers.get("authorization", ""), "Bearer " + KEY):
            return Response("forbidden", status_code=403)
        body = await request.body()
        if len(body) > 2_000_000:
            return Response("too large", status_code=413)
        try:
            model = __import__("json").loads(body).get("model")
        except Exception:
            return Response("bad request", status_code=400)
        if model not in ALLOWED:                       # only our own models, nothing else on this PC
            return Response("model not allowed", status_code=403)
        if STATE["hot"] or STATE["low_ram"]:           # protect the hardware: site uses its backup meanwhile
            return Response("pc cooling down", status_code=503)
        now = int(time.time() // 60)
        if q["minute"] != now:
            q["minute"], q["count"] = now, 0
        q["count"] += 1
        if q["count"] > MAX_PER_MIN or q["waiting"] >= MAX_WAITING:
            return Response("pc busy", status_code=503)
        q["waiting"] += 1
        got = False
        try:
            async with sem:
                got = True
                q["waiting"] -= 1
                r = await client.post(f"{OLLAMA}/v1/{path}", content=body,
                                      headers={"content-type": "application/json"})
        finally:
            if not got:
                q["waiting"] -= 1
        return Response(r.content, status_code=r.status_code,
                        media_type=r.headers.get("content-type", "application/json"))

    uvicorn.run(app, host="127.0.0.1", port=GATE_PORT, log_level="warning")


def ollama_alive():
    import httpx
    try:
        return httpx.get(OLLAMA + "/api/tags", timeout=5).status_code == 200
    except Exception:
        return False


def tunnel(found):
    exe = "cloudflared"
    for c in (Path(os.getenv("ProgramFiles", "C:/Program Files")) / "cloudflared" / "cloudflared.exe",
              Path(os.getenv("ProgramFiles(x86)", "C:/Program Files (x86)")) / "cloudflared" / "cloudflared.exe"):
        if c.exists():
            exe = str(c)
    p = subprocess.Popen([exe, "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{GATE_PORT}"],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="ignore")
    for line in p.stdout:
        m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line)
        if m and not found.get("url"):
            found["url"] = m.group(0)
    found["dead"] = True


def db_exec(sql, args=()):
    import psycopg
    with psycopg.connect(DB, connect_timeout=10) as c:
        c.execute(sql, args)
        c.commit()


def main():
    if os.getenv("OLLAMA_HOST", "127.0.0.1").split(":")[0] not in ("127.0.0.1", "localhost", ""):
        sys.exit("OLLAMA_HOST must stay on 127.0.0.1 (Ollama must not listen on the network)")
    if not DB.startswith("postgres"):
        sys.exit("DATABASE_URL (the same Neon URL the online site uses) is missing in .env")
    db_exec("create table if not exists pc_llm (id int primary key, url text, key text, model text, "
            "fast_model text, updated timestamptz)")
    threading.Thread(target=health_watch, daemon=True).start()
    threading.Thread(target=gate, daemon=True).start()
    found = {}
    threading.Thread(target=tunnel, args=(found,), daemon=True).start()
    for _ in range(60):
        if found.get("url"):
            break
        time.sleep(1)
    if not found.get("url"):
        sys.exit("Cloudflare tunnel did not start (is cloudflared installed?)")
    print("PC AI server online | models:", MODEL, "/", FAST)
    print("Keep this window open. Close it (or turn the PC off) -> the site switches to Gemini by itself.")
    try:
        while not found.get("dead"):
            if STATE["hot"] or STATE["low_ram"]:
                print(time.strftime("%H:%M:%S"), f"protecting PC (GPU {STATE['gpu_c']} C, free RAM {STATE['free_gb']} GB)"
                      " - site uses backup for now", flush=True)
            elif ollama_alive():
                db_exec("insert into pc_llm (id, url, key, model, fast_model, updated) values (1, %s, %s, %s, %s, now()) "
                        "on conflict (id) do update set url = excluded.url, key = excluded.key, model = excluded.model, "
                        "fast_model = excluded.fast_model, updated = now()", (found["url"], KEY, MODEL, FAST))
                print(time.strftime("%H:%M:%S"), f"heartbeat ok | GPU {STATE['gpu_c']} C | free RAM {STATE['free_gb']} GB",
                      flush=True)
            else:
                print(time.strftime("%H:%M:%S"), "Ollama not running - site uses Gemini", flush=True)
            time.sleep(30)
    finally:
        try:
            db_exec("update pc_llm set updated = now() - interval '1 hour' where id = 1")   # go offline at once
        except Exception:
            pass


if __name__ == "__main__":
    main()
