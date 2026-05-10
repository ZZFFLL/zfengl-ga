import { Button, Dropdown, Select, Tooltip } from "antd";
import type { MenuProps } from "antd";
import {
  Menu,
  MessageSquareText,
  MoreHorizontal,
  PanelRight,
  PauseCircle,
  PlayCircle,
  RefreshCcw,
  RotateCcw,
  Square,
} from "lucide-react";
import type { RuntimeState } from "../../types";
import { StatusBadge } from "../app/StatusBadge";

export function TopBar({
  state,
  running,
  conversationTitle,
  onOpenSidebar,
  onCreateConversation,
  onSwitchLlm,
  onAbort,
  onRefresh,
  onReinject,
  onAutonomous,
  onOpenContinue,
  contextOpen,
  onOpenContext,
  onToggleContext,
}: {
  state: RuntimeState | null;
  running: boolean;
  conversationTitle: string;
  onOpenSidebar: () => void;
  onCreateConversation: () => void;
  onSwitchLlm: (index: number) => void;
  onAbort: () => void;
  onRefresh: () => void;
  onReinject: () => void;
  onAutonomous: (enabled: boolean) => void;
  onOpenContinue: () => void;
  contextOpen: boolean;
  onOpenContext: () => void;
  onToggleContext: () => void;
}) {
  const topMenuItems: MenuProps["items"] = [
    {
      key: "new",
      label: "新建空白会话",
      icon: <RotateCcw className="h-4 w-4" aria-hidden="true" />,
      disabled: !state?.configured || running,
      onClick: onCreateConversation,
    },
    {
      key: "refresh",
      label: "刷新状态",
      icon: <RefreshCcw className="h-4 w-4" aria-hidden="true" />,
      onClick: onRefresh,
    },
    {
      key: "reinject",
      label: "重新注入 System Prompt",
      icon: <RefreshCcw className="h-4 w-4" aria-hidden="true" />,
      disabled: !state?.configured || running,
      onClick: onReinject,
    },
    {
      key: "autonomous",
      label: state?.autonomous_enabled ? "关闭自主行动" : "开启自主行动",
      icon: state?.autonomous_enabled ? (
        <PauseCircle className="h-4 w-4" aria-hidden="true" />
      ) : (
        <PlayCircle className="h-4 w-4" aria-hidden="true" />
      ),
      disabled: !state?.configured || running,
      onClick: () => onAutonomous(!state?.autonomous_enabled),
    },
    { type: "divider" },
    {
      key: "continue",
      label: "恢复旧会话（兼容）",
      icon: <MessageSquareText className="h-4 w-4" aria-hidden="true" />,
      disabled: running,
      onClick: onOpenContinue,
    },
  ];

  return (
    <header className="ga-topbar shrink-0">
      {/*
        中文注释：桌面端做右侧面板折叠，移动端只负责打开抽屉，避免把两套交互状态混在一起。
      */}
      <div className="flex min-h-[52px] items-center gap-2.5 px-3 py-2 md:px-5">
        <Tooltip title="打开会话侧栏">
          <Button
            type="text"
            className="xl:hidden"
            aria-label="打开会话侧栏"
            icon={<Menu className="h-5 w-5" aria-hidden="true" />}
            onClick={onOpenSidebar}
          />
        </Tooltip>

        <div className="min-w-0 flex items-center gap-3">
          <div className="min-w-0">
            <div className="truncate text-[15px] font-semibold text-app-textStrong">{conversationTitle}</div>
            <div className="mt-0.5 flex min-w-0 items-center gap-2 text-xs text-app-muted">
              <span className="truncate">{running ? "任务执行中" : state?.configured ? "准备就绪" : "未配置"}</span>
            </div>
          </div>
        </div>

        <div className="ml-auto flex min-w-0 items-center gap-2">
          <div className="hidden min-h-9 min-w-0 items-center gap-2 rounded-xl border border-app-line bg-white px-2 py-1 shadow-[0_1px_0_rgba(31,41,55,0.03)] sm:flex">
            <span className="shrink-0 text-[11px] font-semibold uppercase text-app-muted">
              Model
            </span>
            <Select
              aria-label="选择当前模型"
              className="ga-model-select min-w-[168px]"
              size="small"
              variant="borderless"
              value={state?.current_llm?.index ?? 0}
              disabled={!state?.configured || running}
              options={(state?.llms ?? []).map((llm) => ({
                value: llm.index,
                label: llm.current ? `${llm.name} · 当前` : llm.name,
              }))}
              onChange={(value) => onSwitchLlm(Number(value))}
            />
          </div>

          <Tooltip title={contextOpen ? "收起上下文面板" : "打开上下文面板"}>
            <Button
              type="text"
              className="hidden xl:inline-flex"
              aria-label={contextOpen ? "收起上下文面板" : "打开上下文面板"}
              icon={<PanelRight className="h-5 w-5" aria-hidden="true" />}
              onClick={onToggleContext}
            />
          </Tooltip>

          <Tooltip title="打开上下文面板">
            <Button
              type="text"
              className="xl:hidden"
              aria-label="打开上下文面板"
              icon={<PanelRight className="h-5 w-5" aria-hidden="true" />}
              onClick={onOpenContext}
            />
          </Tooltip>

          <StatusBadge state={state} />

          {running ? (
            <Button
              type="primary"
              icon={<Square className="h-4 w-4" aria-hidden="true" />}
              onClick={onAbort}
            >
              停止任务
            </Button>
          ) : null}

          <Dropdown
            menu={{ items: topMenuItems }}
            trigger={["click"]}
            placement="bottomRight"
            overlayClassName="ga-dropdown"
          >
            <Button
              type="text"
              aria-label="更多 GA 操作"
              icon={<MoreHorizontal className="h-5 w-5" aria-hidden="true" />}
            />
          </Dropdown>
        </div>
      </div>
    </header>
  );
}
