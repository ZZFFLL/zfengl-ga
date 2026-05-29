# Roadmap: GenericAgent Unified Search Tool

## Current Milestone

Add a unified, extensible search capability to GenericAgent without changing the model-visible tool surface for each provider.

### Phase 1: Unified extensible search tool

**Goal:** Design and implement one GA search tool backed by automatically discovered provider implementations.
**Mode:** mvp
**Status:** Complete — 2026-05-29

**Success Criteria**:
1. GA exposes exactly one new model-visible search tool in both tool schema files.
2. A developer can add a provider implementation in the in-repo provider location and have it discovered without editing the core tool list.
3. The tool can run through `GenericAgentHandler.do_*` and return structured results from the selected provider.
4. Provider errors and missing-provider states return normal GA tool error payloads.
5. Focused tests verify schema presence, provider discovery, provider invocation, and failure behavior.

**Requirements:** SRCH-01, SRCH-02, SRCH-03, PROV-01, PROV-02, PROV-03, PROV-04, INTG-01, INTG-02, INTG-03
**Depends on:** Existing GA tool dispatch and tool schema loading

**Canonical refs:**
- `ga.py`
- `agent_loop.py`
- `agentmain.py`
- `assets/tools_schema.json`
- `assets/tools_schema_cn.json`
- `.planning/codebase/ARCHITECTURE.md`
- `.planning/codebase/INTEGRATIONS.md`
- `.planning/codebase/TESTING.md`

**Plans:**

Wave 1:
- `01-01-PLAN.md` — Build `tools/searchserver/` provider core, Tavily adapter, config/key rotation, provider fallback, and deterministic provider tests.

Wave 2 *(blocked on Wave 1 completion)*:
- `01-02-PLAN.md` — Expose one GA `web_search` tool through existing schema/handler dispatch, add integration tests, and add real Tavily smoke coverage.

Cross-cutting constraints:
- Keep exactly one model-visible search tool.
- Keep provider implementations under `tools/searchserver/`.
- Keep provider credentials and endpoint URLs in `mykey.py` templates with placeholders only.
- Return structured provider success and all-provider-failed error payloads.

## Deferred Ideas

- Query multiple providers and merge results in one tool call.
- Add provider-specific advanced options after at least one real provider integration shows the need.
