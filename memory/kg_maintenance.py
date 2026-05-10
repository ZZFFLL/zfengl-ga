"""Maintenance helpers for GA's MemPalace SQLite knowledge graph."""

import sqlite3
from pathlib import Path

from memory.palace_bridge import KG_PATH, PalaceBridge


def _connect(db_path):
    return sqlite3.connect(str(Path(db_path)))


def list_noisy_triples(db_path=KG_PATH, limit=None):
    """Return triples whose object looks like markdown/code/table noise."""
    con = _connect(db_path)
    try:
        rows = con.execute(
            "select id, subject, predicate, object from triples order by extracted_at, id"
        ).fetchall()
    finally:
        con.close()

    noisy = [
        {"id": row[0], "subject": row[1], "predicate": row[2], "object": row[3]}
        for row in rows
        if not PalaceBridge._is_clean_fact_object(row[3])
    ]
    return noisy[:limit] if limit is not None else noisy


def clean_noisy_triples(db_path=KG_PATH, dry_run=True):
    """Delete noisy triples when dry_run is False; always returns a summary."""
    noisy = list_noisy_triples(db_path)
    ids = [row["id"] for row in noisy]
    deleted = 0
    if ids and not dry_run:
        con = _connect(db_path)
        try:
            con.executemany("delete from triples where id = ?", [(triple_id,) for triple_id in ids])
            deleted = con.total_changes
            con.commit()
        finally:
            con.close()
    print(
        f"[MemPalace] 🧹 KG noisy triples matched={len(ids)} "
        f"deleted={deleted} dry_run={dry_run}"
    )
    return {"matched": len(ids), "deleted": deleted, "ids": ids}


def list_orphan_noisy_entities(db_path=KG_PATH, limit=None):
    """Return noisy entities that are not referenced by any triple."""
    con = _connect(db_path)
    try:
        rows = con.execute("select id, name from entities order by created_at, id").fetchall()
        referenced = set()
        for subject, obj in con.execute("select subject, object from triples").fetchall():
            referenced.add(str(subject))
            referenced.add(str(obj))
    finally:
        con.close()

    noisy = [
        {"id": row[0], "name": row[1]}
        for row in rows
        if str(row[0]) not in referenced and not PalaceBridge._is_clean_fact_object(row[1])
    ]
    return noisy[:limit] if limit is not None else noisy


def clean_orphan_noisy_entities(db_path=KG_PATH, dry_run=True):
    """Delete unreferenced noisy entities when dry_run is False."""
    noisy = list_orphan_noisy_entities(db_path)
    ids = [row["id"] for row in noisy]
    deleted = 0
    if ids and not dry_run:
        con = _connect(db_path)
        try:
            con.executemany("delete from entities where id = ?", [(entity_id,) for entity_id in ids])
            deleted = con.total_changes
            con.commit()
        finally:
            con.close()
    print(
        f"[MemPalace] 🧹 KG orphan noisy entities matched={len(ids)} "
        f"deleted={deleted} dry_run={dry_run}"
    )
    return {"matched": len(ids), "deleted": deleted, "ids": ids}
