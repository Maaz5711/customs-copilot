"""Try-out: python -m src.search "frozen chicken" [--index tariff] [--date 2026-07-01] [-k 10] [--no-rerank]"""
import argparse

from . import search


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("--index", default=None)
    ap.add_argument("--date", default=None)
    ap.add_argument("-k", type=int, default=10)
    ap.add_argument("--no-rerank", action="store_true")
    a = ap.parse_args()
    for n, h in enumerate(search(a.query, a.index, a.date, a.k, rerank=not a.no_rerank), 1):
        print(f"{n:>2}. [{h['index']}] {h['score']:<8} {h['method']:<14} {h['id']}  (valid {h['valid_from']}..{h['valid_to']})")
        print(f"      {h['source_file']} p.{h['page']}")
        print(f"      {h['text'][:200]}")


if __name__ == "__main__":
    main()
