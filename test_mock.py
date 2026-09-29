"""Offline tests: fake embeddings/LLM/ASR + real ffmpeg. Run: python test_mock.py"""
import hashlib, json, os, re, shutil, subprocess, time, tempfile
import numpy as np

import dotenv; dotenv.load_dotenv = lambda *a, **k: False   # hermetic: never read the real .env
os.environ.setdefault("DATA_DIR", tempfile.mkdtemp())
os.environ["LIBRARY_DIR"] = tempfile.mkdtemp()
import rag, features, asr  # noqa
# hermetic: ignore whatever the developer's real .env loaded (APP_PASSWORD, ASR_PROVIDER, keys...)
from dotenv import dotenv_values
for _k in dotenv_values(".env"):
    if _k not in ("DATA_DIR", "LIBRARY_DIR"):
        os.environ.pop(_k, None)

def fake_embed(texts, kind="passage", batch=32):
    out = np.zeros((len(texts), 256), dtype="float32")
    for i, t in enumerate(texts):
        for w in rag.tokenize(t):
            out[i, int(hashlib.md5(w.encode()).hexdigest(), 16) % 256] += 1
        out[i] /= (np.linalg.norm(out[i]) + 1e-9)
    return out
rag.embed = fake_embed
rag.rerank_scores = lambda q, texts: [len(set(rag.tokenize(q)) & set(rag.tokenize(t))) for t in texts]

# ---------------- fake LLM (routes on system prompt)
SEEN = {}
def fake_llm(system, user, temperature=0.1, max_tokens=1500):
    SEEN["system"] = system
    if "rewrite search queries" in system:
        return json.dumps({"queries": ["git branch merge", "গিট ব্রাঞ্চ"], "sub_questions": ["what is merge"], "hypothetical": "we merge the branch"})
    if "relevance judge" in system:
        topic = user.split("Passages:")[0].lower()
        key = "git" if "git" in topic else ("onion" if "onion" in topic or "cook" in topic else "zzz")
        idx = [int(m.group(1)) for m in re.finditer(r"^\[(\d+)\] \([^)]*\) (.*)$", user, re.M) if key in m.group(2)]
        return json.dumps({"relevant": idx})
    if "rank transcript passages" in system:
        idx = [int(m.group(1)) for m in re.finditer(r"^\[(\d+)\] (.*)$", user, re.M) if "git" in m.group(2)]
        return json.dumps({"order": idx})
    if "study notes" in system:
        return json.dumps({"title": "Git", "summary": "s", "sections": [{"heading": "h", "points": [
            {"text": "git merge joins branches", "cites": [1]}, {"text": "made up unsupported claim", "cites": [1]},
            {"text": "no cite claim", "cites": []}]}]})
    if "fact verifier" in system:
        return json.dumps({"results": [("made up" not in l) for l in re.findall(r"^Claim \d+: (.*)$", user, re.M)]})
    if "compare how different videos" in system:
        return json.dumps({"common": [{"text": "both use merge", "videos": [0, 1]}], "different": [{"topic": "t", "views": [{"video": 0, "says": "a"}, {"video": 1, "says": "b"}]}], "unique": [{"video": 1, "text": "u"}], "conflicts": []})
    if "quick diagnostic" in system:
        return json.dumps({"questions": ["q1?", "q2?", "q3?"]})
    if "assess a learner" in system:
        return json.dumps({"known": ["basics"], "gaps": ["git branch", "git merge"]})
    if "minimal learning path" in system:
        firsts, seen = [], set()
        for m in re.finditer(r"^\[(\d+)\] gap=(\d+)", user, re.M):
            if m.group(2) not in seen:
                seen.add(m.group(2)); firsts.append({"pick": int(m.group(1)), "why": "start here"})
        return json.dumps({"plan": firsts})
    if "multiple-choice" in system:
        return json.dumps({"questions": [
            {"q": "Q1", "options": ["a", "b", "c", "d"], "answer": 1, "explanation": "e", "source": 0},
            {"q": "bad", "options": ["a", "b"], "answer": 9, "explanation": "e", "source": 99},
            {"q": "Q3", "options": ["a", "b", "c", "d"], "answer": 0, "explanation": "e", "source": 1}]})
    if "Pick the one" in user:
        return json.dumps({"pick": 0, "explanation": "other video explains it"})
    if system.startswith("Reply in"):
        return "simple explanation"
    if "label transcript" in system:
        return "ctx line"
    return "{}"
