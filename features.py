"""Advanced features on top of rag.py: alternative videos + comparison, watch plan, quiz, 'বুঝিনি' explain."""
import json
import math
import os
from datetime import datetime, timezone

import rag
from rag import fmt, parse_json, yt_link


def _ref(vid, c, n=None):
    r = {"video_id": vid, "start": c["start"], "end": c["end"], "url": yt_link(vid, c["start"]),
         "preview": c["text"][:160]}
    if n is not None:
        r["n"] = n
    return r


# ------------------------------------------------------------ alternatives
def search_youtube(query, n=5):
    """YouTube Data API if YT_API_KEY set, else yt-dlp search. Rank = relevance + popularity + recency."""
    import httpx
    key, items = os.getenv("YT_API_KEY"), []
    if key:
        r = httpx.get("https://www.googleapis.com/youtube/v3/search", timeout=20,
                      params={"part": "snippet", "q": query, "type": "video", "maxResults": n * 2, "key": key})
        r.raise_for_status()
        ids = [i["id"]["videoId"] for i in r.json().get("items", [])]
        st = httpx.get("https://www.googleapis.com/youtube/v3/videos", timeout=20,
                       params={"part": "statistics,snippet", "id": ",".join(ids), "key": key}).json()
        by = {v["id"]: v for v in st.get("items", [])}
        for pos, vid in enumerate(ids):
            v = by.get(vid)
            if v:
                items.append({"id": vid, "title": v["snippet"]["title"], "channel": v["snippet"]["channelTitle"],
                              "views": int(v.get("statistics", {}).get("viewCount", 0)),
                              "published": v["snippet"].get("publishedAt"), "pos": pos})
    else:
        import yt_dlp
        with yt_dlp.YoutubeDL({"quiet": True, "extract_flat": True}) as y:
            res = y.extract_info(f"ytsearch{n * 2}:{query}", download=False)
        for pos, e in enumerate(res.get("entries", [])):
            items.append({"id": e["id"], "title": e.get("title", e["id"]), "channel": e.get("channel", ""),
                          "views": e.get("view_count") or 0, "published": None, "pos": pos})
    total = max(len(items), 1)
    for it in items:
        rec = 0.0
        if it.get("published"):
            try:
                age = (datetime.now(timezone.utc) - datetime.fromisoformat(it["published"].replace("Z", "+00:00"))).days
                rec = max(0.0, 1 - age / 1825)
            except Exception:
                pass
        it["score"] = (1 - it["pos"] / total) + 0.3 * math.log10(it["views"] + 1) / 7 + 0.1 * rec
    return sorted(items, key=lambda x: -x["score"])[:n]


def ensure_light_index(vid, title):
    """Captions-only index (no download, no clips) for discovered videos."""
    if rag.index_exists(vid):
        return rag.load_index(vid).meta
    segs = rag.fetch_captions(vid)
    if not segs:
        return None
    return rag.build_index_from_segments(vid, title, segs, "captions", None, "youtube")


def ask_light(vid, question, queries, level="simple"):
    ix = rag.load_index(vid)
    cands = rag.retrieve(ix, queries, question, k=6, mode="hybrid")
    rel, _ = rag.grade_chunks(question, cands)
    if not rel:
        return None
    ev = sorted(rel, key=lambda c: c["start"])[:5]
    ans = rag.generate_answer(question, ev, level)
    if not ans["sections"]:
        return None
    return {"video_id": vid, "title": ix.meta.get("title", vid), "kind": ix.meta.get("kind", "youtube"),
            "answer": ans, "refs": [_ref(vid, c, i + 1) for i, c in enumerate(ev)]}


def compare_answers(question, items):
    blocks = []
    for i, it in enumerate(items):
        pts = [f"- {p['text']}" for s in it["answer"]["sections"] for p in s["points"]]
        blocks.append(f"Video {i}: {it['title']}\n" + "\n".join(pts))
    out = parse_json(rag.llm(
        "You compare how different videos answer the same question. Use ONLY the given points. "
        "Do NOT decide who is right; just show differences and direct contradictions. "
        "Write in Bangla script with English technical terms if the question is Bangla/Banglish.",
        f"Question: {question}\n\n" + "\n\n".join(blocks) +
        "\n\nReturn JSON: {\"common\": [{\"text\": str, \"videos\": [int]}], "
        "\"different\": [{\"topic\": str, \"views\": [{\"video\": int, \"says\": str}]}], "
        "\"unique\": [{\"video\": int, \"text\": str}], "
        "\"conflicts\": [{\"topic\": str, \"views\": [{\"video\": int, \"says\": str}]}]}", max_tokens=1500))
    out = out or {}
    return {k: out.get(k, []) if isinstance(out.get(k, []), list) else [] for k in
            ("common", "different", "unique", "conflicts")}


