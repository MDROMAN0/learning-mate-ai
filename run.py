"""One-command launcher:  python run.py [--share] [--no-browser]
Starts the app on 127.0.0.1:8000 and opens the browser. --share also opens a free public
Cloudflare Quick Tunnel link (needs `cloudflared`; refuses to run without APP_PASSWORD)."""
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser

from dotenv import load_dotenv


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    here = os.path.dirname(os.path.abspath(__file__))
    os.chdir(here)
    if not os.path.exists(".env") and os.path.exists(".env.example"):
        shutil.copy(".env.example", ".env")
        print("⚠️  .env তৈরি হলো — এখন .env খুলে LLM_API_KEY বসাও, তারপর আবার চালাও।")
        return 1
    load_dotenv()
    port = int(os.getenv("PORT", "8000"))
    url = f"http://localhost:{port}"
    tunnel = None
    if "--share" in argv:
        if not os.getenv("APP_PASSWORD"):
            print("❌ --share-এর আগে .env-এ APP_PASSWORD দাও (public link-এ নইলে যে কেউ তোমার LLM quota পোড়াবে)।")
            return 1
        exe = shutil.which("cloudflared")
        if not exe:
            print("❌ cloudflared নেই → Windows: winget install Cloudflare.cloudflared (তারপর terminal নতুন করে খোলো)")
            return 1
        tunnel = subprocess.Popen([exe, "tunnel", "--url", url], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        threading.Thread(target=lambda: [print("[tunnel]", ln.rstrip()) for ln in tunnel.stdout], daemon=True).start()

    def open_when_ready():
        for _ in range(120):
            try:
                urllib.request.urlopen(url + "/healthz", timeout=1)
                print("✅ চালু:", url, " (বন্ধ করতে Ctrl+C)")
                if "--no-browser" not in argv:
                    webbrowser.open(url)
                return
            except Exception:
                time.sleep(0.5)
    threading.Thread(target=open_when_ready, daemon=True).start()
    try:
        import uvicorn
        uvicorn.run("app:app", host="127.0.0.1", port=port, log_level="warning")
    finally:
        if tunnel:
            tunnel.terminate()
            try:
                tunnel.wait(timeout=5)
            except subprocess.TimeoutExpired:
                tunnel.kill()
    return 0


if __name__ == "__main__":
    sys.exit(main())