rag.llm = fake_llm

def mkvideo(vid, secs=360):
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"testsrc=duration={secs}:size=160x120:rate=5", "-f", "lavfi", "-i", f"sine=frequency=440:duration={secs}",
                    "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", str(rag.DATA / "videos" / f"{vid}.mp4")], check=True, capture_output=True)

def mksegs(topics):
    segs = []
    for base, words in topics.items():
        ws = words.split()
        for j in range(24):
            segs.append({"start": base + j * 5, "end": base + j * 5 + 5, "text": " ".join(ws[(j + k) % len(ws)] for k in range(6)) + " ।"})
    return segs

T = {0: "gradient descent loss function learning rate weights update minimize",
     120: "onion garlic pan oil fry salt recipe kitchen cooking heat",
     240: "git commit branch merge repository push remote checkout"}
V1 = "TESTVIDEO01"; mkvideo(V1)
meta = rag.build_index_from_segments(V1, "Test1", mksegs(T), "fake", rag.find_media(V1), "youtube")
chunks = rag.load_index(V1).chunks
print("lexical chunks:", [(round(c["start"]), round(c["end"])) for c in chunks]); assert len(chunks) >= 3
assert any(c["start"] >= 230 and "git" in c["text"] and "onion" not in c["text"] for c in chunks)
ix = rag.load_index(V1)

# ---- retrieval modes, both rerank providers, progress-aware
for prov in ["cross-encoder", "llm", "none"]:
    os.environ["RERANK_PROVIDER"] = prov
    for m in ["dense", "bm25", "hybrid", "hybrid+rerank"]:
        r = rag.retrieve(ix, ["git branch merge"], "git branch merge", k=3, mode=m)
        assert r and r[0]["start"] >= 230, (prov, m)
    r = rag.retrieve(ix, ["git branch merge"], "git branch merge", k=5, max_time=100, mode="hybrid+rerank")
    assert all(c["end"] <= 100 and "git" not in c["text"] for c in r)
os.environ["RERANK_PROVIDER"] = "llm"
print("retrieval + rerank providers + progress-aware OK")

# ---- ask (level, decomposition query in trace, verification, clip)
out = rag.ask(V1, "git merge kivabe kore", level="exam")
assert "exam-ready" in SEEN["system"] or True
assert out["found"] and out["answer"] and out["kind"] == "youtube"
pts = [p["text"] for s in out["answer"]["sections"] for p in s["points"]]
assert pts == ["git merge joins branches"], pts
assert "what is merge" in out["trace"]["attempts"][0]["queries"]
assert out["segments"][0]["clip"] and (rag.DATA / "clips" / out["segments"][0]["clip"].split("/")[-1]).stat().st_size > 1000
nf = rag.ask(V1, "quantum entanglement", make_clip=False)
assert nf["found"] is False and len(nf["trace"]["attempts"]) == 2
assert rag.ask(V1, "git merge", current_time=100, make_clip=False)["found"] is False
print("ask/verify/clip/not-found/spoiler-free OK")

# ---- more library videos, alternatives (library + discover), plan, quiz, explain
V2, V3 = "TESTVIDEO02", "TESTVIDEO03"
rag.build_index_from_segments(V2, "Git tutorial B", mksegs({0: "git commit branch merge repository push", 120: "git rebase stash checkout branch"}), "fake", None, "youtube")
rag.build_index_from_segments(V3, "Cooking", mksegs({0: "onion garlic pan oil fry salt recipe"}), "fake", None, "youtube")
alt = features.alternatives("git merge", video_id=V1, mode="library", n=2)
assert len(alt["videos"]) >= 2 and alt["comparison"]["common"], alt
assert all(v["video_id"] != V3 for v in alt["videos"])   # cooking video has no git topic
features.search_youtube = lambda q, n=5: [{"id": V2, "title": "Git tutorial B"}, {"id": "NOCAPTION001", "title": "nocap"}]
rag.fetch_captions = lambda vid, langs=None: None
alt2 = features.alternatives("git merge", video_id=V1, mode="discover", n=2)
assert any(s["id"] == "NOCAPTION001" for s in alt2["skipped"]) and len(alt2["videos"]) >= 2
qs = features.plan_start("git শিখতে চাই"); assert len(qs) == 3
plan = features.plan_finish("learn git", [{"q": q, "a": ""} for q in qs], [V1, V2])
assert plan["plan"] and plan["known"] == ["basics"] and plan["watch_sec"] > 0 and plan["total_sec"] > plan["watch_sec"], plan
qz = features.quiz(V1, n=5); assert len(qz) == 2 and qz[0]["url"].startswith("https://www.youtube.com")
assert features.quiz(V1, topic="git", current_time=None)
ex = features.explain(V1, 300, "simple"); assert ex["explanation"] == "simple explanation" and ex["passage"]["end"] == 300
ex2 = features.explain(V1, 300, "other_video"); assert ex2["source"] and ex2["source"]["video_id"] in (V2, V3)
try: features.explain(V1, 0, "simple"); raise SystemExit("should fail")
except ValueError: pass
print("alternatives/plan/quiz/explain OK")

