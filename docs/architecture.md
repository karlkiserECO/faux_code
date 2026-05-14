# faux_code architecture

A modular, single-user, local-first system that combines a ChatGPT-style chat
UI, a Cursor / Claude-Code-style agentic coding workbench, web search, and
local RAG, all driven by a multi-provider router across local Ollama and free
remote APIs.

## Layered design

1. **Surfaces** — Next.js web UI at `:3000` and a `faux-code` CLI binary.
2. **Gateway** — FastAPI app at `:8765` exposing OpenAI-compatible chat plus
   agent, RAG, workspace, and settings endpoints.
3. **Provider router** — routes each request to one of: local Ollama, a free
   remote provider (Groq, OpenRouter, Gemini, HF, Cerebras), or an optional
   self-hosted vLLM endpoint, with a fallback chain.
4. **Agent loop** — a ReAct-style planner/executor using native OpenAI tool
   calls. Streams thoughts, tool calls, and results back to the UI in real time.
5. **Tools** — web_search, web_fetch, list_dir, read_file, grep, write_file,
   edit_file, shell, python, rag_search.
6. **Sandbox** — subprocess runner with timeouts, output caps, env scrubbing,
   and path-jailed workspace access. Drop-in upgrade to Docker / gVisor later.
7. **RAG** — LanceDB embedded store, embeddings via local Ollama
   (`nomic-embed-text`), ingestion of PDF/TXT/MD/code.
8. **Persistence** — SQLite via SQLModel for conversations, agent runs,
   document index, and API keys.

## Data flow

### Chat
1. Frontend `POST /v1/chat/completions` with `{provider, model, messages}`.
2. Backend resolves the provider, attaches optional tools, and opens a
   streaming connection.
3. Each delta is forwarded as an SSE `delta` event; final usage in `finish`.
4. The conversation is persisted to SQLite when `persist=true`.

### Agent
1. Frontend `POST /v1/agents/runs` with `{goal, workspace, allowed_tools, ...}`.
2. Backend creates an `AgentRun` row and a per-run event queue. A background
   asyncio task drives the ReAct loop.
3. The loop streams `assistant_delta`, `tool_call`, `tool_result`,
   `approval_request`, and `finished` events both into a live queue and into
   SQLite for replay.
4. Frontend subscribes via `GET /v1/agents/runs/{id}/events` (SSE).
5. Writes (`write_file`, `edit_file`, `shell`) can be gated through
   `approval_mode`; the UI shows a modal and posts to
   `/v1/agents/runs/{id}/approve`.

### RAG
1. Documents uploaded via `/v1/rag/ingest/file` are chunked (~1.8 KB w/ 200 char
   overlap), embedded via Ollama, and stored in a LanceDB table per collection.
2. The agent's `rag_search` tool and the `/v1/rag/search` endpoint use the same
   embedding model to retrieve top-k by cosine distance.

## Security posture (v1, single-user local)

- Backend binds to `127.0.0.1` by default.
- All filesystem tools are path-jailed to a configurable workspace root.
- Sandbox runner strips environment variables, enforces timeouts, caps output,
  and isolates subprocesses to a new process group so killing on timeout works.
- Writes default to `require_for_writes` approval mode in the UI; the agent
  cannot edit files or run shell commands without an explicit approve event.
- API keys are stored in SQLite + pushed to process env at boot; they never
  leave the machine. The Settings page shows only previews after save.

For multi-user / internet-exposed deployments, planned upgrades:
- OIDC ingress (authentik / Keycloak)
- Docker / gVisor sandbox (drop-in: same `SandboxResult` interface)
- Per-user workspaces + quotas
- Langfuse trace export
