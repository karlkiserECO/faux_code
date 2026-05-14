export const API_BASE =
  (typeof window !== "undefined" && (window as any).__API_BASE__) ||
  process.env.NEXT_PUBLIC_API_BASE ||
  "http://127.0.0.1:8765";

export async function api<T = unknown>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init.headers || {}),
    },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API ${path} ${res.status}: ${text || res.statusText}`);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export type ProviderInfo = {
  id: string;
  name: string;
  enabled: boolean;
  requires_key: boolean;
  models: string[];
  description: string;
};

export type ModelEntry = { id: string; provider: string; provider_name: string };

export type ConversationSummary = {
  id: string;
  title: string;
  provider: string;
  model: string;
  created_at: string;
  updated_at: string;
  pinned: boolean;
};

export type ChatMessage = {
  id?: string;
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  created_at?: string;
  provider?: string;
  model?: string;
  tool_name?: string | null;
  tool_args?: unknown;
  tool_result?: unknown;
};

export type ConversationDetail = {
  id: string;
  title: string;
  provider: string;
  model: string;
  system_prompt: string;
  messages: ChatMessage[];
};

export function getProviders() {
  return api<ProviderInfo[]>("/v1/providers");
}

export function getModels() {
  return api<ModelEntry[]>("/v1/models");
}

export function listConversations() {
  return api<ConversationSummary[]>("/v1/conversations");
}

export function getConversation(id: string) {
  return api<ConversationDetail>(`/v1/conversations/${id}`);
}

export function deleteConversation(id: string) {
  return api(`/v1/conversations/${id}`, { method: "DELETE" });
}

export function renameConversation(id: string, title: string) {
  return api(`/v1/conversations/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ title }),
  });
}

export function pinConversation(id: string, pinned: boolean) {
  return api(`/v1/conversations/${id}/pin`, {
    method: "PATCH",
    body: JSON.stringify({ pinned }),
  });
}

export function deleteMessageAndAfter(convId: string, msgId: string) {
  return api<{ ok: boolean; deleted: number }>(
    `/v1/conversations/${convId}/messages/${msgId}`,
    { method: "DELETE" }
  );
}

