---
phase: "01"
plan: "02"
subsystem: "ga tool schema"
tags:
  - search
  - tool-dispatch
  - smoke
key-files:
  - "ga.py"
  - "assets/tools_schema.json"
  - "assets/tools_schema_cn.json"
  - "mykey_template.py"
  - "mykey_template_en.py"
  - "tests/test_search_tool_integration.py"
  - "tests/test_searchserver_smoke.py"
metrics:
  tests: "5 integration tests passed"
  smoke: "1 smoke skipped because local Tavily config is absent"
---

## PLAN COMPLETE

Exposed one provider-neutral GA search tool and connected it to the provider layer.

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 01-02 | Not committed in this run | Added `web_search` schema entries, `GenericAgentHandler.do_web_search()`, template config examples, integration tests, and gated Tavily smoke coverage. |

## What Changed

- Added exactly one `web_search` tool entry to both English and Chinese tool schemas.
- Added `GenericAgentHandler.do_web_search()` as a thin wrapper around `tools.searchserver.search()`.
- Kept `web_scan` and `web_execute_js` behavior unchanged.
- Added commented Tavily config examples to both `mykey` templates using placeholder keys only.
- Added schema/handler integration tests and a real Tavily smoke path gated by local config.

## Verification

- `python -m pytest tests/test_search_tool_integration.py -q` -> 5 passed.
- `python -m pytest tests/test_searchserver.py tests/test_search_tool_integration.py -q` -> 10 passed.
- `python -m pytest tests/test_searchserver_smoke.py -q` -> 1 skipped because `tavily_search_keys` / `tavily_search_url` are not configured locally.
- `git diff --check` -> passed.

## Deviations

- Real Tavily network smoke did not execute in this environment because local Tavily credentials and endpoint variables are absent. The smoke test is present and will exercise the real provider path when those variables are configured.

## Self-Check: PASSED

GA now exposes one model-visible `web_search` tool, accepts only a keyword/query at the tool boundary, delegates all provider behavior to `tools/searchserver/`, and preserves the existing browser tool semantics.
