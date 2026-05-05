"""
palace_bridge.py — MemPalace ↔ GenericAgent bridge.

Parallel capability layer. Does NOT modify GA's existing L0-L4 file system.
Every conversation turn is auto-stored as a verbatim ChromaDB drawer.
Entity relationships accrue in the SQLite knowledge graph.

Usage:
    from memory.palace_bridge import PalaceBridge
    bridge = PalaceBridge()

    # After each turn
    bridge.store_turn(session_id="2026-05-06-001", role="user", content="...")
    bridge.store_turn(session_id="2026-05-06-001", role="assistant", content="...")

    # On wakeup: get relevant context
    results = bridge.search("image upload issue", n_results=5)

    # Knowledge graph facts
    bridge.add_fact("user", "uses_tool", "web_scan")
    bridge.query_facts("user")
"""

import hashlib
import os
import time
from pathlib import Path

from mempalace.knowledge_graph import KnowledgeGraph
from mempalace.palace import get_collection

# ── Config ──────────────────────────────────────────────
# Palace storage lives alongside GA's memory/ directory
GA_ROOT = Path(__file__).resolve().parent.parent
PALACE_PATH = str(GA_ROOT / "memory" / ".palace_db")
KG_PATH = str(GA_ROOT / "memory" / ".kg.sqlite3")


class PalaceBridge:
    """GA's interface to MemPalace capabilities: verbatim storage + KG."""

    def __init__(self, palace_path: str = None, kg_path: str = None):
        self._palace_path = palace_path or PALACE_PATH
        self._kg_path = kg_path or KG_PATH
        self._collection = None
        self._kg = None

    # ── ChromaDB verbatim storage ────────────────────────

    @property
    def collection(self):
        """Lazy-init ChromaDB collection."""
        if self._collection is None:
            os.makedirs(self._palace_path, exist_ok=True)
            self._collection = get_collection(self._palace_path, create=True)
        return self._collection

    def store_turn(self, session_id: str, role: str, content: str,
                   metadata: dict = None) -> str:
        """Store one conversation turn as a verbatim drawer.
        
        Returns the drawer ID (deterministic hash of content+timestamp).
        """
        ts = time.time()
        doc_id = hashlib.sha256(
            f"{session_id}:{role}:{ts}:{content[:80]}".encode()
        ).hexdigest()[:16]

        meta = {
            "session_id": session_id,
            "role": role,
            "timestamp": ts,
            "source": "ga_conversation",
            **(metadata or {}),
        }

        self.collection.add(
            ids=[doc_id],
            documents=[content],
            metadatas=[meta],
        )
        return doc_id

    def search(self, query: str, n_results: int = 5,
               session_id: str = None) -> list:
        """Semantic search against all stored conversation turns.
        
        Returns list of {id, text, score, metadata} dicts.
        """
        where = {"session_id": session_id} if session_id else None
        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=n_results,
                where=where,
            )
        except Exception:
            return []

        out = []
        ids = results.get("ids", [[]])[0]
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        dists = results.get("distances", [[]])[0]

        for i in range(len(ids)):
            out.append({
                "id": ids[i],
                "text": docs[i] if i < len(docs) else "",
                "score": 1.0 - dists[i] if i < len(dists) else 0,
                "metadata": metas[i] if i < len(metas) else {},
            })
        return out

    def recent_turns(self, session_id: str, n: int = 10) -> list:
        """Get most recent turns for a session (by timestamp)."""
        try:
            results = self.collection.get(
                where={"session_id": session_id},
                limit=n * 3,  # over-fetch, then sort
            )
        except Exception:
            return []

        items = []
        ids = results.get("ids", [])
        docs = results.get("documents", [])
        metas = results.get("metadatas", [])

        for i in range(len(ids)):
            items.append({
                "id": ids[i],
                "text": docs[i] if i < len(docs) else "",
                "metadata": metas[i] if i < len(metas) else {},
            })

        items.sort(key=lambda x: x["metadata"].get("timestamp", 0), reverse=True)
        return items[:n]

    # ── Knowledge Graph ──────────────────────────────────

    @property
    def kg(self):
        """Lazy-init SQLite knowledge graph."""
        if self._kg is None:
            self._kg = KnowledgeGraph(db_path=self._kg_path)
        return self._kg

    def add_fact(self, subject: str, predicate: str, obj: str,
                 valid_from: str = None, confidence: float = 1.0):
        """Record an entity relationship fact."""
        self.kg.add_triple(subject, predicate, obj,
                           valid_from=valid_from,
                           confidence=confidence)

    def query_facts(self, entity_name: str, as_of: str = None) -> list:
        """Query all facts about an entity."""
        return self.kg.query_entity(entity_name, as_of=as_of)

    def invalidate_fact(self, subject: str, predicate: str, obj: str,
                        ended: str):
        """Mark a fact as no longer valid."""
        self.kg.invalidate(subject, predicate, obj, ended=ended)


# ── Module-level convenience ────────────────────────────

_default_bridge = None


def get_bridge() -> PalaceBridge:
    """Get or create the singleton bridge instance."""
    global _default_bridge
    if _default_bridge is None:
        _default_bridge = PalaceBridge()
    return _default_bridge