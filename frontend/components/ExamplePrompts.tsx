"use client";

import { Lightbulb, Code2, FileSearch, Sparkles } from "lucide-react";

const EXAMPLES: { icon: React.ReactNode; label: string; prompt: string }[] = [
  {
    icon: <Code2 size={14} />,
    label: "Explain code",
    prompt: "Explain how a Python asyncio event loop works at a high level, then show a small example.",
  },
  {
    icon: <FileSearch size={14} />,
    label: "Research",
    prompt: "What are the trade-offs between Postgres and SQLite for a self-hosted small-team app?",
  },
  {
    icon: <Sparkles size={14} />,
    label: "Brainstorm",
    prompt: "Brainstorm ten startup ideas at the intersection of AI agents and local-first software.",
  },
  {
    icon: <Lightbulb size={14} />,
    label: "Quick how-to",
    prompt: "Show me how to set up a minimal FastAPI app that streams SSE responses.",
  },
];

export default function ExamplePrompts({ onPick }: { onPick: (text: string) => void }) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-w-xl mx-auto">
      {EXAMPLES.map((e) => (
        <button
          key={e.label}
          onClick={() => onPick(e.prompt)}
          className="text-left rounded-lg border border-border bg-card hover:bg-background p-3 group"
        >
          <div className="flex items-center gap-2 text-accent text-xs uppercase tracking-wider mb-1">
            {e.icon} {e.label}
          </div>
          <div className="text-sm text-muted group-hover:text-foreground line-clamp-2">
            {e.prompt}
          </div>
        </button>
      ))}
    </div>
  );
}
