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
        print(f"[MemPalace] ✅ stored {role} turn (session={session_id}, id={doc_id}, len={len(content)})")
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
        except Exception as e:
            print(f"[MemPalace] ❌ search failed: {e}")
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
        print(f"[MemPalace] 🔍 search '{query[:60]}' → {len(out)} results")
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
        result = items[:n]
        print(f"[MemPalace] 📖 recent_turns(session={session_id}) → {len(result)} turns")
        return result

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
        print(f"[MemPalace] 📝 KG fact: {subject} → {predicate} → {obj} (conf={confidence})")

    def query_facts(self, entity_name: str, as_of: str = None) -> list:
        """Query all facts about an entity."""
        facts = self.kg.query_entity(entity_name, as_of=as_of)
        print(f"[MemPalace] 📖 query_facts('{entity_name}') → {len(facts)} facts")
        return facts

    def invalidate_fact(self, subject: str, predicate: str, obj: str,
                        ended: str):
        """Mark a fact as no longer valid."""
        self.kg.invalidate(subject, predicate, obj, ended=ended)
        print(f"[MemPalace] 🗑️ KG invalidated: {subject} → {predicate} → {obj}")

    # ── Auto-extraction from conversation ─────────────────

    # Simple heuristic patterns for extracting facts from GA turns
    _TOOL_PATTERNS = [
        (r'\b(web_scan|web_execute_js|file_read|file_patch|file_write|code_run|'
         r'web_search|ask_user|apply_patch|start_long_term)\b', 'uses_tool'),
    ]
    _PREF_PATTERNS = [
        (r'(?:不要|禁止|别|严禁|Never)\s*(\S+(?:\s+\S+){0,5})', 'dislikes'),
        (r'(?:优先|总是|Always|prefer)\s*(\S+(?:\s+\S+){0,5})', 'prefers'),
    ]

    def extract_conversation_facts(self, session_id: str,
                                   user_text: str, assistant_text: str):
        """Extract lightweight entity facts from a conversation turn.
        
        Detects: tool usage, user preferences, task topics.
        Stores facts as (session, predicate, object) triples.
        Non-blocking; errors are silently ignored.
        """
        import re
        now = time.strftime('%Y-%m-%d %H:%M:%S')
        combined = f"{user_text}\n{assistant_text}"

        # Tool usage
        for pat, pred in self._TOOL_PATTERNS:
            for m in re.finditer(pat, combined, re.IGNORECASE):
                tool = m.group(1).lower()
                try:
                    self.add_fact(session_id, pred, tool,
                                  valid_from=now, confidence=0.9)
                except Exception:
                    pass

        # User preferences (only from user text)
        for pat, pred in self._PREF_PATTERNS:
            for m in re.finditer(pat, user_text, re.IGNORECASE):
                obj = m.group(1).strip().lower()
                if len(obj) > 2 and len(obj) < 60:
                    try:
                        self.add_fact('user', pred, obj,
                                      valid_from=now, confidence=0.7)
                    except Exception:
                        pass

        # Session metadata
        try:
            self.add_fact(session_id, 'occurred_at', now,
                          confidence=1.0)
        except Exception:
            pass

    def get_session_facts_context(self, session_id: str = None,
                                  max_facts: int = 10) -> str:
        """Return a compact KG fact summary for prompt injection.
        
        If session_id is None, returns recent facts across all sessions.
        """
        try:
            if session_id:
                facts = self.query_facts(session_id)
            else:
                facts = self.kg.query_recent(max_facts * 2)
        except Exception as e:
            print(f"[MemPalace] ❌ get_session_facts_context failed: {e}")
            return ""

        if not facts:
            return ""

        lines = ["[MemPalace KG] 实体关系图谱:"]
        seen = set()
        for f in facts[:max_facts]:
            s, p, o = (f.get('subject','?'), f.get('predicate','?'),
                       f.get('object','?'))
            key = (s, p, o)
            if key in seen:
                continue
            seen.add(key)
            valid = f.get('valid_from', '')
            lines.append(f"- {s} {p} {o}" + (f" (since {valid})" if valid else ""))
        result = '\n'.join(lines)
        print(f"[MemPalace] 🧠 KG context injected ({len(seen)} facts)")
        return result


# ── Module-level convenience ────────────────────────────

_default_bridge = None


def get_bridge() -> PalaceBridge:
    """Get or create the singleton bridge instance."""
    global _default_bridge
    if _default_bridge is None:
        _default_bridge = PalaceBridge()
    return _default_bridge