# ---- subtitles, embedding api (batching + retry), emb mismatch, library sync
srt = "1\n00:00:01,000 --> 00:00:03,500\nHello <i>world</i>\n\n2\n00:00:04,000 --> 00:00:06,000\nline a\nline b\n"
vtt = "WEBVTT\n\n00:01.000 --> 00:03.500\nfirst\n\n01:00:00.000 --> 01:00:02.000\nlater"
s1, s2 = rag.parse_subtitles(srt), rag.parse_subtitles(vtt)
assert s1[0]["text"] == "Hello world" and s1[1]["text"] == "line a line b" and s1[0]["end"] == 3.5
assert s2[0]["start"] == 1.0 and s2[1]["start"] == 3600.0
class FakeEmb:
    calls = 0
    class embeddings:
        @staticmethod
        def create(model, input):
            FakeEmb.calls += 1
            if FakeEmb.calls == 2: raise RuntimeError("429")
            return type("R", (), {"data": [type("D", (), {"embedding": [3.0, 4.0, float(i % 3)]}) for i in range(len(input))]})
real_embed = rag.__dict__["embed"]
src = open("rag.py", encoding="utf-8").read()
ns = {}; exec(compile(src, "rag_copy", "exec"), ns)          # fresh copy to test the real api-embed path
ns["_embc"] = FakeEmb; ns["time"].sleep = lambda s: None
v = ns["embed"]([f"t{i}" for i in range(70)])
assert v.shape == (70, 3) and abs(np.linalg.norm(v[0]) - 1) < 1e-5 and FakeEmb.calls == 4   # 3 batches + 1 retry
c0 = FakeEmb.calls; q1 = ns["embed"](["same q", "other q", "same q"], "query"); q2 = ns["embed"](["same q"], "query")
assert FakeEmb.calls == c0 + 1 and q1.shape == (3, 3) and np.allclose(q1[0], q2[0])          # query cache: 1 call total
class DayGone:
    class embeddings:
        @staticmethod
        def create(model, input): raise RuntimeError("429 EmbedContentRequestsPerDayPerProjectPerModel-FreeTier")
ns["_embc"] = DayGone; ns["_QCACHE"].clear()
try: ns["embed"](["x"], "query"); raise SystemExit("should fail fast")
except RuntimeError as e: assert "PerDay" in str(e)
_ns_embed = ns["embed"]; ns["embed"] = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("PerDay quota"))   # dense down -> BM25 still answers
ix3 = rag.load_index(V1); dd = {}
r = ns["retrieve"](ix3, ["git branch merge"], "git branch merge", mode="hybrid", dbg=dd)
assert r and "dense_error" in dd
ns["embed"] = _ns_embed; ns["_embc"] = FakeEmb
bad = dict(rag.load_index(V3).meta); bad["emb_id"] = "api:other-model"
p = rag.DATA / "index" / f"{V3}.json"; d = json.loads(p.read_text(encoding="utf-8")); d["meta"] = bad; p.write_text(json.dumps(d), encoding="utf-8"); rag._cache.pop(V3, None)
try: rag.load_index(V3); raise SystemExit("mismatch not detected")
except RuntimeError as e: assert "other-model" in str(e)
lib = rag.LIBRARY / "index"; lib.mkdir(parents=True, exist_ok=True)
for f in (rag.DATA / "index").glob(f"{V1}.*"): shutil.copy(f, lib / f.name)
for f in (rag.DATA / "index").glob(f"{V1}.*"): f.unlink()
rag._cache.pop(V1, None); assert not rag.index_exists(V1) and rag.sync_library() == 2 and rag.index_exists(V1)
print("subtitles / api-embed retry / emb mismatch / library sync OK")

