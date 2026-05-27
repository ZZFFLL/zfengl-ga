import { Button, Card, Chip, Disclosure, Dropdown, Label, ScrollShadow, Tooltip } from "@heroui/react";
import {
  BookOpen,
  Bot,
  Brain,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  CircleHelp,
  Code2,
  Copy,
  Download,
  Database,
  FilePenLine,
  FileSearch,
  FileText,
  Globe,
  Loader2,
  MessageCircleQuestion,
  MessageSquareText,
  MousePointerClick,
  Paperclip,
  Power,
  Puzzle,
  RefreshCw,
  Search,
  SendToBack,
  Terminal,
  Wrench,
  XCircle,
} from "lucide-react";
import { LayoutGroup, motion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { buildThreadItems, buildTurnRounds, type TurnRound, type TurnState } from "../state";
import { buildToolDetailSections } from "../tool_details";
import type { ArtifactRecord, ExecutionStep, MessageRecord } from "../types";

type ChatSurfaceProps = {
  messages: MessageRecord[];
  timeline: ExecutionStep[];
  artifacts: ArtifactRecord[];
  activeTurn: TurnState | null;
  isLoadingMessages: boolean;
  sessionTitle: string;
  onReplayTurn: (message: MessageRecord) => void;
};

type TimelineMode = "full" | "summary";

export function ChatSurface({ messages, timeline, artifacts, activeTurn, isLoadingMessages, sessionTitle, onReplayTurn }: ChatSurfaceProps) {
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const nowTick = useNowTick(activeTurn?.status === "streaming");
  const isEmpty = messages.length === 0 && timeline.length === 0 && !activeTurn && !isLoadingMessages;
  const threadItems = buildThreadItems(messages, timeline, artifacts);
  const hasUserMessages = messages.some((message) => message.role === "user");

  useEffect(() => {
    const scrollElement = scrollRef.current;
    if (!scrollElement) {
      return;
    }
    scrollElement.scrollTo({ top: scrollElement.scrollHeight, behavior: "smooth" });
  }, [
    activeTurn?.answer,
    activeTurn?.artifacts.length,
    activeTurn?.phase?.label,
    activeTurn?.responses.length,
    activeTurn?.steps.length,
    activeTurn?.tools.length,
    artifacts.length,
    isLoadingMessages,
    messages.length,
    timeline.length,
  ]);

  function scrollToBottom() {
    const scrollElement = scrollRef.current;
    if (!scrollElement) {
      return;
    }
    scrollElement.scrollTo({ top: scrollElement.scrollHeight, behavior: "smooth" });
  }

  function scrollToUserMessage(direction: "previous" | "next") {
    const scrollElement = scrollRef.current;
    if (!scrollElement) {
      return;
    }
    const anchors = Array.from(scrollElement.querySelectorAll<HTMLElement>("[data-user-message-anchor='true']"));
    if (anchors.length === 0) {
      return;
    }
    const scrollRect = scrollElement.getBoundingClientRect();
    const anchorPositions = anchors.map((anchor) => ({
      anchor,
      top: scrollElement.scrollTop + anchor.getBoundingClientRect().top - scrollRect.top,
    }));
    const currentTop = scrollElement.scrollTop;
    const target =
      direction === "previous"
        ? [...anchorPositions].reverse().find((item) => item.top < currentTop - 80) ?? anchorPositions[0]
        : anchorPositions.find((item) => item.top > currentTop + 80) ?? anchorPositions[anchorPositions.length - 1];
    scrollElement.scrollTo({ top: Math.max(target.top - 24, 0), behavior: "smooth" });
  }

  return (
    <div className="chat-surface">
      <ScrollShadow className="conversation-scroll" ref={scrollRef}>
        {/* 只平滑块级位置变化，不对逐字流式文本做 layout 动画。 */}
        <LayoutGroup id="conversation-thread-layout">
          <div className="conversation-thread">
            {isEmpty ? (
              <Card className="empty-prompt" variant="transparent">
                <Card.Header>
                  <Card.Title>你想了解什么？</Card.Title>
                  <Card.Description>
                    输入任务、提出问题，或启动 GenericAgent 智能体流程。回答会保持居中可读，工具执行过程会随专属 bridge 持续演进。
                  </Card.Description>
                </Card.Header>
              </Card>
            ) : null}
            {isLoadingMessages ? <div className="conversation-loading">正在加载会话...</div> : null}

            {threadItems.map((item) =>
              item.type === "message" ? (
                <MessageRow key={item.id} message={item.message} onReplayTurn={onReplayTurn} sessionTitle={sessionTitle} />
              ) : (
                <TurnHistory key={item.id} messages={item.messages} onReplayTurn={onReplayTurn} rounds={item.rounds} sessionTitle={sessionTitle} />
              ),
            )}

            {activeTurn ? <ActiveTurnTimeline activeTurn={activeTurn} nowTick={nowTick} onReplayTurn={onReplayTurn} sessionTitle={sessionTitle} /> : null}
          </div>
        </LayoutGroup>
      </ScrollShadow>
      {!isEmpty ? (
        <div className="message-scroll-nav" aria-label="消息导航">
          <Tooltip delay={0}>
            <Button
              aria-label="跳到上一条用户消息"
              className="message-scroll-nav-button"
              isDisabled={!hasUserMessages}
              isIconOnly
              onPress={() => scrollToUserMessage("previous")}
              size="sm"
              variant="tertiary"
            >
              <ChevronUp size={16} />
            </Button>
            <Tooltip.Content showArrow placement="left">
              <Tooltip.Arrow />
              <p>跳到上一条用户消息</p>
            </Tooltip.Content>
          </Tooltip>
          <Tooltip delay={0}>
            <Button
              aria-label="跳到下一条用户消息"
              className="message-scroll-nav-button"
              isDisabled={!hasUserMessages}
              isIconOnly
              onPress={() => scrollToUserMessage("next")}
              size="sm"
              variant="tertiary"
            >
              <ChevronDown size={16} />
            </Button>
            <Tooltip.Content showArrow placement="left">
              <Tooltip.Arrow />
              <p>跳到下一条用户消息</p>
            </Tooltip.Content>
          </Tooltip>
          <Tooltip delay={0}>
            <Button
              aria-label="回到最新消息"
              className="message-scroll-nav-button message-scroll-nav-latest"
              isIconOnly
              onPress={scrollToBottom}
              size="sm"
              variant="secondary"
            >
              <SendToBack size={16} />
            </Button>
            <Tooltip.Content showArrow placement="left">
              <Tooltip.Arrow />
              <p>回到最新消息</p>
            </Tooltip.Content>
          </Tooltip>
        </div>
      ) : null}
    </div>
  );
}

function TurnHistory({
  messages,
  rounds,
  sessionTitle,
  onReplayTurn,
}: {
  messages: MessageRecord[];
  rounds: TurnRound[];
  sessionTitle: string;
  onReplayTurn: (message: MessageRecord) => void;
}) {
  const userMessages = messages.filter((message) => message.role === "user");
  return (
    <>
      {userMessages.map((message, index) => (
        <MessageRow key={`${message.created_at}-user-${index}`} message={message} onReplayTurn={onReplayTurn} sessionTitle={sessionTitle} />
      ))}
      {rounds.map((round, index) => (
        <TurnRoundView
          key={round.id}
          onReplayTurn={onReplayTurn}
          round={round}
          sessionTitle={sessionTitle}
          showSeparator={index > 0}
          timelineMode="summary"
        />
      ))}
    </>
  );
}

function TurnRoundView({
  round,
  showSeparator = false,
  sessionTitle,
  onReplayTurn,
  timelineMode,
}: {
  round: TurnRound;
  showSeparator?: boolean;
  sessionTitle: string;
  onReplayTurn: (message: MessageRecord) => void;
  timelineMode: TimelineMode;
}) {
  const hasTimeline = round.steps.length > 0 || round.artifacts.length > 0;
  return (
    <motion.section className="turn-round" aria-label="模型回复轮次" layout="position">
      {showSeparator ? <div className="turn-round-separator" aria-hidden="true" /> : null}
      {hasTimeline ? (
        timelineMode === "summary" ? (
          <HistoryTimelineSummary artifacts={round.artifacts} elapsedMs={round.message?.elapsed_ms} steps={round.steps} />
        ) : (
          <TimelineView artifacts={round.artifacts} steps={round.steps} />
        )
      ) : null}
      {round.message ? <MessageRow message={round.message} onReplayTurn={onReplayTurn} sessionTitle={sessionTitle} /> : null}
    </motion.section>
  );
}

function MessageRow({
  message,
  sessionTitle,
  onReplayTurn,
}: {
  message: MessageRecord;
  sessionTitle: string;
  onReplayTurn: (message: MessageRecord) => void;
}) {
  return (
    message.role === "user" ? (
      <motion.article
        animate={{ opacity: 1, scale: 1, y: 0 }}
        className="message-row message-row--user"
        data-message-role={message.role}
        data-user-message-anchor="true"
        initial={{ opacity: 0, scale: 0.985, y: 16 }}
        layout="position"
        transition={{ damping: 24, stiffness: 280, type: "spring" }}
      >
        <MessageBubble content={message.content} />
      </motion.article>
    ) : (
      <article className={`message-row message-row--${message.role}`} data-message-role={message.role}>
        {/* 助手正文保持流式渲染，不做整条消息的位移入场动画。 */}
        <MessageBubble content={message.content} />
        <AssistantActions message={message} onReplayTurn={onReplayTurn} sessionTitle={sessionTitle} />
      </article>
    )
  );
}

function ActiveTurnTimeline({
  activeTurn,
  nowTick,
  sessionTitle,
  onReplayTurn,
}: {
  activeTurn: TurnState;
  nowTick: number;
  sessionTitle: string;
  onReplayTurn: (message: MessageRecord) => void;
}) {
  const liveElapsedMs = Math.max(nowTick - Date.parse(activeTurn.startedAt), 0);
  const liveElapsedLabel = readElapsedLabel(liveElapsedMs);
  const activeMessages: MessageRecord[] = activeTurn.responses.map((response, index) => ({
    role: "assistant",
    content: response.content,
    turn_id: activeTurn.turnId,
    response_id: response.id,
    created_at: response.created_at || `active:${index}`,
    elapsed_ms: typeof response.elapsed_ms === "number" ? response.elapsed_ms : liveElapsedMs,
  }));
  if (activeTurn.answer.trim()) {
    activeMessages.push({
      role: "assistant",
      content: activeTurn.answer,
      turn_id: activeTurn.turnId,
      response_id: activeTurn.currentResponseId || `${activeTurn.turnId}:streaming`,
      created_at: "active:streaming",
      elapsed_ms: liveElapsedMs,
    });
  }
  const rounds = buildTurnRounds(activeMessages, activeTurn.steps, activeTurn.artifacts);

  return (
    <motion.div className="turn-timeline" aria-label="本轮执行过程" layout="position">
      {rounds.map((round, index) => (
        <TurnRoundView
          key={round.id}
          onReplayTurn={onReplayTurn}
          round={round}
          sessionTitle={sessionTitle}
          showSeparator={index > 0}
          timelineMode="full"
        />
      ))}
      {liveElapsedLabel ? (
        <div className="turn-phase turn-phase--footer">
          <span className="turn-phase-duration">已用时 {liveElapsedLabel}</span>
        </div>
      ) : null}
    </motion.div>
  );
}

function HistoryTimelineSummary({
  steps,
  artifacts,
  elapsedMs,
}: {
  steps: ExecutionStep[];
  artifacts: ArtifactRecord[];
  elapsedMs?: number;
}) {
  const failedCount = steps.filter((step) => step.status === "failed").length;
  const elapsedLabel = readElapsedLabel(readTimelineElapsedMs(steps, elapsedMs));
  const summaryParts = [`${steps.length} 次工具调用`];
  if (artifacts.length > 0) {
    summaryParts.push(`${artifacts.length} 个附件`);
  }
  if (elapsedLabel) {
    summaryParts.push(elapsedLabel);
  }
  if (failedCount > 0) {
    summaryParts.push(`${failedCount} 个失败`);
  }

  return (
    <Disclosure className="historical-timeline-summary">
      <Disclosure.Heading>
        <Button className="historical-timeline-summary-trigger" slot="trigger" variant="tertiary">
          <span className="historical-timeline-summary-main">
            <Wrench size={14} />
            <span>{summaryParts.join(" · ")}</span>
          </span>
          <span className="historical-timeline-summary-action">
            查看详情
            <Disclosure.Indicator />
          </span>
        </Button>
      </Disclosure.Heading>
      <Disclosure.Content>
        <Disclosure.Body className="historical-timeline-summary-body">
          <TimelineView artifacts={artifacts} steps={steps} />
        </Disclosure.Body>
      </Disclosure.Content>
    </Disclosure>
  );
}

function TimelineView({
  steps,
  artifacts,
}: {
  steps: ExecutionStep[];
  artifacts: ArtifactRecord[];
}) {
  return (
    <div className="execution-timeline" aria-label="执行过程时间线">
      {steps.map((step) => (
        <TimelineStepCard key={step.id} step={step} />
      ))}
      {artifacts.length > 0 ? (
        <div className="artifact-section">
          <strong>附件（{artifacts.length}）</strong>
          {artifacts.map((artifact) => (
            <div className="artifact-card" key={artifact.id}>
              <span className="artifact-icon" aria-hidden="true">
                <Paperclip size={15} />
              </span>
              <span>{artifact.name}</span>
              {artifact.path ? <code title={artifact.path}>{displayArtifactPath(artifact.path)}</code> : null}
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function TimelineStepCard({ step }: { step: ExecutionStep }) {
  const [isExpanded, setIsExpanded] = useState(Boolean(step.default_open && !isModelSummaryStep(step)));
  const icon = readStepIcon(step);
  const title = readStepHeadline(step);
  const statusLabel = readStepStatusLabel(step);
  const detailSections = step.kind === "thought" ? [] : buildToolDetailSections(step);
  const hasDetail = detailSections.length > 0 || Boolean(step.detail.trim());
  const elapsedLabel = readElapsedLabel(step.elapsed_ms);

  return (
    <motion.div
      animate={{ opacity: 1, scale: 1, x: 0 }}
      className={`timeline-step timeline-step--${step.kind} timeline-step--${step.status}`}
      initial={{ opacity: 0, scale: 0.985, x: -12 }}
      layout="preserve-aspect"
      transition={{ damping: 24, stiffness: 300, type: "spring" }}
      whileHover={{ scale: 1.008, x: 2 }}
    >
      <div className="timeline-dot" aria-hidden="true">
        {icon}
      </div>
      <Disclosure className="timeline-step-card" isExpanded={isExpanded} onExpandedChange={setIsExpanded}>
        <Disclosure.Heading>
          <Button className="timeline-step-trigger" slot="trigger" variant="tertiary">
            <span className="timeline-step-trigger-main">
              <span className="timeline-step-title">{title}</span>
            </span>
            <span className="timeline-step-trigger-meta">
              <Chip className="timeline-step-chip" size="sm" variant="secondary">
                <Chip.Label>{statusLabel}</Chip.Label>
              </Chip>
              {elapsedLabel ? <span className="timeline-step-duration">{elapsedLabel}</span> : null}
              {hasDetail ? <Disclosure.Indicator /> : null}
            </span>
          </Button>
        </Disclosure.Heading>
        {hasDetail ? (
          <Disclosure.Content>
            <Disclosure.Body className={step.kind === "thought" ? "thought-panel" : "tool-detail-panel"}>
              {detailSections.length > 0 ? (
                <div className="tool-detail-sections">
                  {detailSections.map((section) => (
                    <section className={`tool-detail-section tool-detail-section--${section.kind}`} key={`${section.kind}:${section.label}`}>
                      <strong>{section.label}</strong>
                      <pre>{section.content}</pre>
                    </section>
                  ))}
                </div>
              ) : (
                step.detail
              )}
            </Disclosure.Body>
          </Disclosure.Content>
        ) : null}
      </Disclosure>
    </motion.div>
  );
}

function MessageBubble({ content }: { content: string }) {
  return (
    <div className="message-bubble">
      <ReactMarkdown
        components={{
          a: ({ children, ...props }) => (
            <a {...props} rel="noreferrer" target="_blank">
              {children}
            </a>
          ),
        }}
        remarkPlugins={[remarkGfm]}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

function AssistantActions({
  message,
  sessionTitle,
  onReplayTurn,
}: {
  message: MessageRecord;
  sessionTitle: string;
  onReplayTurn: (message: MessageRecord) => void;
}) {
  return (
    <div className="assistant-actions" aria-label="助手消息操作">
      <Dropdown>
        <Dropdown.Trigger>
          <Button aria-label="导出回答" isIconOnly size="sm" variant="ghost">
            <Copy size={16} />
          </Button>
        </Dropdown.Trigger>
        <Dropdown.Popover className="assistant-actions-popover">
          <Dropdown.Menu className="assistant-actions-menu" onAction={(key) => handleAssistantExportAction(String(key), message, sessionTitle)}>
            <Dropdown.Item className="assistant-action-item" id="copy-markdown" textValue="复制为 Markdown">
              <Copy className="size-4 shrink-0 text-muted" />
              <Label>复制为 Markdown</Label>
            </Dropdown.Item>
            <Dropdown.Item className="assistant-action-item" id="download-markdown" textValue="导出为 Markdown 文件">
              <Download className="size-4 shrink-0 text-muted" />
              <Label>导出为 Markdown 文件</Label>
            </Dropdown.Item>
          </Dropdown.Menu>
        </Dropdown.Popover>
      </Dropdown>
      <Button aria-label="重新生成回答" isIconOnly onPress={() => onReplayTurn(message)} size="sm" variant="ghost">
        <RefreshCw size={16} />
      </Button>
    </div>
  );
}

async function handleAssistantExportAction(action: string, message: MessageRecord, sessionTitle: string) {
  const markdown = buildAssistantMarkdown(message, sessionTitle);
  if (action === "copy-markdown") {
    await navigator.clipboard.writeText(markdown);
    return;
  }
  if (action === "download-markdown") {
    downloadMarkdownFile(markdown, sessionTitle, message.created_at);
  }
}

function buildAssistantMarkdown(message: MessageRecord, sessionTitle: string) {
  return `# ${formatExportTitle(sessionTitle)}\n\n${message.content.trim()}\n`;
}

function formatExportTitle(sessionTitle: string) {
  const title = sessionTitle.trim();
  return title || "当前回答";
}

function downloadMarkdownFile(markdown: string, sessionTitle: string, createdAt: string) {
  const blob = new Blob([markdown], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${slugifyFilename(sessionTitle)}-${createdAt.slice(0, 19).replace(/[:T]/g, "-")}.md`;
  link.click();
  URL.revokeObjectURL(url);
}

function slugifyFilename(value: string) {
  const normalized = value.trim().replace(/[\\/:*?"<>|]+/g, "-");
  return normalized || "answer";
}

function readStepIcon(step: ExecutionStep) {
  if (step.status === "failed") {
    return <XCircle size={14} />;
  }
  const toolNameIcon = readToolNameIcon(step.tool_name);
  if (toolNameIcon) {
    return toolNameIcon;
  }
  if (step.kind === "phase") {
    return <MessageSquareText size={14} />;
  }
  if (step.status === "running") {
    return <Loader2 size={14} />;
  }
  if (step.kind === "thought") {
    return <Brain size={14} />;
  }
  if (step.kind === "search") {
    return <Search size={14} />;
  }
  if (step.kind === "read") {
    return <BookOpen size={14} />;
  }
  if (step.kind === "file") {
    return <FileText size={14} />;
  }
  if (step.kind === "command") {
    return <Terminal size={14} />;
  }
  if (step.kind === "skill") {
    return <Puzzle size={14} />;
  }
  if (step.kind === "tape") {
    return <Database size={14} />;
  }
  if (step.kind === "agent") {
    return <Bot size={14} />;
  }
  if (step.kind === "help") {
    return <CircleHelp size={14} />;
  }
  if (step.kind === "control") {
    return <Power size={14} />;
  }
  if (step.kind === "complete") {
    return <CheckCircle2 size={14} />;
  }
  return <Wrench size={14} />;
}

function readToolNameIcon(toolName?: string) {
  const normalizedToolName = normalizeToolName(toolName);
  if (!normalizedToolName) {
    return null;
  }
  if (normalizedToolName.includes("ask_user") || normalizedToolName.includes("human") || normalizedToolName.includes("intervention")) {
    return <MessageCircleQuestion size={14} />;
  }
  if (
    normalizedToolName.includes("web_scan") ||
    normalizedToolName.includes("search") ||
    normalizedToolName.includes("google") ||
    normalizedToolName.includes("bing")
  ) {
    return <Search size={14} />;
  }
  if (
    normalizedToolName.includes("browser") ||
    normalizedToolName.includes("web_action") ||
    normalizedToolName.includes("web_execute") ||
    normalizedToolName.includes("navigate") ||
    normalizedToolName.includes("page")
  ) {
    return <Globe size={14} />;
  }
  if (
    normalizedToolName.includes("click") ||
    normalizedToolName.includes("select") ||
    normalizedToolName.includes("input") ||
    normalizedToolName.includes("type")
  ) {
    return <MousePointerClick size={14} />;
  }
  if (normalizedToolName.includes("file_read") || normalizedToolName.includes("read_file") || normalizedToolName.includes("open_file")) {
    return <FileSearch size={14} />;
  }
  if (
    normalizedToolName.includes("file_write") ||
    normalizedToolName.includes("write_file") ||
    normalizedToolName.includes("edit_file") ||
    normalizedToolName.includes("patch")
  ) {
    return <FilePenLine size={14} />;
  }
  if (
    normalizedToolName.includes("python") ||
    normalizedToolName.includes("code") ||
    normalizedToolName.includes("execute") ||
    normalizedToolName.includes("eval")
  ) {
    return <Code2 size={14} />;
  }
  if (normalizedToolName.includes("shell") || normalizedToolName.includes("command") || normalizedToolName.includes("terminal")) {
    return <Terminal size={14} />;
  }
  if (normalizedToolName.includes("skill")) {
    return <Puzzle size={14} />;
  }
  if (normalizedToolName.includes("tape") || normalizedToolName.includes("memory") || normalizedToolName.includes("database")) {
    return <Database size={14} />;
  }
  if (normalizedToolName.includes("agent")) {
    return <Bot size={14} />;
  }
  return null;
}

function normalizeToolName(toolName?: string) {
  return toolName?.trim().toLowerCase().replace(/[\s-]+/g, "_") ?? "";
}

function readStepHeadline(step: ExecutionStep) {
  const title = readNonEmptyText(step.title);
  if (isModelSummaryStep(step)) {
    return readNonEmptyText(step.summary) || title || "模型输出";
  }
  return title || readNonEmptyText(step.summary) || "执行步骤";
}

function isModelSummaryStep(step: ExecutionStep) {
  return step.kind === "phase" && (Boolean(step.default_open) || readNonEmptyText(step.title) !== "模型输出完成");
}

function readStepStatusLabel(step: ExecutionStep) {
  if (step.status === "running") {
    return "进行中";
  }
  if (step.status === "failed") {
    return readNonEmptyText(step.error) ? "异常" : "失败";
  }
  return "成功";
}

function displayArtifactPath(path: string) {
  return path.split(/[\\/]/).pop() || path;
}

function readNonEmptyText(value?: string) {
  const text = value?.trim();
  return text ? text : "";
}

function readElapsedLabel(elapsedMs?: number) {
  if (typeof elapsedMs !== "number" || elapsedMs < 0) {
    return "";
  }
  if (elapsedMs >= 60000) {
    return `${(elapsedMs / 60000).toFixed(1)}m`;
  }
  return elapsedMs < 100 ? "<0.1s" : `${(elapsedMs / 1000).toFixed(1)}s`;
}

function readTimelineElapsedMs(steps: ExecutionStep[], elapsedMs?: number) {
  if (typeof elapsedMs === "number" && elapsedMs >= 0) {
    return elapsedMs;
  }
  const stepElapsedMs = steps.reduce((total, step) => total + (typeof step.elapsed_ms === "number" ? Math.max(step.elapsed_ms, 0) : 0), 0);
  return stepElapsedMs > 0 ? stepElapsedMs : undefined;
}

function useNowTick(enabled: boolean) {
  const [nowTick, setNowTick] = useState(() => Date.now());

  useEffect(() => {
    if (!enabled) {
      return;
    }
    setNowTick(Date.now());
    const timer = window.setInterval(() => {
      setNowTick(Date.now());
    }, 1000);
    return () => window.clearInterval(timer);
  }, [enabled]);

  return nowTick;
}
