"use client";

import { useEffect, useState } from "react";
import Sidebar from "@/components/Sidebar";
import { getKeys, getProviders, saveKeys } from "@/lib/api";
import { useSettingsStore } from "@/stores/settingsStore";

const KEYS = [
  { id: "GROQ_API_KEY", label: "Groq API Key", url: "https://console.groq.com/keys" },
  { id: "OPENROUTER_API_KEY", label: "OpenRouter API Key", url: "https://openrouter.ai/keys" },
  { id: "GEMINI_API_KEY", label: "Google Gemini API Key", url: "https://aistudio.google.com/app/apikey" },
  { id: "CEREBRAS_API_KEY", label: "Cerebras API Key", url: "https://cloud.cerebras.ai/" },
  { id: "HF_TOKEN", label: "HuggingFace Token", url: "https://huggingface.co/settings/tokens" },
  { id: "TAVILY_API_KEY", label: "Tavily Search Key (web search)", url: "https://tavily.com/" },
  { id: "VLLM_BASE_URL", label: "Self-hosted vLLM Base URL", url: "" },
  { id: "VLLM_API_KEY", label: "Self-hosted vLLM API Key", url: "" },
  { id: "OLLAMA_BASE_URL", label: "Ollama Base URL (default http://127.0.0.1:11434)", url: "" },
];

export default function SettingsPage() {
  const { systemPrompt, setSystemPrompt, temperature, setTemperature } = useSettingsStore();
  const [keys, setKeys] = useState<Record<string, { set: boolean; preview: string }>>({});
  const [inputs, setInputs] = useState<Record<string, string>>({});
  const [providers, setProviders] = useState<any[]>([]);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  async function refresh() {
    const [k, p] = await Promise.all([getKeys(), getProviders()]);
    setKeys(k);
    setProviders(p);
  }

  useEffect(() => {
    refresh().catch(() => {});
  }, []);

  async function save() {
    setSaving(true);
    setSaved(false);
    const cleaned: Record<string, string> = {};
    for (const [k, v] of Object.entries(inputs)) {
      if (v && v.length) cleaned[k] = v;
    }
    if (Object.keys(cleaned).length === 0) {
      setSaving(false);
      return;
    }
    await saveKeys(cleaned);
    setInputs({});
    await refresh();
    setSaving(false);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  }

  return (
    <div className="flex">
      <Sidebar />
      <main className="flex-1 h-screen overflow-y-auto">
        <div className="max-w-3xl mx-auto p-6 space-y-8">
          <h1 className="text-2xl font-semibold">Settings</h1>

          <section className="space-y-3">
            <h2 className="text-lg font-medium">Providers</h2>
            <div className="text-sm text-muted">
              Local Ollama is always enabled. Free remote providers are unlocked by
              adding API keys below. Keys are stored in the local SQLite DB and pushed
              into the backend's environment.
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {providers.map((p) => (
                <div
                  key={p.id}
                  className="rounded-lg border border-border bg-card p-3 flex flex-col gap-1"
                >
                  <div className="flex items-center justify-between">
                    <div className="font-medium">{p.name}</div>
                    <div
                      className={
                        p.enabled
                          ? "text-xs px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-300"
                          : "text-xs px-2 py-0.5 rounded-full bg-muted/15 text-muted"
                      }
                    >
                      {p.enabled ? "enabled" : "disabled"}
                    </div>
                  </div>
                  <div className="text-xs text-muted">{p.description}</div>
                </div>
              ))}
            </div>
          </section>

          <section className="space-y-3">
            <h2 className="text-lg font-medium">API keys</h2>
            <div className="grid grid-cols-1 gap-3">
              {KEYS.map((k) => (
                <label
                  key={k.id}
                  className="flex flex-col gap-1 rounded-lg border border-border bg-card p-3"
                >
                  <div className="flex items-center justify-between text-sm">
                    <span className="font-medium">{k.label}</span>
                    <span className="text-xs text-muted">
                      {keys[k.id]?.set ? `set (${keys[k.id]?.preview})` : "not set"}
                    </span>
                  </div>
                  <input
                    type="password"
                    autoComplete="off"
                    placeholder={keys[k.id]?.set ? "Replace…" : "Paste value"}
                    value={inputs[k.id] || ""}
                    onChange={(e) =>
                      setInputs((s) => ({ ...s, [k.id]: e.target.value }))
                    }
                    className="bg-background border border-border rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-accent"
                  />
                  {k.url && (
                    <a
                      href={k.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-accent underline self-start"
                    >
                      Get a key →
                    </a>
                  )}
                </label>
              ))}
            </div>
            <button
              onClick={save}
              disabled={saving || Object.keys(inputs).length === 0}
              className="px-4 py-2 rounded-md bg-accent text-background disabled:opacity-40 hover:opacity-90"
            >
              {saving ? "Saving…" : "Save changes"}
            </button>
            {saved && (
              <span className="ml-3 text-sm text-emerald-300">
                Saved. Providers reloaded.
              </span>
            )}
          </section>

          <section className="space-y-3">
            <h2 className="text-lg font-medium">Chat defaults</h2>
            <label className="block">
              <div className="text-sm mb-1">System prompt</div>
              <textarea
                value={systemPrompt}
                onChange={(e) => setSystemPrompt(e.target.value)}
                rows={5}
                className="w-full bg-background border border-border rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-accent"
              />
            </label>
            <label className="block">
              <div className="text-sm mb-1">
                Temperature: <span className="text-muted">{temperature}</span>
              </div>
              <input
                type="range"
                min={0}
                max={2}
                step={0.1}
                value={temperature}
                onChange={(e) => setTemperature(parseFloat(e.target.value))}
                className="w-full"
              />
            </label>
          </section>
        </div>
      </main>
    </div>
  );
}
