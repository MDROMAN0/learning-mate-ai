# Learning Mate AI

A YouTube study assistant built on **Retrieval-Augmented Generation (RAG)**. Watch any YouTube video inside the site and ask questions about it — answers come only from what the video actually says, with clickable timestamps and a verification check on every claim.

**Live:** https://learning-mate-ai.onrender.com  ·  NSU CSE 299 Junior Design Project — Md Roman

## Features

- **Watch instantly** — search YouTube or paste a link; the video plays right on the site (no download).
- **Demo mode** — try the sample lecture library without an account (a few free questions per day).
- **Ask across all videos** — one question searched over the whole library; the answer cites the exact video + moment and shows which videos cover the topic.
- **Auto chapters + summary** — every video gets timestamped chapters (grounded on real transcript passages) shown on the timeline.
- **Grounded Q&A** — answers with citations `[1] [2]` that jump to the exact moment in the video; says "not found" instead of guessing.
- **Topic timeline** — a heat-map showing where in the video a topic is discussed.
- **Notebook** — type, draw, take screenshots of the player, add timestamps, ask the AI, export to PDF.
- **Study tools** — quiz, "explain this part", watch plan, compare videos.
- **RAG Lab** (`/lab`) — shows every pipeline step live (query rewrite, hybrid retrieval, rerank, grading, answer, claim verification), plus an Evaluation tab with measured Hit@5 / MRR per retrieval mode and a one-click live test run.
- **Bangla / English** — full UI switch; handles Bangla, English and Banglish questions.
- Accounts, question history, daily usage limit; works on phones and desktop.

## How the RAG pipeline works

```
captions → semantic chunks → embeddings (dense) + BM25 (sparse)
question → rewrite / HyDE → hybrid search → RRF fusion → LLM rerank
        → relevance grading (corrective RAG) → grounded answer with citations
        → claim-by-claim verification → answer + timestamps
```

Details: [`docs/RAG_ARCHITECTURE.md`](docs/RAG_ARCHITECTURE.md) · Evaluation results: [`docs/EVALUATION.md`](docs/EVALUATION.md)

## Tech stack

Python · FastAPI · Gemini API (OpenAI-compatible) · rank-BM25 · NumPy · yt-dlp / youtube-transcript-api · SQLite / PostgreSQL · vanilla JS · YouTube IFrame API · Docker · Render

## Run locally

```bash
pip install -r requirements.txt
python setup_keys.py      # paste your Gemini API key (stored in .env, never committed)
python run.py             # open http://localhost:8000
```

On Windows you can double-click `start.bat`. Deployment guide: [`docs/DEPLOY.md`](docs/DEPLOY.md).

## Project structure

| Path | What it is |
|---|---|
| `rag.py` | chunking, embeddings, hybrid retrieval, rerank, grading, answer, verification |
| `features.py` | YouTube search, quiz, explain, watch plan, comparisons |
| `app.py` | FastAPI server and API |
| `auth.py` | accounts, sessions, usage limits, notes |
| `static/` | web app (`index.html`, notebook, RAG Lab) |
| `extension/` | Chrome extension (side panel on youtube.com) |
| `eval.py`, `eval_set.json` | retrieval and end-to-end evaluation |
