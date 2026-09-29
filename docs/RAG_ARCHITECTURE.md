# RAG Architecture — কোন ধাপে কী হয়, কেন, কোন parameter

> সব কিছু `rag.py` (core) আর `features.py` (extra features)-এ। **RAG Lab** (`/lab`) প্রতিটা ধাপ live দেখায়।
> এই doc-এর প্রতিটা সংখ্যা code থেকে নেওয়া; বদলালে doc-ও বদলাও।

## 0. এক নজরে

```
Video ──► Transcript ──► Semantic chunking ──► Embed + BM25 index ──┐   (INDEX TIME)
 (captions | ASR | .srt | extension)                                 │
                                                                     ▼
Question ─► Query rewrite ─► Hybrid retrieval ─► Rerank ─► Corrective grading ─► Grounded answer ─► Claim verification
 (Banglish)   (3 q + sub-q + HyDE)  (dense+BM25 → RRF)  (LLM|cross-enc)  (relevant? retry once)   (cited JSON)     (drop unsupported)
                                                                     │
                                                       merge ranges ─┴─► ffmpeg clip / embedded player (start,end)   (QUERY TIME)
```

## 1. Index time

### 1.1 Transcript source (`rag.build_index`, `asr.py`)
Priority: YouTube captions (`youtube-transcript-api`) → ASR on the downloaded media (`ASR_PROVIDER=local` faster-whisper | `sarvam`).
Other entries: uploaded video/audio (ASR), `.srt/.vtt` (`parse_subtitles`), Chrome extension (`/api/index_transcript`).
Sarvam REST accepts ≤30 s per request, so audio is split into 25 s WAV chunks with ffmpeg (`ASR_CHUNK_SEC`); each chunk becomes one segment (timestamps ±25 s precise).

### 1.2 Semantic chunking (`semantic_chunks`) — fixed-size chunk না কেন?
Fixed 30 s window কথার মাঝখানে কাটে, আর clip-এর boundary নষ্ট করে। তাই topic-shift ধরে কাটি:
1. প্রতিটা transcript segment → vector (`CHUNK_SIGNAL=lexical`: TF-IDF; `embedding`: embedding API).
   TF-IDF: vocab = df≥2 এবং (n<6 বা df≤0.5n) শব্দ, top 6000; weight = `log(1 + n/df)`. Bangla-safe tokenizer (`\w` Bangla matra ভাঙে, তাই separator দিয়ে split)।
2. `sims[i]` = cosine( mean(আগের 3 segment), mean(পরের 3 segment) ).
3. threshold = `mean(sims) − 0.5·std(sims)`.
4. chunk শেষ হয় যখন `sims[i] < threshold` এবং chunk ≥ **20 s**, অথবা chunk ≥ **90 s** (force).
Similarity curve + boundary → RAG Lab › "Chunking দেখো"।

Optional `ENRICH=1`: প্রতিটা chunk-এ LLM এক লাইনের "এই অংশ কী নিয়ে" context জুড়ে index করে (contextual retrieval)। খরচ: chunk প্রতি ১টা LLM call, default বন্ধ।

### 1.3 Index (`VideoIndex`)
- **Dense**: chunk embedding, normalized, cosine = dot product। `EMB_PROVIDER=api` (default; `gemini-embedding-001` অথবা `text-embedding-3-small`) | `local` (`intfloat/multilingual-e5-small`).
- **Sparse**: `BM25Okapi` (rank_bm25) chunk text-এর ওপর।
- Storage: `data/index/<id>.json` (meta, chunks, chunking-curve) + `.npy` (embeddings).
- `meta.emb_id` কোন embedding দিয়ে বানানো তা মনে রাখে; config না মিললে load-এ error (vector space মেলানো যায় না)।

## 2. Query time (`rag.ask`)

