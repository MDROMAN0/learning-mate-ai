import os
import tempfile
import threading
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import auth
import eval as rag_eval
import features
import rag

app = FastAPI(title="YouTube Topic RAG")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/clips", StaticFiles(directory=str(rag.DATA / "clips")), name="clips")
app.mount("/media", StaticFiles(directory=str(rag.DATA / "videos")), name="media")
app.mount("/static", StaticFiles(directory="static"), name="static")
JOBS = {}
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "200"))


# what a guest (demo mode, no account) may call: read the sample library and ask about it; no indexing/uploads/notes
GUEST_OK = ("/api/library", "/api/job/", "/api/transcript/", "/api/chapters/", "/api/ask", "/api/heat", "/api/quiz",
            "/api/explain", "/api/lab/", "/api/search", "/api/alternatives", "/api/plan/")


def _ip(request: Request):
    return (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "")).split(",")[0].strip()


@app.middleware("http")
async def gate(request: Request, call_next):
    """AUTH=1 -> every /api call needs a logged-in user (or the admin APP_PASSWORD, e.g. the Chrome extension).
    AUTH off -> optional shared APP_PASSWORD only (old behaviour)."""
    path = request.url.path
    request.state.user = None
    request.state.guest = None
    if path.startswith("/api") and request.method != "OPTIONS":
        pw = os.getenv("APP_PASSWORD")
        admin = bool(pw) and request.headers.get("x-app-key") == pw
        if auth.enabled():
            tok = request.cookies.get(auth.COOKIE) or request.headers.get("authorization", "").removeprefix("Bearer ").strip()
            request.state.user = auth.user_from_token(tok) if tok else None
            if not path.startswith("/api/auth/") and not request.state.user and not admin:
                gid = auth.guest_from_token(request.cookies.get(auth.GUEST_COOKIE))
                if gid and path.startswith(GUEST_OK):
                    request.state.guest = gid
                else:
                    return JSONResponse({"detail": "log in to use this (demo mode only covers the sample videos)"
                                         if gid else "login required", "login": True, "guest": bool(gid)},
                                        status_code=401)
        elif pw and not admin and path != "/api/auth/me":
            return JSONResponse({"detail": "wrong or missing app key"}, status_code=401)
    return await call_next(request)


def _charge(request: Request):
    """Per-user daily quota for LLM-heavy calls (protects the free LLM key). Also applies the UI language."""
    rag.set_lang(request.headers.get("x-lang", ""))
    g = getattr(request.state, "guest", None)
    if g and not auth.guest_charge(g, _ip(request)):
        raise HTTPException(429, f"demo limit reached ({auth.guest_limit()} questions) - create a free account to continue")
    u = getattr(request.state, "user", None)
    if u and not auth.charge(u["id"]):
        raise HTTPException(429, f"daily limit reached ({auth.daily_limit()}) - try again tomorrow")


class IndexReq(BaseModel):
    url: str
    force_asr: bool = False


class Seg(BaseModel):
    start: float
    end: float
    text: str


class TranscriptReq(BaseModel):  # used by the Chrome extension (captions fetched on the user's own IP)
    video_id: str
    title: str = ""
    segments: List[Seg]


class AskReq(BaseModel):
    video_id: str
    question: str
    current_time: Optional[float] = None  # seconds; set => spoiler-free (progress-aware)
    clip: bool = True
    mode: str = "hybrid+rerank"  # dense | bm25 | hybrid | hybrid+rerank
    level: str = "simple"  # simple | exam | expert
    use_rewrite: bool = True
    use_grade: bool = True
    use_verify: bool = True
    debug: bool = False  # RAG Lab: return every pipeline stage in trace["debug"]


class CompareReq(BaseModel):
    video_id: str
    question: str
    k: int = 5
    current_time: Optional[float] = None
    use_rewrite: bool = False


class EvalReq(BaseModel):
    items: List[dict]
    full: bool = False
    k: int = 5


class AltReq(BaseModel):
    question: str
    video_id: Optional[str] = None
    mode: str = "library"  # library | discover
    n: int = 3
    level: str = "simple"


