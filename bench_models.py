"""Compare local Ollama models on the full RAG pipeline: quality + speed. Usage: python bench_models.py m1 m2 ..."""
import json, os, sys, time
import rag, eval as ev

items = json.load(open("eval_quick.json", encoding="utf-8"))
res = {}
for m in sys.argv[1:]:
    os.environ["LLM_MODEL"] = m
    os.environ.pop("LLM_FAST_MODEL", None)
    rag._clients.clear(); rag._client = None
    try:
        rag.llm("hi", "hi")                       # load model into GPU first (not timed)
    except Exception as e:
        res[m] = {"error": str(e)[:200]}; continue
    pos = loc = neg = neg_ok = answered = claims = sup = 0
    t0 = time.time(); errs = 0
    for it in items:
        try:
            out = rag.ask(it["video"], it["question"], make_clip=False)
        except Exception as e:
            errs += 1; continue
        if not it.get("gold"):
            neg += 1; neg_ok += int(not out["found"]); continue
        pos += 1
        if out["found"] and any(ev.overlap(s, it["gold"]) for s in out.get("segments", [])):
            loc += 1
        answered += int(bool(out.get("answer")))
        claims += out["trace"].get("claims_total", 0); sup += out["trace"].get("claims_supported", 0)
    n = len(items) - errs
    res[m] = {"locate_acc": round(loc / max(pos, 1), 2), "answer_rate": round(answered / max(pos, 1), 2),
              "claim_support": round(sup / max(claims, 1), 2), "not_found_acc": round(neg_ok / max(neg, 1), 2),
              "sec_per_question": round((time.time() - t0) / max(n, 1), 1), "errors": errs}
    print(m, res[m], flush=True)
json.dump(res, open("bench_result.json", "w"), indent=1)
print(json.dumps(res, indent=1))
