"use client";

import { useState } from "react";
import { Sparkles, X } from "lucide-react";
import clsx from "clsx";

const PRESETS: { id: string; label: string; prompt: string }[] = [
  {
    id: "default",
    label: "Default",
    prompt:
      "You are faux_code, a helpful AI assistant running on the user's machine. Be concise, direct, and use markdown for structure when helpful.",
  },
  {
    id: "concise",
    label: "Concise",
    prompt:
      "You are a terse, expert assistant. Skip pleasantries. Lead with the answer. Use bullet points and code only when they earn their space.",
  },
  {
    id: "explain",
    label: "Patient explainer",
    prompt:
      "You are a patient teacher. Explain concepts step by step. When you show code, narrate what each block does. Prefer simple language over jargon.",
  },
  {
    id: "code",
    label: "Code-first",
    prompt:
      "You are a senior software engineer. Default to producing working code. When asked questions, show a runnable snippet and only add prose if the code alone is ambiguous. Use modern idioms.",
  },
  {
    id: "review",
    label: "Code reviewer",
    prompt:
      "You are a rigorous code reviewer. Identify bugs, security issues, edge cases, performance pitfalls, and stylistic problems. Quote the line in question. Suggest concrete fixes.",
  },
  {
    id: "sql",
    label: "SQL helper",
    prompt:
      "You are a SQL expert. Write correct, readable SQL. State the dialect you're targeting (PostgreSQL by default). When given schema, explain assumptions in one short sentence before the query.",
  },
  {
    id: "interview",
    label: "Interview practice",
    prompt:
      "You are an interviewer running a software-engineering mock interview. Ask one question at a time. After each answer, give a brief evaluation and pose a follow-up.",
  },
];

export default function SystemPromptPicker({
  value,
  onChange,
}: {
  value: string;
  onChange: (s: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const activePreset = PRESETS.find((p) => p.prompt === value);
  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="flex items-center gap-1.5 px-2 py-1 rounded-md border border-border bg-card hover:bg-background text-xs"
        title="System prompt"
      >
        <Sparkles size={12} className="text-accent" />
        <span className="text-muted">style:</span>
        <span>{activePreset?.label || "custom"}</span>
      </button>
      {open && (
        <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4">
          <div className="bg-card border border-border rounded-lg max-w-2xl w-full p-5 space-y-3 max-h-[80vh] overflow-y-auto">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Sparkles size={16} className="text-accent" />
                <span className="font-medium">System prompt</span>
              </div>
              <button onClick={() => setOpen(false)}>
                <X size={16} className="text-muted hover:text-foreground" />
              </button>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
              {PRESETS.map((p) => (
                <button
                  key={p.id}
                  onClick={() => onChange(p.prompt)}
                  className={clsx(
                    "text-left rounded-md border px-2 py-1.5 text-xs",
                    value === p.prompt
                      ? "border-accent text-accent bg-accent/10"
                      : "border-border hover:bg-background"
                  )}
                >
                  {p.label}
                </button>
              ))}
            </div>
            <textarea
              value={value}
              onChange={(e) => onChange(e.target.value)}
              rows={8}
              className="w-full bg-background border border-border rounded-md p-3 text-sm focus:outline-none focus:ring-1 focus:ring-accent"
            />
            <div className="flex justify-end">
              <button
                onClick={() => setOpen(false)}
                className="px-3 py-1.5 rounded-md bg-accent text-background hover:opacity-90 text-sm"
              >
                Done
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