class PlanStartReq(BaseModel):
    goal: str


class QA(BaseModel):
    q: str
    a: str = ""


class PlanFinishReq(BaseModel):
    goal: str
    qa: List[QA]
    video_ids: List[str]


class QuizReq(BaseModel):
    video_id: str
    n: int = 5
    topic: Optional[str] = None
    current_time: Optional[float] = None


class ExplainReq(BaseModel):
    video_id: str
    current_time: float
    style: str = "simple"  # simple | analogy | steps | other_video


def _job(key, fn, *args):
    def run():
        try:
            meta = fn(*args, lambda m: JOBS[key].update(msg=m))
            JOBS[key] = {"status": "done", "msg": "ready", "meta": meta}
        except Exception as e:
            JOBS[key] = {"status": "error", "msg": str(e)}
    JOBS[key] = {"status": "running", "msg": "starting..."}
    threading.Thread(target=run, daemon=True).start()


def _safe(fn, *a, **k):
    try:
        return fn(*a, **k)
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(404 if isinstance(e, FileNotFoundError) else 400, str(e))
    except Exception as e:
        raise HTTPException(500, f"{type(e).__name__}: {e}")


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/api/library")
def library():
    return {"videos": rag.list_library()}


@app.post("/api/index")
def index_video(req: IndexReq, request: Request):
    try:
        vid = rag.extract_video_id(req.url)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if rag.index_exists(vid):
        return {"video_id": vid, "status": "done", "meta": _safe(rag.load_index, vid).meta}
    if JOBS.get(vid, {}).get("status") != "running":
        _charge(request)
        _job(vid, lambda u, f, p: rag.build_index(u, f, p), req.url, req.force_asr)
    return {"video_id": vid, **JOBS[vid]}


@app.post("/api/index_transcript")
def index_transcript(req: TranscriptReq):
    vid = rag.extract_video_id(req.video_id)
    if rag.index_exists(vid):
        return {"video_id": vid, "status": "done", "meta": _safe(rag.load_index, vid).meta}
    segs = [s.model_dump() for s in req.segments]
    if JOBS.get(vid, {}).get("status") != "running":
        _job(vid, lambda t, sg, p: rag.build_index_from_segments(vid, t or vid, sg, "extension", None, "youtube", p),
             req.title, segs)
    return {"video_id": vid, **JOBS[vid]}


@app.post("/api/upload")
def upload(file: UploadFile = File(...), title: str = Form(""), youtube_url: str = Form("")):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in rag.SUB_EXT | rag.AUDIO_EXT | {".mp4", ".mkv", ".webm", ".mov", ".avi"}:
        raise HTTPException(400, "unsupported file type")
    fd, tmp = tempfile.mkstemp(suffix=ext, dir=str(rag.DATA))
    size = 0
    with os.fdopen(fd, "wb") as out:
        while chunk := file.file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_UPLOAD_MB * 1024 * 1024:
                out.close()
                os.remove(tmp)
                raise HTTPException(413, f"file > {MAX_UPLOAD_MB} MB")
            out.write(chunk)
    if youtube_url and ext in rag.SUB_EXT:
        try:
            key = rag.extract_video_id(youtube_url)
        except ValueError as e:
            os.remove(tmp)
            raise HTTPException(400, str(e))
    else:
        key = "up_" + Path(tmp).stem[-8:]
        youtube_url = None
    _job(key, lambda p, t, y, pr: rag.build_index_from_upload(p, t, pr, y), tmp, title or file.filename, youtube_url)
    return {"video_id": key, **JOBS[key]}


@app.get("/api/job/{vid}")
def job(vid: str):
    j = JOBS.get(vid)
    if j and j["status"] == "done":  # upload jobs: meta.video_id is the real id
        return {"video_id": vid, **j}
    if rag.index_exists(vid) and (not j or j["status"] != "running"):
        return {"video_id": vid, "status": "done", "meta": _safe(rag.load_index, vid).meta}
    return {"video_id": vid, **(j or {"status": "unknown", "msg": ""})}


