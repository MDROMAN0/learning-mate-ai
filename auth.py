"""Accounts for the hosted version (ChatGPT-style sign up / log in), no extra dependencies.

AUTH=1 in .env turns it on. Then every /api/* call needs a logged-in session cookie
(or the admin APP_PASSWORD in the x-app-key header - used by the Chrome extension / scripts).
- passwords: PBKDF2-HMAC-SHA256 (200k rounds, per-user salt), never stored in plain text
- sessions: HMAC-signed token (SECRET_KEY) in an HttpOnly cookie, 30 days
- per-user daily limit on LLM-heavy calls (DAILY_LIMIT, default 60) so one user can't burn the free quota
- storage: DATABASE_URL (Postgres, e.g. free Neon) if set - survives free-host restarts;
  else SQLite file AUTH_DB (default <DATA_DIR>/users.db). Free hosts wipe local disk on restart (docs/DEPLOY.md).
"""
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import threading
import time
from pathlib import Path

import rag

_LOCK = threading.Lock()
COOKIE = "vidya_session"
SESSION_DAYS = 30


def enabled():
    return os.getenv("AUTH", "0").strip().lower() in ("1", "true", "yes", "on")


def daily_limit():
    return int(os.getenv("DAILY_LIMIT", "60"))


def _db_path():
    return Path(os.getenv("AUTH_DB") or (rag.DATA / "users.db"))


class _PG:
    """Tiny adapter so the same SQL runs on Postgres (DATABASE_URL, e.g. free Neon/Supabase) - accounts then
    survive free-host restarts. Translates '?' -> '%s' and SQLite-only syntax."""
    def __init__(self, url):
        import psycopg
        from psycopg.rows import dict_row
        self.c = psycopg.connect(url, row_factory=dict_row, autocommit=False)

    def execute(self, sql, args=()):
        sql = sql.replace("?", "%s").replace("INTEGER PRIMARY KEY", "SERIAL PRIMARY KEY").replace(" REAL", " DOUBLE PRECISION")
        if sql.lstrip().upper().startswith("INSERT OR REPLACE INTO USAGE"):
            sql = ("INSERT INTO usage(user_id,day,n) VALUES(%s,%s,%s) "
                   "ON CONFLICT(user_id,day) DO UPDATE SET n=EXCLUDED.n")
        ret = sql.lstrip().upper().startswith("INSERT INTO USERS")
        cur = self.c.execute(sql + (" RETURNING id" if ret else ""), args)
        if ret:
            class _R:
                lastrowid = cur.fetchone()["id"]
            return _R()
        return cur

    def executescript(self, script):
        for stmt in [x.strip() for x in script.split(";") if x.strip()]:
            self.execute(stmt)

    def __enter__(self):
        return self

    def __exit__(self, et, *a):
        (self.c.rollback if et else self.c.commit)()
        self.c.close()


def _conn():
    if os.getenv("DATABASE_URL"):
        c = _PG(os.environ["DATABASE_URL"])
        c.executescript(_SCHEMA)
        return c
    p = _db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(p), check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.executescript(_SCHEMA)
    return c


_SCHEMA = """
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT,
    pw TEXT NOT NULL, salt TEXT NOT NULL, created REAL);
CREATE TABLE IF NOT EXISTS usage(user_id INTEGER, day TEXT, n INTEGER, PRIMARY KEY(user_id, day));
CREATE TABLE IF NOT EXISTS notes(user_id INTEGER, video_id TEXT, content TEXT, updated REAL, PRIMARY KEY(user_id, video_id));
CREATE TABLE IF NOT EXISTS history(id INTEGER PRIMARY KEY, user_id INTEGER, video_id TEXT, title TEXT,
    question TEXT, found INTEGER, answer TEXT, created REAL);
"""


def _secret():
    s = os.getenv("SECRET_KEY")
    if s:
        return s.encode()
    f = rag.DATA / "secret.key"          # generated once per install
    if not f.exists():
        f.write_text(secrets.token_hex(32))
    return f.read_text().strip().encode()


def _hash(pw, salt):
    return hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 200_000).hex()


EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def signup(email, password, name=""):
    email = (email or "").strip().lower()
    if not EMAIL.match(email):
        raise ValueError("invalid email")
    if len(password or "") < 6:
        raise ValueError("password must be at least 6 characters")
    salt = secrets.token_hex(16)
    with _LOCK, _conn() as c:
        try:
            cur = c.execute("INSERT INTO users(email,name,pw,salt,created) VALUES(?,?,?,?,?)",
                            (email, (name or email.split("@")[0]).strip()[:60], _hash(password, salt), salt, time.time()))
        except Exception as e:
            if isinstance(e, sqlite3.IntegrityError) or "unique" in str(e).lower():
                raise ValueError("this email already has an account - log in instead")
            raise
        return {"id": cur.lastrowid, "email": email, "name": (name or email.split("@")[0]).strip()[:60]}


def login(email, password):
    with _LOCK, _conn() as c:
        r = c.execute("SELECT * FROM users WHERE email=?", ((email or "").strip().lower(),)).fetchone()
    if not r or not hmac.compare_digest(r["pw"], _hash(password or "", r["salt"])):
        raise PermissionError("wrong email or password")
    return {"id": r["id"], "email": r["email"], "name": r["name"]}


def make_token(uid):
    exp = int(time.time()) + SESSION_DAYS * 86400
    msg = f"{uid}.{exp}"
    return msg + "." + hmac.new(_secret(), msg.encode(), hashlib.sha256).hexdigest()


def user_from_token(tok):
    try:
        uid, exp, sig = (tok or "").split(".")
        good = hmac.new(_secret(), f"{uid}.{exp}".encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, good) or int(exp) < time.time():
            return None
        with _LOCK, _conn() as c:
            r = c.execute("SELECT id,email,name FROM users WHERE id=?", (int(uid),)).fetchone()
        return dict(r) if r else None
    except Exception:
        return None


def _today():
    return time.strftime("%Y-%m-%d")


def used_today(uid):
    with _LOCK, _conn() as c:
        r = c.execute("SELECT n FROM usage WHERE user_id=? AND day=?", (uid, _today())).fetchone()
    return r["n"] if r else 0


def charge(uid):
    """Count one LLM-heavy request; False when the user is over today's limit."""
    with _LOCK, _conn() as c:
        r = c.execute("SELECT n FROM usage WHERE user_id=? AND day=?", (uid, _today())).fetchone()
        n = r["n"] if r else 0
        if n >= daily_limit():
            return False
        c.execute("INSERT OR REPLACE INTO usage(user_id,day,n) VALUES(?,?,?)", (uid, _today(), n + 1))
    return True


def add_history(uid, video_id, title, question, out):
    ans = out.get("answer") if out.get("found") else None
    with _LOCK, _conn() as c:
        c.execute("INSERT INTO history(user_id,video_id,title,question,found,answer,created) VALUES(?,?,?,?,?,?,?)",
                  (uid, video_id, title or "", question, int(bool(out.get("found"))),
                   json.dumps(ans, ensure_ascii=False) if ans else None, time.time()))


def history(uid, limit=50):
    with _LOCK, _conn() as c:
        rows = c.execute("SELECT id,video_id,title,question,found,created FROM history WHERE user_id=? "
                         "ORDER BY id DESC LIMIT ?", (uid, limit)).fetchall()
    return [dict(r) for r in rows]


NOTE_MAX = 6_000_000  # bytes of JSON (notes html + screenshots + whiteboard images)


def get_note(uid, video_id):
    with _LOCK, _conn() as c:
        r = c.execute("SELECT content, updated FROM notes WHERE user_id=? AND video_id=?", (uid, video_id)).fetchone()
    return {"content": json.loads(r["content"]), "updated": r["updated"]} if r else {"content": None, "updated": None}


def save_note(uid, video_id, content):
    raw = json.dumps(content, ensure_ascii=False)
    if len(raw.encode()) > NOTE_MAX:
        raise ValueError("note too large (remove some screenshots)")
    now = time.time()
    with _LOCK, _conn() as c:
        cur = c.execute("UPDATE notes SET content=?, updated=? WHERE user_id=? AND video_id=?", (raw, now, uid, video_id))
        if not cur.rowcount:
            c.execute("INSERT INTO notes(user_id,video_id,content,updated) VALUES(?,?,?,?)", (uid, video_id, raw, now))
    return {"updated": now}