export function generateConversationTitle(
  convId: string,
  payload: { provider?: string; model: string }
) {
  return api<{ title: string }>(`/v1/conversations/${convId}/title`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getKeys() {
  return api<Record<string, { set: boolean; preview: string }>>("/v1/settings/keys");
}

export function saveKeys(keys: Record<string, string>) {
  return api("/v1/settings/keys", {
    method: "POST",
    body: JSON.stringify({ keys }),
  });
}

export type ChatStreamEvent =
  | { event: "conversation"; data: { id: string; title: string } }
  | { event: "delta"; data: string }
  | { event: "tool_call"; data: unknown }
  | { event: "finish"; data: { reason: string; usage: { input_tokens: number; output_tokens: number } | null } }
  | { event: "error"; data: { message: string } }
  | { event: "done"; data: "" };

export type AgentEvent =
  | { event: "status"; data: { status: string; model?: string } }
  | { event: "assistant_delta"; data: { delta: string; step: number } }
  | { event: "assistant_message"; data: { content: string; tool_calls: any[]; step: number; finish_reason?: string } }
  | { event: "tool_call"; data: { id: string; name: string; arguments: any; step: number } }
  | { event: "tool_result"; data: { id: string; name: string; ok: boolean; is_error?: boolean; content: string; data?: any } }
  | { event: "approval_request"; data: { op: string; args: any } }
  | { event: "approval_resolved"; data: { op: string; approved: boolean } }
  | { event: "error"; data: { message: string } }
  | { event: "finished"; data: { status: string; final?: string; steps_taken: number } }
  | { event: "done"; data: "" };

export type ToolInfo = {
  name: string;
  description: string;
  writes: boolean;
  parameters: any;
};

export type AgentRunSummary = {
  id: string;
  goal: string;
  status: string;
  model: string;
  provider: string;
  steps_taken: number;
  created_at: string;
  updated_at: string;
};

export function listTools() {
  return api<ToolInfo[]>("/v1/agents/tools");
}

export function listAgentRuns() {
  return api<AgentRunSummary[]>("/v1/agents/runs");
}

export function getAgentRun(id: string) {
  return api<any>(`/v1/agents/runs/${id}`);
}

export async function createAgentRun(payload: {
  goal: string;
  provider?: string;
  model: string;
  workspace?: string;
  approval_mode?: string;
  allowed_tools?: string[];
  max_steps?: number;
  system_prompt?: string;
  history?: ChatMessage[];
}): Promise<{ id: string; status: string; events_url: string }> {
  return api("/v1/agents/runs", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function approveAgentRun(id: string, approve: boolean) {
  return api(`/v1/agents/runs/${id}/approve`, {
    method: "POST",
    body: JSON.stringify({ approve }),
  });
}

export function cancelAgentRun(id: string) {
  return api(`/v1/agents/runs/${id}/cancel`, { method: "POST" });
}

export async function* streamAgentRun(id: string): AsyncGenerator<AgentEvent> {
  const res = await fetch(`${API_BASE}/v1/agents/runs/${id}/events`);
  if (!res.ok || !res.body) {
    throw new Error(`stream ${res.status}`);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const blocks = buf.split("\n\n");
    buf = blocks.pop() ?? "";
    for (const block of blocks) {
      const lines = block.split("\n");
      let event = "message";
      const dataLines: string[] = [];
      for (const line of lines) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) dataLines.push(line.slice(5).replace(/^ /, ""));
      }
      const raw = dataLines.join("\n");
      let data: any = raw;
      if (raw && (raw.startsWith("{") || raw.startsWith("["))) {
        try { data = JSON.parse(raw); } catch { /* keep */ }
      }
      yield { event, data } as AgentEvent;
      if (event === "done") return;
    }
  }
}

export type WorkspaceEntry = {
  name: string;
  path: string;
  is_dir: boolean;
  size: number | null;
};

export function getWorkspaceTree(path: string = "", root?: string) {
  const qs = new URLSearchParams();
  if (path) qs.set("path", path);
  if (root) qs.set("root", root);
  return api<WorkspaceEntry[]>(`/v1/workspace/tree?${qs.toString()}`);
}

export function getWorkspaceFile(path: string, root?: string) {
  const qs = new URLSearchParams({ path });
  if (root) qs.set("root", root);
  return api<{ path: string; size: number; content: string }>(`/v1/workspace/file?${qs.toString()}`);
}

export function saveWorkspaceFile(path: string, content: string, root?: string) {
  return api<{ ok: boolean; path: string; size: number }>("/v1/workspace/file", {
    method: "POST",
    body: JSON.stringify({ path, content, root }),
  });
}

export function getWorkspaceInfo(root?: string) {
  const qs = root ? `?root=${encodeURIComponent(root)}` : "";
  return api<{ root: string; exists: boolean }>(`/v1/workspace/info${qs}`);
}

export type RagDocument = {
  id: string;
  title: string;
  collection: string;
  source_path: string;
  mime_type: string;
  n_chunks: number;
  created_at: string;
};

export function listRagDocuments() {
  return api<RagDocument[]>("/v1/rag/documents");
}

export async function uploadRagFile(file: File, collection: string = "default") {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("collection", collection);
  const res = await fetch(`${API_BASE}/v1/rag/ingest/file`, { method: "POST", body: fd });
  if (!res.ok) throw new Error(`upload ${res.status}: ${await res.text()}`);
  return res.json() as Promise<{ document_id: string; chunks: number; title: string }>;
}

export function ingestText(payload: { title: string; text: string; source_path?: string; collection?: string }) {
  return api("/v1/rag/ingest/text", { method: "POST", body: JSON.stringify(payload) });
}

export function searchRag(payload: { query: string; top_k?: number; collection?: string }) {
  return api<{ hits: any[] }>("/v1/rag/search", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function deleteRagCollection(name: string) {
  return api(`/v1/rag/collections/${name}`, { method: "DELETE" });
}

export type SystemStatus = {
  ollama: {
    base_url: string;
    alive: boolean;
    models_installed: string[];
    default_chat: string;
    default_code: string;
    default_embed: string;
  };
  providers: {
    id: string;
    name: string;
    enabled: boolean;
    requires_key: boolean;
    description: string;
  }[];
  workspace_root: string;
  data_dir: string;
};

export type RecommendedModel = {
  id: string;
  role: string;
  description: string;
  size_gb: number;
};

export function getSystemStatus() {
  return api<SystemStatus>("/v1/status/system");
}

export function getRecommendedModels() {
  return api<RecommendedModel[]>("/v1/status/ollama/recommended");
}

export async function* streamPullModel(
  model: string
): AsyncGenerator<{ event: string; data: any }> {
  const res = await fetch(`${API_BASE}/v1/status/ollama/pull`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model }),
  });
  if (!res.ok || !res.body) throw new Error(`pull ${res.status}`);
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const blocks = buf.split("\n\n");
    buf = blocks.pop() ?? "";
    for (const block of blocks) {
      const lines = block.split("\n");
      let event = "message";
      const dataLines: string[] = [];
      for (const line of lines) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) dataLines.push(line.slice(5).replace(/^ /, ""));
      }
      const raw = dataLines.join("\n");
      let data: any = raw;
      if (raw && (raw.startsWith("{") || raw.startsWith("["))) {
        try { data = JSON.parse(raw); } catch { /* keep */ }
      }
      yield { event, data };
      if (event === "done") return;
    }
  }
}

export async function* streamChat(
  payload: {
    conversation_id?: string | null;
    provider?: string;
    model: string;
    messages: ChatMessage[];
    system_prompt?: string;
    tools?: unknown[];
    fallback?: string[];
    temperature?: number;
  },
  signal?: AbortSignal
): AsyncGenerator<ChatStreamEvent> {
  const res = await fetch(`${API_BASE}/v1/chat/completions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal,
  });
  if (!res.ok || !res.body) {
    const text = await res.text().catch(() => "");
    throw new Error(`stream ${res.status}: ${text}`);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const blocks = buf.split("\n\n");
    buf = blocks.pop() ?? "";
    for (const block of blocks) {
      const lines = block.split("\n");
      let event = "message";
      const dataLines: string[] = [];
      for (const line of lines) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) dataLines.push(line.slice(5).replace(/^ /, ""));
      }
      const raw = dataLines.join("\n");
      let data: any = raw;
      if (raw && (raw.startsWith("{") || raw.startsWith("["))) {
        try {
          data = JSON.parse(raw);
        } catch {
          /* keep as string */
        }
      }
      yield { event, data } as ChatStreamEvent;
      if (event === "done") return;
    }
  }
}
