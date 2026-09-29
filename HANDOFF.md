# HANDOFF — Cowork-এর জন্য (কাজ এখান থেকে এগিয়ে নাও)

**Owner:** Roman (NSU CSE, Dhaka). **Project:** YouTube Topic RAG — CSE 299 academic project, পরে 499A/B + product।
**লক্ষ্য:** sir মূলত দেখবেন *RAG কীভাবে কাজ করছে ও কীভাবে implement হয়েছে*। তাই RAG-এর গভীরতা, RAG Lab আর evaluation-ই আসল।

## 0. Roman-এর সাথে কথা বলার নিয়ম (তার সংরক্ষিত পছন্দ)
- Bangla script-এ উত্তর, English technical term রেখে; **ছোট ও সরাসরি**; হ্যাঁ/না আগে; committed recommendation।
- কাজ **একবারে শেষ** করো; শেষে **নিজের কাজ audit** করে বলো (কী test হলো, কী হলো না)।
- PC-তে কাজ থাকলে ধাপ ধরিয়ে না দিয়ে নিজে করো (access দিলে)।
- **API key/password/account:** তুমি বানাবে না, Roman-কে চাইবে; key কখনো repo/chat-এ লিখবে না।

## 0.5 মানব-শুধু ধাপ (Cowork থামবে, Roman করবে) — `docs/YOUR_PART.md`
- Account বানানো, login, **API key/password বসানো**, payment — সব Roman। তুমি এগুলো টাইপ/অনুমান করবে না, chat-এ secret চাইবে না।
- Key লাগলে বলবে: "`python setup_keys.py` চালিয়ে key paste করো" (hidden input, `.env`-এ লেখে)। Render secrets Roman নিজে dashboard-এ।
- বাকি সব (install, test, code ঠিক করা, extension test, GitHub push, deploy কমান্ড) তুমি করবে।
- **Sir-এর মূল শর্ত: RAG + LLM।** এটা কমানো/বাদ দেওয়া যাবে না; Gemini শুধু free বলে default (OpenAI-compatible, বদলানো যায়)।


## ★ আপডেট 30 Sep 2026 (Cowork session) — এখনকার আসল অবস্থা
- **Real run হয়েছে Roman-এর Windows PC-তে** (Python 3.14, ffmpeg+Deno winget দিয়ে): `doctor.py` READY, `test_mock.py` ALL PASSED (Windows-এও)।
- **Model:** free key-তে `gemini-3.8-flash` 429 (quota) → default `gemini-3.5-flash`; 429/503-তে pool rotation (`LLM_FALLBACK_MODELS`) + per-model cooldown + wait-retry। Gemini 3.x thinking token max_tokens খেয়ে খালি reply দিত → `reasoning_effort=none` (flash-lite-এ বাদ)।
- **Real smoke (৪টা Bangla video, ১০ প্রশ্ন):** 10/10 ঠিক (6 found + 4 not-found), সব verify ok, ~12–30 s/প্রশ্ন। Grader/verifier prompt noisy Bangla auto-caption-এর জন্য ঠিক করা হয়েছে।
- **নতুন:** Learning Mate AI UI (dark/light, বাংলা/English toggle `static/i18n.js`), in-app YouTube search (`/api/search`), topic heat-map (`/api/heat`), interactive transcript (`/api/transcript`), history, **accounts** (`auth.py`, AUTH=1, PBKDF2, signed cookie, DAILY_LIMIT, optional Postgres `DATABASE_URL`), RAG Lab redesign, extension side panel redesign।
- **Download বন্ধ (default `YT_DOWNLOAD=0`):** caption সরাসরি YouTube থেকে, segment embedded player-এ। Caption না থাকলে পরিষ্কার error।
- Eval set: `eval_set.json` (26 positive + 8 negative, gold range Claude transcript পড়ে দিয়েছে — Roman ২-৩টা spot-check করুক)। ফল: `docs/EVALUATION.md` §5।
- **বাকি (Roman-এর login লাগে):** GitHub repo বানিয়ে push, Render Blueprint + secrets, (ঐচ্ছিক) Neon DATABASE_URL — `docs/DEPLOY.md`। Extension আসল Chrome-এ Load unpacked করে test হয়নি। Docker build চালানো হয়নি।
- **Notes (নতুন):** Notes tab — rich text + timestamp chip (Alt+N), video screenshot (Alt+S; YouTube-এ প্রথমবার "This tab" share permission, তারপর instant), Whiteboard (pen/highlighter/eraser/undo, note-এ বসানো), PDF export (print → Save as PDF), answer → "Note-এ যোগ করো"। Login থাকলে notes account-এ (`/api/notes/{vid}`), না থাকলে browser-এ।
- **Retrieval ablation আসল ফল** `docs/EVALUATION.md` §5-এ (dense 1.00/0.92, bm25 0, hybrid+rerank 1.00/0.93)। End-to-end eval free embedding quota (1000/দিন) শেষ হওয়ায় বাকি — দুপুর ১টার পর `python eval.py eval_set.json --full`।
- Embedding quota শেষ হলে এখন retrieval BM25-এ নামে (crash না), query embedding cache হয়।
- UI-তে emoji নেই — `static/icons.js` (SVG icon set)।
- Git: local repo-তে ২টা commit আছে; push বাকি (GitHub login লাগবে)।
- Beginner guide: `docs/START_HERE.md`।

