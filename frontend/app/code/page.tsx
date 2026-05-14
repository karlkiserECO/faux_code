"use client";

import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import Sidebar from "@/components/Sidebar";
import FileTree from "@/components/FileTree";
import DiffViewer from "@/components/DiffViewer";
import {
  createAgentRun,
  getWorkspaceFile,
  getWorkspaceInfo,
  saveWorkspaceFile,
  streamAgentRun,
} from "@/lib/api";
import { useSettingsStore } from "@/stores/settingsStore";
import ModelPicker from "@/components/ModelPicker";
import { FolderOpen, Save, Wand2, Square, X, FileDiff, Code2 } from "lucide-react";
import clsx from "clsx";

const Monaco = dynamic(() => import("@monaco-editor/react"), { ssr: false });

const EXT_TO_LANG: Record<string, string> = {
  ts: "typescript", tsx: "typescript", js: "javascript", jsx: "javascript",
  py: "python", rs: "rust", go: "go", java: "java",
  c: "c", cpp: "cpp", h: "c", hpp: "cpp",
  json: "json", yaml: "yaml", yml: "yaml", md: "markdown",
  html: "html", css: "css", scss: "scss",
  sh: "shell", bash: "shell", sql: "sql", toml: "ini", ini: "ini",
  dockerfile: "dockerfile",
};

type TabState = {
  path: string;
  language: string;
  content: string;       // current editor content
  saved: string;         // last saved on disk content
  baseline: string;      // pre-edit content for diff display
};

