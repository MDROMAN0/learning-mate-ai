# Sir-এর সামনে উপস্থাপন — outline + demo script

Sir মূলত দেখবেন **RAG কীভাবে কাজ করছে আর আমরা কীভাবে implement করেছি**। তাই পুরো presentation-এর কেন্দ্র = `/lab` (RAG Lab) আর একটা ছোট evaluation table।

## Slides (৮–১০টা)
1. **Problem** — লম্বা video থেকে নির্দিষ্ট topic/উত্তর খোঁজা কষ্টের; YouTube-এর Ask বোতাম আছে, কিন্তু তার supported ভাষার তালিকায় Bengali নেই (YouTube Help, দেখা: সেপ্টেম্বর 2026 — presentation-এর আগে আবার দেখে নাও) আর সব video-তে আসে না।
2. **Idea** — শুধু Q&A না: topic আছে কিনা + clip + verified notes; spoiler-free; alternatives; watch plan।
3. **Architecture diagram** — `docs/RAG_ARCHITECTURE.md`-এর §0 ডায়াগ্রাম।
4. **Index time** — semantic chunking (similarity curve দেখাও)।
5. **Query time** — rewrite → hybrid (dense+BM25, RRF) → rerank → corrective grading।
6. **Faithfulness** — grounded generation + claim verification (কোন claim ফেলা হলো)।
7. **Extra RAG features** — progress-aware filtering, multi-video comparison, watch plan।
8. **Evaluation** — ablation table (তোমার নিজের সংখ্যা) + not-found accuracy।
9. **Limitations ও future work** — `docs/RAG_ARCHITECTURE.md` §5।
10. **Demo** (নিচে)।

## ৮ মিনিটের live demo (RAG Lab)
আগে থেকে ২–৩টা video index করে রাখো (নিরাপত্তা জাল)। Live YouTube অংশের নিয়ম: `docs/LIVE_DEMO.md`।
1. `/lab` খোলো, একটা video বেছে প্রশ্ন লেখো (Banglish, যেমন "gradient descent ta ki") → **"1) Full pipeline"**।
   - Stage 0: প্রশ্ন কীভাবে ৪–৭টা query হলো।
   - Stage 1: dense আর BM25 আলাদা ranking, তারপর RRF, তারপর rerank-এর before/after।
   - Stage 2: কোন chunk "relevant", কোনটা "dropped"।
   - Stage 5: কোন claim verification-এ বাদ পড়ল (লাল badge)।
   - Σ: কত ms, কয়টা LLM call।
2. **"2) Retrieval modes compare"** → একই প্রশ্নে চার mode-এর top-5 পাশাপাশি; কোথায় পার্থক্য দেখাও।
3. **না-থাকা topic** দিয়ে pipeline চালাও → দুই attempt-এর পর "নেই" (hallucination করে না)।
4. **"3) Chunking"** → similarity curve, লাল threshold, সবুজ boundary।
5. Main app → **spoiler-free** (video মাঝখানে থামিয়ে) → ভবিষ্যতের topic "নেই"।
6. **Alternatives** (library-র ২টা video) → common/different।
7. **Evaluation** table।

## সম্ভাব্য প্রশ্ন (সৎ উত্তর)
- *"এটা ChatGPT-তে transcript paste করার থেকে আলাদা কীভাবে?"* — retrieval (পুরো video context-এ ঢোকে না), timestamp-সহ citation, "নেই" বলার ক্ষমতা, claim verification, clip; আর evaluation দিয়ে মাপা যায়।
- *"Accuracy কত?"* — শুধু নিজের eval table-এর সংখ্যা বলো, n সহ। আগে থেকে দাবি কোরো না।
- *"LLM-as-judge নির্ভরযোগ্য?"* — না পুরোপুরি; তাই ১০–২০টা হাতে যাচাই করে judge precision বলো।
- *"Novelty?"* — Bangla-first + progress-aware + watch plan; আমরা খুঁজে অন্য tool-এ পাইনি, কিন্তু "কেউ করেনি" নিশ্চিত দাবি কোরো না।
- *"Copyright/ToS?"* — academic prototype; product হলে embedded player ব্যবহার, download নয়।