def alternatives(question, video_id=None, mode="library", n=3, level="simple"):
    """mode=library: compare across already-indexed videos (works on free hosting).
    mode=discover: search YouTube for popular videos + fetch captions (needs a non-blocked IP)."""
    cands, skipped = [], []
    if mode == "discover":
        for it in search_youtube(question, n + 2):
            if it["id"] == video_id:
                continue
            try:
                meta = ensure_light_index(it["id"], it["title"])
            except Exception as e:
                skipped.append({"id": it["id"], "reason": str(e)[:100]})
                continue
            if meta:
                cands.append(it["id"])
            else:
                skipped.append({"id": it["id"], "title": it["title"], "reason": "no captions / blocked"})
            if len(cands) >= n:
                break
        if video_id:
            cands.insert(0, video_id)
    else:
        ids = [m["video_id"] for m in rag.list_library()]
        cands = ([video_id] if video_id in ids else []) + [i for i in ids if i != video_id]
        cands = cands[:n + 1]
    if len(cands) < 2:
        return {"videos": [], "comparison": None, "skipped": skipped,
                "message": "তুলনা করার মতো কমপক্ষে ২টা video লাগবে (library-তে আরও video যোগ করো)।"}
    title0 = rag.load_index(cands[0]).meta.get("title", "")
    queries = rag.rewrite_query(question, title0)
    items = []
    for vid in cands:
        try:
            r = ask_light(vid, question, queries, level)
        except Exception as e:
            skipped.append({"id": vid, "reason": str(e)[:100]})
            continue
        if r:
            items.append(r)
        else:
            skipped.append({"id": vid, "reason": "topic not found"})
    if not items:
        return {"videos": [], "comparison": None, "skipped": skipped, "message": "কোনো video-তে topic পাওয়া যায়নি।"}
    comp = compare_answers(question, items) if len(items) > 1 else None
    return {"videos": items, "comparison": comp, "skipped": skipped, "message": None}


# -------------------------------------------------------------- watch plan
def plan_start(goal):
    out = parse_json(rag.llm(
        "You are a tutor writing quick diagnostic questions.",
        f"Learner goal: {goal}\nWrite 3 short diagnostic questions (1-2 sentence answers) that reveal what "
        "they already know. Language: Bangla script (keep English technical terms) if the goal is Bangla/"
        "Banglish, else English. Return JSON: {\"questions\": [str]}", max_tokens=300))
    qs = [q for q in (out or {}).get("questions", []) if isinstance(q, str)][:3]
    if not qs:
        raise RuntimeError("could not generate questions")
    return qs


def plan_finish(goal, qa, video_ids):
    """qa=[{q,a}] -> gaps -> segments across videos -> ordered minimal watch plan."""
    qa_txt = "\n".join(f"Q: {x.get('q', '')}\nA: {x.get('a', '') or '(no answer)'}" for x in qa)
    j = parse_json(rag.llm(
        "You assess a learner's knowledge from diagnostic answers.",
        f"Goal: {goal}\n{qa_txt}\n\nReturn JSON: {{\"known\": [short topics they already know], "
        "\"gaps\": [2-5 short search phrases for specific subtopics they still need]}", max_tokens=300)) or {}
    gaps = [g for g in j.get("gaps", []) if isinstance(g, str)][:5] or [goal]
    idxs = {v: rag.load_index(v) for v in video_ids}
    cand = []
    for gi, g in enumerate(gaps):
        for vid, ix in idxs.items():
            for c in rag.retrieve(ix, [g], g, k=2, mode="hybrid"):
                cand.append({"gap": gi, "video_id": vid, "c": c})
    if not cand:
        return {"known": j.get("known", []), "gaps": gaps, "plan": [], "watch_sec": 0, "total_sec": 0}
    listing = "\n".join(f"[{i}] gap={x['gap']} video=\"{idxs[x['video_id']].meta.get('title', '')}\" "
                        f"({fmt(x['c']['start'])}-{fmt(x['c']['end'])}): {x['c']['text'][:300]}"
                        for i, x in enumerate(cand))
    pick = parse_json(rag.llm(
        "You design a minimal learning path. Choose the single best segment per gap, skipping what the "
        "learner already knows, ordered from prerequisites to advanced.",
        f"Goal: {goal}\nGaps: {json.dumps(gaps, ensure_ascii=False)}\nCandidates:\n{listing}\n\n"
        "Return JSON: {\"plan\": [{\"pick\": candidate index, \"why\": one short line}]}", max_tokens=600)) or {}
    plan, seen = [], set()
    for p in pick.get("plan", []):
        i = p.get("pick")
        if isinstance(i, int) and 0 <= i < len(cand) and i not in seen:
            seen.add(i)
            x = cand[i]
            plan.append({"gap": gaps[x["gap"]], "why": str(p.get("why", "")), **_ref(x["video_id"], x["c"]),
                         "title": idxs[x["video_id"]].meta.get("title", "")})
    watch = sum(p["end"] - p["start"] for p in plan)
    total = sum(ix.meta.get("duration", 0) for ix in idxs.values())
    return {"known": j.get("known", []), "gaps": gaps, "plan": plan, "watch_sec": watch, "total_sec": total}


