# Evaluation guide

কোনো সংখ্যা এখানে আগে থেকে দেওয়া নেই — **সংখ্যা তোমার নিজের eval set থেকে আসতে হবে**। নিচের table খালি; চালিয়ে ভরো।

## 1. Eval set বানানো
`eval_set.example.json` দেখো। প্রতিটা item:
```json
{"video": "<youtube url বা video id (index করা)>", "question": "...", "gold": [start_sec, end_sec]}
{"video": "...", "question": "video-তে নেই এমন topic", "gold": null}
```
- 3–5টা video, মোট **≥20 positive + ≥6 negative** প্রশ্ন। কম হলে result "প্রাথমিক" বলো।
- `gold` = যে অংশে উত্তর আছে, **video দেখে নিজে মেপে** লেখো। খুব চওড়া range Hit@k ফুলিয়ে দেয়; উত্তরের অংশ 30–120 s রাখো।
- প্রশ্ন মিশাও: Bangla script, Banglish, English। কিছু "জটিল" (দুই ভাগের) প্রশ্ন রাখো।
- Negative প্রশ্ন = ঐ video-র বিষয়ের কাছাকাছি কিন্তু আসলে আলোচিত হয়নি (কঠিন negative), একদম অপ্রাসঙ্গিক না।

## 2. চালানো
```
python eval.py eval_set.json            # retrieval ablation (LLM লাগে শুধু rewrite/rerank-এ)
python eval.py eval_set.json --full     # + end-to-end baseline vs full
```
অথবা browser-এ `/lab` → "4) Evaluation"।

## 3. Metric-এর মানে
Overlap = retrieved chunk-এর সময়-range `gold`-এর সাথে ছেদ করলে "hit"।
| Metric | মানে |
|---|---|
| Hit@5 | top-5 chunk-এর কোনোটা gold ছুঁয়েছে এমন প্রশ্নের ভগ্নাংশ |
| MRR | প্রথম সঠিক chunk-এর rank-এর reciprocal-এর গড় (1.0 = সবসময় #1) |
| avg_ms | প্রতি প্রশ্নে retrieval সময় (rerank/rewrite-এ LLM latency ধরে) |
| locate_accuracy | full pipeline-এর segment gold ছুঁয়েছে |
| not_found_accuracy | negative প্রশ্নে "নেই" বলেছে (hallucination-এর বিপরীত) |
| claim_support_rate | generate করা claim-এর কত অংশ verification পাস করেছে |
| claims_dropped | verification যত claim ফেলেছে |

## 4. Ablation configs
`dense` · `bm25` · `hybrid` · `hybrid+rerank` · `hybrid+rerank+rewrite`
End-to-end: **baseline** (rewrite/grade/verify বন্ধ) বনাম **full**।
(কোন config ভালো হবে তা আগে থেকে ধরে নিও না; উল্টো ফলও রিপোর্ট করো।)

## 5. ফলাফলের table (আসল run)
Run date: **30 Sep 2026** (Roman-এর PC, `python eval.py eval_set.json --full`)  Videos: **4** (DBMS normalization, computer network, binary tree, python intro — সব Bangla, YouTube auto-caption)  n(pos)=**26** n(neg)=**8**  Embedding: `gemini-embedding-001` (3072-d)  LLM: `gemini-3.5-flash` (+ fallback pool)  Rerank: LLM
Gold range: Claude transcript পড়ে দিয়েছে (video দেখে নয়) — Roman ৩–৪টা spot-check করবে।

| Config | Hit@5 | MRR | avg ms |
|---|---|---|---|
| dense | 1.00 | 0.92 | 576 |
| bm25 | 0.00 | 0.00 | 0 |
| hybrid | 0.96 | 0.86 | 516 |
| hybrid+rerank | **1.00** | **0.93** | 1794 |
| hybrid+rerank+rewrite | 1.00 | 0.86 | 11528 |

**যা শেখা গেল (উল্টো ফলও):**
- **BM25 = 0**: প্রশ্ন বেশিরভাগ Banglish/English, কিন্তু caption Bangla script-এ ("partial dependency" বনাম "পার্শিয়াল ডিপেন্ডেন্সি") → হুবহু শব্দ মেলে না। এজন্যই dense দরকার, আর query rewrite একটা Bangla-script query বানায়।
- Hybrid (0.96) dense-এর (1.00) চেয়ে সামান্য খারাপ — BM25-এর noisy ranking RRF-এ একটু টেনে নামায়; LLM rerank সেটা ঠিক করে সবচেয়ে ভালো MRR (0.93) দেয়।
- Rewrite এই set-এ Hit বাড়ায়নি (আগেই 1.00), MRR কমিয়েছে ও latency ~6× বাড়িয়েছে → retrieval-এর জন্য rewrite ঐচ্ছিক; তবে ছোট set, ৪টা video — প্রাথমিক ফল।

| End-to-end | locate_acc | not_found_acc | claim_support | claims_dropped |
|---|---|---|---|---|
| baseline | — | — | — | — |
| full | — | — | — | — |

End-to-end run মাঝপথে থেমেছে: free tier-এর **embedding daily quota (1000 request/দিন)** শেষ (reset: বাংলাদেশ দুপুর ১টা)। পরে আবার চালাও: `python eval.py eval_set.json --full`। এখন app embedding শেষ হলে BM25-এ নেমে যায় ও query embedding cache করে।
আলাদা informal smoke test (একই ৪ video, ১০ প্রশ্ন, full pipeline): **10/10** (6/6 found, 4/4 “নেই”), সব claim verified।

## 6. সতর্কতা
- LLM-as-judge (grading/verification) নিজেই ভুল করে; কিছু dropped claim আসলে ঠিক ছিল কিনা ১০–২০টা হাতে দেখে "judge precision" লিখলে রিপোর্ট শক্ত হয়।
- Temperature 0.1 হলেও LLM output চালানোয় একটু বদলায়; গুরুত্বপূর্ণ সংখ্যা ২–৩ বার চালিয়ে দেখো।
- Free-tier rate limit-এ eval আটকালে `--full` ছোট set-এ চালাও।