export default function CodePage() {
  const { provider, model } = useSettingsStore();
  const [root, setRoot] = useState<string>("");
  const [rootInput, setRootInput] = useState<string>("");
  const [tabs, setTabs] = useState<TabState[]>([]);
  const [activePath, setActivePath] = useState<string>("");
  const [showDiff, setShowDiff] = useState(false);
  const [saving, setSaving] = useState(false);
  const [agentPrompt, setAgentPrompt] = useState("");
  const [agentRunning, setAgentRunning] = useState(false);
  const [agentLog, setAgentLog] = useState<string[]>([]);
  const [agentRunId, setAgentRunId] = useState<string | null>(null);
  const [touchedPaths, setTouchedPaths] = useState<Set<string>>(new Set());

  useEffect(() => {
    getWorkspaceInfo()
      .then((d) => {
        setRoot(d.root);
        setRootInput(d.root);
      })
      .catch(() => {});
  }, []);

  const active = tabs.find((t) => t.path === activePath);

  async function openFile(path: string) {
    const existing = tabs.find((t) => t.path === path);
    if (existing) {
      setActivePath(path);
      setShowDiff(false);
      return;
    }
    try {
      const data = await getWorkspaceFile(path, root);
      const ext = path.split(".").pop()?.toLowerCase() || "";
      const language = EXT_TO_LANG[ext] || "plaintext";
      setTabs((prev) => [
        ...prev,
        { path, language, content: data.content, saved: data.content, baseline: data.content },
      ]);
      setActivePath(path);
      setShowDiff(false);
    } catch (e) {
      alert(`Failed to open ${path}: ${e}`);
    }
  }

  function closeTab(path: string) {
    setTabs((prev) => {
      const next = prev.filter((t) => t.path !== path);
      if (path === activePath) {
        setActivePath(next.length ? next[next.length - 1].path : "");
      }
      return next;
    });
  }

  function updateContent(path: string, content: string) {
    setTabs((prev) =>
      prev.map((t) => (t.path === path ? { ...t, content } : t))
    );
  }

  async function save() {
    if (!active) return;
    setSaving(true);
    try {
      await saveWorkspaceFile(active.path, active.content, root);
      setTabs((prev) =>
        prev.map((t) =>
          t.path === active.path ? { ...t, saved: t.content, baseline: t.content } : t
        )
      );
    } catch (e: any) {
      alert(`Save failed: ${e.message || e}`);
    } finally {
      setSaving(false);
    }
  }

  async function refreshTab(path: string) {
    try {
      const data = await getWorkspaceFile(path, root);
      setTabs((prev) =>
        prev.map((t) =>
          t.path === path
            ? { ...t, content: data.content, saved: data.content }
            : t
        )
      );
    } catch {}
  }

  function applyRoot() {
    if (rootInput && rootInput !== root) {
      setRoot(rootInput);
      setTabs([]);
      setActivePath("");
      setTouchedPaths(new Set());
    }
  }

  async function runAgentOnFile() {
    if (!agentPrompt.trim() || agentRunning) return;
    setAgentRunning(true);
    setAgentLog([]);
    setTouchedPaths(new Set());
    // Snapshot baselines for diff
    setTabs((prev) => prev.map((t) => ({ ...t, baseline: t.content })));

    try {
      const openFiles = tabs.map((t) => t.path).join(", ");
      const context = active
        ? `Open file: \`${active.path}\`${tabs.length > 1 ? ` (also open: ${openFiles})` : ""}\n\n`
        : "";
      const goal = `${context}${agentPrompt}\n\nWhen you finish, re-read any files you changed so I can verify them.`;
      const { id } = await createAgentRun({
        goal,
        provider,
        model,
        workspace: root,
        approval_mode: "auto",
        allowed_tools: [
          "list_dir", "read_file", "grep", "write_file", "edit_file",
          "shell", "python", "web_search", "web_fetch",
          "apply_patch", "git_status", "git_diff", "git_log",
        ],
        max_steps: 25,
      });
      setAgentRunId(id);
      let final = "";
      const localTouched = new Set<string>();
      for await (const ev of streamAgentRun(id)) {
        if (ev.event === "tool_call") {
          setAgentLog((l) => [...l, `→ ${ev.data.name}(${shortArgs(ev.data.arguments)})`]);
          const path = ev.data.arguments?.path;
          if (path && (ev.data.name === "write_file" || ev.data.name === "edit_file")) {
            localTouched.add(path);
          }
        } else if (ev.event === "tool_result") {
          setAgentLog((l) => [
            ...l,
            `${ev.data.is_error ? "✗" : "✓"} ${ev.data.name}${ev.data.is_error ? ": error" : ""}`,
          ]);
        } else if (ev.event === "finished") {
          final = ev.data.final || "";
          setAgentLog((l) => [...l, `\n[completed in ${ev.data.steps_taken} step(s)]`]);
        } else if (ev.event === "error") {
          setAgentLog((l) => [...l, `[error] ${ev.data.message}`]);
        } else if (ev.event === "done") {
          break;
        }
      }
      if (final) setAgentLog((l) => [...l, "", "Summary:", final]);
      // Refresh any touched tabs that are currently open.
      setTouchedPaths(localTouched);
      for (const p of localTouched) {
        if (tabs.find((t) => t.path === p)) await refreshTab(p);
      }
    } catch (e: any) {
      setAgentLog((l) => [...l, `Error: ${e?.message || e}`]);
    } finally {
      setAgentRunning(false);
      setAgentRunId(null);
    }
  }

  const dirty = active ? active.content !== active.saved : false;
  const hasDiff = active ? active.content !== active.baseline : false;

  return (
    <div className="flex h-screen">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0">
        <header className="flex items-center gap-2 px-4 py-2 border-b border-border">
          <FolderOpen size={14} className="text-muted" />
          <input
            value={rootInput}
            onChange={(e) => setRootInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && applyRoot()}
            placeholder="Workspace root path (absolute)"
            className="flex-1 bg-background border border-border rounded-md px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-accent"
          />
          <button
            onClick={applyRoot}
            className="px-3 py-1 rounded-md border border-border hover:bg-background text-sm"
          >
            Open
          </button>
          <div className="ml-2">
            <ModelPicker />
          </div>
        </header>
        <div className="flex-1 grid grid-cols-[260px_1fr_380px] min-h-0">
          <aside className="border-r border-border bg-card/30 min-h-0">
            {root ? (
              <FileTree root={root} activePath={activePath} onSelect={openFile} />
            ) : (
              <div className="p-3 text-xs text-muted">No workspace.</div>
            )}
          </aside>
          <section className="min-w-0 flex flex-col">
            {/* Tab bar */}
            <div className="flex items-center border-b border-border bg-card/20 overflow-x-auto">
              {tabs.length === 0 && (
                <div className="px-3 py-1.5 text-xs text-muted">No file open</div>
              )}
              {tabs.map((t) => {
                const isDirty = t.content !== t.saved;
                const isTouched = touchedPaths.has(t.path);
                return (
                  <div
                    key={t.path}
                    onClick={() => {
                      setActivePath(t.path);
                      setShowDiff(false);
                    }}
                    className={clsx(
                      "group flex items-center gap-1.5 px-3 py-1.5 border-r border-border text-xs cursor-pointer min-w-0",
                      activePath === t.path
                        ? "bg-background"
                        : "hover:bg-background/60 text-muted"
                    )}
                  >
                    <Code2 size={11} className="shrink-0" />
                    <span className="truncate max-w-[160px]">{t.path.split("/").pop()}</span>
                    {isTouched && (
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" title="modified by agent" />
                    )}
                    {isDirty && (
                      <span className="w-1.5 h-1.5 rounded-full bg-yellow-400" title="unsaved" />
                    )}
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        closeTab(t.path);
                      }}
                      className="opacity-0 group-hover:opacity-100 hover:text-red-300"
                    >
                      <X size={11} />
                    </button>
                  </div>
                );
              })}
            </div>
            {/* Toolbar */}
            <div className="flex items-center justify-between px-3 py-1 border-b border-border text-xs">
              <span className="text-muted truncate">
                {active?.path || ""}
              </span>
              <div className="flex items-center gap-2">
                {hasDiff && (
                  <button
                    onClick={() => setShowDiff((v) => !v)}
                    className={clsx(
                      "flex items-center gap-1 px-2 py-1 rounded border",
                      showDiff
                        ? "border-accent text-accent"
                        : "border-border hover:bg-background"
                    )}
                  >
                    <FileDiff size={11} /> {showDiff ? "Hide diff" : "Show diff"}
                  </button>
                )}
                <button
                  onClick={save}
                  disabled={!dirty || !active || saving}
                  className="flex items-center gap-1 px-2 py-1 rounded border border-border hover:bg-background disabled:opacity-40"
                >
                  <Save size={11} /> {saving ? "Saving…" : "Save"}
                </button>
              </div>
            </div>
            {/* Editor or diff */}
            <div className="flex-1 min-h-0">
              {!active ? (
                <div className="h-full flex items-center justify-center text-muted text-sm">
                  Pick a file from the tree.
                </div>
              ) : showDiff ? (
                <div className="h-full overflow-auto p-3 bg-background">
                  <DiffViewer
                    oldText={active.baseline}
                    newText={active.content}
                    fileName={active.path}
                  />
                </div>
              ) : (
                <Monaco
                  height="100%"
                  theme="vs-dark"
                  language={active.language}
                  value={active.content}
                  onChange={(v) => updateContent(active.path, v ?? "")}
                  options={{
                    fontSize: 13,
                    minimap: { enabled: false },
                    wordWrap: "on",
                    smoothScrolling: true,
                    automaticLayout: true,
                  }}
                />
              )}
            </div>
          </section>
          <aside className="border-l border-border bg-card/30 flex flex-col min-h-0">
            <div className="px-3 py-2 text-xs uppercase tracking-wider text-muted border-b border-border flex items-center gap-2">
              <Wand2 size={12} className="text-accent" />
              Code agent
            </div>
            <div className="flex-1 overflow-y-auto px-3 py-2 text-xs font-mono whitespace-pre-wrap">
              {agentLog.length === 0 ? (
                <div className="text-muted">
                  Ask the agent to read or edit files in this workspace. The open
                  file (and any others in tabs) is included as context.
                </div>
              ) : (
                agentLog.join("\n")
              )}
            </div>
            <div className="p-2 border-t border-border space-y-2">
              <textarea
                value={agentPrompt}
                onChange={(e) => setAgentPrompt(e.target.value)}
                disabled={agentRunning}
                rows={3}
                placeholder="e.g. add a docstring to the open function"
                className="w-full resize-none bg-background border border-border rounded-md px-2 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-accent"
              />
              <button
                onClick={runAgentOnFile}
                disabled={!agentPrompt.trim() || agentRunning}
                className="w-full px-3 py-1.5 rounded-md bg-accent text-background disabled:opacity-40 text-sm flex items-center justify-center gap-2"
              >
                {agentRunning ? (
                  <>
                    <Square size={12} /> Running…
                  </>
                ) : (
                  <>
                    <Wand2 size={12} /> Run agent
                  </>
                )}
              </button>
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
}

function shortArgs(a: any) {
  if (!a || typeof a !== "object") return "";
  const s = JSON.stringify(a);
  return s.length > 60 ? s.slice(0, 57) + "…" : s;
}
