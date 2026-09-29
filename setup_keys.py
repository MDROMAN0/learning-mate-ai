"""Safe secret setup — paste keys HERE (hidden input), never in chat.   python setup_keys.py
Writes/updates .env (keeps every other line). Keys are never printed."""
import getpass
import os
import re
import secrets
import shutil


def set_env(path, key, value):
    """Replace an active `KEY=...` line or append one. Commented lines are left alone."""
    text = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
    line = f"{key}={value}"
    if re.search(rf"^{re.escape(key)}=.*$", text, flags=re.M):
        text = re.sub(rf"^{re.escape(key)}=.*$", lambda m: line, text, flags=re.M)
    else:
        text = text.rstrip("\n") + ("\n" if text else "") + line + "\n"
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def main(ask=getpass.getpass, say=print, path=".env"):
    here = os.path.dirname(os.path.abspath(__file__))
    if not os.path.isabs(path):
        path = os.path.join(here, path)
    if not os.path.exists(path):
        shutil.copy(os.path.join(here, ".env.example"), path)
    say("Chrome-এ https://aistudio.google.com/apikey থেকে Gemini key copy করে এখানে paste করো (দেখা যাবে না)।")
    llm = ask("LLM_API_KEY (Enter = skip): ").strip()
    if llm:
        set_env(path, "LLM_API_KEY", llm)
    say("Bangla ASR (Sarvam) চাইলে https://dashboard.sarvam.ai থেকে key; না চাইলে Enter।")
    sarvam = ask("SARVAM_API_KEY (Enter = skip): ").strip()
    if sarvam:
        set_env(path, "SARVAM_API_KEY", sarvam)
        set_env(path, "ASR_PROVIDER", "sarvam")
    pw = ask("APP_PASSWORD — public link/host-এর জন্য (Enter = নিজে বানিয়ে দেবে): ").strip()
    generated = not pw
    pw = pw or secrets.token_urlsafe(9)
    set_env(path, "APP_PASSWORD", pw)
    if generated:
        say(f"APP_PASSWORD তৈরি হলো: {pw}   ← কোথাও সেভ করে রাখো (website-এ App key হিসেবে লাগবে)")
    say("✅ .env আপডেট হলো। এরপর: python doctor.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