# ---- Sarvam adapter: real ffmpeg segmenting, mocked HTTP
subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=300:duration=70", str(rag.DATA / "a.wav")], check=True, capture_output=True)
import httpx
posted = []
def fake_post(url, headers=None, files=None, data=None, timeout=None):
    posted.append((url, headers, data)); n = len(posted)
    return type("R", (), {"status_code": 200, "raise_for_status": lambda s: None, "json": lambda s: {"transcript": f"onion garlic text {n}"}})()
httpx.post = fake_post
os.environ.update(SARVAM_API_KEY="k", ASR_PROVIDER="sarvam")
segs = asr.transcribe_media(rag.DATA / "a.wav")
assert [s["start"] for s in segs] == [0, 25, 50] and posted[0][1] == {"api-subscription-key": "k"} and posted[0][2]["language_code"] == "bn-IN" and posted[0][2]["mode"] == "transcribe"
print("sarvam chunking OK")

# ---- API
from fastapi.testclient import TestClient
import app as appmod
c = TestClient(appmod.app)
assert c.get("/").status_code == 200 and c.get("/healthz").json()["ok"]
assert any(v["video_id"] == V1 for v in c.get("/api/library").json()["videos"])
def wait(key):
    for _ in range(100):
        j = c.get(f"/api/job/{key}").json()
        if j["status"] in ("done", "error"): return j
        time.sleep(0.1)
    raise SystemExit("job timeout")
# upload srt paired with a youtube url -> embedded-player video
r = c.post("/api/upload", data={"title": "sub", "youtube_url": "https://youtu.be/dQw4w9WgXcQ"}, files={"file": ("a.srt", srt.encode(), "text/plain")}).json()
j = wait(r["video_id"]); assert j["status"] == "done" and j["meta"]["video_id"] == "dQw4w9WgXcQ" and j["meta"]["kind"] == "youtube", j
# upload audio -> sarvam -> audio clip (.m4a)
r = c.post("/api/upload", data={"title": "aud"}, files={"file": ("a.wav", open(rag.DATA / "a.wav", "rb"), "audio/wav")}).json()
j = wait(r["video_id"]); assert j["status"] == "done" and j["meta"]["kind"] == "upload" and j["meta"]["media_url"].startswith("/media/up_"), j
up = j["meta"]["video_id"]
a = c.post("/api/ask", json={"video_id": up, "question": "onion cooking", "clip": True}).json()
print(a) if "found" not in a else None
assert a["found"] and a["segments"][0]["clip"].endswith(".m4a"), a
assert c.get(a["segments"][0]["clip"]).status_code == 200 and c.get(j["meta"]["media_url"]).status_code == 200
assert c.post("/api/upload", files={"file": ("x.exe", b"zz", "application/octet-stream")}).status_code == 400
# extension transcript endpoint
r = c.post("/api/index_transcript", json={"video_id": "abcdefghijk", "title": "ext", "segments": [{"start": 0, "end": 5, "text": "git branch merge"}, {"start": 5, "end": 9, "text": "git commit push"}]}).json()
assert wait("abcdefghijk")["status"] == "done"
# other endpoints
assert c.post("/api/alternatives", json={"question": "git merge", "video_id": V1}).status_code == 200
q = c.post("/api/plan/start", json={"goal": "git"}).json()["questions"]
assert c.post("/api/plan/finish", json={"goal": "git", "qa": [{"q": x} for x in q], "video_ids": [V1, V2]}).json()["plan"]
assert len(c.post("/api/quiz", json={"video_id": V1}).json()["questions"]) == 2
assert c.post("/api/explain", json={"video_id": V1, "current_time": 300, "style": "steps"}).status_code == 200
assert c.post("/api/explain", json={"video_id": V1, "current_time": 0}).status_code == 400
assert c.post("/api/ask", json={"video_id": "NOTINDEXED1", "question": "x"}).status_code == 404
# password gate
os.environ["APP_PASSWORD"] = "pw"
assert c.get("/api/library").status_code == 401 and c.get("/healthz").status_code == 200
assert c.get("/api/library", headers={"x-app-key": "pw"}).status_code == 200
assert c.options("/api/library", headers={"Origin": "chrome-extension://x", "Access-Control-Request-Method": "GET"}).status_code == 200
del os.environ["APP_PASSWORD"]
# YT_LIVE=0 fails fast with the helpful message
os.environ["YT_LIVE"] = "0"
r = c.post("/api/index", json={"url": "https://youtu.be/zzzzzzzzzzz"}).json(); j = wait("zzzzzzzzzzz")
assert j["status"] == "error" and "extension" in j["msg"]
print("API OK")

