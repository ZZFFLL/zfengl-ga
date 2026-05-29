# Phase 01: Unified extensible search tool - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-29
**Phase:** 01-Unified extensible search tool
**Areas discussed:** Provider plugin boundary, Tool input and result contract, Provider selection and configuration, Failure and fallback semantics, Test and smoke scope

---

## Provider Plugin Boundary

| Option | Description | Selected |
|--------|-------------|----------|
| Provider implementations under `tools/searchserver/` | Keep search service tooling in a bounded in-repo location. | ✓ |
| Reuse GA's existing tool registration and dispatch conventions | Add one model-visible search tool through the same schema/handler path used by current tools. | ✓ |
| Expose one model-visible tool per provider | Add a separate GA tool for each provider. | |

**User's choice:** Search service tooling should live under `tools/searchserver/`. Reuse GA's current tool registration/exposure method so GA discovers exactly one search service tool.
**Notes:** The user explicitly rejected future expansion into N different search tools.

---

## Tool Input And Result Contract

| Option | Description | Selected |
|--------|-------------|----------|
| Single keyword/query argument | Keep the model-facing input minimal. | ✓ |
| Rich normalized options object | Let the tool accept advanced filters and provider-neutral options. | |
| Provider-specific arguments | Expose provider-specific API options at the model-facing layer. | |

**User's choice:** Tool input is only the search keyword/query.
**Notes:** Exact result field details can be planned later, but the result must stay structured enough for model follow-up.

---

## Provider Selection And Configuration

| Option | Description | Selected |
|--------|-------------|----------|
| Tavily first | Implement Tavily as the first default provider. | ✓ |
| Provider keys and full URLs in `mykey.py` | Keep local service credentials and endpoint URLs in existing GA local config. | ✓ |
| Multi-key rotation | Try the next configured key when the current key cannot be used. | ✓ |

**User's choice:** Default provider can be Tavily first. Future providers should only implement concrete service API calls and then be discovered. Keys and full endpoint URLs are maintained in `mykey.py` with different variable names per service.
**Notes:** Multi-key rotation is required.

---

## Failure And Fallback Semantics

| Option | Description | Selected |
|--------|-------------|----------|
| Automatic provider fallback | If one provider fails, try the next available search service. | ✓ |
| Fail fast on selected provider | Stop after the first provider failure. | |
| Return all provider errors only when every provider fails | Include each unavailable provider's reason in the final all-failed response. | ✓ |

**User's choice:** Allow fallback. One failed provider should automatically fall through to the next search service. If all are unavailable, return that search cannot be performed and include every service's error reason.
**Notes:** This applies across providers, not only across keys.

---

## Test And Smoke Scope

| Option | Description | Selected |
|--------|-------------|----------|
| Schema/discovery/unit tests only | Verify the integration without live external calls. | |
| Fake provider integration test | Use a local fake provider to verify dispatch/discovery behavior. | |
| Real provider smoke test | Exercise a real provider when local configuration is available. | ✓ |

**User's choice:** A real provider smoke test is required.
**Notes:** Fake provider tests are still useful for deterministic coverage, but not sufficient by themselves.

---

## the agent's Discretion

- Exact provider interface names and result item field names are left to planning/implementation, constrained by the locked decisions in `01-CONTEXT.md`.

## Deferred Ideas

- Advanced provider-specific search options.
- Multi-provider result merging in one successful response.
