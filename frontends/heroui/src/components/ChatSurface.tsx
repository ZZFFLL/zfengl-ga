import { Button, Card, Chip, Disclosure, ScrollShadow, Tooltip } from "@heroui/react";
import {
  BookOpen,
  Bot,
  Brain,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  CircleHelp,
  Copy,
  Database,
  FileText,
  Loader2,
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
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { buildThreadItems, buildTurnRounds, type TurnRound, type TurnState } from "../state";
import type { ArtifactRecord, ExecutionStep, MessageRecord } from "../types";

type ChatSurfaceProps = {
  messages: MessageRecord[];
  timeline: ExecutionStep[];
  artifacts: ArtifactRecord[];
  activeTurn: TurnState | null;
  isLoadingMessages: boolean;
};

type ToolDetailSection = {
  kind: "input" | "output" | "error" | "detail";
  label: string;
  content: string;
};

export function ChatSurface({ messages, timeline, artifacts, activeTurn, isLoadingMessages }: ChatSurfaceProps) {
  const scrollRef = useRef<HTMLDivElement | null>(null);
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
              <MessageRow key={item.id} message={item.message} />
            ) : (
              <TurnHistory key={item.id} messages={item.messages} rounds={item.rounds} />
            ),
          )}

          {activeTurn ? (
            <ActiveTurnTimeline activeTurn={activeTurn} />
          ) : null}
        </div>
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
}: {
  messages: MessageRecord[];
  rounds: TurnRound[];
}) {
  const userMessages = messages.filter((message) => message.role === "user");
  return (
    <>
      {userMessages.map((message, index) => (
        <MessageRow key={`${message.created_at}-user-${index}`} message={message} />
      ))}
      {rounds.map((round, index) => (
        <TurnRoundView key={round.id} round={round} showSeparator={index > 0} />
      ))}
    </>
  );
}

function TurnRoundView({ round, showSeparator = false }: { round: TurnRound; showSeparator?: boolean }) {
  return (
    <section className="turn-round" aria-label="模型回复轮次">
      {showSeparator ? <div className="turn-round-separator" aria-hidden="true" /> : null}
      {round.steps.length > 0 || round.artifacts.length > 0 ? (
        <TimelineView artifacts={round.artifacts} steps={round.steps} />
      ) : null}
      {round.message ? <MessageRow message={round.message} /> : null}
    </section>
  );
}

function MessageRow({ message }: { message: MessageRecord }) {
  return (
    <article
      className={`message-row message-row--${message.role}`}
      data-message-role={message.role}
      data-user-message-anchor={message.role === "user" ? "true" : undefined}
    >
      <MessageBubble content={message.content} />
      {message.role === "assistant" ? <AssistantActions /> : null}
    </article>
  );
}

function ActiveTurnTimeline({ activeTurn }: { activeTurn: TurnState }) {
  const activeMessages: MessageRecord[] = activeTurn.responses.map((response, index) => ({
    role: "assistant",
    content: response.content,
    turn_id: activeTurn.turnId,
    response_id: response.id,
    created_at: response.created_at || `active:${index}`,
  }));
  if (activeTurn.answer.trim()) {
    activeMessages.push({
      role: "assistant",
      content: activeTurn.answer,
      turn_id: activeTurn.turnId,
      response_id: activeTurn.currentResponseId || `${activeTurn.turnId}:streaming`,
      created_at: "active:streaming",
    });
  }
  const rounds = buildTurnRounds(activeMessages, activeTurn.steps, activeTurn.artifacts);

  return (
    <div className="turn-timeline" aria-label="本轮执行过程">
      {activeTurn.phase && activeTurn.status === "streaming" ? <div className="turn-phase">{activeTurn.phase.label}</div> : null}
      {rounds.map((round, index) => (
        <TurnRoundView key={round.id} round={round} showSeparator={index > 0} />
      ))}
    </div>
  );
}

function TimelineView({ steps, artifacts }: { steps: ExecutionStep[]; artifacts: ArtifactRecord[] }) {
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
    <div className={`timeline-step timeline-step--${step.kind} timeline-step--${step.status}`}>
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
    </div>
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

function AssistantActions() {
  return (
    <div className="assistant-actions" aria-label="助手消息操作">
      <Button aria-label="复制回答" isIconOnly size="sm" variant="ghost">
        <Copy size={16} />
      </Button>
      <Button aria-label="重新生成回答" isIconOnly size="sm" variant="ghost">
        <RefreshCw size={16} />
      </Button>
    </div>
  );
}

function readStepIcon(step: ExecutionStep) {
  if (step.status === "running") {
    return <Loader2 size={14} />;
  }
  if (step.status === "failed") {
    return <XCircle size={14} />;
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

function readStepHeadline(step: ExecutionStep) {
  const title = readNonEmptyText(step.title);
  if (isModelSummaryStep(step)) {
    return readSummaryFromModelDetail(step.detail) || readNonEmptyText(step.summary) || title || "模型输出";
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

function buildToolDetailSections(step: ExecutionStep): ToolDetailSection[] {
  const sections: ToolDetailSection[] = [];
  const input = readNonEmptyText(step.input);
  const output = readNonEmptyText(step.output);
  const error = readNonEmptyText(step.error);
  const detail = readNonEmptyText(step.detail);

  if (input) {
    sections.push({ kind: "input", label: "入参", content: input });
  }
  if (output) {
    sections.push({ kind: "output", label: "结果", content: output });
  }
  if (error) {
    sections.push({ kind: "error", label: "错误", content: error });
  }
  if (step.kind === "phase" && step.default_open && detail) {
    return [{ kind: "output", label: "模型输出", content: detail }];
  }

  if (sections.length === 0) {
    const parsedSections = splitToolDetail(step.detail);
    if (parsedSections.length > 0) {
      return parsedSections;
    }
  }

  if (detail && !sections.some((section) => section.content === detail)) {
    sections.push({ kind: "detail", label: sections.length > 0 ? "过程" : "详情", content: detail });
  }

  return sections;
}

function splitToolDetail(detail: string): ToolDetailSection[] {
  return detail
    .split("\n")
    .map((line) => {
      const match = line.match(/^(参数|结果|输出|错误)：([\s\S]*)$/);
      return match ? { kind: readDetailSectionKind(match[1]), label: match[1], content: match[2] } : null;
    })
    .filter((section): section is ToolDetailSection => Boolean(section));
}

function readDetailSectionKind(label: string): ToolDetailSection["kind"] {
  if (label === "参数") {
    return "input";
  }
  if (label === "结果" || label === "输出") {
    return "output";
  }
  if (label === "错误") {
    return "error";
  }
  return "detail";
}

function readNonEmptyText(value?: string) {
  const text = value?.trim();
  return text ? text : "";
}

function readSummaryFromModelDetail(detail?: string) {
  const text = readNonEmptyText(detail);
  if (!text) {
    return "";
  }
  const match = text.match(/<summary>\s*([\s\S]*?)\s*<\/summary>/i);
  return match ? match[1].trim().replace(/\s+/g, " ") : "";
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
