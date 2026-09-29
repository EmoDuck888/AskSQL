"use client";

import React, { useMemo, useState, useCallback, useLayoutEffect, useRef } from "react";
import { SubAgentIndicator } from "@/pages/SmartChat/components/SubAgentIndicator";
import { ToolCallBox } from "@/pages/SmartChat/components/ToolCallBox";
import { MarkdownContent } from "@/pages/SmartChat/components/MarkdownContent";
import { MultimodalPreview } from "@/pages/SmartChat/components/MultimodalPreview";
import type {
  SubAgent,
  ToolCall,
  ActionRequest,
  ReviewConfig,
} from "@/pages/SmartChat/types/types";
import { Message } from "@langchain/langgraph-sdk";
import { ContentBlock } from "@langchain/core/messages";
import {
  extractSubAgentContent,
  extractStringFromMessageContent,
} from "@/pages/SmartChat/utils/utils";
import { cn } from "@/lib/utils";

/** image_url block as sent to OpenAI-compatible APIs (e.g. Doubao) */
interface ImageUrlBlock {
  type: "image_url";
  image_url: { url: string };
}

/** Returns true for image_url blocks stored in message.content */
function isImageUrlBlock(block: unknown): block is ImageUrlBlock {
  if (typeof block !== "object" || block === null || !("type" in block))
    return false;
  const b = block as { type: unknown; image_url?: unknown };
  return (
    b.type === "image_url" &&
    typeof b.image_url === "object" &&
    b.image_url !== null &&
    "url" in (b.image_url as object) &&
    typeof (b.image_url as { url: unknown }).url === "string"
  );
}

/** Returns true for PDF blocks in additional_kwargs.attachments */
function isMultimodalBlock(
  block: unknown
): block is ContentBlock.Multimodal.Data {
  if (typeof block !== "object" || block === null || !("type" in block))
    return false;
  const b = block as { type: unknown; mimeType?: unknown };
  return (
    b.type === "file" &&
    typeof b.mimeType === "string" &&
    b.mimeType === "application/pdf"
  );
}

interface ChatMessageProps {
  message: Message;
  toolCalls: ToolCall[];
  isLoading?: boolean;
  isStreaming?: boolean;
  actionRequestsMap?: Map<string, ActionRequest>;
  reviewConfigsMap?: Map<string, ReviewConfig>;
  ui?: any[];
  stream?: any;
  onResumeInterrupt?: (value: any) => void;
  graphId?: string;
}

function areToolCallsEqual(prevToolCalls: ToolCall[], nextToolCalls: ToolCall[]) {
  if (prevToolCalls === nextToolCalls) return true;
  if (prevToolCalls.length !== nextToolCalls.length) return false;

  return prevToolCalls.every((toolCall, index) => {
    const nextToolCall = nextToolCalls[index];
    return (
      toolCall.id === nextToolCall.id &&
      toolCall.name === nextToolCall.name &&
      toolCall.status === nextToolCall.status &&
      toolCall.result === nextToolCall.result &&
      toolCall.args === nextToolCall.args
    );
  });
}

function areUiEntriesEqual(prevUi?: any[], nextUi?: any[]) {
  if (prevUi === nextUi) return true;
  if (!prevUi || !nextUi) return prevUi === nextUi;
  if (prevUi.length !== nextUi.length) return false;

  return prevUi.every((entry, index) => entry === nextUi[index]);
}

