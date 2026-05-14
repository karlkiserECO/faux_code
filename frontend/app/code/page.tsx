"use client";

import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import Sidebar from "@/components/Sidebar";
import FileTree from "@/components/FileTree";
import {
  createAgentRun,
  getWorkspaceFile,
  getWorkspaceInfo,
  saveWorkspaceFile,
  streamAgentRun,
} from "@/lib/api";
import { useSettingsStore } from "@/stores/settingsStore";
import ModelPicker from "@/components/ModelPicker";
import { FolderOpen, Save, Wand2, Square } from "lucide-react";

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

export default function CodePage() {
  const { provider, model } = useSettingsStore();
  const [root, setRoot] = useState<string>("");
  const [rootInput, setRootInput] = useState<string>("");
  const [activePath, setActivePath] = useState<string>("");
  const [content, setContent] = useState<string>("");
  const [originalContent, setOriginalContent] = useState<string>("");
  const [language, setLanguage] = useState<string>("plaintext");
  const [saving, setSaving] = useState(false);
  const [agentPrompt, setAgentPrompt] = useState("");
  const [agentRunning, setAgentRunning] = useState(false);
  const [agentLog, setAgentLog] = useState<string[]>([]);
  const [agentRunId, setAgentRunId] = useState<string | null>(null);

  useEffect(() => {
    getWorkspaceInfo()
      .then((d) => {
        setRoot(d.root);
        setRootInput(d.root);
      })
      .catch(() => {});
  }, []);

  async function openFile(path: string) {
    try {
      const data = await getWorkspaceFile(path, root);
      setActivePath(path);
      setContent(data.content);
      setOriginalContent(data.content);
      const ext = path.split(".").pop()?.toLowerCase() || "";
      setLanguage(EXT_TO_LANG[ext] || "plaintext");
    } catch (e) {
      alert(`Failed to open ${path}: ${e}`);
    }
  }

  async function save() {
    if (!activePath) return;
    setSaving(true);
    try {
      await saveWorkspaceFile(activePath, content, root);
      setOriginalContent(content);
    } catch (e: any) {
      alert(`Save failed: ${e.message || e}`);
    } finally {
      setSaving(false);
    }
  }

  function applyRoot() {
    if (rootInput && rootInput !== root) {
      setRoot(rootInput);
      setActivePath("");
      setContent("");
      setOriginalContent("");
    }
  }

  async function runAgentOnFile() {
    if (!agentPrompt.trim() || agentRunning) return;
    setAgentRunning(true);
    setAgentLog([]);
    try {
      const goal = activePath
        ? `Working in file \`${activePath}\` (already open in the editor):\n\n${agentPrompt}\n\nUse read_file and edit_file (or write_file) to make changes. After editing, re-read the file to confirm.`
        : agentPrompt;
      const { id } = await createAgentRun({
        goal,
        provider,
        model,
        workspace: root,
        approval_mode: "auto",
        allowed_tools: ["list_dir", "read_file", "grep", "write_file", "edit_file", "shell", "python", "web_search", "web_fetch"],
        max_steps: 20,
      });
      setAgentRunId(id);
      let final = "";
      for await (const ev of streamAgentRun(id)) {
        if (ev.event === "tool_call") {
          setAgentLog((l) => [...l, `→ ${ev.data.name}(${shortArgs(ev.data.arguments)})`]);
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
      if (activePath) {
        try {
          const data = await getWorkspaceFile(activePath, root);
          setContent(data.content);
          setOriginalContent(data.content);
        } catch {}
      }
    } catch (e: any) {
      setAgentLog((l) => [...l, `Error: ${e?.message || e}`]);
    } finally {
      setAgentRunning(false);
      setAgentRunId(null);
    }
  }

  const dirty = content !== originalContent;

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
        <div className="flex-1 grid grid-cols-[260px_1fr_360px] min-h-0">
          <aside className="border-r border-border bg-card/30 min-h-0">
            {root ? (
              <FileTree root={root} activePath={activePath} onSelect={openFile} />
            ) : (
              <div className="p-3 text-xs text-muted">No workspace.</div>
            )}
          </aside>
          <section className="min-w-0 flex flex-col">
            <div className="flex items-center justify-between px-3 py-1.5 border-b border-border text-xs">
              <span className="text-muted truncate">
                {activePath || "(no file open)"}
              </span>
              <div className="flex items-center gap-2">
                {dirty && <span className="text-yellow-400">unsaved</span>}
                <button
                  onClick={save}
                  disabled={!dirty || !activePath || saving}
                  className="flex items-center gap-1 px-2 py-1 rounded border border-border hover:bg-background disabled:opacity-40"
                >
                  <Save size={12} /> {saving ? "Saving…" : "Save"}
                </button>
              </div>
            </div>
            <div className="flex-1 min-h-0">
              {activePath ? (
                <Monaco
                  height="100%"
                  theme="vs-dark"
                  language={language}
                  value={content}
                  onChange={(v) => setContent(v ?? "")}
                  options={{
                    fontSize: 13,
                    minimap: { enabled: false },
                    wordWrap: "on",
                    smoothScrolling: true,
                    automaticLayout: true,
                  }}
                />
              ) : (
                <div className="h-full flex items-center justify-center text-muted text-sm">
                  Pick a file from the tree.
                </div>
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
                  Ask the agent to read or edit files in this workspace. Active file
                  context is included automatically.
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