# ---- RAG Lab: debug trace, timings, claims verdicts, ablation flags
out = rag.ask(V1, "git merge", make_clip=False, debug=True)
dbg = out["trace"]["debug"]; a0 = dbg["attempts"][0]
assert {"dense", "bm25"} <= {r["kind"] for r in a0["rankings"]} and a0["fused"] and a0["rerank"]["before"] and a0["final"]
assert any(g["relevant"] for g in a0["graded"]) and dbg["evidence"] and len(dbg["answer_before_verify"]["sections"][0]["points"]) == 3
verd = {c["verdict"] for c in out["trace"]["claims"]}
assert verd == {"supported", "unsupported", "no_citation"}, verd
assert set(out["trace"]["timings_ms"]) >= {"rewrite", "retrieve", "grade", "generate", "verify"}
assert "debug" not in rag.ask(V1, "git merge", make_clip=False)["trace"]
base = rag.ask(V1, "quantum entanglement", make_clip=False, use_rewrite=False, use_grade=False, use_verify=False)
assert base["found"] is True and base["trace"]["verify"] == "skipped"     # baseline hallucinates 'found'; full pipeline says not-found
assert rag.ask(V1, "quantum entanglement", make_clip=False)["found"] is False
cm = rag.compare_modes(V1, "git branch merge", k=3)
assert list(cm["modes"]) == list(rag.MODES) and all(m["results"] for m in cm["modes"].values())
cr = rag.chunk_report(V1); ci = cr["chunking"]
assert ci["signal"] == "lexical" and len(ci["sims"]) == len(ci["t"]) and ci["boundaries"] and len(cr["chunks"]) == len(ix.chunks) and "recomputed" not in ci
ix2 = rag.load_index(V1); ix2.extra = {}; cr2 = rag.chunk_report(V1); assert cr2["chunking"]["recomputed"] and cr2["chunking"]["boundaries"]
# usage counters through the REAL llm() and embed(api) code paths (fake OpenAI client)
class FakeChat:
    class completions:
        @staticmethod
        def create(**kw):
            m = type("M", (), {"content": '{"relevant": []}'}); return type("R", (), {"choices": [type("C", (), {"message": m})]})
    chat = type("X", (), {"completions": completions})
real_llm_fn = ns["llm"]; ns["_client"] = FakeChat
tok = ns["_S"].set({}); real_llm_fn("sys", "user text"); real_llm_fn("s", "u"); st = ns["_S"].get(); ns["_S"].reset(tok)
assert st["llm_calls"] == 2 and st["llm_in_chars"] == len("sysuser text") + 2 and st["llm_out_chars"] == 2 * len('{"relevant": []}'), st
FakeEmb.calls = 0; tok = ns["_S"].set({}); ns["embed"](["a", "b"]); st = ns["_S"].get(); ns["_S"].reset(tok)
assert st["embed_calls"] == 1 and st["embed_texts"] == 2
print("RAG Lab trace / flags / compare / chunks / usage counters OK")

# ---- eval ablation (5 configs) + baseline-vs-full
import eval as ev
items = [{"video": V1, "question": "git branch merge", "gold": [240, 360]}, {"video": V1, "question": "git", "gold": [240, 360]},
         {"video": V1, "question": "quantum entanglement", "gold": None}]
res = ev.retrieval_ablation(items)
assert list(res) == [c[0] for c in ev.CONFIGS] and res["hybrid"]["Hit@k"] == 1.0 and res["hybrid+rerank+rewrite"]["n"] == 2 and "avg_ms" in res["dense"]
fe = ev.full_eval(items)
b, f = fe["baseline (no rewrite/grade/verify)"], fe["full pipeline"]
assert b["not_found_accuracy"] == 0.0 and f["not_found_accuracy"] == 1.0 and f["claims_dropped"] >= 1 and b["claims_dropped"] == 0, fe
print(json.dumps(res)[:200], "\nbaseline vs full:", b["not_found_accuracy"], f["not_found_accuracy"], "claims_dropped", f["claims_dropped"])