| # | ধাপ | ফাংশন | কী করে | Parameter |
|---|---|---|---|---|
| 0 | Query rewrite | `rewrite_query` | Banglish/Bangla/English প্রশ্ন থেকে 3 search query (Bangla script, English, technical terms) + জটিল হলে ≤3 sub-question (decomposition) + 1 hypothetical answer passage (HyDE-style). মূল প্রশ্নও থাকে; duplicate বাদ | 1 LLM call |
| 1 | Hybrid retrieval | `retrieve` | প্রতিটা query × {dense, BM25} = আলাদা ranking; সব ranking **Reciprocal Rank Fusion** `Σ 1/(60+rank)` দিয়ে জোড়া | pool 20 (attempt 2: 40) |
| 2 | Rerank | `rerank_llm` / `rerank_scores` | pool-এর top 12 (LLM listwise) বা পুরো pool (cross-encoder `bge-reranker-v2-m3`) পুনর্বিন্যাস | `RERANK_PROVIDER=llm\|cross-encoder\|none` |
| 3 | **Corrective grading** | `grade_chunks` | কড়া relevance judge: "সরাসরি আলোচনা/ব্যাখ্যা করলেই relevant, শুধু keyword মিললে না"। কিছুই relevant না হলে **1 বার retry**: broader query, k=16, pool=40। তবু না হলে "topic নেই" | k=8 → 16 |
| 4 | Grounded generation | `generate_answer` | শুধু numbered evidence (কালানুক্রমে, ≤8 chunk) থেকে JSON: title, summary, sections→points, প্রতিটা point-এ `cites:[n]`। `level`: simple/exam/expert | 1 LLM call |
| 5 | **Claim verification** | `verify_answer` | প্রতিটা point তার cited evidence দিয়ে যাচাই (LLM-as-judge, 1 batch call)। verdict: `supported` / `unsupported` / `no_citation` / `unverified`। unsupported ও no_citation **বাদ** | `use_verify` |
| 6 | Segment merge | `merge_ranges` | relevant chunk-এর সময়-range জোড়া (gap ≤10 s), padding −1 s/+1.5 s, ≤300 s, সর্বোচ্চ 3 segment; duration/current_time-এ clamp | — |
| 7 | Clip | `cut_clip` | ffmpeg (video→mp4, audio→m4a)। media না থাকলে UI YouTube embed `?start=&end=` দেখায় | — |

**Progress-aware (spoiler-free)**: `current_time=t` দিলে `start ≥ t` chunk retrieval-এ আসেই না; t-কে ছুঁয়ে যাওয়া chunk `trim_chunk` দিয়ে t পর্যন্ত কাটা হয়; rerank, grading, answer সবাই কাটা text দেখে।

### Per-request observability
`trace` সবসময়: `timings_ms` (rewrite/retrieve/grade/generate/verify/merge_clip), `usage` (LLM calls, in/out chars, embedding calls/texts), `claims` (প্রতিটা claim-এর verdict), `attempts`।
`debug=true` হলে অতিরিক্ত `trace.debug`: প্রতি ranking-এর top-6 + score, RRF top-10, rerank before/after, প্রতি candidate-এর relevant/dropped, evidence, verify-এর আগের raw answer।

## 3. Extra features (`features.py`) — সবই RAG-এর ওপর
| Feature | RAG technique |
|---|---|
| Alternatives | multi-video retrieval → per-video grounded answer → cross-source comparison (common/different/unique/conflicts; **রায় দেয় না**) |
| Watch plan | diagnostic pre-test → knowledge-gap → multi-video retrieval per gap → LLM দিয়ে minimal ordered path |
| Quiz | retrieved/sampled chunk থেকে MCQ; ভুল উত্তরে source chunk-এর timestamp (remediation) |
| বুঝিনি | timestamp-এর আগের 90 s passage → সহজ/উপমা/ধাপ; `other_video` = অন্য video থেকে একই concept retrieve |
| Query decomposition, level | §2 ধাপ 0, 4 |

## 4. Design decisions (কেন)
- **Hybrid**: Banglish/mixed শব্দে BM25 exact match ধরে, dense ধরে অর্থ; RRF-এ score scale মেলাতে হয় না।
- **Corrective + verification আলাদা**: grading = "সঠিক অংশ পেলাম কি?" (retrieval quality), verification = "উত্তরের প্রতিটা দাবি প্রমাণে আছে কি?" (generation faithfulness)।
- **Lexical chunk signal default**: API embedding-এ প্রতি segment embed করলে free-tier rate limit-এ আটকায়; TF-IDF কোনো API ছাড়া চলে।
- **LLM rerank default**: cross-encoder torch টানে, 512 MB host-এ আঁটে না।
- **Index-এ emb_id**: local আর host-এর embedding আলাদা হলে নীরবে ভুল result না দিয়ে error দেয়।

## 5. Limitations (sir-কে সৎভাবে বলার জন্য)
1. Verification/grading/rerank সবই LLM-as-judge; ভুল করতে পারে, human-labeled ground truth না।
2. Bangla auto-caption মান খারাপ হতে পারে; ASR-এর error retrieval-এ ছড়ায়। Whisper large-v3 Bangla-য় দুর্বল (এক public benchmark-এ leader-দের 4–5× CER, তবে সেই benchmark-এর clip ছোট)।
3. Chunk threshold (`k=0.5`, min 20 s, max 90 s) আসল Bangla video-তে tune করা হয়নি।
4. RRF-এ সব ranking সমান ওজন।
5. Progress-aware: t-ছোঁয়া chunk-এর *ranking score* পুরো chunk-এর text থেকে আসে (শুধু দেখানো/answer text কাটা) — সামান্য leakage।
6. Sarvam path: 25 s granularity; clip ±25 s।
7. Free host-এ disk ephemeral; runtime-এ বানানো index restart-এ হারায় (`library/` ছাড়া)।
8. Eval set ছোট হলে সংখ্যা statistically দুর্বল — n সবসময় লেখো।
