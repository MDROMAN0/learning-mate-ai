"""Run LOCALLY (home IP works with YouTube): build indexes, then export them for the free host.
  python prepare.py <youtube-url-or-file> [more ...] [--asr] [--export]
--export copies data/index/* into library/index/ (commit that folder; the host loads it at startup).
Use the SAME EMB_* settings locally and on the host (index records which embedding model built it)."""
import shutil
import sys
from pathlib import Path

import rag

args = [a for a in sys.argv[1:] if not a.startswith("--")]
for a in args:
    print("indexing", a)
    if Path(a).exists():
        meta = rag.build_index_from_upload(a, Path(a).name, print)
    else:
        meta = rag.build_index(a, "--asr" in sys.argv, print)
    print("  ->", meta["title"], meta["n_chunks"], "chunks", meta["source"])
if "--export" in sys.argv:
    out = rag.LIBRARY / "index"
    out.mkdir(parents=True, exist_ok=True)
    for f in (rag.DATA / "index").glob("*"):
        shutil.copy(f, out / f.name)
    print("exported to", out, "- now git add library && git push")
