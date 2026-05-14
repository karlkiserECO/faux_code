# faux_code

A self-hosted, free, multi-provider AI chat and agentic coding workbench.
Think ChatGPT + Cursor + Claude Code, but assembled from open-source parts and
free remote APIs, all running locally on your machine.

```
                  ┌────────────────────────────────────┐
                  │  Next.js UI (chat / agent / code)  │
                  └─────────────────┬──────────────────┘
                                    │
                  ┌─────────────────▼──────────────────┐
                  │      FastAPI gateway (SSE)         │
                  │  /v1/chat  /v1/agents  /v1/rag …   │
                  └─────┬──────────┬─────────┬─────────┘
                        │          │         │
       ┌────────────────┘          │         └────────────────┐
       ▼                           ▼                          ▼
 ┌──────────┐               ┌─────────────┐           ┌──────────────┐
 │ Provider │               │ Agent loop  │           │  RAG store   │
 │  router  │               │ (ReAct +    │           │  (LanceDB +  │
 │          │               │   tools)    │           │  embeddings) │
 └─────┬────┘               └──────┬──────┘           └──────────────┘
       │                            │
   ┌───┴────┬─────────┬───────┐    ▼
   ▼        ▼         ▼       ▼  Sandbox runner (subprocess + path jail)
 Ollama  Groq   OpenRouter  Gemini    ├── shell, python
 (local) HF     Cerebras    vLLM      ├── fs read/write/edit
                                      └── web_search, web_fetch
```

## What you get

- **Chat** — ChatGPT-style streaming UI with conversation history, markdown +
  syntax-highlighted code, and a model picker.
- **Agent mode** — give the agent a goal, watch it plan, call tools, edit
  files, run shell + Python in a sandbox, and stream every step.
- **Code workspace** — Cursor-style three-pane view: file tree + Monaco editor
  + side-panel code agent.
- **Documents (RAG)** — upload PDFs / code / text, get a local semantic index
  the agent can query with `rag_search`.
- **Multi-provider router** — local Ollama plus free remote APIs:
  - **Groq** (very fast Llama / Qwen)
  - **OpenRouter** (many `:free` models including DeepSeek-R1)
  - **Google Gemini** (free tier, OpenAI-compatible)
  - **Cerebras** (very fast Llama)
  - **HuggingFace Inference Router**
  - Optional self-hosted **vLLM**
- **CLI** — `faux-code chat` and `faux-code agent` for terminal-first usage,
  auto-starts the backend.
- **OpenAI-compatible API** — point Continue, Aider, or any OpenAI-compatible
  tool at `http://127.0.0.1:8765/v1`.

## Quick start (macOS / Linux)

```bash
# 1. Install Ollama + pull default models (one-time)
./infra/scripts/install_ollama.sh
./infra/scripts/pull_models.sh        # ~10 GB

# 2. Boot the dev stack (backend + frontend)
./infra/scripts/dev.sh
```

Open <http://localhost:3000>.

### Defaults on a 16 GB Apple Silicon

| Role        | Model                                      | Size  |
|-------------|--------------------------------------------|-------|
| Chat        | `llama3.1:8b-instruct-q4_K_M`              | 4.7 GB |
| Code agent  | `qwen2.5-coder:7b-instruct-q4_K_M`         | 4.4 GB |
| Embeddings  | `nomic-embed-text`                          | 270 MB |

Override with `OLLAMA_DEFAULT_CHAT`, `OLLAMA_DEFAULT_CODE`,
`OLLAMA_DEFAULT_EMBED` env vars, or in the Settings page.

## Free remote providers (optional, $0)

Add any of these in Settings to unlock frontier-quality models without
spending money:

| Provider     | Why you'd use it                       | Get a key |
|--------------|----------------------------------------|-----------|
| Groq         | 300+ tok/s Llama 3.3 70B / Qwen2.5    | https://console.groq.com |
| OpenRouter   | Many `:free` models (DeepSeek-R1, etc.)| https://openrouter.ai |
| Gemini       | Gemini 2.0 Flash, generous free tier  | https://aistudio.google.com |
| Cerebras     | 1000+ tok/s Llama 3.3 70B             | https://cloud.cerebras.ai |
| HuggingFace  | Wide model catalog through router     | https://huggingface.co/settings/tokens |
| Tavily       | High-quality web search (1000/mo free)| https://tavily.com |

Without any keys: still works on local Ollama plus Wikipedia + DuckDuckGo web
search.

## CLI

```bash
faux-code chat                                # interactive
faux-code chat "explain transformers"         # one-shot
faux-code agent "add type hints to src/utils.py" --workspace .
faux-code models
faux-code pull qwen2.5-coder:7b-instruct
```

## OpenAI-compatible endpoint

Point Continue or Aider at:
```
Base URL: http://127.0.0.1:8765/v1
API key:  any value
Model:    any from /v1/models
```

## Layout

```
faux_code/
  backend/       FastAPI gateway, providers, agent loop, tools, RAG, sandbox
  frontend/      Next.js 15 web UI
  cli/           faux-code terminal binary
  infra/         install scripts, docker-compose, Dockerfiles
  docs/          architecture, runbooks, security notes
  tests/         eval task suite (canonical agent tasks)
  workspaces/    agent default workspace root (git-ignored)
```

## Tests

```bash
./.venv/bin/python -m pytest backend/tests -v
./.venv/bin/python -m tests.evals.run_evals --model qwen2.5-coder:7b-instruct
```

## Privacy

Local-first by design:
- Backend binds to `127.0.0.1`.
- Local Ollama keeps data on disk.
- API keys live in SQLite next to your conversations; they never leave your
  machine.
- Remote providers only see content you explicitly route to them (the model
  picker shows which provider serves the active model).

## Roadmap

- [ ] Per-conversation provider lock ("privacy mode = local only").
- [ ] BGE-M3 + reranker for stronger RAG.
- [ ] Vision / image input for multimodal models.
- [ ] OIDC ingress for multi-user deployments.
- [ ] Docker / gVisor sandbox upgrade path.
- [ ] Langfuse hook for trace observability.
- [ ] Streaming tool-call calls into UI step-by-step.

## License

MIT
