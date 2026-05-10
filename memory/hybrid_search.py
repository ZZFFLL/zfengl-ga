"""
hybrid_search.py — Semantic + keyword hybrid search for GA.

Wraps ChromaDB semantic search from palace_bridge with optional
keyword fallback. Designed as a drop-in enhancement for rg-based searches.

Usage:
    from memory.hybrid_search import hybrid_search
    results = hybrid_search("处理图片上传的问题", n_results=5)
"""

from memory.palace_bridge import get_bridge


def hybrid_search(query: str, n_results: int = 5,
                   min_score: float = 0.3,
                   session_id: str = None) -> list:
    """Search stored conversations using semantic similarity.

    Returns list of {id, text, score, metadata} dicts,
    filtered by min_score threshold.
    """
    bridge = get_bridge()
    results = bridge.search(query, n_results=n_results,
                            session_id=session_id)
    # Filter low-confidence results
    filtered = [r for r in results if r.get("score", 0) >= min_score]
    print(f"[MemPalace] 🔍 hybrid_search '{query[:50]}' → "
          f"{len(results)} raw, {len(filtered)} after min_score={min_score}")
    return filtered


def search_with_fallback(query: str, n_results: int = 5,
                          min_score: float = 0.3) -> dict:
    """Search with semantic results + stats for diagnostics.

    Returns {results: [...], total: int, avg_score: float}.
    """
    results = hybrid_search(query, n_results=n_results,
                            min_score=min_score)
    avg = (sum(r["score"] for r in results) / len(results)
           if results else 0.0)
    return {
        "results": results,
        "total": len(results),
        "avg_score": round(avg, 3),
    }