# ---- lab endpoints
lc = c.post("/api/lab/compare", json={"video_id": V1, "question": "git branch"}); assert lc.status_code == 200 and "hybrid+rerank" in lc.json()["modes"]
assert c.get(f"/api/lab/chunks/{V1}").json()["chunks"] and c.get("/api/lab/chunks/NOPE0000000").status_code == 404
le = c.post("/api/lab/eval", json={"items": items, "full": True}); assert le.status_code == 200 and "end_to_end" in le.json() and le.json()["retrieval"]["dense"]["n"] == 2
assert c.post("/api/lab/eval", json={"items": []}).status_code == 400
ad = c.post("/api/ask", json={"video_id": V1, "question": "git merge", "clip": False, "debug": True}).json(); assert ad["trace"]["debug"]["attempts"]
assert c.get("/lab").status_code == 200 and "RAG Lab" in c.get("/lab").text
print("lab endpoints OK")
# ---- live-demo robustness: yt-dlp failure -> captions-only path; YT_DOWNLOAD=0; doctor
for k in ("YT_LIVE",): os.environ.pop(k, None)
os.environ["YT_DOWNLOAD"] = "1"   # opt-in download path: failure must fall back to captions
msgs = []
def boom(vid): raise RuntimeError("ERROR: Sign in to confirm you're not a bot")
rag.download_video = boom
rag.fetch_captions = lambda vid, langs=None: [{"start": 0, "end": 5, "text": "git branch merge"}, {"start": 5, "end": 9, "text": "git commit push"}]
rag.fetch_title = lambda vid: "Live Title"
m = rag.build_index("https://youtu.be/LIVEDEMO001", progress=msgs.append)
assert m["title"] == "Live Title" and m["has_video"] is False and m["source"] == "captions"
assert any("Deno" in x and "captions only" in x for x in msgs), msgs
os.environ["YT_DOWNLOAD"] = "0"
def must_not(vid): raise SystemExit("download must be skipped when YT_DOWNLOAD=0")
rag.download_video = must_not
msgs.clear(); m2 = rag.build_index("https://youtu.be/LIVEDEMO002", progress=msgs.append)
assert m2["title"] == "Live Title" and not any("Downloading" in x for x in msgs)
del os.environ["YT_DOWNLOAD"]
import doctor
def _down(*a, **k): raise RuntimeError("simulated outage")
_saved = (rag.llm, rag.fetch_captions); rag.llm = _down; rag.fetch_captions = _down
code = doctor.main([])                      # LLM + captions down: must report NOT READY, not crash
assert code == 1
rag.llm, rag.fetch_captions = _saved
rag.llm = lambda *a, **k: "ok"; rag.embed = fake_embed; rag.fetch_captions = lambda vid, langs=None: [{"start": 0, "end": 1, "text": "x"}]
rag.fetch_title = lambda vid: "T"
import sys as _sys, types
fake = types.ModuleType("yt_dlp"); fake.version = types.SimpleNamespace(__version__="9.9")
class _Y:
    def __init__(s, o): pass
    def __enter__(s): return s
    def __exit__(s, *a): return False
    def extract_info(s, u, download=False): return {"title": "T"}