@app.post("/api/ask")
def ask(req: AskReq, request: Request):
    if not req.question.strip():
        raise HTTPException(400, "empty question")
    _charge(request)
    out = _safe(rag.ask, req.video_id, req.question, req.current_time, req.clip, req.mode,
                req.use_rewrite, req.level, req.use_grade, req.use_verify, req.debug)
    u = request.state.user
    if u:
        try:
            auth.add_history(u["id"], out.get("video_id"), out.get("title"), req.question, out)
        except Exception:
            pass
    return out


@app.post("/api/lab/compare")
def lab_compare(req: CompareReq, request: Request):
    _charge(request)
    return _safe(rag.compare_modes, req.video_id, req.question, req.k, req.current_time, req.use_rewrite)


@app.get("/api/lab/chunks/{vid}")
def lab_chunks(vid: str):
    return _safe(rag.chunk_report, vid)


@app.post("/api/lab/eval")
def lab_eval(req: EvalReq, request: Request):
    _charge(request)
    if req.full:
        rag.set_lang(request.headers.get("x-lang", ""))
    if not req.items or len(req.items) > 40 or (req.full and len(req.items) > 15):
        raise HTTPException(400, "items: 1..40 (1..15 with full=true)")
    if request.state.guest and (req.full or len(req.items) > 12):
        raise HTTPException(400, "demo mode: retrieval eval only, up to 12 questions - log in for the full run")
    def run():
        out = {"retrieval": rag_eval.retrieval_ablation(req.items, req.k)}
        if req.full:
            out["end_to_end"] = rag_eval.full_eval(req.items)
        return out
    return _safe(run)


@app.post("/api/alternatives")
def alternatives(req: AltReq, request: Request):
    _charge(request)
    return _safe(features.alternatives, req.question, req.video_id, req.mode, req.n, req.level)


@app.post("/api/plan/start")
def plan_start(req: PlanStartReq, request: Request):
    _charge(request)
    return {"questions": _safe(features.plan_start, req.goal)}


@app.post("/api/plan/finish")
def plan_finish(req: PlanFinishReq, request: Request):
    _charge(request)
    return _safe(features.plan_finish, req.goal, [x.model_dump() for x in req.qa], req.video_ids)


@app.post("/api/quiz")
def quiz(req: QuizReq, request: Request):
    _charge(request)
    return {"questions": _safe(features.quiz, req.video_id, req.n, req.topic, req.current_time)}


@app.post("/api/explain")
def explain(req: ExplainReq, request: Request):
    _charge(request)
    return _safe(features.explain, req.video_id, req.current_time, req.style)


class AskAllReq(BaseModel):
    question: str
    video_ids: Optional[List[str]] = None
    level: str = "simple"


@app.post("/api/ask_all")
def ask_all(req: AskAllReq, request: Request):
    """Ask one question across the whole library (or a chosen set of videos)."""
    if not req.question.strip():
        raise HTTPException(400, "empty question")
    _charge(request)
    out = _safe(rag.ask_all, req.question, req.video_ids, req.level)
    u = request.state.user
    if u:
        try:
            auth.add_history(u["id"], "course", "All videos", req.question, out)
        except Exception:
            pass
    return out


@app.get("/api/chapters/{vid}")
def chapters(vid: str, request: Request):
    rag.set_lang(request.headers.get("x-lang", ""))
    got = _safe(rag.chapters, vid, True)
    if got:
        return got
    _charge(request)
    return _safe(rag.chapters, vid)


@app.get("/api/lab/evalset")
def lab_evalset():
    """The built-in evaluation questions (eval_set.json) for videos that are in the library."""
    try:
        import json as _json
        items = _json.loads(Path("eval_set.json").read_text(encoding="utf-8"))
    except Exception:
        items = []
    have = {m["video_id"] for m in rag.list_library()}
    items = [it for it in items if rag.extract_video_id(it.get("video", "")) in have]
    return {"items": items, "n_pos": sum(1 for it in items if it.get("gold")),
            "n_neg": sum(1 for it in items if not it.get("gold"))}


class AuthReq(BaseModel):
    email: str
    password: str
    name: str = ""


