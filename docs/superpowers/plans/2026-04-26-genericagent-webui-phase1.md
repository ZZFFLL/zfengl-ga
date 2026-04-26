# GenericAgent WebUI Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an optional Vite/React WebUI for GenericAgent that preserves the current Streamlit phase-1 behavior.

**Architecture:** Add a local Python bridge server that owns `GeneraticAgent` integration and exposes JSON/SSE endpoints. Add a Vite React TypeScript app under `frontends/webui/` that renders the light Agent operations console and calls the bridge. Keep the existing Streamlit UI as the default path while adding an explicit `launch.pyw --webui` mode.

**Tech Stack:** Python standard library HTTP server, React, TypeScript, Vite, Tailwind CSS, lucide-react.

---

## File Structure

- Create `frontends/webui_server.py`: local API/static server, task registry, SSE streaming, command handling, and optional real `GeneraticAgent` startup.
- Create `tests/test_webui_server.py`: unit tests for execution-log parsing, bridge task lifecycle, `/new`, `/continue`, LLM switching, reinjection, and pet/autonomous controls with fake agents.
- Modify `launch.pyw`: add `--webui` and start the new server only when that flag is present.
- Modify `.gitignore`: ignore `frontends/webui/node_modules/` while keeping frontend source trackable.
- Create `frontends/webui/package.json`, `index.html`, `vite.config.ts`, `tsconfig*.json`, `tailwind.config.ts`, `postcss.config.js`.
- Create `frontends/webui/src/`: React app, API client, types, and CSS.

## Task 1: Backend Bridge Tests

**Files:**
- Create: `tests/test_webui_server.py`
- Later implementation: `frontends/webui_server.py`

- [ ] **Step 1: Write failing tests for backend bridge behavior**

Create `tests/test_webui_server.py` with fake agents and these test cases:

```python
import queue
import unittest

from frontends.webui_server import (
    WebUITaskManager,
    build_state,
    parse_execution_log,
)


class FakeBackend:
    def __init__(self):
        self.history = ["existing"]


class FakeClient:
    def __init__(self, name):
        self.backend = FakeBackend()
        self.last_tools = "cached"
        self.name = name


class FakeAgent:
    def __init__(self):
        self.llm_no = 0
        self.llmclients = [FakeClient("primary"), FakeClient("backup")]
        self.llmclient = self.llmclients[0]
        self.history = ["old"]
        self.handler = object()
        self.is_running = False
        self.aborted = False
        self.pet_requests = []
        self.tasks = []

    def list_llms(self):
        return [(i, f"Fake/{client.name}", i == self.llm_no) for i, client in enumerate(self.llmclients)]

    def get_llm_name(self):
        return f"Fake/{self.llmclients[self.llm_no].name}"

    def next_llm(self, n=-1):
        self.llm_no = ((self.llm_no + 1) if n < 0 else n) % len(self.llmclients)
        self.llmclient = self.llmclients[self.llm_no]
        self.llmclient.last_tools = ""

    def abort(self):
        self.aborted = True
        self.is_running = False

    def put_task(self, query, source="user", images=None):
        output = queue.Queue()
        self.tasks.append((query, source, images or [], output))
        return output
```

The tests should assert:

- `parse_execution_log()` splits `LLM Running (Turn n)` content and extracts `<summary>` first-line titles.
- `WebUITaskManager.start_chat()` creates a running task and returns a `task_id`.
- `WebUITaskManager.drain_task()` turns `next` queue items into stream events and finalizes on `done`.
- `build_state()` reports LLM list, current LLM, running status, autonomous flag, and last reply time.
- `switch_llm()`, `abort()`, `reinject()`, `set_autonomous()`, and `send_pet_request()` delegate to the fake agent.
- `reset_conversation()` clears fake agent visible state.

- [ ] **Step 2: Verify tests fail**

Run:

```powershell
py -3 -m unittest tests.test_webui_server -v
```

Expected: import failure because `frontends.webui_server` does not exist.

## Task 2: Backend Bridge Implementation

**Files:**
- Create: `frontends/webui_server.py`
- Test: `tests/test_webui_server.py`

- [ ] **Step 1: Implement backend bridge**

Create `frontends/webui_server.py` with:

