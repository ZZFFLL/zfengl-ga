import test from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { pathToFileURL } from "node:url";

const moduleUrl = pathToFileURL(
  path.resolve("frontends/webui/src/state/workbench-layout-state.ts"),
).href;
const {
  DEFAULT_WORKBENCH_LAYOUT,
  WORKBENCH_LAYOUT_STORAGE_KEY,
  clampWorkbenchLayout,
  readWorkbenchLayoutPreference,
  writeWorkbenchLayoutPreference,
  nextWorkbenchLayoutFromSidebarResize,
  nextWorkbenchLayoutFromInspectorResize,
} = await import(moduleUrl);

function createMemoryStorage(initial = {}) {
  const store = new Map(Object.entries(initial));
  return {
    getItem(key) {
      return store.has(key) ? store.get(key) : null;
    },
    setItem(key, value) {
      store.set(key, String(value));
    },
    removeItem(key) {
      store.delete(key);
    },
  };
}

test("workbench layout preferences fall back to responsive defaults", () => {
  assert.deepEqual(readWorkbenchLayoutPreference(createMemoryStorage()), DEFAULT_WORKBENCH_LAYOUT);
  assert.deepEqual(readWorkbenchLayoutPreference(createMemoryStorage({ [WORKBENCH_LAYOUT_STORAGE_KEY]: "broken" })), DEFAULT_WORKBENCH_LAYOUT);
});

test("workbench layout preferences are clamped and persisted", () => {
  const storage = createMemoryStorage();
  const layout = clampWorkbenchLayout({ sidebar: 4, main: 20, inspector: 80 });

  assert.deepEqual(layout, { sidebar: 12, main: 64, inspector: 36 });

  writeWorkbenchLayoutPreference(storage, layout);
  assert.deepEqual(readWorkbenchLayoutPreference(storage), layout);
});

test("workbench layout resize helpers convert splitter sizes to percentages", () => {
  const current = DEFAULT_WORKBENCH_LAYOUT;

  assert.deepEqual(nextWorkbenchLayoutFromSidebarResize(current, [320, 1280]), {
    ...current,
    sidebar: 20,
  });
  assert.deepEqual(nextWorkbenchLayoutFromInspectorResize(current, [900, 300]), {
    ...current,
    main: 75,
    inspector: 25,
  });
});
