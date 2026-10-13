"""Build the four search indexes: python -m src.search.build [--only tariff,notes]"""
from __future__ import annotations

import argparse
import json
import time

import numpy as np

from . import docs as D
from .engine import EMBED_MODEL, INDEX_DIR, _embedder


def build(only: list[str] | None = None) -> dict:
    sizes = {}
    emb = _embedder()
    for name, fn in D.BUILDERS.items():
        if only and name not in only:
            continue
        t0 = time.time()
        rows = fn()
        # hard rule: no row without dates, source_file and page
        for r in rows:
            for f in ("valid_from", "valid_to", "source_file", "page", "id", "text"):
                if r.get(f) in (None, ""):
                    raise ValueError(f"{name}: row {r.get('id')} missing {f}")
        ids = [r["id"] for r in rows]
        if len(set(ids)) != len(ids):
            dup = {i for i in ids if ids.count(i) > 1}
            raise ValueError(f"{name}: duplicate ids, e.g. {sorted(dup)[:3]}")
        vecs = np.array(list(emb.embed([r["text"] for r in rows], batch_size=64)), dtype=np.float32)
        vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
        out = INDEX_DIR / name
        out.mkdir(parents=True, exist_ok=True)
        (out / "docs.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf8")
        np.save(out / "emb.npy", vecs)
        sizes[name] = len(rows)
        print(f"{name}: {len(rows)} docs, {vecs.shape}, {time.time() - t0:.0f}s")
    meta_path = INDEX_DIR / "meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {"sizes": {}}
    meta["sizes"].update(sizes)
    meta["embed_model"] = EMBED_MODEL
    meta_path.write_text(json.dumps(meta, indent=1))
    return sizes


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="comma list of indexes")
    a = ap.parse_args()
    build([x for x in a.only.split(",") if x] or None)
