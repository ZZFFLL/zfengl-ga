from __future__ import annotations

from typing import Any

from ga_browser_use.results import failed_result


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _contains(haystack: Any, needle: Any) -> bool:
    needle_text = _norm(needle)
    return bool(needle_text and needle_text in _norm(haystack))


def safe_max_results(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = 5
    return max(1, min(parsed, 20))


def _text_parts(element: dict[str, Any]) -> list[str]:
    parts = [element.get("text"), element.get("value")]
    parts.extend(element.get("labels") or [])
    field_context = element.get("field_context") or {}
    parts.extend(field_context.get("labels") or [])
    parts.extend([field_context.get("nearby_text"), field_context.get("placeholder")])
    attrs = element.get("attributes") or {}
    parts.extend([attrs.get("aria-label"), attrs.get("title"), attrs.get("placeholder")])
    return [str(part) for part in parts if part]


def _table_value(table_context: dict[str, Any], *names: str) -> str:
    for name in names:
        value = table_context.get(name)
        if value:
            return str(value)
    return ""


def _field_value(field_context: dict[str, Any], *names: str) -> str:
    for name in names:
        value = field_context.get(name)
        if value:
            return str(value)
    return ""


def _score_field_context(field_context: dict[str, Any], query: str) -> tuple[float, list[str]]:
    if not query:
        return 0.0, []
    score = 0.0
    reasons: list[str] = []
    row_label = _field_value(field_context, "row_label", "previous_cell_text")
    nearby_text = _field_value(field_context, "nearby_text")
    field_id = _field_value(field_context, "field_id")
    field_name = _field_value(field_context, "field_name")
    if row_label and _norm(row_label) == _norm(query):
        score += 68
        reasons.append("field row label")
    elif row_label and _contains(row_label, query):
        score += 52
        reasons.append("field row label")
    elif nearby_text and _contains(nearby_text, query):
        score += 44
        reasons.append("nearby field text")
    if field_id and _norm(field_id) == _norm(query):
        score += 70
        reasons.append("field id")
    if field_name and _norm(field_name) == _norm(query):
        score += 70
        reasons.append("field name")
    return score, reasons


def _score_label_text(parts: list[str], labels: list[str], query: str) -> tuple[float, list[str]]:
    if not query:
        return 0.0, []
    if any(_norm(label) == _norm(query) for label in labels):
        return 70.0, ["exact label"]
    if any(_contains(label, query) for label in labels):
        return 50.0, ["label"]
    if any(_contains(part, query) for part in parts):
        return 25.0, ["text"]
    return 0.0, []


def _has_locator_constraint(
    *,
    query: str,
    role: str | None,
    control_kind: str | None,
    layer: str | None,
    frame_path: list[Any] | None,
    table: dict[str, Any] | None,
) -> bool:
    if query:
        return True
    return isinstance(table, dict) and any(table.get(key) for key in ("row_text", "column_text", "header_text"))


def _score_element(
    element: dict[str, Any],
    *,
    query: str,
    role: str | None,
    control_kind: str | None,
    layer: str | None,
    frame_path: list[Any] | None,
    table: dict[str, Any] | None,
) -> tuple[float, list[str]]:
    reasons: list[str] = []
    if role and _norm(element.get("role")) != _norm(role):
        return 0.0, []
    if control_kind and _norm(element.get("control_kind")) != _norm(control_kind):
        return 0.0, []
    if layer and _norm(element.get("layer")) != _norm(layer):
        return 0.0, []
    if frame_path is not None and element.get("frame_path") != frame_path:
        return 0.0, []
    score = 0.0
    parts = _text_parts(element)
    labels = [str(label) for label in (element.get("labels") or [])]
    field_context = element.get("field_context") or {}
    if query:
        field_score, field_reasons = _score_field_context(field_context, query)
        label_text_score, label_text_reasons = _score_label_text(parts, labels, query)
        semantic_score, semantic_reasons = label_text_score, label_text_reasons
        if field_score > label_text_score:
            semantic_score, semantic_reasons = field_score, field_reasons
        if not semantic_score:
            return 0.0, []
        score += semantic_score
        reasons.extend(semantic_reasons)

    table_context = element.get("table_context") or {}
    if table:
        row_text = table.get("row_text")
        column_text = table.get("column_text") or table.get("header_text")
        if row_text:
            row_value = _table_value(table_context, "row_text", "row_header")
            if not _contains(row_value, row_text):
                return 0.0, []
            score += 35
            reasons.append("table row")
        if column_text:
            column_value = _table_value(table_context, "column_header", "column_text", "header_text")
            if not _contains(column_value, column_text):
                return 0.0, []
            score += 35
            reasons.append("table column")

    if element.get("visible") is True:
        score += 10
        reasons.append("visible")
    if _norm(element.get("layer")) != "main":
        score += 5
        reasons.append("layer")
    if control_kind:
        score += 10
        reasons.append("control_kind")
    if element.get("disabled") is True:
        score -= 2
        reasons.append("disabled")
    return score, reasons


def find_in_state(
    state: dict[str, Any],
    *,
    query: str | None = None,
    role: str | None = None,
    control_kind: str | None = None,
    layer: str | None = None,
    frame_path: list[Any] | None = None,
    table: dict[str, Any] | None = None,
    max_results: int = 5,
) -> dict[str, Any]:
    if not isinstance(state, dict):
        return failed_result(None, "state_missing", "browser_find requires a successful browser_state.")
    query_text = str(query or "").strip()
    if state.get("status") != "success":
        result = dict(state)
        result.setdefault("status", "failed")
        result.setdefault("stage", "state_missing")
        result.setdefault("error", "browser_find requires a successful browser_state.")
        return result
    if not _has_locator_constraint(
        query=query_text,
        role=role,
        control_kind=control_kind,
        layer=layer,
        frame_path=frame_path,
        table=table,
    ):
        result = failed_result(None, "invalid_args", "browser_find requires query or table; role, control_kind, layer, and frame_path are filters only.")
        result["recovery"]["code"] = "provide_locator"
        result["recovery"]["message"] = "Provide query or table before using browser_find; role, control_kind, layer, and frame_path are filters only."
        result["recovery"]["stop_retry"] = True
        result["recovery"].pop("next_tool", None)
        result["recovery"].pop("next_args", None)
        return result
    elements = state.get("elements") if isinstance(state.get("elements"), list) else []
    matches = []
    for element in elements:
        if not isinstance(element, dict):
            continue
        score, reasons = _score_element(
            element,
            query=query_text,
            role=role,
            control_kind=control_kind,
            layer=layer,
            frame_path=frame_path,
            table=table,
        )
        if score <= 0:
            continue
        matches.append(
            {
                "index": element.get("index"),
                "score": min(round(score / 100, 3), 1.0),
                "reason": "; ".join(reasons),
                "element": element,
            }
        )
    matches.sort(key=lambda item: item["score"], reverse=True)
    limit = safe_max_results(max_results)
    if not matches:
        result = failed_result(None, "target_not_found", "No browser element matched the requested criteria.")
        result["recovery"]["code"] = "refresh_state_then_find"
        result["recovery"]["message"] = "Refresh browser_state and retry browser_find with the same semantic locator."
        result["recovery"]["next_tool"] = "browser_find"
        next_args = {"refresh": True, "query": query_text, "max_results": limit}
        if role:
            next_args["role"] = role
        if control_kind:
            next_args["control_kind"] = control_kind
        if layer:
            next_args["layer"] = layer
        if frame_path is not None:
            next_args["frame_path"] = frame_path
        if table:
            next_args["table"] = table
        result["recovery"]["next_args"] = next_args
        return result
    ambiguous = len(matches) > 1 and abs(matches[0]["score"] - matches[1]["score"]) <= 0.05
    matches = matches[:limit]
    return {"status": "success", "matches": matches, "ambiguous": ambiguous, "recovery": None}