- `parse_execution_log(text)`
- `build_state(agent, manager)`
- `WebUITaskManager`
- lightweight HTTP handler for `/api/state`, `/api/chat`, `/api/chat/{id}/stream`, `/api/abort`, `/api/llm`, `/api/reinject`, `/api/new`, `/api/continue`, `/api/autonomous`, `/api/pet`
- static serving from `frontends/webui/dist` if present
- a CLI entry point accepting `--host`, `--port`, and `--dev-url`

- [ ] **Step 2: Verify backend tests pass**

Run:

```powershell
py -3 -m unittest tests.test_webui_server -v
```

Expected: all tests in `tests.test_webui_server` pass.

## Task 3: Frontend App Scaffold

**Files:**
- Create: `frontends/webui/package.json`
- Create: `frontends/webui/index.html`
- Create: `frontends/webui/vite.config.ts`
- Create: `frontends/webui/tsconfig.json`
- Create: `frontends/webui/tsconfig.node.json`
- Create: `frontends/webui/tailwind.config.ts`
- Create: `frontends/webui/postcss.config.js`
- Create: `frontends/webui/src/main.tsx`
- Create: `frontends/webui/src/App.tsx`
- Create: `frontends/webui/src/api.ts`
- Create: `frontends/webui/src/types.ts`
- Create: `frontends/webui/src/styles.css`
- Modify: `.gitignore`

- [ ] **Step 1: Add frontend scaffold**

Add Vite React TypeScript files with Tailwind and lucide-react. Keep dependencies minimal.

- [ ] **Step 2: Implement API client**

Implement:

- `fetchState()`
- `startChat(prompt)`
- `streamTask(taskId, handlers)`
- `abortTask()`
- `switchLlm(index)`
- `reinject()`
- `resetConversation()`
- `continueConversation(command)`
- `setAutonomous(enabled)`
- `startPet()`

- [ ] **Step 3: Build the React operations console**

Implement:

- adaptive layout
- left controls
- center chat
- right execution log
- drawers for narrow screens
- hidden `#last-reply-time`
- LLM missing configuration error state

- [ ] **Step 4: Install and build**

Run:

```powershell
npm install --prefix frontends/webui
npm run build --prefix frontends/webui
```

Expected: Vite build succeeds and outputs `frontends/webui/dist`.

## Task 4: Launch Integration

**Files:**
- Modify: `launch.pyw`
- Test: manual launch checks

- [ ] **Step 1: Add optional `--webui` mode**

Modify `launch.pyw` so default behavior stays Streamlit, and `--webui` starts `frontends/webui_server.py`.

- [ ] **Step 2: Verify default launch command path is unchanged**

Inspect the command-building code and ensure the default still uses:

```text
python -m streamlit run frontends/stapp.py
```

- [ ] **Step 3: Verify WebUI launch starts a local server**

Run:

```powershell
py -3 frontends/webui_server.py --port 18601
```

Expected: process starts and serves `/api/state`.

## Task 5: Verification and Commit

**Files:**
- All files touched above

- [ ] **Step 1: Run Python tests**

Run:

```powershell
py -3 -m unittest tests.test_webui_server -v
```

Expected: pass.

- [ ] **Step 2: Run frontend build**

Run:

```powershell
npm run build --prefix frontends/webui
```

Expected: pass.

- [ ] **Step 3: Check git status**

Run:

```powershell
git -c safe.directory=E:/zfengl-ai-project/GenericAgent status --short
```

Expected: only intended WebUI files, plan/spec changes, and pre-existing unrelated untracked files appear.

- [ ] **Step 4: Commit intended files**

Stage only WebUI implementation files and docs.

```powershell
git -c safe.directory=E:/zfengl-ai-project/GenericAgent add -- .gitignore launch.pyw frontends/webui_server.py frontends/webui tests/test_webui_server.py docs/superpowers/plans/2026-04-26-genericagent-webui-phase1.md
git -c safe.directory=E:/zfengl-ai-project/GenericAgent diff --cached --name-status
git -c safe.directory=E:/zfengl-ai-project/GenericAgent commit -m "feat: add optional webui console"
```

Expected: commit succeeds without staging unrelated existing untracked files.
