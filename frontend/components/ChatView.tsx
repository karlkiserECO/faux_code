"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ChatMessage,
  getConversation,
  streamChat,
} from "@/lib/api";
import { useSettingsStore } from "@/stores/settingsStore";
import MessageBubble from "./MessageBubble";
import ModelPicker from "./ModelPicker";
import { ArrowUp, Square } from "lucide-react";

export default function ChatView({ conversationId }: { conversationId?: string }) {
  const router = useRouter();
  const { provider, model, systemPrompt, temperature } = useSettingsStore();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [streamingText, setStreamingText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (!conversationId) {
      setMessages([]);
      return;
    }
    getConversation(conversationId)
      .then((d) => setMessages(d.messages))
      .catch(() => setMessages([]));
  }, [conversationId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingText]);

  async function send() {
    const text = input.trim();
    if (!text || busy) return;
    setError(null);
    const userMsg: ChatMessage = { role: "user", content: text };
    const newMessages = [...messages, userMsg];
    setMessages(newMessages);
    setInput("");
    setBusy(true);
    setStreamingText("");

    let liveText = "";
    let newConvId: string | undefined = conversationId;

    try {
      const stream = streamChat({
        conversation_id: conversationId ?? null,
        provider,
        model,
        messages: newMessages,
        system_prompt: systemPrompt,
        temperature,
      });

      for await (const ev of stream) {
        if (ev.event === "conversation") {
          newConvId = (ev.data as any).id;
        } else if (ev.event === "delta") {
          liveText += ev.data as string;
          setStreamingText(liveText);
        } else if (ev.event === "finish") {
          /* nothing */
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
      setStreamingText("");

      if (!conversationId && newConvId) {
        router.replace(`/chat/${newConvId}`);
      }
    } catch (e: any) {
      setError(e?.message || String(e));
    } finally {
      setBusy(false);
      abortRef.current = null;
    }
  }

  function handleKey(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }

  return (
    <div className="flex-1 flex flex-col h-screen">
      <header className="flex items-center justify-between px-4 py-3 border-b border-border">
        <div className="text-sm text-muted">Chat</div>
        <ModelPicker />
      </header>

      <main className="flex-1 overflow-y-auto">
        {messages.length === 0 && !streamingText && (
          <div className="h-full flex items-center justify-center text-center px-6">
            <div>
              <div className="text-2xl font-semibold mb-2">
                faux<span className="text-accent">_</span>code
              </div>
              <div className="text-muted max-w-md text-sm">
                Multi-provider AI chat + agentic coding workbench. Pick a model in the
                top-right, type a message, hit Enter. Add API keys in{" "}
                <a className="text-accent underline" href="/settings">
                  Settings
                </a>{" "}
                to unlock free remote providers.
              </div>
            </div>
          </div>
        )}
        {messages.map((m, i) => (
          <MessageBubble key={i} message={m} />
        ))}
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
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKey}
            placeholder="Message faux_code…"
            rows={Math.min(8, Math.max(1, input.split("\n").length))}
            className="flex-1 resize-none rounded-lg border border-border bg-background px-3 py-2.5 focus:outline-none focus:ring-1 focus:ring-accent placeholder:text-muted"
          />
          <button
            onClick={send}
            disabled={busy || !input.trim()}
            className="h-10 w-10 shrink-0 flex items-center justify-center rounded-lg bg-accent text-background disabled:opacity-40 disabled:cursor-not-allowed hover:opacity-90"
            title="Send"
          >
            {busy ? <Square size={16} /> : <ArrowUp size={18} />}
          </button>
        </div>
        <div className="text-[11px] text-muted text-center mt-2">
          {busy ? "Generating…" : "Enter to send, Shift+Enter for newline."}
        </div>
      </footer>
    </div>
  );
}