# -------------------------------------------------------------------- quiz
def quiz(video_id, n=5, topic=None, current_time=None):
    ix = rag.load_index(video_id)
    if topic:
        ev = rag.retrieve(ix, [topic], topic, k=6, max_time=current_time, mode="hybrid")
    else:
        pool = [rag.trim_chunk(c, current_time) for c in ix.chunks]
        pool = [c for c in pool if c]
        step = max(len(pool) / (n + 2), 1)
        ev = [pool[int(i * step)] for i in range(min(n + 2, len(pool)))]
    ev = sorted(ev, key=lambda c: c["start"])
    if not ev:
        return []
    text = "\n\n".join(f"[{i}] {c['text'][:900]}" for i, c in enumerate(ev))
    out = parse_json(rag.llm(
        "You write multiple-choice questions ONLY from the given transcript passages. Language: Bangla "
        "script (keep English technical terms) if the passages are Bangla, else English.",
        f"Passages:\n{text}\n\nWrite {n} questions. Return JSON: {{\"questions\": [{{\"q\": str, "
        "\"options\": [4 strings], \"answer\": index 0-3, \"explanation\": str, \"source\": passage index}]}",
        temperature=0.3, max_tokens=1800)) or {}
    res = []
    for q in out.get("questions", []):
        try:
            opts, a, s = q["options"], q["answer"], q["source"]
            if len(opts) == 4 and isinstance(a, int) and 0 <= a < 4 and isinstance(s, int) and 0 <= s < len(ev):
                res.append({"q": str(q["q"]), "options": [str(o) for o in opts], "answer": a,
                            "explanation": str(q.get("explanation", "")), **_ref(video_id, ev[s])})
        except Exception:
            continue
    return res[:n]


# ----------------------------------------------- 'বুঝিনি' explain at a timestamp
STYLES = {"simple": "Explain the passage more simply, in short sentences.",
          "analogy": "Explain with one everyday analogy. Label the analogy 'উপমা (video-তে নেই):'.",
          "steps": "Explain step by step as a short numbered list."}


def explain(video_id, current_time, style="simple"):
    ix = rag.load_index(video_id)
    seg = [s for c in ix.chunks for s in c["segs"] if current_time - 90 <= s[0] < current_time]
    if not seg:
        raise ValueError("এই সময়ের আগে কোনো transcript নেই")
    passage = " ".join(s[1] for s in seg)
    rng = {"start": seg[0][0], "end": current_time}
    lang = os.getenv("EXPLAIN_LANG", "Bangla script, keep English technical terms")
    if style == "other_video":
        cands = []
        for m in rag.list_library():
            if m["video_id"] == video_id:
                continue
            try:
                for c in rag.retrieve(rag.load_index(m["video_id"]), [passage[:400]], passage[:400], k=1, mode="hybrid"):
                    cands.append((m, c))
            except Exception:
                continue
        if cands:
            lst = "\n".join(f"[{i}] ({m['title']}) {c['text'][:500]}" for i, (m, c) in enumerate(cands))
            out = parse_json(rag.llm(
                f"Reply in {lang}. Use ONLY the passages given.",
                f"The learner did not understand this passage:\n{passage}\n\nAlternative passages from other "
                f"videos:\n{lst}\n\nPick the one that explains the same concept differently/clearer, or -1 if "
                "none fits. Return JSON: {\"pick\": int, \"explanation\": str}", max_tokens=700)) or {}
            p = out.get("pick")
            if isinstance(p, int) and 0 <= p < len(cands):
                m, c = cands[p]
                return {"style": style, "explanation": str(out.get("explanation", "")), "passage": rng,
                        "source": {**_ref(m["video_id"], c), "title": m["title"]}}
        style = "simple"  # fallback: no usable alternative video
    txt = rag.llm(f"Reply in {lang}. Use ONLY the passage; do not add facts.",
              f"{STYLES.get(style, STYLES['simple'])}\n\nPassage:\n{passage}", max_tokens=600)
    return {"style": style, "explanation": txt.strip(), "passage": rng, "source": None}


# ------------------------------------------------------------ in-app YouTube browse
def browse_youtube(query, n=16):
    """Search results for the in-app YouTube browser (id, title, channel, duration, views, indexed?).
    yt-dlp flat search (works from a home IP, no API key); YouTube Data API when YT_API_KEY is set."""
    query = (query or "").strip()
    if not query:
        return []
    out = []
    if os.getenv("YT_API_KEY"):
        for it in search_youtube(query, n):
            out.append({"id": it["id"], "title": it["title"], "channel": it.get("channel", ""),
                        "duration": None, "views": it.get("views")})
    else:
        import yt_dlp
        with yt_dlp.YoutubeDL({"quiet": True, "extract_flat": True, "skip_download": True}) as y:
            res = y.extract_info(f"ytsearch{n}:{query}", download=False)
        for e in res.get("entries") or []:
            if not e or not e.get("id") or len(e["id"]) != 11:
                continue
            out.append({"id": e["id"], "title": e.get("title") or e["id"], "channel": e.get("channel") or e.get("uploader") or "",
                        "duration": e.get("duration"), "views": e.get("view_count")})
    for it in out:
        it["indexed"] = rag.index_exists(it["id"])
    return out