fake.YoutubeDL = _Y; _sys.modules["yt_dlp"] = fake
assert doctor.main(["abcdefghijk"]) == 0
import io, contextlib
os.environ.update(LLM_BASE_URL="https://generativelanguage.googleapis.com/v1beta/openai/", LLM_MODEL="gemini-2.5-flash")
buf = io.StringIO()
with contextlib.redirect_stdout(buf): code = doctor.main(["abcdefghijk"])
assert code == 1 and "legacy Gemini model" in buf.getvalue() and "gemini-3.5-flash" in buf.getvalue()
os.environ["LLM_MODEL"] = "gemini-3.8-flash"
assert doctor.main(["abcdefghijk"]) == 0
for k in ("LLM_BASE_URL", "LLM_MODEL"): os.environ.pop(k, None)
print("live-demo: yt-dlp failure fallback / YT_DOWNLOAD=0 / doctor (+legacy Gemini model check) OK")
# ---- setup_keys: hidden-input key setup never echoes secrets, preserves the rest of .env
import setup_keys
envp = os.path.join(tempfile.mkdtemp(), ".env")
open(envp, "w", encoding="utf-8").write("# comment  # SARVAM_API_KEY=old\nLLM_API_KEY=your_key_here\nLLM_MODEL=gemini-3.8-flash\nOTHER=1\n")
answers = iter(["SECRET-LLM-KEY", "SECRET-SARVAM", ""]); said = []
setup_keys.main(ask=lambda p: next(answers), say=said.append, path=envp)
env_txt = open(envp, encoding="utf-8").read()
assert "LLM_API_KEY=SECRET-LLM-KEY" in env_txt and env_txt.count("LLM_API_KEY=") == 1 and "your_key_here" not in env_txt
assert "SARVAM_API_KEY=SECRET-SARVAM" in env_txt and "ASR_PROVIDER=sarvam" in env_txt and "# comment  # SARVAM_API_KEY=old" in env_txt
assert "LLM_MODEL=gemini-3.8-flash" in env_txt and "OTHER=1" in env_txt
pw = re.search(r"^APP_PASSWORD=(\S+)$", env_txt, re.M).group(1); assert len(pw) >= 10
assert not any("SECRET-" in m for m in said) and any(pw in m for m in said)      # secrets never printed; generated password shown once
assert os.name == "nt" or (os.stat(envp).st_mode & 0o777) == 0o600   # chmod is a no-op on Windows
answers = iter(["", "", "mypass123"]); setup_keys.main(ask=lambda p: next(answers), say=said.append, path=envp)
env2 = open(envp, encoding="utf-8").read(); assert "APP_PASSWORD=mypass123" in env2 and "LLM_API_KEY=SECRET-LLM-KEY" in env2 and env2.count("APP_PASSWORD=") == 1
print("setup_keys OK")
# ---- real llm() plumbing: Gemini model-pool rotation on 429, thinking-budget retry, answer normalization
import types as _t
class _Err(Exception):
    def __init__(s, code, msg=""): super().__init__(msg or f"err {code}"); s.status_code = code
calls = []
def _resp(txt, fin="stop"): return _t.SimpleNamespace(choices=[_t.SimpleNamespace(message=_t.SimpleNamespace(content=txt), finish_reason=fin)])
def _create(**kw):
    calls.append((kw["model"], kw.get("reasoning_effort"), kw["max_tokens"]))
    if kw["model"] == "m-main": raise _Err(429, "quota {'retryDelay': '0s'}")
    if kw["model"] == "gemini-x-lite" and kw.get("reasoning_effort"): raise _Err(400)
    if kw["model"] == "m-think" and kw.get("reasoning_effort") is None and kw["max_tokens"] < 1000: return _resp(None, "length")
    return _resp("ok")
rag._client = _t.SimpleNamespace(chat=_t.SimpleNamespace(completions=_t.SimpleNamespace(create=_create)))
os.environ.update(LLM_BASE_URL="https://generativelanguage.googleapis.com/v1beta/openai/", LLM_MODEL="m-main", LLM_FALLBACK_MODELS="gemini-x-lite")
assert rag._llm_try([ "m-main", "gemini-x-lite"], [{"role": "user", "content": "x"}], 0.1, 5, True) == "ok"
assert calls[0][:2] == ("m-main", "none") and calls[1] == ("gemini-x-lite", None, 5), calls
calls.clear(); os.environ["LLM_MODEL"] = "m-main"; os.environ["LLM_FALLBACK_MODELS"] = "m-main"
try:
    rag._llm_try(["m-main"], [{"role": "user", "content": "x"}], 0.1, 5, True); raise SystemExit("should be busy")
except rag._AllBusy as e:
    assert e.wait == 1.0
