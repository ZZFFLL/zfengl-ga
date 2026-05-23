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
import { useEffect, useRef } from "react";
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
  const showFallbackBubble = activeTurn.responses.length === 0 && !activeTurn.answer.trim() && activeTurn.steps.length === 0;

  return (
    <div className="turn-timeline" aria-label="本轮执行过程">
      {activeTurn.phase && activeTurn.status === "streaming" ? <div className="turn-phase">{activeTurn.phase.label}</div> : null}
      {rounds.map((round, index) => (
        <TurnRoundView key={round.id} round={round} showSeparator={index > 0} />
      ))}
      {showFallbackBubble ? (
        <article className="message-row message-row--assistant is-streaming">
          <MessageBubble content={activeTurn.phase?.label || "正在思考..."} />
          <AssistantActions />
        </article>
      ) : null}
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
  const hasDetail = Boolean(step.detail.trim());
  const icon = readStepIcon(step);
  const statusLabel = readStepStatusLabel(step.status);
  const detailSections = splitToolDetail(step.detail);
  const elapsedLabel = readElapsedLabel(step.elapsed_ms);
  const showToolLabel = Boolean(step.tool_label && !step.title.includes(step.tool_label));

  return (
    <div className={`timeline-step timeline-step--${step.kind} timeline-step--${step.status}`}>
      <div className="timeline-dot" aria-hidden="true">
        {icon}
      </div>
      <Disclosure className="timeline-step-card">
        <Disclosure.Heading>
          <Button className="timeline-step-trigger" slot="trigger" variant="tertiary">
            <span className="timeline-step-title">{step.title}</span>
            {showToolLabel ? <span className="timeline-tool-label">{step.tool_label}</span> : null}
            {step.tool_name ? <code className="timeline-tool-name">{step.tool_name}</code> : null}
            <Chip className="timeline-step-chip" size="sm" variant="secondary">
              <Chip.Label>{statusLabel}</Chip.Label>
            </Chip>
            {elapsedLabel ? <span className="timeline-step-duration">{elapsedLabel}</span> : null}
            {hasDetail ? <Disclosure.Indicator /> : null}
          </Button>
        </Disclosure.Heading>
        {hasDetail ? (
          <Disclosure.Content>
            <Disclosure.Body className={step.kind === "thought" ? "thought-panel" : "tool-detail-panel"}>
              {detailSections.length > 0 ? (
                <div className="tool-detail-sections">
                  {detailSections.map((section) => (
                    <section className="tool-detail-section" key={section.label}>
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
      {step.error ? <p className="timeline-step-summary timeline-step-summary--error">{step.error}</p> : null}
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

function readStepStatusLabel(status: ExecutionStep["status"]) {
  if (status === "running") {
    return "进行中";
  }
  if (status === "failed") {
    return "失败";
  }
  return "已完成";
}

function displayArtifactPath(path: string) {
  return path.split(/[\\/]/).pop() || path;
}

function splitToolDetail(detail: string) {
  return detail
    .split("\n")
    .map((line) => {
      const match = line.match(/^(参数|结果|输出|错误)：([\s\S]*)$/);
      return match ? { label: match[1], content: match[2] } : null;
    })
    .filter((section): section is { label: string; content: string } => Boolean(section));
}

function readElapsedLabel(elapsedMs?: number) {
  if (typeof elapsedMs !== "number" || elapsedMs < 0) {
    return "";
  }
  return elapsedMs >= 1000 ? `${(elapsedMs / 1000).toFixed(1)}s` : `${elapsedMs}ms`;
}
