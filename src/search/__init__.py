"""Hybrid search (BM25 + dense + rerank) over tariff, legal notes, SRO clauses, rulings.

Usage: python -m src.search.build   then   from src.search import search
"""
from .engine import search, INDEXES  # noqa: F401
