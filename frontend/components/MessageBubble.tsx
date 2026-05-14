"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism";
import clsx from "clsx";
import { Bot, User, Wrench, Copy, RotateCw, Check, Pencil, X } from "lucide-react";
import { useState } from "react";
import { ChatMessage } from "@/lib/api";

export default function MessageBubble({
  message,
  streaming,
  onRegenerate,
  onEdit,
  onCancelEdit,
  editing,
}: {
  message: ChatMessage;
  streaming?: boolean;
  onRegenerate?: () => void;
  onEdit?: (newContent: string) => void;
  onCancelEdit?: () => void;
  editing?: boolean;
}) {
  const role = message.role;
  const [copied, setCopied] = useState(false);
  const [draft, setDraft] = useState(message.content);

  async function copy() {
    try {
      await navigator.clipboard.writeText(message.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    } catch {}
  }

  function commitEdit() {
    onEdit?.(draft);
  }

  return (
    <div
      className={clsx(
        "group flex gap-3 py-4 px-4",
        role === "user" ? "" : "bg-card/40"
      )}
    >
      <div className="shrink-0 mt-1">
        {role === "user" ? (
          <div className="w-7 h-7 rounded-full bg-accent/20 text-accent flex items-center justify-center">
            <User size={16} />
          </div>
        ) : role === "tool" ? (
          <div className="w-7 h-7 rounded-full bg-yellow-500/20 text-yellow-400 flex items-center justify-center">
            <Wrench size={16} />
          </div>
        ) : (
          <div className="w-7 h-7 rounded-full bg-emerald-500/20 text-emerald-400 flex items-center justify-center">
            <Bot size={16} />
          </div>
        )}
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-xs text-muted flex items-center gap-2 mb-1">
          <span className="font-medium capitalize">{role}</span>
          {message.provider && (
            <span className="text-[10px] uppercase tracking-wider opacity-70">
              {message.provider} / {message.model}
            </span>
          )}
          {streaming && (
            <span className="text-[10px] uppercase tracking-wider text-accent">streaming…</span>
          )}
        </div>

        {editing ? (
          <div className="space-y-2">
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              rows={Math.min(12, Math.max(2, draft.split("\n").length))}
              className="w-full bg-background border border-border rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-accent"
              autoFocus
            />
            <div className="flex gap-2">
              <button
                onClick={commitEdit}
                className="px-3 py-1 rounded-md bg-accent text-background text-xs hover:opacity-90"
              >
                Save & regenerate
              </button>
              <button
                onClick={onCancelEdit}
                className="px-3 py-1 rounded-md border border-border text-xs hover:bg-background"
              >
                <X size={12} className="inline" /> Cancel
              </button>
            </div>
          </div>
        ) : role === "tool" ? (
          <ToolMessage message={message} />
        ) : (
          <div className="prose-faux text-[15px]">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                code({ inline, className, children, ...props }: any) {
                  const match = /language-(\w+)/.exec(className || "");
                  if (inline) {
                    return (
                      <code className={className} {...props}>
                        {children}
                      </code>
                    );
                  }
                  return (
                    <CodeBlock
                      language={match?.[1] || "text"}
                      value={String(children).replace(/\n$/, "")}
                    />
                  );
                },
              }}
            >
              {message.content || (streaming ? "…" : "")}
            </ReactMarkdown>
          </div>
        )}

        {!editing && !streaming && message.content && (
          <div className="mt-1.5 flex items-center gap-1 text-[11px] text-muted opacity-0 group-hover:opacity-100 transition-opacity">
            <button
              onClick={copy}
              className="flex items-center gap-1 px-1.5 py-0.5 rounded hover:bg-background"
              title="Copy"
            >
              {copied ? <Check size={11} className="text-emerald-300" /> : <Copy size={11} />}
              {copied ? "copied" : "copy"}
            </button>
            {onRegenerate && (
              <button
                onClick={onRegenerate}
                className="flex items-center gap-1 px-1.5 py-0.5 rounded hover:bg-background"
                title="Regenerate"
              >
                <RotateCw size={11} /> regenerate
              </button>
            )}
            {onEdit && role === "user" && (
              <button
                onClick={() => {
                  setDraft(message.content);
                  onEdit("__START_EDIT__");
                }}
                className="flex items-center gap-1 px-1.5 py-0.5 rounded hover:bg-background"
                title="Edit"
              >
                <Pencil size={11} /> edit
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function CodeBlock({ language, value }: { language: string; value: string }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    } catch {}
  }
  return (
    <div className="relative group/code">
      <div className="absolute top-2 right-2 flex items-center gap-2 text-xs text-muted opacity-0 group-hover/code:opacity-100 transition-opacity">
        <span className="px-1.5 py-0.5 rounded bg-background/80">{language}</span>
        <button
          onClick={copy}
          className="px-2 py-0.5 rounded bg-background/80 hover:bg-background"
        >
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <SyntaxHighlighter
        language={language}
        style={vscDarkPlus}
        customStyle={{
          margin: 0,
          background: "rgb(var(--card))",
          border: "1px solid rgb(var(--border))",
          borderRadius: 8,
          fontSize: 13.5,
          padding: "0.85rem 1rem",
        }}
        PreTag="div"
      >
        {value}
      </SyntaxHighlighter>
    </div>
  );
}

function ToolMessage({ message }: { message: ChatMessage }) {
  return (
    <details className="rounded-md border border-border bg-background/60 px-3 py-2 text-sm">
      <summary className="cursor-pointer text-yellow-300/90">
        Tool: {message.tool_name || "(unknown)"}
      </summary>
      {message.tool_args ? (
        <pre className="mt-2 text-xs whitespace-pre-wrap text-muted">
          args: {JSON.stringify(message.tool_args, null, 2)}
        </pre>
      ) : null}
      {message.content ? (
        <pre className="mt-2 text-xs whitespace-pre-wrap">{message.content}</pre>
      ) : null}
    </details>
  );
}