def _session(resp: Response, user):
    resp.set_cookie(auth.COOKIE, auth.make_token(user["id"]), max_age=auth.SESSION_DAYS * 86400,
                    httponly=True, samesite="lax", secure=os.getenv("COOKIE_SECURE", "0") == "1")
    return {"user": user}


@app.post("/api/auth/signup")
def signup(req: AuthReq, resp: Response):
    if not auth.enabled():
        raise HTTPException(400, "accounts are off (AUTH=0)")
    try:
        return _session(resp, auth.signup(req.email, req.password, req.name))
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/auth/login")
def login(req: AuthReq, resp: Response):
    if not auth.enabled():
        raise HTTPException(400, "accounts are off (AUTH=0)")
    try:
        return _session(resp, auth.login(req.email, req.password))
    except PermissionError as e:
        raise HTTPException(401, str(e))


@app.post("/api/auth/logout")
def logout(resp: Response):
    resp.delete_cookie(auth.COOKIE)
    resp.delete_cookie(auth.GUEST_COOKIE)
    return {"ok": True}


@app.post("/api/auth/guest")
def guest(request: Request, resp: Response):
    """Demo mode: try the sample library without an account (small daily question limit)."""
    if not auth.enabled():
        return {"guest": False}
    tok = request.cookies.get(auth.GUEST_COOKIE)
    if not auth.guest_from_token(tok):
        tok = auth.make_guest_token()
    resp.set_cookie(auth.GUEST_COOKIE, tok, max_age=7 * 86400, httponly=True, samesite="lax",
                    secure=os.getenv("COOKIE_SECURE", "0") == "1")
    return {"guest": True, "limit": auth.guest_limit()}


@app.get("/api/auth/me")
def me(request: Request):
    u = request.state.user
    gid = None if u else auth.guest_from_token(request.cookies.get(auth.GUEST_COOKIE))
    if gid:
        return {"auth": auth.enabled(), "user": None, "guest": True, "limit": auth.guest_limit(),
                "used": auth.guest_used(gid), "app_password": False}
    return {"auth": auth.enabled(), "user": u, "guest": False, "limit": auth.daily_limit(),
            "used": auth.used_today(u["id"]) if u else 0,
            "app_password": bool(os.getenv("APP_PASSWORD")) and not auth.enabled()}


@app.get("/api/history")
def history(request: Request):
    u = request.state.user
    return {"items": auth.history(u["id"]) if u else []}


class NoteReq(BaseModel):
    content: dict


@app.get("/api/notes")
def list_notes(request: Request):
    u = request.state.user
    if not u:
        return {"items": []}
    titles = {m["video_id"]: m for m in rag.list_library()}
    return {"items": [{**n, "title": titles.get(n["video_id"], {}).get("title", n["video_id"]),
                       "kind": titles.get(n["video_id"], {}).get("kind", "youtube")} for n in auth.list_notes(u["id"])]}


@app.get("/api/notes/{vid}")
def get_note(vid: str, request: Request):
    u = request.state.user
    if not u:
        raise HTTPException(400, "log in to sync notes (AUTH=1)")
    return auth.get_note(u["id"], vid)


@app.put("/api/notes/{vid}")
def put_note(vid: str, req: NoteReq, request: Request):
    u = request.state.user
    if not u:
        raise HTTPException(400, "log in to sync notes (AUTH=1)")
    try:
        return auth.save_note(u["id"], vid, req.content)
    except ValueError as e:
        raise HTTPException(413, str(e))


@app.get("/api/search")
def search(q: str, n: int = 16):
    return {"results": _safe(features.browse_youtube, q, max(1, min(n, 30)))}


class HeatReq(BaseModel):
    video_id: str
    question: str


@app.post("/api/heat")
def heat(req: HeatReq):
    return _safe(rag.topic_heat, req.video_id, req.question)


@app.get("/api/transcript/{vid}")
def transcript(vid: str):
    return _safe(rag.transcript, vid)


NO_CACHE = {"Cache-Control": "no-cache"}


@app.get("/")
def home():
    return FileResponse("static/index.html", headers=NO_CACHE)


@app.get("/lab")
def lab():
    return FileResponse("static/lab.html", headers=NO_CACHE)
