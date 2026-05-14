"use client";

import { useEffect, useRef, useState } from "react";
import {
  approveAgentRun,
  cancelAgentRun,
  createAgentRun,
  listTools,
  streamAgentRun,
  ToolInfo,
} from "@/lib/api";
import { useSettingsStore } from "@/stores/settingsStore";
import ModelPicker from "./ModelPicker";
import ToolEvent, { ToolEventState } from "./ToolEvent";
import ApprovalModal from "./ApprovalModal";
import MessageBubble from "./MessageBubble";
import { ArrowUp, ShieldAlert, Square, Wrench, FolderOpen } from "lucide-react";
import clsx from "clsx";

type StreamStep = {
  step: number;
  assistantText: string;
  toolCalls: Record<string, ToolEventState>;
  toolCallOrder: string[];
  done: boolean;
};

export default function AgentView({ workspace: workspaceProp }: { workspace?: string } = {}) {
  const { provider, model, systemPrompt } = useSettingsStore();
  const [goal, setGoal] = useState("");
  const [workspace, setWorkspace] = useState(workspaceProp || "");
  const [tools, setTools] = useState<ToolInfo[]>([]);
  const [selectedTools, setSelectedTools] = useState<Set<string>>(
    new Set([
      "web_search",
      "web_fetch",
      "list_dir",
      "read_file",
      "grep",
      "write_file",
      "edit_file",
      "shell",
      "python",
      "rag_search",
    ])
  );
  const [approvalMode, setApprovalMode] = useState("require_for_writes");
  const [maxSteps, setMaxSteps] = useState(20);
  const [running, setRunning] = useState(false);
  const [runId, setRunId] = useState<string | null>(null);
  const [steps, setSteps] = useState<StreamStep[]>([]);
  const [finalText, setFinalText] = useState("");
  const [statusText, setStatusText] = useState("");
  const [pendingApproval, setPendingApproval] = useState<{ op: string; args: any } | null>(null);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    listTools().then(setTools).catch(() => {});
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [steps, finalText, statusText]);

  function toggleTool(name: string) {
    setSelectedTools((s) => {
      const next = new Set(s);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  }

  async function start() {
    if (!goal.trim() || running) return;
    setRunning(true);
    setSteps([]);
    setFinalText("");
    setStatusText("Starting…");
    setPendingApproval(null);
    try {
      const { id } = await createAgentRun({
        goal: goal.trim(),
        provider,
        model,
        workspace: workspace || undefined,
        approval_mode: approvalMode,
        allowed_tools: Array.from(selectedTools),
        max_steps: maxSteps,
        system_prompt: systemPrompt,
      });
      setRunId(id);
      await consumeStream(id);
    } catch (e: any) {
      setStatusText(`Error: ${e?.message || e}`);
    } finally {
      setRunning(false);
      setRunId(null);
    }
  }

  async function consumeStream(id: string) {
    const stepsByIdx: Record<number, StreamStep> = {};
    for await (const ev of streamAgentRun(id)) {
      if (ev.event === "status") {
        setStatusText(`Status: ${ev.data.status}`);
      } else if (ev.event === "assistant_delta") {
        const s = ensureStep(stepsByIdx, ev.data.step);
        s.assistantText += ev.data.delta;
        flush(stepsByIdx);
      } else if (ev.event === "assistant_message") {
        const s = ensureStep(stepsByIdx, ev.data.step);
        s.assistantText = ev.data.content;
        s.done = true;
        flush(stepsByIdx);
      } else if (ev.event === "tool_call") {
        const s = ensureStep(stepsByIdx, ev.data.step);
        s.toolCalls[ev.data.id] = {
          callId: ev.data.id,
          name: ev.data.name,
          step: ev.data.step,
          args: ev.data.arguments,
        };
        s.toolCallOrder.push(ev.data.id);
        flush(stepsByIdx);
      } else if (ev.event === "tool_result") {
        for (const s of Object.values(stepsByIdx)) {
          if (s.toolCalls[ev.data.id]) {
            s.toolCalls[ev.data.id].result = {
              ok: ev.data.ok,
              is_error: ev.data.is_error,
              content: ev.data.content,
              data: ev.data.data,
            };
          }
        }
        flush(stepsByIdx);
      } else if (ev.event === "approval_request") {
        setPendingApproval(ev.data);
      } else if (ev.event === "approval_resolved") {
        setPendingApproval(null);
      } else if (ev.event === "error") {
        setStatusText(`Error: ${ev.data.message}`);
      } else if (ev.event === "finished") {
        setFinalText(ev.data.final || "");
        setStatusText(`Completed in ${ev.data.steps_taken} step(s).`);
      } else if (ev.event === "done") {
        break;
      }
    }
  }

  function ensureStep(map: Record<number, StreamStep>, idx: number): StreamStep {
    if (!map[idx]) {
      map[idx] = {
        step: idx,
        assistantText: "",
        toolCalls: {},
        toolCallOrder: [],
        done: false,
      };
    }
    return map[idx];
  }

  function flush(map: Record<number, StreamStep>) {
    setSteps(
      Object.values(map).sort((a, b) => a.step - b.step).map((s) => ({ ...s }))
    );
  }

  async function approve(yes: boolean) {
    if (!runId) return;
    await approveAgentRun(runId, yes);
    setPendingApproval(null);
  }

  async function stop() {
    if (!runId) return;
    await cancelAgentRun(runId);
    setStatusText("Cancelled.");
  }

  return (
    <div className="flex-1 flex flex-col h-screen">
      <header className="flex items-center justify-between px-4 py-3 border-b border-border">
        <div className="flex items-center gap-2 text-sm">
          <Wrench size={14} className="text-accent" />
          <span className="text-muted">Agent mode</span>
        </div>
        <ModelPicker />
      </header>

      <div className="border-b border-border bg-card/30 px-4 py-3 space-y-2">
        <div className="flex items-center gap-2">
          <FolderOpen size={14} className="text-muted" />
          <input
            value={workspace}
            onChange={(e) => setWorkspace(e.target.value)}
            placeholder="Workspace path (absolute or relative). Leave blank to use the default."
            className="flex-1 bg-background border border-border rounded-md px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-accent"
          />
          <button
            onClick={() => setShowAdvanced((v) => !v)}
            className="text-xs text-muted hover:text-foreground"
          >
            {showAdvanced ? "hide advanced" : "advanced"}
          </button>
        </div>
        {showAdvanced && (
          <div className="space-y-2">
            <div className="flex items-center gap-3 text-xs">
              <span className="text-muted">Approval:</span>
              {(["auto", "require_for_writes", "require_all"] as const).map((m) => (
                <button
                  key={m}
                  onClick={() => setApprovalMode(m)}
                  className={clsx(
                    "px-2 py-1 rounded border text-xs",
                    approvalMode === m
                      ? "border-accent text-accent"
                      : "border-border text-muted hover:text-foreground"
                  )}
                >
                  {m.replace(/_/g, " ")}
                </button>
              ))}
              <span className="text-muted ml-3">Max steps</span>
              <input
                type="number"
                min={1}
                max={100}
                value={maxSteps}
                onChange={(e) => setMaxSteps(parseInt(e.target.value, 10) || 1)}
                className="bg-background border border-border rounded px-2 py-1 w-16"
              />
            </div>
            <div className="flex flex-wrap gap-1.5">
              {tools.map((t) => (
                <button
                  key={t.name}
                  onClick={() => toggleTool(t.name)}
                  className={clsx(
                    "px-2 py-0.5 rounded-full border text-xs",
                    selectedTools.has(t.name)
                      ? "border-accent text-accent bg-accent/10"
                      : "border-border text-muted hover:text-foreground"
                  )}
                  title={t.description}
                >
                  {t.name}
                  {t.writes && <span className="ml-1 text-yellow-400">●</span>}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      <main className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
        {steps.length === 0 && !running && (
          <div className="h-full flex items-center justify-center text-center text-muted">
            <div className="max-w-md">
              <ShieldAlert size={28} className="mx-auto mb-2 text-accent" />
              <div className="font-medium text-foreground mb-1">Agent mode</div>
              <p className="text-sm">
                Set a goal, point at a workspace folder, and let the agent plan and act
                using the tools you've enabled. Writes default to approval-required.
              </p>
            </div>
          </div>
        )}

        {steps.map((s) => (
          <div key={s.step} className="space-y-2">
            <div className="text-xs text-muted">Step {s.step + 1}</div>
            {s.assistantText && (
              <MessageBubble
                message={{ role: "assistant", content: s.assistantText, provider, model }}
                streaming={!s.done && running}
              />
            )}
            {s.toolCallOrder.map((id) => (
              <ToolEvent key={id} ev={s.toolCalls[id]} />
            ))}
          </div>
        ))}

        {finalText && (
          <div className="rounded-md border border-emerald-500/30 bg-emerald-500/5 p-3">
            <div className="text-xs uppercase tracking-wider text-emerald-300 mb-1">
              Final answer
            </div>
            <div className="prose-faux text-sm whitespace-pre-wrap">{finalText}</div>
          </div>
        )}
        {statusText && (
          <div className="text-xs text-muted text-center">{statusText}</div>
        )}
        <div ref={bottomRef} />
      </main>

      <footer className="p-3 border-t border-border bg-card/30">
        <div className="relative flex items-end gap-2 max-w-4xl mx-auto">
          <textarea
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
            disabled={running}
            placeholder="Describe what you want the agent to do…"
            rows={Math.min(6, Math.max(1, goal.split("\n").length))}
            className="flex-1 resize-none rounded-lg border border-border bg-background px-3 py-2.5 focus:outline-none focus:ring-1 focus:ring-accent placeholder:text-muted disabled:opacity-60"
          />
          {running ? (
            <button
              onClick={stop}
              className="h-10 w-10 shrink-0 flex items-center justify-center rounded-lg bg-red-500/80 text-white hover:opacity-90"
              title="Stop"
            >
              <Square size={16} />
            </button>
          ) : (
            <button
              onClick={start}
              disabled={!goal.trim()}
              className="h-10 w-10 shrink-0 flex items-center justify-center rounded-lg bg-accent text-background disabled:opacity-40 disabled:cursor-not-allowed hover:opacity-90"
              title="Run agent"
            >
              <ArrowUp size={18} />
            </button>
          )}
        </div>
      </footer>

      {pendingApproval && (
        <ApprovalModal
          request={pendingApproval}
          onApprove={() => approve(true)}
          onDeny={() => approve(false)}
        />
      )}
    </div>
  );
}
