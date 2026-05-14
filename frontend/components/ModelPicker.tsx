"use client";

import { useEffect, useState } from "react";
import { getModels, getProviders, ModelEntry, ProviderInfo } from "@/lib/api";
import { useSettingsStore } from "@/stores/settingsStore";
import { ChevronDown } from "lucide-react";
import clsx from "clsx";

export default function ModelPicker() {
  const { provider, model, setProviderModel } = useSettingsStore();
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [models, setModels] = useState<ModelEntry[]>([]);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    Promise.all([getProviders(), getModels()])
      .then(([p, m]) => {
        setProviders(p);
        setModels(m);
        const enabledProvider = p.find((x) => x.id === provider && x.enabled);
        if (!enabledProvider) {
          const fallback = p.find((x) => x.enabled);
          if (fallback) {
            const firstModel = m.find((mm) => mm.provider === fallback.id);
            if (firstModel) setProviderModel(fallback.id, firstModel.id);
          }
        }
      })
      .catch(() => {});
  }, [provider, setProviderModel]);

  const grouped = providers
    .filter((p) => p.enabled)
    .map((p) => ({
      provider: p,
      models: models.filter((m) => m.provider === p.id),
    }));

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 px-3 py-1.5 rounded-md border border-border bg-card hover:bg-background text-sm"
      >
        <span className="text-muted text-xs uppercase tracking-wider">
          {providers.find((p) => p.id === provider)?.name || provider}
        </span>
        <span className="font-medium">{model}</span>
        <ChevronDown size={14} className="text-muted" />
      </button>
      {open && (
        <div
          className="absolute right-0 mt-1 z-20 w-[420px] max-h-[60vh] overflow-y-auto rounded-md border border-border bg-card shadow-xl"
          onMouseLeave={() => setOpen(false)}
        >
          {grouped.length === 0 && (
            <div className="p-3 text-sm text-muted">
              No enabled providers. Add API keys in{" "}
              <a className="text-accent underline" href="/settings">
                Settings
              </a>
              {" "}or start Ollama.
            </div>
          )}
          {grouped.map(({ provider: p, models: ms }) => (
            <div key={p.id} className="border-b border-border last:border-0">
              <div className="px-3 py-2 text-xs uppercase tracking-wider text-muted">
                {p.name}
              </div>
              {ms.length === 0 && (
                <div className="px-3 pb-2 text-xs text-muted">No models reported.</div>
              )}
              {ms.map((m) => (
                <button
                  key={`${p.id}:${m.id}`}
                  onClick={() => {
                    setProviderModel(p.id, m.id);
                    setOpen(false);
                  }}
                  className={clsx(
                    "w-full text-left px-3 py-1.5 hover:bg-background text-sm",
                    p.id === provider && m.id === model && "bg-background text-accent"
                  )}
                >
                  {m.id}
                </button>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
