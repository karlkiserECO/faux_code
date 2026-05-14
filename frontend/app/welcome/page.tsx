"use client";

import { useEffect, useState } from "react";
import Sidebar from "@/components/Sidebar";
import {
  getRecommendedModels,
  getSystemStatus,
  RecommendedModel,
  streamPullModel,
  SystemStatus,
} from "@/lib/api";
import {
  CheckCircle2,
  XCircle,
  Download,
  Loader2,
  Sparkles,
  Rocket,
  Settings as SettingsIcon,
} from "lucide-react";
import Link from "next/link";
import clsx from "clsx";

export default function WelcomePage() {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [recommended, setRecommended] = useState<RecommendedModel[]>([]);
  const [pulling, setPulling] = useState<string | null>(null);
  const [pullProgress, setPullProgress] = useState<string>("");
  const [pullError, setPullError] = useState<string | null>(null);

  async function refresh() {
    try {
      const [s, r] = await Promise.all([getSystemStatus(), getRecommendedModels()]);
      setStatus(s);
      setRecommended(r);
    } catch (e: any) {
      console.error(e);
    }
  }

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 5000);
    return () => clearInterval(id);
  }, []);

  async function pull(model: string) {
    setPulling(model);
    setPullProgress("");
    setPullError(null);
    try {
      for await (const ev of streamPullModel(model)) {
        if (ev.event === "progress") {
          const d = ev.data;
          let line = d.status || "";
          if (d.total && d.completed) {
            const pct = Math.round((d.completed / d.total) * 100);
            line += ` ${pct}%`;
          }
          setPullProgress(line);
        } else if (ev.event === "error") {
          setPullError(ev.data?.message || "pull failed");
        } else if (ev.event === "done") {
          break;
        }
      }
      await refresh();
    } catch (e: any) {
      setPullError(e?.message || String(e));
    } finally {
      setPulling(null);
      setPullProgress("");
    }
  }

  const enabledProviders = (status?.providers || []).filter((p) => p.enabled);
  const installed = new Set(status?.ollama.models_installed || []);

  return (
    <div className="flex h-screen">
      <Sidebar />
      <main className="flex-1 overflow-y-auto">
        <div className="max-w-3xl mx-auto p-6 space-y-6">
          <header>
            <div className="flex items-center gap-2">
              <Rocket size={24} className="text-accent" />
              <h1 className="text-2xl font-semibold">Welcome to faux_code</h1>
            </div>
            <p className="text-muted text-sm mt-1">
              A quick status check and one-click setup for your local AI workbench.
            </p>
          </header>

          <section className="rounded-lg border border-border bg-card p-4 space-y-3">
            <h2 className="text-sm uppercase tracking-wider text-muted">
              Local runtime
            </h2>
            <div className="flex items-center gap-2">
              {status?.ollama.alive ? (
                <CheckCircle2 size={16} className="text-emerald-300" />
              ) : (
                <XCircle size={16} className="text-red-300" />
              )}
              <span className="text-sm">
                Ollama at <code className="text-xs">{status?.ollama.base_url}</code>{" "}
                {status?.ollama.alive ? "is reachable." : "is not running."}
              </span>
            </div>
            {!status?.ollama.alive && (
              <div className="text-xs text-muted">
                Start it with: <code className="text-foreground">ollama serve</code>{" "}
                (macOS: open the Ollama app). The dev script does this automatically.
              </div>
            )}
            <div>
              <div className="text-xs text-muted mb-1">Installed models</div>
              {!status || status.ollama.models_installed.length === 0 ? (
                <div className="text-xs text-muted">(none yet)</div>
              ) : (
                <div className="flex flex-wrap gap-1.5">
                  {status.ollama.models_installed.map((m) => (
                    <span
                      key={m}
                      className="text-xs px-2 py-0.5 rounded-full bg-background border border-border"
                    >
                      {m}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </section>

          <section className="rounded-lg border border-border bg-card p-4 space-y-3">
            <h2 className="text-sm uppercase tracking-wider text-muted flex items-center gap-2">
              <Sparkles size={12} className="text-accent" /> Recommended models
            </h2>
            <div className="text-xs text-muted">
              Tuned for a 16 GB Apple Silicon machine. Click a model to pull it
              into Ollama.
            </div>
            <div className="space-y-2">
              {recommended.map((m) => {
                const have = installed.has(m.id);
                const isPulling = pulling === m.id;
                return (
                  <div
                    key={m.id}
                    className="rounded-md border border-border bg-background/40 p-3 flex items-center gap-3"
                  >
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <code className="text-sm font-medium">{m.id}</code>
                        <span className="text-[10px] uppercase tracking-wider text-muted">
                          {m.role}
                        </span>
                        <span className="text-[10px] text-muted">{m.size_gb} GB</span>
                      </div>
                      <div className="text-xs text-muted mt-0.5">{m.description}</div>
                    </div>
                    {have ? (
                      <span className="flex items-center gap-1 text-xs text-emerald-300">
                        <CheckCircle2 size={12} /> installed
                      </span>
                    ) : isPulling ? (
                      <div className="flex items-center gap-2 text-xs">
                        <Loader2 size={12} className="animate-spin text-accent" />
                        <span className="text-muted truncate max-w-[160px]">
                          {pullProgress || "pulling…"}
                        </span>
                      </div>
                    ) : (
                      <button
                        onClick={() => pull(m.id)}
                        disabled={!!pulling || !status?.ollama.alive}
                        className="flex items-center gap-1 px-3 py-1 rounded-md border border-border hover:bg-background text-xs disabled:opacity-40"
                      >
                        <Download size={11} /> Pull
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
            {pullError && (
              <div className="text-xs text-red-300">{pullError}</div>
            )}
          </section>

          <section className="rounded-lg border border-border bg-card p-4 space-y-2">
            <h2 className="text-sm uppercase tracking-wider text-muted">Providers</h2>
            <div className="text-xs text-muted">
              {enabledProviders.length} of {status?.providers.length || 0} providers
              enabled. Add API keys in{" "}
              <Link href="/settings" className="text-accent underline">
                Settings
              </Link>
              {" "}to unlock more.
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {(status?.providers || []).map((p) => (
                <div
                  key={p.id}
                  className={clsx(
                    "rounded-md border p-2 text-xs",
                    p.enabled
                      ? "border-emerald-500/30 bg-emerald-500/5"
                      : "border-border opacity-60"
                  )}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-medium">{p.name}</span>
                    {p.enabled ? (
                      <CheckCircle2 size={12} className="text-emerald-300" />
                    ) : (
                      <span className="text-[10px] text-muted">disabled</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </section>

          <section className="rounded-lg border border-border bg-card p-4 space-y-3">
            <h2 className="text-sm uppercase tracking-wider text-muted">Next steps</h2>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-sm">
              <Link
                href="/chat"
                className="rounded-md border border-border bg-background/40 p-3 hover:bg-background"
              >
                <div className="font-medium">Start chatting</div>
                <div className="text-xs text-muted mt-0.5">
                  Multi-provider streaming chat with markdown + code.
                </div>
              </Link>
              <Link
                href="/agent"
                className="rounded-md border border-border bg-background/40 p-3 hover:bg-background"
              >
                <div className="font-medium">Run an agent</div>
                <div className="text-xs text-muted mt-0.5">
                  Goal-driven loop with web + file + shell tools.
                </div>
              </Link>
              <Link
                href="/code"
                className="rounded-md border border-border bg-background/40 p-3 hover:bg-background"
              >
                <div className="font-medium">Open code workspace</div>
                <div className="text-xs text-muted mt-0.5">
                  Cursor-style editor with side-panel agent.
                </div>
              </Link>
            </div>
            <div className="flex items-center gap-2 text-xs text-muted">
              <SettingsIcon size={12} /> Workspace root:{" "}
              <code>{status?.workspace_root || "…"}</code>
            </div>
          </section>
        </div>
      </main>
    </div>
  );
}