## 1. প্রজেক্ট এক নজরে
| ফাইল | কাজ |
|---|---|
| `rag.py` | পুরো RAG core: transcript → chunk → index → rewrite → hybrid retrieve → rerank → grade → answer → verify → clip; RAG Lab-এর `compare_modes`, `chunk_report`; per-request `usage`/`timings` |
| `features.py` | Alternatives (multi-video compare), Watch plan, Quiz, "বুঝিনি" explain |
| `asr.py` | ASR: local faster-whisper | Sarvam (Bangla) |
| `app.py` | FastAPI: `/api/*`, `/lab`, `/`; upload, extension endpoint, `APP_PASSWORD` gate, CORS |
| `eval.py` | Ablation + end-to-end eval (CLI ও `/api/lab/eval`) |
| `prepare.py` | **local PC-তে** index বানিয়ে `library/`-তে export |
| `static/index.html`, `static/lab.html` | Main UI, RAG Lab |
| `extension/` | Chrome MV3 side panel |
| `Dockerfile`, `render.yaml` | Render free deploy |
| `test_mock.py` | offline test (নকল LLM/embedding/ASR + আসল ffmpeg) |
| `run.py`, `start.bat`, `start_share.bat` | এক-ক্লিকে চালু (venv+deps প্রথমবার), `--share` = Cloudflare Quick Tunnel (APP_PASSWORD বাধ্যতামূলক); `.bat` Windows-এ আসল চালানো হয়নি |
| `setup_keys.py` | key/password `.env`-এ hidden input-এ বসায় (chat-এ secret লাগে না) |
| `doctor.py` | demo-র আগের readiness check |
| `docs/` | RAG_ARCHITECTURE, EVALUATION, PRESENTATION_OUTLINE, DEPLOY, **LIVE_DEMO** |

গভীর ব্যাখ্যা: `docs/RAG_ARCHITECTURE.md`। Deploy: `docs/DEPLOY.md`।

## 2. অবস্থা — সৎ audit
**✅ Offline test-এ পাস (`python test_mock.py`):** semantic chunking (lexical), ৪ retrieval mode, ৩ rerank provider, progress-aware trimming, corrective retry, claim verification ও per-claim verdict, clip (mp4 + audio m4a), alternatives (library+discover mock), watch plan, quiz, explain, SRT/VTT parse, API-embedding batching+retry, embedding-mismatch check, library sync, Sarvam 25 s chunking (HTTP mock), upload API, `index_transcript`, password gate + CORS preflight, `YT_LIVE=0` fail-fast, debug trace/timings/usage counters (আসল `llm()`/`embed()` path), ablation flags, `/api/lab/*`, eval (৫ config, baseline vs full)। JS syntax check (index, lab, extension) + extension DOM-fallback parsing unit test।

**⚠️ কখনো আসলে চালানো হয়নি (এগুলোই তোমার আসল কাজ):**
1. আসল LLM (Gemini/OpenAI) JSON output — prompt-গুলো `rag.py`/`features.py`-তে; parse ব্যর্থ হলে fallback আছে, কিন্তু মান যাচাই হয়নি।
2. আসল embedding endpoint (`gemini-embedding-001` via OpenAI-compatible URL) ও free-tier rate limit (batch=32, retry=5 ধরে নেওয়া)।
3. `yt-dlp` download (2026-এ Deno + yt-dlp[default] লাগে; `YT_DOWNLOAD=0` fallback), `youtube-transcript-api` (v1.x ও v0.6 দুই API-র জন্য code আছে), Whisper।
4. **Sarvam** adapter: endpoint/param docs থেকে; `saarika:v2.5` deprecated হচ্ছে বলে default `saaras:v3` + `mode=transcribe`। Model নাম/param dashboard docs-এ মেলাও।
5. Docker build, Render deploy, memory (offline import-এ ~53 MB RSS, torch লোড হয় না)।
6. **Chrome extension** আসল Chrome-এ। Caption json3 খালি আসতে পারে (YouTube-এর PO token); fallback = transcript panel scrape (selector বদলাতে পারে)।
7. Browser UI-র আসল রেন্ডারিং (শুধু JS syntax check হয়েছে)।
8. Chunking threshold (`k=0.5`, 20–90 s) আসল Bangla video-তে tune হয়নি।

