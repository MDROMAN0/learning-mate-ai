"""Study tools that remember things per user: flashcards with spaced repetition, watch progress,
quiz scores, the progress dashboard, notebook search / share links, and AI-made notes.
Storage: the same database as accounts (auth._conn: SQLite locally, Postgres when DATABASE_URL is set)."""
import html
import json
import re
import secrets
import time
import uuid

import auth
import rag

DAY = 86400.0


def _rows(sql, args=()):
    with auth._LOCK, auth._conn() as c:
        return [dict(r) for r in c.execute(sql, args).fetchall()]


def _run(sql, args=()):
    with auth._LOCK, auth._conn() as c:
        c.execute(sql, args)


# ------------------------------------------------------------ flashcards (SM-2 spaced repetition)
def add_cards(uid, video_id, cards):
    """cards: [{front, back, start}] -> how many were added. Duplicates (same front) are skipped."""
    have = {r["front"] for r in _rows("SELECT front FROM cards WHERE user_id=? AND video_id=?", (uid, video_id))}
    now, n = time.time(), 0
    with auth._LOCK, auth._conn() as c:
        for cd in cards[:50]:
            front, back = str(cd.get("front", "")).strip()[:500], str(cd.get("back", "")).strip()[:1500]
            if not front or not back or front in have:
                continue
            have.add(front)
            start = cd.get("start")
            c.execute("INSERT INTO cards(id,user_id,video_id,front,back,start,due,ivl,ease,reps,created) "
                      "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                      (uuid.uuid4().hex, uid, video_id, front, back,
                       float(start) if isinstance(start, (int, float)) else None, now, 0.0, 2.5, 0, now))
            n += 1
    return n


def due_cards(uid, video_id=None, limit=30):
    now = time.time()
    where, args = "user_id=?", [uid]
    if video_id:
        where += " AND video_id=?"
        args.append(video_id)
    due = _rows(f"SELECT * FROM cards WHERE {where} AND due<=? ORDER BY due LIMIT ?", (*args, now, limit))
    total = _rows(f"SELECT COUNT(*) AS n FROM cards WHERE {where}", tuple(args))[0]["n"]
    n_due = _rows(f"SELECT COUNT(*) AS n FROM cards WHERE {where} AND due<=?", (*args, now))[0]["n"]
    return {"cards": due, "due": n_due, "total": total}


