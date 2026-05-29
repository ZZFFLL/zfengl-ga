---
phase: "01"
slug: "unified-extensible-search-tool"
status: approved
nyquist_compliant: true
wave_0_complete: true
created: "2026-05-29"
updated: "2026-05-29"
---

# Phase 01 - Validation Strategy

Per-phase validation contract for feedback sampling during execution.

## Test Infrastructure

| Property | Value |
|----------|-------|
| Framework | pytest |
| Config file | `pyproject.toml` |
| Quick run command | `python -m pytest tests/test_searchserver.py tests/test_search_tool_integration.py -q` |
| Full suite command | `python -m pytest tests/test_searchserver.py tests/test_search_tool_integration.py tests/test_searchserver_smoke.py -q` |
| Compile check | `python -m py_compile ga.py mykey_template.py mykey_template_en.py tools/searchserver/__init__.py tools/searchserver/base.py tools/searchserver/config.py tools/searchserver/registry.py tools/searchserver/providers/__init__.py tools/searchserver/providers/tavily.py` |
| Whitespace check | `git diff --check` |
| Estimated runtime | ~3 seconds without network smoke; ~5 seconds with configured Tavily smoke |

## Sampling Rate

- After provider-layer edits: run `python -m pytest tests/test_searchserver.py -q`.
- After handler/schema edits: run `python -m pytest tests/test_search_tool_integration.py -q`.
- After any search behavior change: run the quick command plus compile check.
- Before phase sign-off: run the full suite command and `git diff --check`.
- Max feedback latency: under 10 seconds in the current workspace.

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 01-01-01 | 01-01 | 1 | PROV-01 | N/A | Provider count does not create more model-visible tools | unit | `python -m pytest tests/test_search_tool_integration.py::test_tool_schemas_expose_exactly_one_provider_neutral_search_tool -q` | yes | green |
| 01-01-02 | 01-01 | 1 | PROV-02 | N/A | Provider implementations are discovered behind bounded registry code | unit | `python -m pytest tests/test_searchserver.py::test_registry_build_providers_supports_default_and_explicit_selection -q` | yes | green |
| 01-01-03 | 01-01 | 1 | PROV-03 | N/A | Default discovery and explicit provider selection both work | unit | `python -m pytest tests/test_searchserver.py::test_registry_build_providers_supports_default_and_explicit_selection -q` | yes | green |
| 01-01-04 | 01-01 | 1 | PROV-04 | N/A | Provider failures become structured errors, not agent-loop crashes | unit | `python -m pytest tests/test_searchserver.py::test_search_reports_all_provider_errors_when_all_fail tests/test_searchserver.py::test_search_reports_discovery_errors_as_all_failed_payload -q` | yes | green |
| 01-01-05 | 01-01 | 1 | SRCH-03 | N/A | Success payload has status, provider, query, and result items | unit | `python -m pytest tests/test_searchserver.py::test_tavily_provider_rotates_keys_and_normalizes_results -q` | yes | green |
| 01-01-06 | 01-01 | 1 | INTG-03 | N/A | Provider fallback, key rotation, and error reporting are covered | unit | `python -m pytest tests/test_searchserver.py -q` | yes | green |
| 01-02-01 | 01-02 | 2 | SRCH-01 | N/A | GA exposes one search tool for external search tasks | unit | `python -m pytest tests/test_search_tool_integration.py::test_tool_schemas_expose_exactly_one_provider_neutral_search_tool -q` | yes | green |
| 01-02-02 | 01-02 | 2 | SRCH-02 | N/A | English and Chinese schemas stay in parity | unit | `python -m pytest tests/test_search_tool_integration.py::test_tool_schemas_expose_exactly_one_provider_neutral_search_tool -q` | yes | green |
| 01-02-03 | 01-02 | 2 | INTG-01 | N/A | `BaseHandler.dispatch()` reaches `GenericAgentHandler.do_web_search()` | unit | `python -m pytest tests/test_search_tool_integration.py::test_web_search_dispatch_forwards_structured_success -q` | yes | green |
| 01-02-04 | 01-02 | 2 | INTG-02 | N/A | Search complements browser tools without changing their schemas | unit | `python -m pytest tests/test_search_tool_integration.py::test_tool_schemas_expose_exactly_one_provider_neutral_search_tool -q` | yes | green |
| 01-02-05 | 01-02 | 2 | INTG-03 | N/A | Handler forwards success, alias, malformed input, and all-failed payloads | unit | `python -m pytest tests/test_search_tool_integration.py -q` | yes | green |
| 01-02-06 | 01-02 | 2 | SRCH-03 / PROV-04 | N/A | Real Tavily path works when configured and does not print secrets | smoke | `python -m pytest tests/test_searchserver_smoke.py -q -rs` | yes | green |

## Wave 0 Requirements

Existing infrastructure covers all Phase 01 requirements.

Validation audit added one deterministic provider-registry test:

- `tests/test_searchserver.py::test_registry_build_providers_supports_default_and_explicit_selection`

## Manual-Only Verifications

All Phase 01 behaviors have automated verification.

## Validation Audit 2026-05-29

| Metric | Count |
|--------|-------|
| Gaps found | 1 |
| Resolved | 1 |
| Escalated | 0 |

Resolved gap:

- PROV-02 / PROV-03 lacked an explicit offline test for multiple discovered providers plus explicit provider selection. Added `test_registry_build_providers_supports_default_and_explicit_selection`.

## Latest Verification Run

- `python -m py_compile ga.py mykey_template.py mykey_template_en.py tools/searchserver/__init__.py tools/searchserver/base.py tools/searchserver/config.py tools/searchserver/registry.py tools/searchserver/providers/__init__.py tools/searchserver/providers/tavily.py` -> passed.
- `python -m pytest tests/test_searchserver.py tests/test_search_tool_integration.py -q` -> 13 passed.
- `python -m pytest tests/test_searchserver_smoke.py -q -rs` -> 1 passed.
- `git diff --check` -> passed.

## Validation Sign-Off

- [x] All tasks have automated verify coverage or an existing test dependency.
- [x] Sampling continuity: no 3 consecutive tasks without automated verify.
- [x] Wave 0 covers all missing references.
- [x] No watch-mode flags.
- [x] Feedback latency < 10 seconds for offline checks.
- [x] `nyquist_compliant: true` set in frontmatter.

Approval: approved 2026-05-29
