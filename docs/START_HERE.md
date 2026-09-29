# Vidya — শুরু এখান থেকে (beginner guide)

**Vidya** = লম্বা YouTube video থেকে ঠিক দরকারি অংশ খুঁজে, timestamp-সহ যাচাই করা উত্তর দেয় (RAG + LLM)।
Video **download করে না** — caption সরাসরি YouTube থেকে পড়ে, আর উত্তরের অংশ YouTube player-এই চালায়।

## ১. চালানো (Windows)
1. `start.bat`-এ double-click → browser-এ `http://localhost:8000` খুলবে।
2. প্রথমবার **Sign up** (নাম, email, password) → এরপর থেকে **Log in**। (এগুলো শুধু তোমার PC-র database-এ থাকে।)
3. উপরে **বাংলা / English** button দিয়ে পুরো site-এর ভাষা বদলাও; ◐ = dark/light।

## ২. ব্যবহার — ৩ ধাপ
| ধাপ | কী করবে |
|---|---|
| 1. Video খোঁজো | বাঁ দিকে **YouTube খুঁজুন** → topic লেখো → video card-এ click। অথবা link paste করে **Index**। |
| 2. Index | ১০–৩০ সেকেন্ড: caption → semantic chunk → embedding। শেষ হলে video খুলে যাবে। |
| 3. প্রশ্ন | ডান দিকে **প্রশ্ন** tab-এ Bangla/English/Banglish-এ লেখো → Enter। |

উত্তরে যা দেখবে:
- **✓ n/n claims verified** — প্রতিটা point transcript দিয়ে যাচাই হয়েছে।
- **▶ 2:58** chip — চাপলে player ঠিক ওই সেকেন্ডে যায়।
- **Topic timeline** — video-র কোথায় কোথায় topic আছে (গাঢ় = বেশি)। timeline-এ click করলেও seek হয়।
- video-তে না থাকলে **“এই video-তে নেই”** — বানিয়ে বলে না।

অন্য tab: **Compare** (library-র কয়েকটা video কী বলে), **Watch plan** (তুমি যা জানো না শুধু সেটুকু), **Quiz**, **বুঝিনি** (player-এর এখনকার অংশ সহজ করে)।

## ৩. RAG Lab (sir-কে দেখানোর জন্য) — `http://localhost:8000/lab`
একটা প্রশ্ন দিয়ে **Full pipeline** চাপো → প্রতিটা ধাপ আসল data-সহ: query rewrite → dense + BM25 → RRF → rerank → grading → evidence → answer → claim verification → latency। **Retrieval mode তুলনা**, **Semantic chunking** graph, আর **Evaluation** table-ও এখানে।

## ৪. সমস্যা হলে
| সমস্যা | সমাধান |
|---|---|
| “no captions found” | caption আছে এমন video বাছো (বেশিরভাগ Bangla tutorial-এ auto caption থাকে) |
| উত্তর আসতে দেরি / 429 | free Gemini-র প্রতি মিনিটের limit; app নিজে অন্য model-এ যায় ও অপেক্ষা করে — ১ মিনিট পর আবার চেষ্টা |
| “আজকের limit শেষ” | প্রতি user-এর দিনে `DAILY_LIMIT` (default 60) প্রশ্ন — `.env`-এ বাড়াও |
| কিছুই চলছে না | `python doctor.py` → যা ❌ দেখায় তা ঠিক করো |

## ৫. ফোল্ডার কোনটা কী
| ফাইল | কাজ |
|---|---|
| `start.bat` | এক-ক্লিকে চালু · `start_share.bat` = public link (Cloudflare tunnel) |
| `rag.py` | RAG core (chunking, hybrid retrieval, rerank, grading, answer, verification) |
| `features.py` | Compare, Watch plan, Quiz, Explain, YouTube search |
| `auth.py` | Sign up / log in, প্রতি-user daily limit, history |
| `app.py` | Web server (FastAPI) |
| `static/` | Website (index = Study, lab = RAG Lab, `i18n.js` = বাংলা/English লেখা) |
| `extension/` | Chrome extension (YouTube-এর পাশেই প্রশ্ন) |
| `eval.py`, `eval_set.json` | Evaluation (সংখ্যা: `docs/EVALUATION.md`) |
| `docs/` | Architecture, deploy, demo, presentation |