def schedule(card, grade):
    """SM-2 (the Anki algorithm, simplified). grade: 0 again, 1 hard, 2 good, 3 easy -> new (ivl days, ease, reps)."""
    ivl, ease, reps = float(card["ivl"] or 0), float(card["ease"] or 2.5), int(card["reps"] or 0)
    if grade == 0:
        return 10 / 1440, max(1.3, ease - 0.2), 0              # see it again in 10 minutes
    q = {1: 3, 2: 4, 3: 5}[grade]
    ease = max(1.3, ease + 0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
    if reps == 0:
        ivl = 1.0 if grade < 3 else 3.0
    elif reps == 1:
        ivl = 3.0 if grade < 3 else 6.0
    else:
        ivl = ivl * (1.2 if grade == 1 else ease) * (1.3 if grade == 3 else 1.0)
    return round(min(ivl, 365.0), 4), round(ease, 3), reps + 1


def review(uid, card_id, grade):
    rows = _rows("SELECT * FROM cards WHERE id=? AND user_id=?", (card_id, uid))
    if not rows:
        raise FileNotFoundError("card not found")
    ivl, ease, reps = schedule(rows[0], int(grade))
    due = time.time() + ivl * DAY
    _run("UPDATE cards SET ivl=?, ease=?, reps=?, due=? WHERE id=? AND user_id=?", (ivl, ease, reps, due, card_id, uid))
    return {"id": card_id, "due": due, "ivl_days": ivl}


def delete_card(uid, card_id):
    _run("DELETE FROM cards WHERE id=? AND user_id=?", (card_id, uid))


# ------------------------------------------------------------ progress, quiz scores, dashboard
def save_progress(uid, video_id, t, duration):
    """Remember the furthest point watched (never goes backwards)."""
    t, duration = max(0.0, float(t)), max(0.0, float(duration or 0))
    with auth._LOCK, auth._conn() as c:
        r = c.execute("SELECT watched, duration FROM progress WHERE user_id=? AND video_id=?", (uid, video_id)).fetchone()
        if r:
            c.execute("UPDATE progress SET watched=?, duration=?, updated=? WHERE user_id=? AND video_id=?",
                      (max(float(r["watched"] or 0), t), duration or float(r["duration"] or 0), time.time(), uid, video_id))
        else:
            c.execute("INSERT INTO progress(user_id,video_id,watched,duration,updated) VALUES(?,?,?,?,?)",
                      (uid, video_id, t, duration, time.time()))
    return {"ok": True}


def save_quiz(uid, video_id, score, total):
    total = max(1, int(total))
    _run("INSERT INTO quizzes(id,user_id,video_id,score,total,created) VALUES(?,?,?,?,?,?)",
         (uuid.uuid4().hex, uid, video_id, max(0, min(int(score), total)), total, time.time()))
    return {"ok": True}


def dashboard(uid):
    titles = {m["video_id"]: m for m in rag.list_library()}
    prog = {r["video_id"]: r for r in _rows("SELECT * FROM progress WHERE user_id=?", (uid,))}
    quiz = {}
    for r in _rows("SELECT video_id, score, total FROM quizzes WHERE user_id=?", (uid,)):
        q = quiz.setdefault(r["video_id"], [0, 0, 0])
        q[0] += r["score"]; q[1] += r["total"]; q[2] += 1
    notes = {r["video_id"] for r in auth.list_notes(uid)}
    asked = {}
    days = set()
    for r in _rows("SELECT video_id, created FROM history WHERE user_id=?", (uid,)):
        asked[r["video_id"]] = asked.get(r["video_id"], 0) + 1
        days.add(time.strftime("%Y-%m-%d", time.localtime(r["created"])))
    for r in prog.values():
        days.add(time.strftime("%Y-%m-%d", time.localtime(r["updated"])))
    now = time.time()
    cards = {}
    for r in _rows("SELECT video_id, due FROM cards WHERE user_id=?", (uid,)):
        c = cards.setdefault(r["video_id"], [0, 0])
        c[0] += 1; c[1] += r["due"] <= now
    vids = set(prog) | set(quiz) | notes | set(asked) | set(cards)
    out = []
    for v in vids:
        p, m = prog.get(v) or {}, titles.get(v) or {}
        dur = float(p.get("duration") or m.get("duration") or 0)
        q = quiz.get(v)
        out.append({"video_id": v, "title": m.get("title", v), "kind": m.get("kind", "youtube"),
                    "watched_pct": round(min(100.0, 100 * float(p.get("watched") or 0) / dur)) if dur else 0,
                    "quiz_pct": round(100 * q[0] / q[1]) if q and q[1] else None, "quizzes": q[2] if q else 0,
                    "questions": asked.get(v, 0), "has_notes": v in notes,
                    "cards": (cards.get(v) or [0, 0])[0], "cards_due": (cards.get(v) or [0, 0])[1],
                    "updated": float(p.get("updated") or 0)})
    out.sort(key=lambda x: -x["updated"])
    streak, d = 0, time.time()
    while time.strftime("%Y-%m-%d", time.localtime(d)) in days:
        streak += 1; d -= DAY
    return {"videos": out, "streak": streak, "cards_due": sum(x["cards_due"] for x in out),
            "questions": sum(asked.values()), "quizzes": sum(x["quizzes"] for x in out)}


# ------------------------------------------------------------ notebook: search + read-only share links
def _note_text(content):
    """Plain text of a notebook (text items, timestamp labels, screenshot captions)."""
    parts = []
    for it in (content or {}).get("items") or []:
        if it.get("type") == "text":
            parts.append(re.sub(r"<[^>]+>", " ", it.get("html") or ""))
        elif it.get("type") == "ts" and it.get("label"):
            parts.append(it["label"])
    return html.unescape(re.sub(r"\s+", " ", " ".join(parts))).strip()


def search_notes(uid, q):
    q = (q or "").strip().lower()
    if len(q) < 2:
        return []
    titles = {m["video_id"]: m.get("title", "") for m in rag.list_library()}
    out = []
    for n in auth.list_notes(uid):
        c = auth.get_note(uid, n["video_id"]).get("content") or {}
        txt = _note_text(c)
        title = c.get("title") or titles.get(n["video_id"], n["video_id"])
        i = txt.lower().find(q)
        if i < 0 and q not in title.lower():
            continue
        snip = txt[max(0, i - 60): i + len(q) + 90] if i >= 0 else txt[:150]
        out.append({"video_id": n["video_id"], "title": title, "snippet": snip, "updated": n["updated"]})
    return out[:30]


def share_note(uid, video_id):
    rows = _rows("SELECT token FROM shares WHERE user_id=? AND video_id=?", (uid, video_id))
    if rows:
        return rows[0]["token"]
    tok = secrets.token_urlsafe(12)
    _run("INSERT INTO shares(token,user_id,video_id,created) VALUES(?,?,?,?)", (tok, uid, video_id, time.time()))
    return tok


def unshare_note(uid, video_id):
    _run("DELETE FROM shares WHERE user_id=? AND video_id=?", (uid, video_id))


def shared_note(token):
    rows = _rows("SELECT user_id, video_id FROM shares WHERE token=?", (token,))
    if not rows:
        raise FileNotFoundError("this share link was turned off or does not exist")
    r = rows[0]
    c = auth.get_note(r["user_id"], r["video_id"]).get("content")
    m = next((x for x in rag.list_library() if x["video_id"] == r["video_id"]), {})
    return {"video_id": r["video_id"], "title": (c or {}).get("title") or m.get("title", r["video_id"]),
            "kind": m.get("kind", "youtube"), "doc": m.get("doc"), "content": c}


# ------------------------------------------------------------ AI notes: summary notes / mind map / flashcards
KINDS = {
    "summary": ("study notes", "Return JSON: {\"title\": str, \"sections\": [{\"heading\": str, \"points\": [{\"text\": str, "
                "\"source\": passage index}]}]} with 3-6 sections and 2-5 short points each."),
    "mindmap": ("a mind map", "Return JSON: {\"center\": main topic (max 5 words), \"branches\": [{\"label\": str (max 5 words), "
                "\"source\": passage index, \"children\": [{\"label\": str (max 8 words), \"source\": passage index}]}]} "
                "with 3-6 branches and 2-4 children each."),
    "flashcards": ("flashcards", "Return JSON: {\"cards\": [{\"front\": a question, \"back\": short answer (1-2 sentences), "
                   "\"source\": passage index}]} with 8-12 cards about the most important facts and definitions."),
}


def ai_notes(video_id, kind, current_time=None):
    if kind not in KINDS:
        raise ValueError("kind must be summary, mindmap or flashcards")
    ix = rag.load_index(video_id)
    pool = [c for c in (rag.trim_chunk(c, current_time) for c in ix.chunks) if c]
    if not pool:
        raise ValueError("nothing watched yet")
    per = max(150, min(600, 14000 // len(pool)))
    listing = "\n".join(f"[{i}] ({rag.fmt(c['start'])}) {c['text'][:per]}" for i, c in enumerate(pool))
    what, shape = KINDS[kind]
    out = rag.parse_json(rag.llm(
        f"You turn a lecture transcript into {what} for a student. Use ONLY what the transcript says. "
        "The transcript is noisy auto-captions (often Bangla; English terms may be in Bangla script). "
        + rag.lang_rule("Write in Bangla script, keep English technical terms."),
        f"Video title: {ix.meta.get('title', video_id)}\n\nNumbered transcript passages:\n{listing}\n\n{shape}",
        temperature=0.2, max_tokens=2200)) or {}
    at = lambda s: pool[s]["start"] if isinstance(s, int) and 0 <= s < len(pool) else None
    if kind == "flashcards":
        cards = [{"front": str(c.get("front", "")).strip(), "back": str(c.get("back", "")).strip(), "start": at(c.get("source"))}
                 for c in out.get("cards") or [] if isinstance(c, dict)]
        cards = [c for c in cards if c["front"] and c["back"]]
        if not cards:
            raise RuntimeError("could not make flashcards - try again")
        return {"kind": kind, "cards": cards}
    if kind == "mindmap":
        br = []
        for b in out.get("branches") or []:
            if not isinstance(b, dict) or not str(b.get("label", "")).strip():
                continue
            kids = [{"label": str(k.get("label", "")).strip(), "start": at(k.get("source"))}
                    for k in b.get("children") or [] if isinstance(k, dict) and str(k.get("label", "")).strip()]
            br.append({"label": str(b["label"]).strip(), "start": at(b.get("source")), "children": kids})
        if not br:
            raise RuntimeError("could not make a mind map - try again")
        return {"kind": kind, "center": str(out.get("center") or ix.meta.get("title", "")).strip()[:60], "branches": br[:7]}
    secs = []
    for s in out.get("sections") or []:
        if not isinstance(s, dict):
            continue
        pts = [{"text": str(p.get("text", "")).strip(), "start": at(p.get("source"))}
               for p in s.get("points") or [] if isinstance(p, dict) and str(p.get("text", "")).strip()]
        if pts:
            secs.append({"heading": str(s.get("heading", "")).strip(), "points": pts})
    if not secs:
        raise RuntimeError("could not make notes - try again")
    return {"kind": kind, "title": str(out.get("title", "")).strip(), "sections": secs}
