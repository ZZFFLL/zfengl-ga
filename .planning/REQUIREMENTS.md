# Requirements: GenericAgent Unified Search Tool

**Defined:** 2026-05-29
**Core Value:** GA should expose one model-facing search capability while letting developers add or swap concrete search providers behind it.

## v1 Requirements

### Search Tool Surface

- [x] **SRCH-01**: Agent can call one model-visible search tool for search tasks that browser page inspection cannot solve.
- [x] **SRCH-02**: The tool schema exists in both English and Chinese tool schema files so model routing keeps parity.
- [x] **SRCH-03**: Search results return a structured payload suitable for follow-up reasoning, including status, provider identity, query, and result items.

### Provider Extension

- [x] **PROV-01**: Developers can implement a new concrete search provider without adding another model-visible tool.
- [x] **PROV-02**: Provider implementations are automatically discovered from a bounded in-repo location.
- [x] **PROV-03**: Provider selection has a simple default path and an optional explicit override when multiple providers exist.
- [x] **PROV-04**: Provider failures are reported through the existing tool-result style instead of crashing the agent loop.

### Integration

- [x] **INTG-01**: The search tool integrates through the existing `GenericAgentHandler.do_*` dispatch pattern.
- [x] **INTG-02**: The search tool complements `web_scan` and `web_execute_js`; it does not change their browser-control semantics.
- [x] **INTG-03**: Focused tests cover provider discovery, provider invocation, error handling, and schema presence.

## v2 Requirements

### Provider Features

- **PROV-05**: Provider-specific advanced options can be exposed through a normalized options object if needed.
- **PROV-06**: Multiple providers can be queried and merged in one call if a later phase proves this is needed.

## Out of Scope

| Feature | Reason |
|---------|--------|
| One model-visible tool per provider | Conflicts with the core requirement that provider count must not expand the GA tool surface |
| Replacing browser tools | Browser tools solve a different page-control problem |
| External dependency edits | The user explicitly requires no dependency-project modifications without permission |
| Full search ranking framework | Provider APIs already rank results; v1 should keep aggregation simple |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| SRCH-01 | Phase 1 | Complete |
| SRCH-02 | Phase 1 | Complete |
| SRCH-03 | Phase 1 | Complete |
| PROV-01 | Phase 1 | Complete |
| PROV-02 | Phase 1 | Complete |
| PROV-03 | Phase 1 | Complete |
| PROV-04 | Phase 1 | Complete |
| INTG-01 | Phase 1 | Complete |
| INTG-02 | Phase 1 | Complete |
| INTG-03 | Phase 1 | Complete |
| PROV-05 | Deferred | Deferred |
| PROV-06 | Deferred | Deferred |

**Coverage:**
- v1 requirements: 10 total
- Mapped to phases: 10
- Unmapped: 0
- v2 deferred requirements: 2

---
*Requirements defined: 2026-05-29*
*Last updated: 2026-05-29 after Phase 1 execution*