## 3. করণীয় (অগ্রাধিকার অনুযায়ী) — প্রতিটার "শেষ" শর্ত সহ
0. **আগে `python doctor.py`** (ffmpeg, Deno, yt-dlp[default], LLM/embedding, captions) — সব ঠিক করে `READY` আনো; live-demo নিয়ম `docs/LIVE_DEMO.md`।
1. **Setup:** venv, `pip install -r requirements.txt`, ffmpeg, `python test_mock.py` → `ALL TESTS PASSED`। *(Roman-এর কাছ থেকে `.env`-এ `LLM_API_KEY` চেয়ে নাও।)*
2. **Real smoke test:** ৩টা Bangla YouTube video `python prepare.py` দিয়ে index (একটা caption-সহ, একটা `--asr`)। `/lab` খুলে ৫টা প্রশ্ন চালাও; ভাঙা জিনিস ঠিক করো। *শেষ:* প্রতিটা stage-এ sensible data, "নেই" প্রশ্নে not-found।
3. **Prompt/parse hardening:** আসল LLM output-এ যেখানে JSON ভাঙে (`trace.attempts[].grader_ok=false`, `verify: failed`) সেখানে prompt/parse ঠিক করো।
4. **Chunking tune:** `/lab › Chunking` দেখে `min_dur/max_dur/k` ঠিক করো (`semantic_chunks` default); বদলালে docs আপডেট করো।
5. **Eval set + সংখ্যা:** `docs/EVALUATION.md` অনুযায়ী ≥20 positive + ≥6 negative প্রশ্ন Roman-এর সাথে বানাও (gold range video দেখে); `python eval.py ... --full`; `docs/EVALUATION.md` §5 table ভরো। **সংখ্যা বানানো/অনুমান করা যাবে না।**
6. **Sarvam ASR** ৫ মিনিটের Bangla clip-এ test; না চললে docs অনুযায়ী ঠিক করো (Batch API বিকল্প)।
7. **Extension:** Chrome-এ Load unpacked; আসল video-তে index → ask → timestamp click; ভাঙলে ঠিক করো। (Claude in Chrome থাকলে সেটা দিয়ে UI দেখো।)
8. **Deploy (Roman-কে লগইন/secret দিতে হবে):** `prepare.py --export`, GitHub push, Render blueprint, `APP_PASSWORD`, `/healthz`, extension-এ Render URL। *শেষ:* live URL-এ library video-তে ask কাজ করে।
9. **Presentation:** `docs/PRESENTATION_OUTLINE.md` অনুযায়ী slides + demo রিহার্সাল (sir-এর আগে host গরম করো)।
10. (ঐচ্ছিক, পরে) GraphRAG/RAPTOR-lite, visual RAG, comments RAG, speaker-aware — এগুলো ইচ্ছা করেই বাদ; index-time LLM cost বা GPU লাগে।

## 4. জানা সীমা / সিদ্ধান্ত
- **LLM/embedding API লাগবেই** (rewrite, grade, answer, verify, quiz, plan সব LLM)। Default = Gemini (AI Studio free tier, card লাগে না — তৃতীয়-পক্ষ সূত্র; free-tier input Google উন্নয়নে ব্যবহার করতে পারে)। Gemini model নাম বদলায়: Google-এর deprecations page (updated 24 Sep 2026) অনুযায়ী `gemini-2.5-*` নতুন প্রজেক্টে সীমিত; default `gemini-3.8-flash` (**আসল key দিয়ে চালানো হয়নি**)। Embedding `gemini-embedding-001` (shutdown 2028-05-14; নতুন `gemini-embedding-2` vector space আলাদা → বদলালে re-index)। `python doctor.py` legacy model ধরে।
- Free host-এ YouTube cloud-IP block ⇒ live YouTube index নয়; extension/upload/`library/`। Hugging Face Docker Space এখন paid (docs যাচাই), তাই Render।
- Free host disk ephemeral ⇒ স্থায়ী library = repo-র `library/index`।
- Embedding মডেল local↔host মেলাতে হবে (`meta.emb_id`)।
- LLM-as-judge (rerank/grade/verify) ভুল করতে পারে।
- Academic হলে `yt-dlp` download ঠিক আছে; product হলে ToS/copyright ঝুঁকি ⇒ embedded player (`start/end`), download নয়।
- `APP_PASSWORD` না দিলে public host-এ যে কেউ LLM quota পোড়াতে পারে; rate limit নেই।

## 5. কমান্ড চিট-শিট
```
python test_mock.py                       # offline test
uvicorn app:app --reload                  # http://localhost:8000  ·  /lab
python prepare.py <url> [<url>] [--asr] [--export]
python eval.py eval_set.json [--full]
```
