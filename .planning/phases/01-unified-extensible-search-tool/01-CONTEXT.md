# Phase 01: Unified extensible search tool - Context

**Gathered:** 2026-05-29
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase delivers one model-visible GA search tool for information lookup that `web_scan` and `web_execute_js` cannot reliably solve because those tools operate on current browser page state and DOM execution. The search tool must live inside the GenericAgent repo, expose a single stable tool surface to the model, and route behind that surface to automatically discovered provider implementations.

</domain>

<decisions>
## Implementation Decisions

### Provider Plugin Boundary
- **D-01:** Search service code lives under `tools/searchserver/`.
- **D-02:** GA should discover exactly one model-visible search service tool through the existing GA tool exposure path.
- **D-03:** Provider count must not leak into the model-visible tool list. Future providers are implementation modules behind the one search tool.
- **D-04:** Future search providers should only need to implement the concrete service API call to become discoverable.

### Tool Input And Result Contract
- **D-05:** The model-facing tool input is only the search keyword/query.
- **D-06:** Planning may define the exact success payload shape, but it must be structured and usable for follow-up reasoning. At minimum, success should identify the provider, query, and result items.

### Provider Selection And Configuration
- **D-07:** v1 should implement Tavily as the default provider.
- **D-08:** Search provider keys and full endpoint URLs are maintained in `mykey.py`.
- **D-09:** Different search services use different variable names in `mykey.py` for keys and full URL endpoints.
- **D-10:** Provider keys must support multi-key rotation. If one key cannot be used, GA tries the next key for that provider.

### Failure And Fallback Semantics
- **D-11:** Fallback across providers is allowed and required: if one provider fails, automatically try the next available search service.
- **D-12:** If all providers fail or are unavailable, return that search cannot be performed.
- **D-13:** The all-failed response must include each unavailable provider's error reason.

### Test And Smoke Scope
- **D-14:** Verification must include real provider smoke coverage, not only fake provider/unit coverage.
- **D-15:** Focused tests should cover schema presence, provider discovery, provider invocation, key fallback behavior, provider fallback behavior, and all-failed error reporting.

### the agent's Discretion
- Planner may choose exact Python class/function names and result item fields if they preserve the decisions above.
- Planner may choose whether discovery is implemented by module scanning, class registration, or a registry helper, as long as provider authors only implement the concrete provider API layer and do not edit the model-visible tool list.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Tool Dispatch And Schema
- `ga.py` — Existing `GenericAgentHandler.do_*` tool handlers and browser tool implementation.
- `agent_loop.py` — `BaseHandler.dispatch()` maps tool names to `do_<tool>()` methods and normalizes tool results.
- `agentmain.py` — Tool schema loading and agent loop wiring.
- `assets/tools_schema.json` — English model-visible tool schema.
- `assets/tools_schema_cn.json` — Chinese model-visible tool schema.

### Configuration And Packaging
- `mykey_template.py` — Local config template that should gain search provider key/URL examples if needed.
- `mykey_template_en.py` — English local config template that should gain search provider key/URL examples if needed.
- `pyproject.toml` — Dependency and Python version constraints.

### Planning Context
- `.planning/PROJECT.md` — Project boundary and core value for this phase.
- `.planning/REQUIREMENTS.md` — v1 requirements and traceability.
- `.planning/ROADMAP.md` — Phase goal, success criteria, and deferred ideas.

### Codebase Maps
- `.planning/codebase/ARCHITECTURE.md` — Existing runtime architecture, tool dispatch, and extension points.
- `.planning/codebase/INTEGRATIONS.md` — Existing integration/config patterns and secret handling.
- `.planning/codebase/STACK.md` — Python stack, test tools, and dependency layout.
- `.planning/codebase/TESTING.md` — Existing test patterns and recommended verification style.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `GenericAgentHandler.do_*` in `ga.py`: the new search tool should follow this established handler naming pattern.
- `assets/tools_schema.json` and `assets/tools_schema_cn.json`: the one search tool must be added to both schemas.
- `mykey.py` / `mykey_template*.py`: existing local configuration pattern for provider credentials and URLs.

### Established Patterns
- Tool names in schemas must match `GenericAgentHandler.do_<name>` or dispatch reports an unknown tool.
- Tool functions return structured dictionaries with `status` and error/message fields rather than raising through the agent loop.
- Optional external services are configured locally and secrets must not be committed.

### Integration Points
- Add the model-visible search tool through the existing tool schema loading path.
- Add the handler method in `ga.py` or a thin `ga.py` wrapper that delegates into `tools/searchserver/`.
- Add provider discovery and concrete provider implementation under `tools/searchserver/`.
- Add tests under `tests/` using existing lightweight fake-object patterns, plus a real Tavily smoke path gated on local config availability.

</code_context>

<specifics>
## Specific Ideas

- Default concrete provider for v1 is Tavily.
- Provider keys rotate within a provider before moving on where applicable.
- Cross-provider fallback tries the next available search service after provider failure.
- If no provider can search, return every provider failure reason in the final tool result.

</specifics>

<deferred>
## Deferred Ideas

- Advanced provider-specific search options.
- Multi-provider result merging in one successful response.

</deferred>

---

*Phase: 01-Unified extensible search tool*
*Context gathered: 2026-05-29*
