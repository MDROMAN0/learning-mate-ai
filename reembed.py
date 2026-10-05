"""Re-embed every indexed video with the CURRENT embedding config (after switching EMB_* settings).
Chunks/timestamps stay the same; only the vectors are rebuilt. Old index is backed up first."""
import json, shutil, time
import numpy as np
import rag

rag.sync_library()
idx = rag.DATA / "index"
bak = rag.DATA / ("index_backup_" + time.strftime("%Y%m%d_%H%M%S"))
shutil.copytree(idx, bak)
print("backup:", bak)
ok = 0
for p in sorted(idx.glob("*.json")):
    d = json.loads(p.read_text(encoding="utf-8"))
    meta, chunks = d["meta"], d["chunks"]
    if meta.get("emb_id") == rag.emb_id():
        continue
    E = rag.embed([rag.index_text(c) for c in chunks], "passage")
    meta["emb_id"] = rag.emb_id()
    rag.save_index(meta["video_id"], meta, chunks, E, d.get("extra"))
    ok += 1
    print("re-embedded", meta["video_id"], len(chunks), "chunks", E.shape)
print("done:", ok, "videos ->", rag.emb_id())
