export type WorkbenchLayoutPreference = {
  sidebar: number;
  main: number;
  inspector: number;
};

export const WORKBENCH_LAYOUT_STORAGE_KEY = "genericagent.webui.workbench.layout.v1";

export const DEFAULT_WORKBENCH_LAYOUT: WorkbenchLayoutPreference = {
  sidebar: 18,
  main: 72,
  inspector: 28,
};

const SIDEBAR_MIN = 12;
const SIDEBAR_MAX = 28;
const INSPECTOR_MIN = 20;
const INSPECTOR_MAX = 36;

export type WorkbenchLayoutStorage = Pick<Storage, "getItem" | "setItem">;

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}

function numeric(value: unknown, fallback: number) {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

export function clampWorkbenchLayout(
  value: Partial<WorkbenchLayoutPreference>,
): WorkbenchLayoutPreference {
  const sidebar = clamp(numeric(value.sidebar, DEFAULT_WORKBENCH_LAYOUT.sidebar), SIDEBAR_MIN, SIDEBAR_MAX);
  const inspector = clamp(
    numeric(value.inspector, DEFAULT_WORKBENCH_LAYOUT.inspector),
    INSPECTOR_MIN,
    INSPECTOR_MAX,
  );
  return {
    sidebar,
    main: 100 - inspector,
    inspector,
  };
}

export function readWorkbenchLayoutPreference(
  storage: WorkbenchLayoutStorage | undefined,
): WorkbenchLayoutPreference {
  if (!storage) return DEFAULT_WORKBENCH_LAYOUT;
  try {
    const raw = storage.getItem(WORKBENCH_LAYOUT_STORAGE_KEY);
    if (!raw) return DEFAULT_WORKBENCH_LAYOUT;
    return clampWorkbenchLayout(JSON.parse(raw));
  } catch {
    return DEFAULT_WORKBENCH_LAYOUT;
  }
}

export function writeWorkbenchLayoutPreference(
  storage: WorkbenchLayoutStorage | undefined,
  layout: WorkbenchLayoutPreference,
) {
  if (!storage) return;
  storage.setItem(WORKBENCH_LAYOUT_STORAGE_KEY, JSON.stringify(clampWorkbenchLayout(layout)));
}

export function nextWorkbenchLayoutFromSidebarResize(
  current: WorkbenchLayoutPreference,
  sizes: number[],
): WorkbenchLayoutPreference {
  const total = sizes.reduce((sum, size) => sum + Math.max(0, size), 0);
  if (total <= 0) return current;
  return clampWorkbenchLayout({
    ...current,
    sidebar: (Math.max(0, sizes[0] ?? 0) / total) * 100,
  });
}

export function nextWorkbenchLayoutFromInspectorResize(
  current: WorkbenchLayoutPreference,
  sizes: number[],
): WorkbenchLayoutPreference {
  const total = sizes.reduce((sum, size) => sum + Math.max(0, size), 0);
  if (total <= 0) return current;
  const inspector = (Math.max(0, sizes[1] ?? 0) / total) * 100;
  return clampWorkbenchLayout({
    ...current,
    main: 100 - inspector,
    inspector,
  });
}
