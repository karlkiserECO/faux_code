"use client";

import { useState } from "react";
import { ChevronRight, Wrench, CheckCircle2, XCircle, Globe, FileText, Terminal, Code2, Search, FolderOpen, Pencil } from "lucide-react";
import clsx from "clsx";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const ICON_MAP: Record<string, React.ReactNode> = {
  web_search: <Search size={14} />,
  web_fetch: <Globe size={14} />,
  list_dir: <FolderOpen size={14} />,
  read_file: <FileText size={14} />,
  write_file: <Pencil size={14} />,
  edit_file: <Pencil size={14} />,
  grep: <Search size={14} />,
  shell: <Terminal size={14} />,
  python: <Code2 size={14} />,
  rag_search: <Search size={14} />,
};

export type ToolEventState = {
  callId: string;
  name: string;
  step: number;
  args: any;
  result?: {
    ok: boolean;
    is_error?: boolean;
    content: string;
    data?: any;
  };
};

export default function ToolEvent({ ev }: { ev: ToolEventState }) {
  const [open, setOpen] = useState(false);
  const ok = ev.result ? !ev.result.is_error && ev.result.ok : undefined;
  const argSummary = summarizeArgs(ev.args);
  const icon = ICON_MAP[ev.name] || <Wrench size={14} />;

  return (
    <div className="border border-border rounded-md bg-background/40 my-2">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2 px-3 py-1.5 text-sm hover:bg-background/60"
      >
        <ChevronRight
          size={14}
          className={clsx("transition-transform text-muted", open && "rotate-90")}
        />
        <span
          className={clsx(
            "shrink-0 rounded p-1",
            ok === undefined ? "bg-muted/15 text-muted"
              : ok ? "bg-emerald-500/15 text-emerald-300"
              : "bg-red-500/15 text-red-300"
          )}
        >
          {icon}
        </span>
        <span className="font-medium">{ev.name}</span>
        <span className="text-muted text-xs truncate flex-1 text-left">
          {argSummary}
        </span>
        <span className="text-xs text-muted">step {ev.step + 1}</span>
        {ev.result &&
          (ok ? (
            <CheckCircle2 size={14} className="text-emerald-300" />
          ) : (
            <XCircle size={14} className="text-red-300" />
          ))}
      </button>
      {open && (
        <div className="px-3 py-2 border-t border-border space-y-2 text-sm">
          {Object.keys(ev.args || {}).length > 0 && (
            <div>
              <div className="text-xs text-muted mb-1">Arguments</div>
              <pre className="bg-card/60 rounded p-2 text-xs whitespace-pre-wrap overflow-x-auto">
                {JSON.stringify(ev.args, null, 2)}
              </pre>
            </div>
          )}
          {ev.result ? (
            <div>
              <div className="text-xs text-muted mb-1">Result</div>
              <div className="prose-faux text-[13.5px] bg-card/60 rounded p-2 overflow-x-auto">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {ev.result.content || "(no output)"}
                </ReactMarkdown>
              </div>
            </div>
          ) : (
            <div className="text-xs text-muted italic">running…</div>
          )}
        </div>
      )}
    </div>
  );
}

function summarizeArgs(args: any): string {
  if (!args || typeof args !== "object") return "";
  const keys = Object.keys(args);
  if (keys.length === 0) return "";
  return keys
    .map((k) => {
      const v = args[k];
      let s = typeof v === "string" ? v : JSON.stringify(v);
      if (s.length > 80) s = s.slice(0, 77) + "…";
      return `${k}=${s}`;
    })
    .join(" ");
}
