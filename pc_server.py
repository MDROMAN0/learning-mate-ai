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


def gate():
    import httpx
    import uvicorn
    from fastapi import FastAPI, Request, Response

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    client = httpx.AsyncClient(timeout=300)

    @app.post("/v1/{path:path}")
    async def proxy(path: str, request: Request):
        if path not in ("chat/completions", "embeddings"):
            return Response("not found", status_code=404)
        if not secrets.compare_digest(request.headers.get("authorization", ""), "Bearer " + KEY):
            return Response("forbidden", status_code=403)
        r = await client.post(f"{OLLAMA}/v1/{path}", content=await request.body(),
                              headers={"content-type": "application/json"})
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
    if not DB.startswith("postgres"):
        sys.exit("DATABASE_URL (the same Neon URL the online site uses) is missing in .env")
    db_exec("create table if not exists pc_llm (id int primary key, url text, key text, model text, "
            "fast_model text, updated timestamptz)")
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
            if ollama_alive():
                db_exec("insert into pc_llm (id, url, key, model, fast_model, updated) values (1, %s, %s, %s, %s, now()) "
                        "on conflict (id) do update set url = excluded.url, key = excluded.key, model = excluded.model, "
                        "fast_model = excluded.fast_model, updated = now()", (found["url"], KEY, MODEL, FAST))
                print(time.strftime("%H:%M:%S"), "heartbeat ok", flush=True)
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
