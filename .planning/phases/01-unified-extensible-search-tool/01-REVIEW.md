---
status: findings
phase: "01"
phase_name: "unified-extensible-search-tool"
depth: standard
files_reviewed: 13
findings:
  critical: 0
  warning: 2
  info: 0
  total: 2
reviewed_at: "2026-05-29"
---

# Code Review: Phase 01

## Scope

Reviewed source changes from Phase 01:

- `ga.py`
- `assets/tools_schema.json`
- `assets/tools_schema_cn.json`
- `mykey_template.py`
- `mykey_template_en.py`
- `tools/__init__.py`
- `tools/searchserver/__init__.py`
- `tools/searchserver/base.py`
- `tools/searchserver/config.py`
- `tools/searchserver/registry.py`
- `tools/searchserver/providers/__init__.py`
- `tools/searchserver/providers/tavily.py`
- `tests/test_searchserver.py`
- `tests/test_search_tool_integration.py`
- `tests/test_searchserver_smoke.py`

## Findings

### WR-01: Provider discovery exceptions bypass structured fallback

- Severity: Warning
- File: `tools/searchserver/registry.py:15`, `tools/searchserver/__init__.py:12`
- Risk: A single future provider module with a bad import or missing optional dependency can make every `web_search` call raise before provider fallback runs. That breaks the phase requirement that provider failures return structured unavailable reasons instead of crashing the agent loop.
- Evidence: `discover_provider_classes()` imports each provider module without catching import-time failures, and `search()` calls `registry.build_providers()` before entering its provider-error collection loop. A runtime probe with `discover_provider_classes` raising `RuntimeError("bad provider import")` produced `RuntimeError bad provider import` instead of an all-failed payload.
- Suggested fix: Catch per-module import exceptions during discovery and return them as unavailable provider errors, or wrap `build_providers()` in `search()` and convert discovery/config exceptions to `base.all_failed_payload()`.

### WR-02: Non-string search input can crash the handler before structured validation

- Severity: Warning
- File: `ga.py:380`
- Risk: Native tool calls are usually schema-shaped, but malformed tool arguments can still happen. If `keyword` or `query` is a number/object, `.strip()` raises and the agent loop sees an exception instead of a normal `{"status": "error"}` tool result.
- Evidence: A runtime probe through `BaseHandler.dispatch(..., "web_search", {"keyword": 123}, "")` produced `AttributeError 'int' object has no attribute 'strip'`.
- Suggested fix: Coerce before stripping, e.g. `keyword = str(args.get("keyword") or args.get("query") or "").strip()`, or pass the raw value into `searchserver.search()` and let the provider layer's existing string coercion handle it.

## Positive Checks

- Exactly one model-visible search tool is added to both schemas.
- Provider API logic stays outside `ga.py`.
- Tavily key values are redacted in per-key failure aggregation.
- Template config names avoid `api/config/cookie`, reducing risk of LLM-session auto-scan collisions.
- Tavily's current official API documentation uses `POST /search` with bearer-token authentication, matching the implementation shape.

## Verification Used During Review

- `gsd-sdk query init.phase-op 1`
- `gsd-sdk query config-get workflow.code_review --default true`
- `gsd-sdk query config-get workflow.code_review_depth --default standard`
- Runtime probe for malformed `web_search` input.
- Runtime probe for discovery exception propagation.

## Recommendation

Fix both warnings before treating the phase as ready for commit. They are small changes and directly target the stated extension/fallback contract.
