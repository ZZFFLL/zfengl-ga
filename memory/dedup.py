"""
dedup.py — Duplicate detection for MemPalace storage.

Checks semantic similarity before storing to prevent duplicates.
Threshold: 0.85 (configurable).

Usage:
    from memory.dedup import is_duplicate, guard_write
    if not is_duplicate("some text"):
        bridge.store_turn(...)
"""

from memory.palace_bridge import get_bridge


DEFAULT_THRESHOLD = 0.85


def is_duplicate(text: str, threshold: float = DEFAULT_THRESHOLD,
                 session_id: str = None) -> bool:
    """Check if text is semantically similar to existing stored content.

    Returns True if similarity >= threshold (likely duplicate).
    """
    bridge = get_bridge()
    results = bridge.search(text, n_results=1, session_id=session_id)
    if not results:
        return False
    score = results[0].get("score", 0.0)
    is_dup = score >= threshold
    if is_dup:
        print(f"[MemPalace] 🚫 dedup BLOCKED (score={score:.3f} >= "
              f"threshold={threshold}): '{text[:60]}'")
    return is_dup


def guard_write(text: str, store_fn, threshold: float = DEFAULT_THRESHOLD,
                session_id: str = None) -> str | None:
    """Guard wrapper: only store if not duplicate.

    Args:
        text: content to potentially store
        store_fn: callable that performs the actual storage
        threshold: similarity threshold
        session_id: optional session filter

    Returns:
        doc_id if stored, None if blocked as duplicate.
    """
    if is_duplicate(text, threshold=threshold, session_id=session_id):
        return None
    return store_fn()