export const ChatMessage = React.memo<ChatMessageProps>(
  ({
    message,
    toolCalls,
    isLoading,
    isStreaming,
    actionRequestsMap,
    reviewConfigsMap,
    ui,
    stream,
    onResumeInterrupt,
    graphId,
  }) => {
    const isUser = message.type === "human";
    const isAi = message.type === "ai";
    const messageContent = extractStringFromMessageContent(message);
    const hasContent = messageContent && messageContent.trim() !== "";
    const hasToolCalls = toolCalls.length > 0;
    const isStreamingMessage = isAi && isStreaming === true;

    const messageRef = useRef<HTMLDivElement>(null);

    useLayoutEffect(() => {
      if (isStreaming && messageRef.current) {
        messageRef.current.scrollIntoView({ behavior: "auto", block: "end" });
      }
    }, [messageContent, isStreaming]);

    const subAgents = useMemo(
      () =>
        toolCalls
          .filter(
            (tc: ToolCall) =>
              tc.name === "task" &&
              tc.args["subagent_type"] &&
              tc.args["subagent_type"] !== "" &&
              tc.args["subagent_type"] !== null
          )
          .map((tc: ToolCall) => ({
            id: tc.id,
            name: tc.name,
            subAgentName: (tc.args as Record<string, unknown>)["subagent_type"] as string,
            input: tc.args,
            output: tc.result ? { result: tc.result } : undefined,
            status: tc.status,
          } as SubAgent)),
      [toolCalls]
    );

    const [expandedSubAgents, setExpandedSubAgents] = useState<Record<string, boolean>>({});
    const isSubAgentExpanded = useCallback(
      (id: string) => expandedSubAgents[id] ?? true,
      [expandedSubAgents]
    );
    const toggleSubAgent = useCallback((id: string) => {
      setExpandedSubAgents((prev) => ({
        ...prev,
        [id]: prev[id] === undefined ? false : !prev[id],
      }));
    }, []);

    // Images: image_url blocks in message.content (sent directly to LLM)
    const imageUrlBlocks = Array.isArray(message.content)
      ? (message.content as unknown[]).filter(isImageUrlBlock)
      : [];

    // PDFs: in additional_kwargs.attachments (backend parses them)
    const rawAttachments = (message.additional_kwargs as Record<string, unknown>)?.attachments;
    const pdfBlocks = Array.isArray(rawAttachments)
      ? (rawAttachments as unknown[]).reduce<ContentBlock.Multimodal.Data[]>(
          (acc, b) => { if (isMultimodalBlock(b)) acc.push(b); return acc; },
          []
        )
      : [];

    const hasAttachments = imageUrlBlocks.length > 0 || pdfBlocks.length > 0;

    return (
      <div
        className={cn("flex w-full max-w-full overflow-x-hidden", isUser && "flex-row-reverse")}
      >
        <div className={cn("min-w-0 max-w-full", isUser ? "max-w-[70%]" : "w-full")}>
          {isUser ? (
            /* ── Human message: images + PDFs + text ── */
            <div className="mt-4 flex flex-col items-end gap-2">
              {hasAttachments && (
                <div className="flex flex-wrap justify-end gap-2">
                  {/* Images: rendered from data URL directly */}
                  {imageUrlBlocks.map((block, idx) => (
                    <img
                      key={`img-${idx}`}
                      src={block.image_url.url}
                      alt={`uploaded image ${idx + 1}`}
                      className="h-16 w-16 rounded-md object-cover"
                    />
                  ))}
                  {/* PDFs: rendered via MultimodalPreview */}
                  {pdfBlocks.map((block, idx) => (
                    <MultimodalPreview key={`pdf-${idx}`} block={block} size="md" />
                  ))}
                </div>
              )}
              {hasContent && (
                <div
                  className="overflow-hidden break-words rounded-sm rounded-br-none border border-border px-3 py-2 text-sm font-normal leading-[150%] text-foreground"
                  style={{ backgroundColor: "var(--color-user-message-bg)" }}
                >
                  <p className="m-0 whitespace-pre-wrap break-words text-sm leading-relaxed">
                    {messageContent}
                  </p>
                </div>
              )}
            </div>
          ) : (
            /* ── AI message ── */
            hasContent && (
              <div ref={messageRef} className={cn("relative flex items-end gap-0")}>
                <div className="mt-4 overflow-hidden break-words text-sm font-normal leading-[150%] text-foreground">
                  <MarkdownContent
                    content={messageContent}
                    streaming={isStreamingMessage}
                  />
                </div>
              </div>
            )
          )}
          {hasToolCalls && (
            <div className="mt-4 flex w-full flex-col">
              {toolCalls.map((toolCall: ToolCall) => {
                if (toolCall.name === "task") return null;
                const toolCallGenUiComponent =
                  ui && ui.length > 0
                    ? ui.find((u) => u.metadata?.tool_call_id === toolCall.id)
                    : undefined;
                const actionRequest = actionRequestsMap?.get(toolCall.name);
                const reviewConfig = reviewConfigsMap?.get(toolCall.name);
                return (
                  <ToolCallBox
                    key={toolCall.id}
                    toolCall={toolCall}
                    uiComponent={toolCallGenUiComponent}
                    stream={stream}
                    graphId={graphId}
                    actionRequest={actionRequest}
                    reviewConfig={reviewConfig}
                    onResume={onResumeInterrupt}
                    isLoading={isLoading}
                  />
                );
              })}
            </div>
          )}
          {!isUser && subAgents.length > 0 && (
            <div className="flex w-fit max-w-full flex-col gap-4">
              {subAgents.map((subAgent) => (
                <div key={subAgent.id} className="flex w-full flex-col gap-2">
                  <div className="flex items-end gap-2">
                    <div className="w-[calc(100%-100px)]">
                      <SubAgentIndicator
                        subAgent={subAgent}
                        onClick={() => toggleSubAgent(subAgent.id)}
                        isExpanded={isSubAgentExpanded(subAgent.id)}
                      />
                    </div>
                  </div>
                  {isSubAgentExpanded(subAgent.id) && (
                    <div className="w-full max-w-full">
                      <div className="bg-surface rounded-md border border-border p-4">
                        <h4 className="text-primary/70 mb-2 text-xs font-semibold uppercase tracking-wider">
                          输入
                        </h4>
                        <div className="mb-4">
                          <MarkdownContent content={extractSubAgentContent(subAgent.input)} />
                        </div>
                        {subAgent.output && (
                          <>
                            <h4 className="text-primary/70 mb-2 text-xs font-semibold uppercase tracking-wider">
                              输出
                            </h4>
                            <MarkdownContent content={extractSubAgentContent(subAgent.output)} />
                          </>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    );
  },
  (prevProps, nextProps) => {
    const isSameMessage = prevProps.message === nextProps.message;
    const isSameToolCalls = areToolCallsEqual(
      prevProps.toolCalls,
      nextProps.toolCalls
    );
    const isSameUi = areUiEntriesEqual(prevProps.ui, nextProps.ui);
    const isSameInterruptMaps =
      prevProps.actionRequestsMap === nextProps.actionRequestsMap &&
      prevProps.reviewConfigsMap === nextProps.reviewConfigsMap;

    const isSameLastMessageState =
      prevProps.stream === nextProps.stream &&
      prevProps.onResumeInterrupt === nextProps.onResumeInterrupt &&
      prevProps.graphId === nextProps.graphId &&
      prevProps.isLoading === nextProps.isLoading &&
      prevProps.isStreaming === nextProps.isStreaming;

    return (
      isSameMessage &&
      isSameToolCalls &&
      isSameUi &&
      isSameInterruptMaps &&
      isSameLastMessageState
    );
  }
);

ChatMessage.displayName = "ChatMessage";

