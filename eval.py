"""Evaluation + ablation (also exposed in the RAG Lab page and POST /api/lab/eval).
CLI:  python eval.py eval_set.json [--full]
eval_set.json = [{"video": "<url or id>", "question": "...", "gold": [start_sec, end_sec]},
                 {"video": "...", "question": "topic NOT in video", "gold": null}]

1) Retrieval ablation (no answer generation): Hit@k, MRR and latency for
   dense | bm25 | hybrid | hybrid+rerank | hybrid+rerank+rewrite
2) --full end-to-end, baseline (no rewrite/grade/verify) vs full pipeline:
   locate_accuracy, not_found_accuracy, claim_support_rate, claims_dropped
"""
import json
import sys
import time

import rag

CONFIGS = [("dense", "dense", False), ("bm25", "bm25", False), ("hybrid", "hybrid", False),
           ("hybrid+rerank", "hybrid+rerank", False), ("hybrid+rerank+rewrite", "hybrid+rerank", True)]


def overlap(c, g):
    return c["start"] < g[1] and c["end"] > g[0]


def retrieval_ablation(items, k=5):
    res = {n: {"hit": 0, "rr": 0.0, "n": 0, "ms": 0.0} for n, _, _ in CONFIGS}
    for it in items:
        if not it.get("gold"):
            continue
        vid = rag.extract_video_id(it["video"])
        ix = rag.load_index(vid)
        rewritten = None
        for name, mode, rw in CONFIGS:
            t0 = time.perf_counter()
            if rw:
                rewritten = rewritten or rag.rewrite_query(it["question"], ix.meta.get("title", vid))
                qs = rewritten
            else:
                qs = [it["question"]]
            r = rag.retrieve(ix, qs, it["question"], k=k, mode=mode)
            res[name]["ms"] += (time.perf_counter() - t0) * 1000
            ranks = [i for i, c in enumerate(r) if overlap(c, it["gold"])]
            res[name]["n"] += 1
            if ranks:
                res[name]["hit"] += 1
                res[name]["rr"] += 1.0 / (ranks[0] + 1)
    return {m: {"Hit@k": v["hit"] / max(v["n"], 1), "MRR": v["rr"] / max(v["n"], 1),
                "avg_ms": round(v["ms"] / max(v["n"], 1)), "n": v["n"]} for m, v in res.items()}


def _full(items, **flags):
    pos = loc = neg = neg_ok = claims = supported = 0
    for it in items:
        out = rag.ask(it["video"], it["question"], make_clip=False, **flags)
        if not it.get("gold"):
            neg += 1
            neg_ok += int(not out["found"])
            continue
        pos += 1
        if out["found"] and any(overlap(s, it["gold"]) for s in out["segments"]):
            loc += 1
        claims += out["trace"].get("claims_total", 0)
        supported += out["trace"].get("claims_supported", 0)
    return {"locate_accuracy": loc / max(pos, 1), "not_found_accuracy": neg_ok / max(neg, 1),
            "claim_support_rate": supported / max(claims, 1), "claims_dropped": claims - supported,
            "positives": pos, "negatives": neg}


def full_eval(items):
    return {"baseline (no rewrite/grade/verify)": _full(items, use_rewrite=False, use_grade=False, use_verify=False),
            "full pipeline": _full(items)}


if __name__ == "__main__":
    data = json.load(open(sys.argv[1], encoding="utf-8"))
    print(f"{'config':24}{'Hit@5':>8}{'MRR':>8}{'ms':>7}{'n':>4}")
    for m, v in retrieval_ablation(data).items():
        print(f"{m:24}{v['Hit@k']:8.2f}{v['MRR']:8.2f}{v['avg_ms']:7d}{v['n']:4d}")
    if "--full" in sys.argv:
        print(json.dumps(full_eval(data), indent=2, ensure_ascii=False))
