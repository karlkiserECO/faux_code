"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";

type SettingsState = {
  provider: string;
  model: string;
  systemPrompt: string;
  temperature: number;
  setProviderModel: (p: string, m: string) => void;
  setSystemPrompt: (s: string) => void;
  setTemperature: (t: number) => void;
};

export const useSettingsStore = create<SettingsState>()(
  persist(
    (set) => ({
      provider: "ollama",
      model: "llama3.1:8b-instruct-q4_K_M",
      systemPrompt:
        "You are faux_code, a helpful AI assistant running on the user's machine. Be concise, direct, and use markdown for structure when helpful.",
      temperature: 0.7,
      setProviderModel: (p, m) => set({ provider: p, model: m }),
      setSystemPrompt: (s) => set({ systemPrompt: s }),
      setTemperature: (t) => set({ temperature: t }),
    }),
    { name: "faux-code-settings" }
  )
);