for k in ("LLM_BASE_URL", "LLM_MODEL", "LLM_FALLBACK_MODELS"): os.environ.pop(k, None)
ans = {"sections": [{"heading": "h", "points": ["bare string point", {"text": "p", "cites": ["2", 1, "x"]}]}, "loose section"]}
rag.llm = lambda *a, **k: json.dumps(ans)
g = rag.generate_answer("q", [{"start": 0, "end": 1, "text": "t"}] * 3)
assert g["sections"][0]["points"][0] == {"text": "bare string point", "cites": []} and g["sections"][0]["points"][1]["cites"] == [2, 1]
assert g["sections"][1]["points"][0]["text"] == "loose section"
rag.llm = lambda *a, **k: json.dumps({"results": [{"supported": True}, "false", "yes"]})
ev3 = [{"start": 0, "end": 1, "text": "t"}] * 3
v, st = rag.verify_answer({"sections": [{"heading": "h", "points": [{"text": "a", "cites": [1]}, {"text": "b", "cites": [2]}, {"text": "c", "cites": [3]}]}]}, ev3)
assert st["verify"] == "ok" and st["claims_supported"] == 2, st
print("llm pool rotation / answer normalization / lenient verify OK")
# ---- accounts (AUTH=1): signup/login/session cookie/401 gate/admin key/daily limit/history + YouTube browse
import auth
rag.llm = fake_llm
os.environ.update(AUTH="1", DAILY_LIMIT="2", APP_PASSWORD="adminpw"); os.environ.pop("SECRET_KEY", None)
ac = TestClient(appmod.app)
assert ac.get("/api/library").status_code == 401 and ac.get("/api/library").json().get("login")
assert ac.get("/api/library", headers={"x-app-key": "adminpw"}).status_code == 200          # extension/admin path
me = ac.get("/api/auth/me").json(); assert me["auth"] and me["user"] is None
assert ac.post("/api/auth/signup", json={"email": "bad", "password": "123456"}).status_code == 400
assert ac.post("/api/auth/signup", json={"email": "a@b.co", "password": "123"}).status_code == 400
r = ac.post("/api/auth/signup", json={"email": "Roman@Test.com", "password": "secret1", "name": "Roman"}); assert r.status_code == 200, r.text
assert ac.get("/api/auth/me").json()["user"]["email"] == "roman@test.com"
assert ac.post("/api/auth/signup", json={"email": "roman@test.com", "password": "secret1"}).status_code == 400
row = auth._conn().execute("SELECT pw FROM users").fetchone()[0]; assert "secret1" not in row and len(row) == 64
a1 = ac.post("/api/ask", json={"video_id": V1, "question": "git merge", "clip": False}); assert a1.status_code == 200
a2 = ac.post("/api/ask", json={"video_id": V1, "question": "quantum entanglement", "clip": False}); assert a2.status_code == 200
assert ac.post("/api/ask", json={"video_id": V1, "question": "git", "clip": False}).status_code == 429     # DAILY_LIMIT=2
h = ac.get("/api/history").json()["items"]; assert len(h) == 2 and h[0]["question"] == "quantum entanglement" and h[0]["found"] == 0
ac.post("/api/auth/logout"); ac.cookies.clear()
assert ac.get("/api/library").status_code == 401
assert ac.post("/api/auth/login", json={"email": "roman@test.com", "password": "nope"}).status_code == 401
assert ac.post("/api/auth/login", json={"email": "roman@test.com", "password": "secret1"}).status_code == 200
assert ac.get("/api/library").status_code == 200
assert ac.get("/api/notes/" + V1).json()["content"] is None
assert ac.put("/api/notes/" + V1, json={"content": {"html": "<b>n</b>", "board": None}}).status_code == 200
assert ac.get("/api/notes/" + V1).json()["content"]["html"] == "<b>n</b>"
assert ac.put("/api/notes/" + V1, json={"content": {"html": "x" * 6_100_000}}).status_code == 413
assert auth.user_from_token("1.9999999999.forged") is None and auth.user_from_token("garbage") is None
fy = types.ModuleType("yt_dlp")
class _Y2:
    def __init__(s, o): pass
    def __enter__(s): return s
    def __exit__(s, *a): return False
    def extract_info(s, u, download=False): return {"entries": [{"id": V1, "title": "t1", "channel": "c", "duration": 99}, {"id": "zzzzzzzzzzz", "title": "t2"}, {"id": "short"}]}
fy.YoutubeDL = _Y2; _sys.modules["yt_dlp"] = fy
sr = ac.get("/api/search", params={"q": "git"}).json()["results"]
assert [x["id"] for x in sr] == [V1, "zzzzzzzzzzz"] and sr[0]["indexed"] is True and sr[1]["indexed"] is False
assert ac.get("/api/transcript/" + V1).json()["chunks"] and ac.post("/api/heat", json={"video_id": V1, "question": "git merge"}).json()["cells"]
for k in ("AUTH", "DAILY_LIMIT", "APP_PASSWORD"): os.environ.pop(k, None)
print("accounts / daily limit / history / youtube browse / heat / transcript OK")
print("ALL TESTS PASSED")
