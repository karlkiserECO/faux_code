"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ChatMessage,
  deleteMessageAndAfter,
  generateConversationTitle,
  getConversation,
  streamChat,
} from "@/lib/api";
import { useSettingsStore } from "@/stores/settingsStore";
import MessageBubble from "./MessageBubble";
import ModelPicker from "./ModelPicker";
import ExamplePrompts from "./ExamplePrompts";
import SystemPromptPicker from "./SystemPromptPicker";
import ToolEvent, { ToolEventState } from "./ToolEvent";
import { ArrowUp, Square, Zap, Wrench } from "lucide-react";

export default function ChatView({ conversationId }: { conversationId?: string }) {
  const router = useRouter();
  const { provider, model, systemPrompt, temperature, toolsEnabled, setSystemPrompt, setToolsEnabled } =
    useSettingsStore();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [streamingText, setStreamingText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [usage, setUsage] = useState<{ input_tokens: number; output_tokens: number } | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [liveToolEvents, setLiveToolEvents] = useState<Record<string, ToolEventState>>({});
  const [liveToolOrder, setLiveToolOrder] = useState<string[]>([]);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    if (!conversationId) {
      setMessages([]);
      setUsage(null);
      return;
    }
    getConversation(conversationId)
      .then((d) => setMessages(d.messages))
      .catch(() => setMessages([]));
  }, [conversationId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingText]);

  async function runStream(history: ChatMessage[], targetConvId: string | undefined) {
    setBusy(true);
    setStreamingText("");
    setError(null);
    setLiveToolEvents({});
    setLiveToolOrder([]);
    abortRef.current = new AbortController();
    let liveText = "";
    let newConvId: string | undefined = targetConvId;
    let liveUsage: typeof usage = null;

    try {
      const stream = streamChat(
        {
          conversation_id: targetConvId ?? null,
          provider,
          model,
          messages: history,
          system_prompt: systemPrompt,
          temperature,
          enable_tools: toolsEnabled,
        },
        abortRef.current.signal
      );

      for await (const ev of stream) {
        if (ev.event === "conversation") {
          newConvId = (ev.data as any).id;
        } else if (ev.event === "delta") {
          liveText += ev.data as string;
          setStreamingText(liveText);
        } else if (ev.event === "tool_call_started") {
          const d = ev.data;
          setLiveToolEvents((prev) => ({
            ...prev,
            [d.id]: {
              callId: d.id,
              name: d.name,
              step: d.step,
              args: d.arguments,
            },
          }));
          setLiveToolOrder((prev) =>
            prev.includes(d.id) ? prev : [...prev, d.id]
          );
        } else if (ev.event === "tool_result") {
          const d = ev.data;
          setLiveToolEvents((prev) => ({
            ...prev,
            [d.id]: {
              ...(prev[d.id] || { callId: d.id, name: d.name, step: 0, args: {} }),
              result: {
                ok: d.ok,
                is_error: d.is_error,
                content: d.content,
              },
            },
          }));
        } else if (ev.event === "finish") {
          liveUsage = (ev.data as any)?.usage || null;
        } else if (ev.event === "error") {
          setError((ev.data as any).message || "stream error");
        } else if (ev.event === "done") {
          break;
        }
      }

      const finalMsg: ChatMessage = {
        role: "assistant",
        content: liveText,
        provider,
        model,
      };
      setMessages((m) => [...m, finalMsg]);
      setUsage(liveUsage);
      setStreamingText("");
      setLiveToolEvents({});
      setLiveToolOrder([]);

      if (!targetConvId && newConvId) {
        // Fire-and-forget title generation, then route to the new convo.
        generateConversationTitle(newConvId, { provider, model }).catch(() => {});
        router.replace(`/chat/${newConvId}`);
      } else if (targetConvId && history.length <= 4) {
        // Re-title after the first couple of turns.
        generateConversationTitle(targetConvId, { provider, model }).catch(() => {});
      }
    } catch (e: any) {
      if (e?.name === "AbortError") {
        // Keep partial text as the assistant message so the user can see it.
        if (liveText) {
          setMessages((m) => [
            ...m,
            { role: "assistant", content: liveText + "\n\n_(stopped)_", provider, model },
          ]);
        }
        setStreamingText("");
      } else {
        setError(e?.message || String(e));
      }
    } finally {
      setBusy(false);
      abortRef.current = null;
    }
  }

  async function send() {
    const text = input.trim();
    if (!text || busy) return;
    const userMsg: ChatMessage = { role: "user", content: text };
    const newMessages = [...messages, userMsg];
    setMessages(newMessages);
    setInput("");
    await runStream(newMessages, conversationId);
  }

  function stop() {
    if (abortRef.current) {
      abortRef.current.abort();
    }
  }

  async function regenerate() {
    if (busy || messages.length === 0) return;
    // Drop the last assistant turn, re-stream from the state before it.
    const lastAssistantIdx = [...messages].reverse().findIndex((m) => m.role === "assistant");
    if (lastAssistantIdx < 0) return;
    const idx = messages.length - 1 - lastAssistantIdx;
    const toRemove = messages[idx];
    const trimmed = messages.slice(0, idx);
    setMessages(trimmed);
    if (toRemove.id && conversationId) {
      try {
        await deleteMessageAndAfter(conversationId, toRemove.id);
      } catch {}
    }
    await runStream(trimmed, conversationId);
  }

  function startEdit(msg: ChatMessage) {
    if (!msg.id) return;
    setEditingId(msg.id);
  }

  async function applyEdit(msg: ChatMessage, newContent: string) {
    if (newContent === "__START_EDIT__") {
      startEdit(msg);
      return;
    }
    setEditingId(null);
    if (!msg.id) return;
    const idx = messages.findIndex((m) => m.id === msg.id);
    if (idx < 0) return;
    const before = messages.slice(0, idx);
    const updatedUser: ChatMessage = { ...msg, content: newContent };
    const newHistory = [...before, updatedUser];
    setMessages(newHistory);
    if (conversationId) {
      try {
        await deleteMessageAndAfter(conversationId, msg.id);
      } catch {}
    }
    await runStream(newHistory, conversationId);
  }

  function handleKey(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    } else if (e.key === "Escape" && busy) {
      stop();
    }
  }

  function usePrompt(p: string) {
    setInput(p);
    inputRef.current?.focus();
  }

  const lastAssistantIdx = (() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === "assistant") return i;
    }
    return -1;
  })();

  return (
    <div className="flex-1 flex flex-col h-screen">
      <header className="flex items-center justify-between px-4 py-3 border-b border-border">
        <div className="flex items-center gap-2 text-sm">
          <span className="text-muted">Chat</span>
          {usage && (
            <span className="flex items-center gap-1 text-[11px] text-muted px-1.5 py-0.5 rounded-md bg-card border border-border">
              <Zap size={10} className="text-accent" />
              {usage.input_tokens || 0} in / {usage.output_tokens || 0} out
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setToolsEnabled(!toolsEnabled)}
            className={`flex items-center gap-1.5 px-2 py-1 rounded-md border text-xs ${
              toolsEnabled
                ? "border-accent text-accent bg-accent/10"
                : "border-border bg-card text-muted hover:text-foreground"
            }`}
            title="When on, the assistant can call tools (web search, file ops, shell, python, RAG) inside this chat."
          >
            <Wrench size={12} />
            Tools {toolsEnabled ? "on" : "off"}
          </button>
          <SystemPromptPicker value={systemPrompt} onChange={setSystemPrompt} />
          <ModelPicker />
        </div>
      </header>

      <main className="flex-1 overflow-y-auto">
        {messages.length === 0 && !streamingText && (
          <div className="h-full flex items-center justify-center text-center px-6">
            <div className="max-w-2xl space-y-6">
              <div>
                <div className="text-3xl font-semibold mb-2">
                  faux<span className="text-accent">_</span>code
                </div>
                <div className="text-muted text-sm">
                  Multi-provider AI workbench. Pick a model up top, type a message, hit
                  Enter. Add API keys in{" "}
                  <a className="text-accent underline" href="/settings">
                    Settings
                  </a>{" "}
                  to unlock free remote providers.
                </div>
              </div>
              <ExamplePrompts onPick={usePrompt} />
            </div>
          </div>
        )}
        {messages.map((m, i) => (
          <MessageBubble
            key={m.id || i}
            message={m}
            editing={editingId === m.id && m.role === "user"}
            onEdit={
              m.role === "user"
                ? (txt) => applyEdit(m, txt)
                : undefined
            }
            onCancelEdit={() => setEditingId(null)}
            onRegenerate={
              !busy && i === lastAssistantIdx && m.role === "assistant"
                ? regenerate
                : undefined
            }
          />
        ))}
        {liveToolOrder.length > 0 && (
          <div className="px-4 py-2 space-y-1">
            {liveToolOrder.map((id) => (
              <ToolEvent key={id} ev={liveToolEvents[id]} />
            ))}
          </div>
        )}
        {streamingText && (
          <MessageBubble
            message={{ role: "assistant", content: streamingText, provider, model }}
            streaming
          />
        )}
        {error && (
          <div className="m-4 p-3 rounded-md border border-red-500/30 bg-red-500/10 text-sm text-red-300">
            {error}
          </div>
        )}
        <div ref={bottomRef} />
      </main>

      <footer className="p-3 border-t border-border bg-card/30">
        <div className="relative flex items-end gap-2 max-w-4xl mx-auto">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKey}
            placeholder={busy ? "Press Esc to stop, or wait…" : "Message faux_code…"}
            rows={Math.min(8, Math.max(1, input.split("\n").length))}
            className="flex-1 resize-none rounded-lg border border-border bg-background px-3 py-2.5 focus:outline-none focus:ring-1 focus:ring-accent placeholder:text-muted"
          />
          {busy ? (
            <button
              onClick={stop}
              className="h-10 w-10 shrink-0 flex items-center justify-center rounded-lg bg-red-500/80 text-white hover:opacity-90"
              title="Stop (Esc)"
            >
              <Square size={16} />
            </button>
          ) : (
            <button
              onClick={send}
              disabled={!input.trim()}
              className="h-10 w-10 shrink-0 flex items-center justify-center rounded-lg bg-accent text-background disabled:opacity-40 disabled:cursor-not-allowed hover:opacity-90"
              title="Send (Enter)"
            >
              <ArrowUp size={18} />
            </button>
          )}
        </div>
        <div className="text-[11px] text-muted text-center mt-2">
          {busy ? "Generating… press Esc or Stop to cancel." : "Enter to send · Shift+Enter for newline · ↑ to regenerate"}
        </div>
      </footer>
    </div>
  );
}
