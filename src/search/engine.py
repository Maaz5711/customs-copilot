"""Hybrid retrieval: exact-code lookup, then BM25 + dense (RRF) + cross-encoder rerank.

All models are local (fastembed / ONNX, CPU). No API keys. Indexes are built by
`python -m src.search.build` into data/processed/search_index/.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
INDEX_DIR = ROOT / "data" / "processed" / "search_index"
INDEXES = ("tariff", "notes", "sro", "rulings")
EMBED_MODEL = "BAAI/bge-small-en-v1.5"
RERANK_MODEL = "Xenova/ms-marco-MiniLM-L-6-v2"
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

_STOP = {"the", "a", "an", "of", "and", "or", "for", "to", "in", "on", "is", "are", "with", "by", "at", "from", "as", "that", "this", "it"}


def _stem(w: str) -> str:
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


def tokenize(text: str) -> list[str]:
    return [_stem(w) for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in _STOP]


def _to_iso(d) -> str | None:
    if d is None:
        return None
    if isinstance(d, (date, datetime)):
        return d.strftime("%Y-%m-%d")
    datetime.strptime(str(d), "%Y-%m-%d")  # raises on a bad date
    return str(d)


class _Index:
    def __init__(self, name: str):
        from rank_bm25 import BM25Okapi
        d = INDEX_DIR / name
        if not (d / "docs.jsonl").exists():
            raise FileNotFoundError(f"index '{name}' not built. Run: python -m src.search.build")
        self.name = name
        self.docs = [json.loads(l) for l in (d / "docs.jsonl").read_text(encoding="utf8").splitlines()]
        self.emb = np.load(d / "emb.npy")
        self.bm25 = BM25Okapi([tokenize(x["text"]) for x in self.docs])
        self.vf = np.array([x["valid_from"] for x in self.docs])
        self.vt = np.array([x["valid_to"] for x in self.docs])

    def mask(self, iso: str | None) -> np.ndarray:
        if iso is None:
            return np.ones(len(self.docs), dtype=bool)
        return (self.vf <= iso) & (self.vt >= iso)


_cache: dict[str, _Index] = {}
_models: dict = {}


def _index(name: str) -> _Index:
    if name not in _cache:
        _cache[name] = _Index(name)
    return _cache[name]


def _embedder():
    if "emb" not in _models:
        from fastembed import TextEmbedding
        _models["emb"] = TextEmbedding(EMBED_MODEL)
    return _models["emb"]


def _reranker():
    if "rr" not in _models:
        from fastembed.rerank.cross_encoder import TextCrossEncoder
        _models["rr"] = TextCrossEncoder(RERANK_MODEL)
    return _models["rr"]


def embed_query(q: str) -> np.ndarray:
    v = np.array(list(_embedder().embed([QUERY_PREFIX + q]))[0], dtype=np.float32)
    return v / (np.linalg.norm(v) or 1.0)


# ---------- exact code lookup ----------
_CODE_WHOLE = re.compile(r"^\s*(\d{2}\.?\d{2}(?:\.?\d{2,4})?)\s*$")
_CODE_EMBED = re.compile(r"(?<![\d.])(\d{4}\.\d{2,4}|\d{2}\.\d{2}|\d{8})(?![\d])")


def extract_codes(query: str) -> tuple[list[str], bool]:
    """Return (digit codes found, query_is_only_a_code)."""
    m = _CODE_WHOLE.match(query)
    if m:
        c = re.sub(r"\D", "", m.group(1))
        if len(c) in (4, 6, 8):
            return [c], True
    codes = [re.sub(r"\D", "", x) for x in _CODE_EMBED.findall(query)]
    return [c for c in codes if len(c) in (4, 6, 8)], False


def _exact(ix: _Index, code: str, mask: np.ndarray) -> list[tuple[float, int]]:
    out = []
    for i, d in enumerate(ix.docs):
        if not mask[i] or not d["code"]:
            continue
        dc = d["code"]
        if ix.name == "notes":
            if dc == code[:2]:
                out.append((700.0, i))
            continue
        if dc == code:
            out.append((1000.0, i))
        elif len(dc) >= 4 and len(dc) < len(code) and code.startswith(dc):
            out.append((900.0 + len(dc) / 10, i))      # ancestor (heading / 6-digit row covering the code)
        elif len(dc) > len(code) and dc.startswith(code) and ix.name == "tariff":
            out.append((800.0 - len(dc) / 100, i))     # descendants
    out.sort(key=lambda t: (-t[0], ix.docs[t[1]]["code"], ix.docs[t[1]].get("fy", "")))
    return out


def _hit(ix: _Index, i: int, score: float, method: str, **extra) -> dict:
    d = dict(ix.docs[i])
    d.update({"score": round(float(score), 4), "method": method, "index": ix.name})
    d.update(extra)
    return d


def _hybrid(ix: _Index, query: str, mask: np.ndarray, k: int, rerank: bool, pool: int = 40) -> list[dict]:
    qt = tokenize(query)
    bm = ix.bm25.get_scores(qt) if qt else np.zeros(len(ix.docs))
    bm = np.where(mask, bm, -1e9)
    dense = ix.emb @ embed_query(query)
    dense = np.where(mask, dense, -1e9)
    nvalid = int(mask.sum())
    pool = min(pool, nvalid)
    if pool == 0:
        return []
    b_rank = {int(i): r for r, i in enumerate(np.argsort(-bm)[:pool]) if bm[i] > 0}
    d_rank = {int(i): r for r, i in enumerate(np.argsort(-dense)[:pool])}
    rrf: dict[int, float] = {}
    for rk in (b_rank, d_rank):
        for i, r in rk.items():
            rrf[i] = rrf.get(i, 0.0) + 1.0 / (60 + r)
    cands = sorted(rrf, key=lambda i: -rrf[i])[:pool]
    info = {i: {"bm25": float(bm[i]), "dense": float(dense[i]), "rrf": rrf[i]} for i in cands}
    if not rerank:
        return [_hit(ix, i, rrf[i], "hybrid", **info[i]) for i in cands[:k]]
    texts = [ix.docs[i]["text"][:600] for i in cands]
    rr = dict(zip(cands, (float(x) for x in _reranker().rerank(query, texts))))
    # fuse reranker rank with first-stage rank so one model cannot fully override the other
    rr_rank = {i: r for r, i in enumerate(sorted(cands, key=lambda j: -rr[j]))}
    fused = {i: 2.0 / (10 + rr_rank[i]) + 1.0 / (10 + n) for n, i in enumerate(cands)}
    order = sorted(cands, key=lambda i: -fused[i])[:k]
    return [_hit(ix, i, fused[i], "hybrid+rerank", rerank_score=rr[i], **info[i]) for i in order]


def search(query: str, index: str | None = None, as_of_date=None, k: int = 10, rerank: bool = True) -> list[dict]:
    """Search one index (name) or all four (index=None).

    Returns hits ranked best-first. Every hit has id, index, source_file, page,
    valid_from, valid_to, text, score, method. With index=None the result is the
    top k per index merged (each index keeps its own ranking, round-robin by rank)
    so a flood of tariff rows cannot hide a ruling or a note.
    as_of_date (date or 'YYYY-MM-DD') keeps only rows valid on that date (inclusive).
    """
    iso = _to_iso(as_of_date)
    names = INDEXES if index is None else (index,)
    if any(n not in INDEXES for n in names):
        raise ValueError(f"index must be one of {INDEXES}")
    per: list[list[dict]] = []
    codes, only_code = extract_codes(query)
    for n in names:
        ix = _index(n)
        mask = ix.mask(iso)
        hits: list[dict] = []
        seen: set[str] = set()
        for c in codes:
            for sc, i in _exact(ix, c, mask)[: max(k, 1) * 2]:
                if ix.docs[i]["id"] not in seen:
                    seen.add(ix.docs[i]["id"])
                    hits.append(_hit(ix, i, sc, "exact_code", matched_code=c))
        if not (only_code and hits):
            text_q = _CODE_EMBED.sub(" ", query).strip() or query
            for h in _hybrid(ix, text_q, mask, k, rerank):
                if h["id"] not in seen:
                    hits.append(h)
        per.append(hits[:k])
    if len(per) == 1:
        return per[0]
    merged, r = [], 0
    while len(merged) < k and any(r < len(p) for p in per):
        for p in per:
            if r < len(p) and len(merged) < k:
                merged.append(p[r])
        r += 1
    return merged
