# Deploy ও চালানো

## A. Local (sir-এর demo-র জন্য সবচেয়ে নিরাপদ)
```
python -m venv .venv && .venv\Scripts\activate       # Windows  (Linux/Mac: source .venv/bin/activate)
pip install -r requirements.txt                       # হালকা (API embeddings)
# অথবা: pip install -r requirements-local.txt        # local embedding/Whisper/cross-encoder চাইলে
copy .env.example .env                                # তারপর LLM_API_KEY বসাও
winget install ffmpeg                                 # clip কাটার জন্য লাগে
python prepare.py <youtube-url> <youtube-url>         # তোমার PC-তে index (home IP-তে YouTube কাজ করে)
uvicorn app:app --reload                              # http://localhost:8000  ·  /lab = RAG Lab
python test_mock.py                                   # offline test (API key ছাড়াই)
```
Local-এ `EMB_PROVIDER=local` আর host-এ `api` **মেলাবে না** — index-এ embedding নাম লেখা থাকে, না মিললে error। দুই জায়গায় একই রাখো।

> **Presentation-এর live demo Render-এ না, তোমার PC-তে** — `docs/LIVE_DEMO.md`।

> **Vercel / Cloudflare Pages / GitHub Pages কেন না:** Pages = শুধু static HTML; আমাদের backend Python (numpy, BM25, ffmpeg, কয়েক মিনিটের indexing, disk-এ file) — serverless function-এর জন্য বানানো না। আর YouTube সমস্যা host-এর নামের না, **cloud IP-র**: Vercel-ও ঐ block-এর তালিকায় আছে। Vercel Hobby আবার শুধু non-commercial।
> Public link দরকার হলে সবচেয়ে সহজ: PC-তে app চালিয়ে Cloudflare Quick Tunnel (`docs/LIVE_DEMO.md`)।

## B. Free host — কী যাচাই করা হয়েছে (দেখা: 30 Sep 2026)
| কী | ফল |
|---|---|
| Hugging Face Spaces (Docker/Gradio) | **এখন paid plan লাগে** (HF official docs); শুধু Static Space free → এটা ব্যবহার করা যায় না |
| Render free web service | card লাগে না, 512 MB RAM, 15 মিনিট idle-এ sleep (ফিরতে ~১ মিনিট), disk ephemeral (তৃতীয়-পক্ষ তুলনা, 26 Sep 2026; Render dashboard-এ নিজে মিলিয়ে নাও) |
| Koyeb / Cloud Run / Oracle | card লাগে |
| YouTube থেকে cloud IP | **block** (youtube-transcript-api-র README; Render-এও রিপোর্ট আছে) |

তাই design: host-এ YouTube থেকে সরাসরি আনা নয় → (1) Chrome extension, (2) Upload tab, (3) `prepare.py` দিয়ে `library/` — এই তিনটা।

### Render-এ deploy — ChatGPT-এর মতো public website (login সহ)
যা পাবে: `https://vidya-rag.onrender.com` — যে কেউ **Sign up / Log in** করে ব্যবহার করবে; প্রতি user-এর দিনে `DAILY_LIMIT`টা প্রশ্ন (তোমার free Gemini quota বাঁচাতে), নিজের history।

**Roman-এর কাজ (login/secret — Claude করবে না):**
1. **GitHub** account-এ নতুন repo বানাও (যেমন `vidya-rag`, Private চলবে)।
2. **Render.com** → GitHub দিয়ে sign up (card লাগে না)।
3. (ঐচ্ছিক কিন্তু ভালো) **neon.tech** → free Postgres → connection string (`postgresql://...`) copy। না দিলে Render-এর disk restart-এ মুছে যায় → account-গুলোও মুছে যাবে।
4. Render → **New → Blueprint** → repo বেছে নাও → `render.yaml` পড়বে → চাইলে দেবে: `LLM_API_KEY` (Gemini key), `DATABASE_URL` (Neon), `APP_PASSWORD` (extension-এর admin key)। `SECRET_KEY` Render নিজে বানায়।

**Claude/terminal-এর কাজ:** `git add . && git commit && git push` (`.env`, `data/`, `jobs/` `.gitignore`-এ আছে — key কখনো GitHub-এ যায় না)। `library/index/`-এর আগে-index করা video-গুলো host-এ সাথে যায়।

5. Deploy শেষে `https://<name>.onrender.com/healthz` → `{"ok":true}` → site খুলে Sign up।
6. Free plan ১৫ মিনিট idle থাকলে ঘুমায় — প্রথম request ~১ মিনিট। sir-এর demo-র আগে একবার খুলে রাখো।

### Host-এ সীমা (সৎভাবে)
- **YouTube cloud IP block করে** → host থেকে নতুন YouTube video index/search অনেক সময় ব্যর্থ হবে। সমাধান: (ক) `library/`-এর video (PC-তে index করে push), (খ) Chrome extension (user-এর নিজের browser থেকে caption পাঠায়), (গ) .srt/audio upload।
- **সবচেয়ে ভালো live demo:** PC-তে `start_share.bat` (Cloudflare tunnel) — site তোমার PC-তে চলে বলে YouTube search/index সব কাজ করে, আর link যে কেউ খুলতে পারে (login সহ)। PC চালু থাকতে হবে।
- Runtime-এ নতুন index করা video host restart-এ হারায় (library/ ছাড়া)।
- Free Gemini: প্রতি model-এর per-minute ও per-day limit (reset: Pacific রাত ১২টা = বাংলাদেশ দুপুর ১টা)। অনেক user হলে paid key লাগবে।

## C. Chrome extension
1. `chrome://extensions` → Developer mode → **Load unpacked** → `extension/` ফোল্ডার।
2. Side panel-এ Backend URL (`http://localhost:8000` বা Render URL) আর App key।
3. YouTube video খুলে "এই video index করো" → caption আনে (json3 → না পেলে transcript panel scrape) → server-এ পাঠায় → প্রশ্ন করো।
4. `manifest.json`-এর `host_permissions`-এ তোমার নিজের Render domain না মিললে (`*.onrender.com` ধরে) fetch ব্লক হবে — domain বদলালে সেখানে যোগ করো।
**Untested**: আসল Chrome-এ চালানো হয়নি। YouTube caption endpoint/DOM বদলাতে পারে।

## D. Environment variables
`.env.example` দেখো (LLM, LLM_FALLBACK_MODELS, EMB_*, RERANK_PROVIDER, CHUNK_SIGNAL, ASR_PROVIDER, SARVAM_*, ENRICH, YT_LIVE, YT_DOWNLOAD (default 0 = download নয়), YT_API_KEY, AUTH, DAILY_LIMIT, SECRET_KEY, DATABASE_URL, APP_PASSWORD, DATA_DIR, LIBRARY_DIR)।
