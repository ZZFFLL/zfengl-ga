# GenericAgent

## What This Is

GenericAgent is an existing autonomous AI Agent framework with a synchronous tool loop, browser-control tools, multiple LLM backends, memory, and several frontends. The current planning focus is a narrow extension: add one unified search tool that covers information `web_scan` and `web_execute_js` cannot reliably find because those tools are tied to current browser page state and DOM execution.

## Core Value

GA should expose one model-facing search capability while letting developers add or swap concrete search providers behind it.

## Requirements

### Validated

- GA already supports model-visible tools through `assets/tools_schema*.json`, `GenericAgentHandler.do_*`, and `BaseHandler.dispatch()`.
- GA already has browser tools for page inspection and JavaScript execution; the search tool must complement them rather than replace their browser-control role.
- Phase 1 added one model-visible `web_search` tool backed by `tools/searchserver/` provider discovery.
- Phase 1 validated that developers can add provider implementations without adding a new GA tool per provider.
- Phase 1 kept provider discovery and invocation small: provider-specific API calls live behind the searchserver provider interface.

### Active

- [ ] Configure real Tavily credentials in local `mykey.py` when live provider smoke is needed in this environment.

### Out of Scope

- Replacing `web_scan` or `web_execute_js` — those remain browser/page-control tools.
- Modifying external dependency repositories — this work stays inside GenericAgent.
- Creating one model-visible tool per search provider — provider count must not leak into the GA tool list.
- Building a general workflow engine for arbitrary external APIs — this phase is scoped to search providers.

## Context

- Current tool dispatch is name-based: `BaseHandler.dispatch()` calls `GenericAgentHandler.do_<tool_name>()`.
- Tool schemas are loaded from `assets/tools_schema.json` and `assets/tools_schema_cn.json`.
- Existing browser tools live in `ga.py` as `web_scan()` / `web_execute_js()` plus `do_web_scan()` / `do_web_execute_js()`.
- The new search capability should target cases where page DOM inspection cannot reach search-engine or API results, especially when the agent needs broad web lookup rather than operating on an already-open page.

## Constraints

- **Scope**: Implement one GA tool, not N provider tools — keeps model behavior stable as providers change.
- **Extensibility**: Provider-specific code should be isolated behind a small developer-facing provider interface.
- **Compatibility**: Existing tool flow and schemas should remain recognizable to avoid broad agent-loop changes.
- **Safety**: Provider implementations must not require editing external dependency projects.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Use one model-visible search tool with provider discovery behind it | Future providers should not expand the model tool surface | Implemented in Phase 1 |
| Keep browser tools separate from search providers | `web_scan` and `web_execute_js` operate on page state; search providers query external/search APIs | Implemented in Phase 1 |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition**:
1. Requirements invalidated? Move to Out of Scope with reason.
2. Requirements validated? Move to Validated with phase reference.
3. New requirements emerged? Add to Active.
4. Decisions to log? Add to Key Decisions.
5. "What This Is" still accurate? Update if drifted.

**After each milestone**:
1. Full review of all sections.
2. Core Value check: still the right priority?
3. Audit Out of Scope: reasons still valid?
4. Update Context with current state.

---
*Last updated: 2026-05-29 after Phase 1 execution*
