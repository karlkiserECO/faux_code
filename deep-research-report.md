# Building a Free Self-Hosted Claude-Like Code and Chat Agent

## Executive summary

A practical, self-hosted system that gets close to ChatGPT plus Cursor plus “agent mode” is absolutely possible in 2026, but the best design depends on whether you are optimizing for simplicity on one machine or for safe multi-user serving at higher concurrency. The most credible local-first stack today is: **Open WebUI** for a ChatGPT-like browser UI, **Continue** for Cursor-like IDE workflows, **Ollama** or **llama.cpp** for simple local serving, and **Qdrant** or **pgvector** for retrieval. For a stronger team or cloud deployment, the best default is **vLLM** as the OpenAI-compatible serving layer, **Open WebUI** or **LibreChat** as the front end, **OpenHands** for agentic software tasks inside a sandbox, **Qdrant/pgvector** for RAG, **Langfuse + OpenTelemetry + Prometheus/Grafana** for observability, and **OIDC-authenticated ingress** in front of everything. vLLM is the most future-proof serving choice in this stack because it exposes an OpenAI-compatible API and supports distributed tensor/pipeline parallel serving; Hugging Face’s own TGI docs now describe TGI as maintenance mode and explicitly recommend newer engines such as vLLM, SGLang, and local engines like llama.cpp or MLX going forward. citeturn24view3turn23search2turn23search14turn24view0

For models, the highest-confidence recommendations are these. For **coding and agentic software work**, **Qwen3-Coder-30B-A3B-Instruct** is currently the most compelling open-weight balance of capability and deployability: it is Apache 2.0 licensed, has 30.5B total and 3.3B activated parameters, and supports a native **262,144-token** context window; its model card explicitly targets agentic coding and platform integrations. **Devstral Small 1.0** is another top pick for software agents: Mistral and All Hands position it specifically for software engineering agents, it is **Apache 2.0**, has **24B** parameters, **128k** context, and is advertised as runnable on a **single RTX 4090** or a **32 GB Mac**. For **general chat**, **Qwen3-32B** is the strongest broadly useful Apache-2.0 option in this class, with **32.8B** parameters and **32,768 native / 131,072 with YaRN** context, plus explicit agent/tool capability claims. **Mistral Small 3.1** is the best “one-model-for-most-things” dense open model for many deployments: **Apache 2.0**, **128k** context, advertised **150 tokens/sec**, and also positioned as runnable on a single **RTX 4090** or **32 GB Mac**. If you need a smaller lightweight option, **Granite 3.3 8B Instruct** is a credible enterprise-friendly fallback with **128k** context under **Apache 2.0**. citeturn31view0turn32view1turn28view1turn31view1turn32view0turn36view1turn36view2turn28view6

The largest gap between a good self-hosted stack and the hosted frontier is not the UI. It is the combination of frontier model quality, eval discipline, and safe orchestration. That means the right goal is **functional parity** rather than exact model parity: build a modular system that can handle chat, code editing, retrieval, tool calling, and safe execution, then swap models as open models improve. Also, do **not** build your production system around reverse-engineered or leaked Claude wrappers. Public repos exist that acknowledge using Claude’s internal web APIs, exported cookies, or leaked proprietary source, but those approaches are operationally fragile, create clear legal and security risk, and are the opposite of a safe self-hosted design. Anthropic has also publicly tightened treatment of some third-party subscription-driven agent usage. A robust self-hosted system should instead stick to open models and documented local or OpenAI-compatible APIs. citeturn22search0turn22search10turn22search1turn22news50turn22news51

## Model landscape and ranked recommendations

The most useful way to choose models is by **deployment class** rather than benchmark obsession. Dense 8B models are the safest default for low-latency personal use. Dense 24B–32B models are the current sweet spot for serious local chat and coding on a 24–48 GB class machine. MoE coding models such as Qwen3-Coder-30B-A3B offer better effective capability per unit of active compute, but you still need memory for the full weights. Very large reasoning models such as **DeepSeek-R1** are impressive, but the upstream R1 checkpoint is a **671B-total / 37B-active** MoE with **128k** context and is not a practical self-host target unless you already operate a serious GPU cluster; its **distilled** variants are the practical entry point. citeturn31view0turn31view1turn35view1turn35view2turn35view3

### Recommended model shortlist

| Model | Primary use | Official model facts | Practical self-host fit | Latency tier | Licensing posture | Recommended deployment |
|---|---|---|---|---|---|---|
| **Qwen3-Coder-30B-A3B-Instruct** | Best overall code + agentic coding | 30.5B total, 3.3B activated, **262,144 native context**, Apache-2.0, explicitly positioned for agentic coding and long-repo work. citeturn31view0turn32view1 | Best on **48 GB VRAM** or aggressive 4-bit quantization on **24 GB**; good cloud fit on A100 40/80 or H100. | Medium | True open-source style license | Cloud or high-end local |
| **Devstral Small 1.0** | Code agents, multi-file edits, SWE tasks | **24B**, **128k** context, Apache-2.0; Mistral says it is built for software engineering agents and can run on a **single RTX 4090** or **32 GB Mac**. citeturn28view1 | Strong local high-end default; practical on 24 GB GPU. | Medium | True open-source style license | Local or cloud |
| **Qwen3-32B** | Best general chat + reasoning + tools | **32.8B**, **32,768 native / 131,072 with YaRN**, Apache-2.0; supports thinking/non-thinking modes and agent capabilities. citeturn31view1turn32view0 | Best on **48 GB VRAM**; workable on **24 GB 4-bit** with some tradeoffs. | Medium-slow | True open-source style license | Local enthusiast or cloud |
| **Mistral Small 3.1** | Best one-model generalist | **128k** context, Apache-2.0, multimodal, function calling, advertised **150 tok/s**, runnable on **single RTX 4090** or **32 GB Mac**. citeturn36view1turn36view2turn36view3 | Excellent for local “one model does most things.” | Medium-fast | True open-source style license | Local or cloud |
| **Granite 3.3 8B Instruct** | Lightweight chat/reasoning/coding | **8B**, **128k** context, Apache-2.0; IBM highlights gains in reasoning, coding, and instruction following. citeturn28view6 | Comfortable on **12–16 GB** with quantization; good shared CPU/GPU fallback. | Fast | True open-source style license | Local low-cost |
| **Llama 3.1 8B** | Broad compatibility fallback | **8B**, **128k** context, widespread tooling support, but under the **Llama 3.1 Community License**, not Apache/MIT. citeturn34view2turn34view3turn34view0 | Easy to run on **12–16 GB** quantized. | Fast | Source-available, custom terms | Local fallback |
| **DeepSeek-R1 family** | Reasoning-heavy planner, not default runtime | Upstream model is **671B total / 37B active**, **128k**, MIT; distills are available from **1.5B to 70B**. citeturn35view1turn35view2turn35view3 | Use the **distills**, not the upstream checkpoint, unless you have a real cluster. | Slow upstream; distills vary | MIT upstream, derivative-license caveats on distills | Cloud planner or optional reasoning tier |
| **StarCoder2-15B** | Fill-in-the-middle and code completion specialist | **15B**, trained on **600+ languages**, **16,384** context, BigCode OpenRAIL-M; model card says it is **not an instruction model**. citeturn29view3 | Reasonable specialist model, but weaker as a general chat agent. | Medium | OpenRAIL-style | Completion/FIM niche |

A practical ranking for **code** is: **Qwen3-Coder-30B-A3B-Instruct**, **Devstral Small 1.0**, **Qwen2.5-Coder family** for smaller hardware, **DeepSeek-R1 distills** if you specifically want a stronger planner rather than a faster editor, and **StarCoder2** when fill-in-the-middle and raw code completion matter more than conversational quality. Qwen2.5-Coder’s own card still frames the family as a strong code-specific line and states that the 32B variant reached state-of-the-art open code performance at release. citeturn31view0turn28view1turn33view1turn28view3

A practical ranking for **chat** is: **Qwen3-32B**, **Mistral Small 3.1**, **Llama 3.3 70B** if you can afford the hardware, **Granite 3.3 8B** where licensing simplicity and cost matter, and **Llama 3.1 8B** as the smallest broadly supported compatibility option. If your organization is strict about OSI-style licensing, bias toward **Apache-2.0/MIT** models such as **Qwen3**, **Devstral**, **Mistral Small 3.1**, **Granite**, and **DeepSeek-R1**; treat **Llama** as a high-quality **source-available** family with custom downstream obligations, not as an Apache/MIT equivalent. citeturn31view1turn36view1turn28view6turn34view0turn35view3turn37search8

### Hardware, latency, and marginal run cost

The cleanest way to size hardware is by model class. An **8B dense model** is comfortable on a **12–16 GB** card when quantized; a **24B dense model** generally wants **24–48 GB** depending on quantization and context; a **30B-class MoE** still stores the full weights, so assume **24 GB is aggressive**, **48 GB is healthy**; and a **70B dense model** is normally a **multi-GPU** or **80 GB-class** decision. Ollama’s own context guidance is relevant here: by default it scales context by available VRAM, and for coding tools, web search, and agents it recommends **at least 64k tokens** when possible. citeturn23search12turn23search0

For operating cost, the **marginal electricity** on a local workstation is usually much smaller than the hardware amortization. With the February 2026 U.S. residential average at **17.65¢/kWh**, an RTX 4090’s official **450 W** board power implies roughly **$0.08/hour** for the GPU alone at full draw; an NVIDIA A10 at **150 W** implies roughly **$0.03/hour**. A 4090 workstation with CPU, memory, storage, and cooling included is more realistically in the **$0.09–$0.12/hour** all-in electricity range under sustained generation load, excluding purchase cost. On cloud GPUs, official Lambda on-demand pricing is much simpler: **V100 16 GB $0.79/GPU-hour**, **A100 40 GB $1.99**, **A100 80 GB $2.79**, and **H100 80 GB $3.99**. AWS’s G6e family is worth special attention if you prefer AWS primitives: it uses the **L40S 48 GB** GPU and is explicitly marketed by AWS as a cost-efficient inference target for gen-AI deployments. citeturn17view0turn14search1turn14search3turn11search1turn11search0turn12search3

## Interfaces, wrappers, and orchestration tools

The right mental model is to separate the system into **four layers**: the **model runner**; the **developer surface**; the **agent or application framework**; and the **retrieval/sandbox/ops** layer. A lot of projects overlap, but most problems in self-hosting come from expecting one tool to do all four jobs. citeturn20search4turn21search1turn4search8turn4search13

### Comparison of wrappers and interfaces

| Tool | Category | Strengths | Weaknesses / risks | Best fit |
|---|---|---|---|---|
| **Open WebUI** | Web UI | Fastest route to a ChatGPT-like self-hosted UI; supports Ollama, OpenAI-compatible providers, RAG, plugins, SSO, and Helm deployment. citeturn20search0turn20search4turn20search3turn20search9 | Powerful but dangerous plugin surface: official docs warn that Tools and Functions execute arbitrary Python on your server and should be restricted to trusted admins. citeturn20search2turn20search17 | Best browser UI default |
| **LibreChat** | Web UI + agents | Broad provider support, custom endpoints, MCP, code interpreter, agents, authentication, horizontal scaling with Redis. citeturn3search10turn3search2 | Heavier than Open WebUI; more moving parts. | Team multi-user UI |
| **Continue** | IDE assistant | Strong Cursor-like workflow inside IDEs; explicit roles for chat, autocomplete, edit, apply, embed, rerank; works with Ollama or any OpenAI-compatible endpoint. citeturn21search0turn21search1turn21search12turn21search15 | Needs careful model-role assignment to feel good. | Best IDE-native experience |
| **Aider** | Terminal code agent | Excellent git-centric pair-programming; supports OpenAI-compatible endpoints; architect/code/ask modes are practical for serious coding. citeturn4search3turn21search2 | CLI-first, not a full chat web surface. | Terminal-heavy developers |
| **OpenHands** | Software agent | Purpose-built for software tasks; official docs recommend sandboxing with Docker; local-LLM guide currently recommends strong coding models such as Qwen3-Coder-30B-A3B-Instruct. citeturn19search2turn19search10turn21search3 | Requires better models and more safety controls than a simple chat app. | Agentic workflows and repo automation |
| **Ollama** | Local runner | Easiest local model packaging and serving; Modelfiles and context-length controls make local experimentation simple. citeturn23search1turn23search0 | Great for single-user or small setups, but not the best choice for high-concurrency multi-user serving. | Simple local serving |
| **llama.cpp server** | Local runner / API | Very strong for CPU/GGUF/local work; official server supports OpenAI-compatible routes, Anthropic Messages compatibility, continuous batching, monitoring, reranking, and tool use. citeturn23search3 | Better for local inference than large-scale shared serving. | Local and edge deployments |
| **vLLM** | Shared GPU serving | OpenAI-compatible API, strong throughput, tensor/pipeline parallelism, multi-node serving via Ray, and a large ecosystem around it. citeturn24view3turn23search2turn23search14 | More operational complexity than Ollama/llama.cpp. | Best shared inference plane |
| **Hugging Face TGI** | Shared GPU serving | Prometheus and OpenTelemetry built in; mature; still useful if you already standardize on HF tooling. citeturn24view2 | HF docs now describe it as **maintenance mode** and recommend vLLM/SGLang/local engines going forward. citeturn24view0turn24view2 | Legacy HF-heavy deployments |
| **Hugging Face Inference Endpoints** | Managed serving | Dedicated managed infrastructure with autoscaling, logs, metrics, and support for engines such as vLLM and TGI. citeturn24view1 | Not free and not self-hosted in the strict sense. | Burst capacity / managed fallback |
| **LangChain** | Agent framework | Open-source agent framework with production-ready agent primitives and broad integrations. citeturn4search8turn4search12 | Framework, not a UI or serving system. | Custom app composition |
| **LlamaIndex** | RAG framework | Strong focus on RAG, workflows, tool calling, and observability. citeturn4search13turn4search1 | Same caveat: framework, not a complete product surface. | Retrieval-centered apps |
| **OpenAssistant** | Historical open project | Important community milestone and reference implementation for an open assistant. citeturn27search0turn27search5 | Public release cadence appears largely stalled; latest GitHub release shown is from **November 2023**. citeturn27search7 | Historical reference, not first-choice 2026 deploy |
| **Unofficial Claude web wrappers / leaked Claude code repos** | Unauthorized wrappers | They can mimic Claude-like UX or APIs. citeturn22search0turn22search2turn22search10 | High operational, legal, and security risk: unofficial web APIs, exported cookies, or leaked proprietary code; avoid for any “safe system.” citeturn22search0turn22search10turn22search1turn22news50turn22news51 | **Do not use in production** |

The safest “Claude-like” UX path is therefore not to chase leaked wrappers. It is to reproduce the **interaction model** with open components: browser chat, long context, artifact generation, code editing, tool use, retrieval, and sandboxed execution. Open WebUI gives the browser/chat side, Continue gives the IDE side, llama.cpp or vLLM give the API surface, and OpenHands or Aider give the deeper agent loop. That combination is much safer and more maintainable than unofficial browser-cookie shims. citeturn20search4turn21search0turn23search3turn24view3turn19search2turn21search2

## Reference architectures and deployment patterns

For a **single-user or small-lab deployment**, the winning pattern is to keep the stack extremely thin: one model runner, one UI, one retrieval store, local auth, and no autonomous execution by default. For a **team** or **internet-exposed** deployment, you want clear separation between **ingress/auth**, **UI**, **model serving**, **retrieval**, **sandbox**, and **observability**. Open WebUI’s own Helm docs underline that production multi-node deployments should assume **PostgreSQL, Redis, a vector database, shared storage, and content extraction** as external infrastructure dependencies. citeturn20search3

```mermaid
flowchart LR
    user[Developer] --> ide[VS Code or JetBrains + Continue]
    user --> webui[Open WebUI]
    ide --> runner[Ollama or llama.cpp]
    webui --> runner
    webui --> vectordb[Qdrant or pgvector]
    webui --> files[Local docs / repos]
    runner --> logs[Local logs]
    classDef box fill:#f7f7f7,stroke:#999,stroke-width:1px;
    class user,ide,webui,runner,vectordb,files,logs box;
```

That single-server design favors **Ollama** if you want the easiest setup and **llama.cpp server** if you need a very lightweight OpenAI-compatible or Anthropic-Messages-compatible endpoint with GGUF models. It is the right design for private local usage because the blast radius is small and the admin burden is low. Keep plugins and arbitrary execution disabled until you have a reason to turn them on. citeturn23search3turn23search1turn20search2turn20search17

```mermaid
flowchart TD
    internet[Users / IDEs] --> ingress[Caddy or Traefik + OIDC]
    ingress --> ui[Open WebUI or LibreChat]
    ingress --> api[OpenAI-compatible gateway]
    api --> vllm[vLLM model pool]
    ui --> rag[Retriever service]
    rag --> vectordb[Qdrant or pgvector]
    rag --> object[Document/object storage]
    ui --> agent[OpenHands]
    agent --> sandbox[Docker sandbox or gVisor/Firecracker]
    ui --> obs[Langfuse / OTel]
    api --> obs
    sandbox --> obs
    obs --> monitor[Prometheus + Grafana]
    auth[Authentik or Keycloak] --> ingress
```

For the distributed design, **vLLM** is the best default inference plane because it gives OpenAI-compatible APIs and supports tensor- and pipeline-parallel inference. **Qdrant** is a sensible dedicated vector default because it is straightforward to self-host and purpose-built for vector retrieval; **pgvector** is the better answer if your team already lives in Postgres and values operational simplicity over having a separate vector service. **OpenSearch** is logical only if you already depend on it for broader search workloads. citeturn24view3turn23search2turn8search0turn8search1turn8search3

On the retrieval side, a simple but strong stack is **BGE-M3** for embeddings and **BGE reranker v2** or a similar reranker on top; BGE-M3 explicitly supports dense, sparse, and multi-vector retrieval and more than 100 languages, while Qdrant or pgvector handle storage and retrieval orchestration. If you want long-document embeddings, **jina-embeddings-v3** supports **8192-token** input sequences. citeturn18search8turn18search0turn18search3turn18search2

## Local deployment on consumer hardware

The consumer-hardware target should optimize for **privacy, simplicity, and low blast radius**. The clean default is: **Ollama** for local model serving, **Open WebUI** for browser chat, **Continue** for IDE-native workflows, and optional **Qdrant** for retrieval. If you have a **24 GB GPU**, target **Devstral Small 1.0**, **Mistral Small 3.1**, or a quantized **Qwen3-32B / Qwen3-Coder-30B-A3B-Instruct** depending on how patient you are about latency. If you have **12–16 GB**, use **Granite 3.3 8B**, **Llama 3.1 8B**, or a smaller Qwen2.5-Coder variant for code tasks. Ollama’s own docs recommend setting larger contexts for coding tools and agentic workflows and specifically call out **64k** as a useful target. citeturn28view1turn36view1turn31view1turn31view0turn28view6turn34view3turn23search12turn23search0

### Local setup steps

1. Install **Docker** and, if you are on Linux, run it in **rootless mode**. Docker’s own security docs describe rootless mode as running the daemon as a non-root user, which is the correct default for a self-hosted AI stack on a workstation. Also keep Docker’s default **seccomp** profile enabled. citeturn25search0turn5search2

2. Install **Ollama** and start it with a larger context limit. Ollama documents `OLLAMA_CONTEXT_LENGTH` for this purpose. citeturn23search0turn23search12

```bash
export OLLAMA_CONTEXT_LENGTH=65536
ollama serve
```

3. Pull or import your models. Exact Ollama tags vary by registry and release, so verify the current names in your model registry, but a workable split is:
   - chat: a 24B–32B general model
   - code: a specialized coding model or a second chat model with better code performance
   - embeddings: a long-context embedding model

```bash
# Examples only — verify the exact current registry tags you intend to use.
ollama pull <chat-model-tag>
ollama pull <code-model-tag>
ollama pull <embedding-model-tag>
```

4. Launch **Open WebUI** and **Qdrant** with Docker Compose.

```yaml
# docker-compose.local.yml
services:
  qdrant:
    image: qdrant/qdrant:latest
    restart: unless-stopped
    volumes:
      - qdrant_data:/qdrant/storage
    ports:
      - "6333:6333"
    security_opt:
      - no-new-privileges:true

  open-webui:
    image: ghcr.io/open-webui/open-webui:main
    restart: unless-stopped
    ports:
      - "3000:8080"
    environment:
      WEBUI_AUTH: "True"
      OLLAMA_BASE_URL: "http://host.docker.internal:11434"
      VECTOR_DB: "qdrant"
      QDRANT_URL: "http://qdrant:6333"
    volumes:
      - openwebui_data:/app/backend/data
    depends_on:
      - qdrant
    extra_hosts:
      - "host.docker.internal:host-gateway"
    security_opt:
      - no-new-privileges:true
    read_only: false

volumes:
  qdrant_data:
  openwebui_data:
```

```bash
docker compose -f docker-compose.local.yml up -d
```

5. Install **Continue** in VS Code or JetBrains and point it to your local stack. Continue’s docs explicitly support role-based model assignment and self-hosted OpenAI-compatible or Ollama backends. citeturn21search0turn21search1turn21search12

```yaml
# ~/.continue/config.yaml
name: local-stack
version: 1
models:
  - name: local-chat
    provider: ollama
    model: <chat-model-tag>
    roles: [chat, edit, apply]
  - name: local-autocomplete
    provider: ollama
    model: <small-code-model-tag>
    roles: [autocomplete]
  - name: local-embed
    provider: ollama
    model: <embedding-model-tag>
    roles: [embed]
context:
  - provider: code
  - provider: docs
rules:
  - "Never run shell commands automatically."
  - "Prefer minimal diffs and explain risky changes."
```

6. Keep the **plugin surface tight**. Open WebUI’s own docs are unusually explicit here: Tools and Functions execute arbitrary Python on the server, and giving users the ability to create or import them is effectively giving shell access. For a consumer-hardware deployment, leave custom Tools/Functions off unless you are the only admin and you have reviewed the code. citeturn20search2turn20search17

### Local hardening baseline

For a “safe by default” local box, keep the model runner and web UI bound to **localhost** unless you really need LAN access; use **rootless Docker**, keep containers **non-privileged**, retain **seccomp**, and avoid mounting sensitive host paths into the UI. If you later add autonomous code execution, prefer a separate sandbox service rather than granting your chat UI shell-level powers. OWASP’s Docker guidance also recommends dropping unnecessary capabilities and avoiding `--privileged` containers entirely. citeturn25search0turn5search2turn25search1

## Cloud GPU deployment

The cloud-target design should assume **multiple users, isolated auth, safe execution, observability, and rollback discipline**. The best default stack is **vLLM + Open WebUI + OpenHands + Qdrant + Langfuse + OIDC ingress**, with **Prometheus/Grafana** for metrics and either **Docker sandboxing** or a stronger runtime such as **gVisor** or **Firecracker** for untrusted code execution. OpenHands’ own docs recommend Docker sandboxing as the default local sandbox provider, and gVisor plus Firecracker both exist precisely to improve workload isolation for untrusted or multi-tenant code. citeturn19search2turn19search10turn5search0turn5search1

### Cloud VM setup

Use a GPU VM that matches the model class:
- **A100 40 GB** is a practical minimum for many 24B–32B workloads.
- **A100 80 GB** or **H100 80 GB** is the comfortable tier for 32B+ models with larger contexts or concurrency.
- Official Lambda pricing is **$1.99/h for A100 40 GB**, **$2.79/h for A100 80 GB**, and **$3.99/h for H100 80 GB**. citeturn11search1

Install a model server:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install vllm

vllm serve Qwen/Qwen3-Coder-30B-A3B-Instruct \
  --host 0.0.0.0 \
  --port 8000 \
  --api-key change-me \
  --max-model-len 262144 \
  --gpu-memory-utilization 0.92
```

vLLM exposes an OpenAI-compatible endpoint, so most tools that expect an OpenAI-style API can target it directly. For multi-GPU and multi-node deployments, vLLM supports tensor and pipeline parallelism and uses Ray for multi-node execution. citeturn24view3turn23search2turn23search14

Place **Open WebUI** behind a reverse proxy with OIDC. Open WebUI documents SSO via OAuth/OIDC and has an official Helm path for Kubernetes deployment. If you prefer self-hosted identity, **authentik** is a straightforward OIDC provider and explicitly supports self-hosted SSO. citeturn20search9turn20search3turn10search12

### Cloud Docker Compose example

```yaml
# docker-compose.cloud.yml
services:
  qdrant:
    image: qdrant/qdrant:latest
    restart: unless-stopped
    volumes:
      - qdrant_data:/qdrant/storage

  langfuse:
    image: langfuse/langfuse:2
    restart: unless-stopped
    environment:
      DATABASE_URL: postgresql://langfuse:langfuse@postgres:5432/langfuse
      NEXTAUTH_SECRET: change-me
      SALT: change-me-too
    depends_on:
      - postgres

  postgres:
    image: postgres:16
    restart: unless-stopped
    environment:
      POSTGRES_USER: langfuse
      POSTGRES_PASSWORD: langfuse
      POSTGRES_DB: langfuse
    volumes:
      - pg_data:/var/lib/postgresql/data

  open-webui:
    image: ghcr.io/open-webui/open-webui:main
    restart: unless-stopped
    environment:
      OPENAI_API_BASE_URL: http://vllm:8000/v1
      OPENAI_API_KEY: change-me
      VECTOR_DB: qdrant
      QDRANT_URL: http://qdrant:6333
      ENABLE_OAUTH_SIGNUP: "false"
      OAUTH_CLIENT_ID: your-client-id
      OAUTH_CLIENT_SECRET: your-client-secret
      OPENID_PROVIDER_URL: https://auth.example.com/application/o/yourapp/.well-known/openid-configuration
    depends_on:
      - qdrant
      - vllm

  vllm:
    image: vllm/vllm-openai:latest
    command:
      - --model
      - Qwen/Qwen3-Coder-30B-A3B-Instruct
      - --host
      - 0.0.0.0
      - --port
      - "8000"
      - --api-key
      - change-me
      - --max-model-len
      - "262144"
    deploy:
      resources:
        reservations:
          devices:
            - capabilities: [gpu]

volumes:
  qdrant_data:
  pg_data:
```

This compose pattern gives you a real gatewayed application surface while keeping the model runner and vector DB off the public edge. Add **OpenHands** only after the chat and IDE workflows are stable; agentic execution amplifies every weakness in your model, sandbox, and observability story. citeturn19search2turn9search0turn20search9

### Kubernetes base manifests

Below is a deliberately minimal pattern for a production-ish cluster. It assumes an NVIDIA GPU node pool, OIDC ingress, and a `RuntimeClass` such as gVisor where appropriate. Kubernetes’ own docs recommend the **Restricted** Pod Security profile for more security-sensitive workloads, and NetworkPolicies are the correct mechanism for pod-to-pod traffic restriction. citeturn25search2turn25search3turn25search5

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: vllm
  namespace: ai
spec:
  replicas: 1
  selector:
    matchLabels:
      app: vllm
  template:
    metadata:
      labels:
        app: vllm
    spec:
      runtimeClassName: nvidia
      containers:
        - name: vllm
          image: vllm/vllm-openai:latest
          args:
            - --model=Qwen/Qwen3-Coder-30B-A3B-Instruct
            - --host=0.0.0.0
            - --port=8000
            - --api-key=$(API_KEY)
            - --max-model-len=262144
          env:
            - name: API_KEY
              valueFrom:
                secretKeyRef:
                  name: vllm-secret
                  key: api-key
          ports:
            - containerPort: 8000
          resources:
            limits:
              nvidia.com/gpu: "1"
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: false
            runAsNonRoot: true
            seccompProfile:
              type: RuntimeDefault
---
apiVersion: v1
kind: Service
metadata:
  name: vllm
  namespace: ai
spec:
  selector:
    app: vllm
  ports:
    - port: 8000
      targetPort: 8000
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: vllm-ingress
  namespace: ai
spec:
  podSelector:
    matchLabels:
      app: vllm
  policyTypes: [Ingress, Egress]
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: open-webui
  egress:
    - {}
```

For **Open WebUI** in Kubernetes, use the official Helm chart path rather than inventing your own large template set. Its Helm docs explicitly target EKS, AKS, GKE, OpenShift, Rancher, and self-managed Kubernetes. citeturn20search3

## Safety, privacy, monitoring, and operations

A safe deployable system should assume the OWASP LLM threat categories are real from day one: **prompt injection**, **sensitive information disclosure**, and supply-chain or tool misuse are not edge cases. The biggest architectural rule is this: **treat model output as untrusted input**, especially when an agent can call tools, fetch the web, or execute code. Sandboxing, least privilege, and telemetry matter more than an extra benchmark point. citeturn5search3

### Safety controls that are worth implementing immediately

Use a **two-tier safety model**. First, add lightweight **input/output filtering** with a model such as **Prompt Guard** or **Llama Guard 4**, plus programmable dialog guardrails through **NeMo Guardrails** or **Guardrails AI** for topic control, jailbreak handling, and structured validation. Second, keep **execution authorization** separate: even if the model is allowed to propose a command, it should only run in a sandbox with least privilege and explicit policy. Meta’s Prompt Guard and Llama Guard families, NVIDIA’s NeMo Guardrails, and Guardrails AI all exist specifically to make these controls implementable. citeturn7search4turn6search0turn6search3turn6search7turn7search2turn7search6

If you allow code execution, use **Docker sandboxing at minimum**, but prefer **gVisor** or **Firecracker** in multi-user or internet-exposed environments. gVisor is explicitly positioned as an extra security layer for containers, and Firecracker is purpose-built for secure multi-tenant microVM workloads. **nsjail** is a lighter Linux process-isolation option when you need a focused execution jail. OpenHands already leans into sandboxed execution with Docker as its recommended default. citeturn5search0turn5search1turn26search4turn19search2turn19search10

Apply **container hardening** everywhere else: run Docker in **rootless mode**, keep **seccomp** on, do not use privileged containers, drop unnecessary capabilities, and use **no-new-privileges**. On Kubernetes, enforce **Pod Security Standards Restricted**, use **NetworkPolicies**, and keep the model server, vector DB, and databases on private networks only. These are boring controls, but they are exactly the ones that reduce compromise impact in real deployments. citeturn25search0turn5search2turn25search1turn25search2turn25search3

### Monitoring, eval, and red-team testing

For observability, use **Langfuse** for trace-level LLM telemetry, **OpenTelemetry** for standardized spans/logs/metrics, and **Prometheus/Grafana** for system dashboards and alerts. Langfuse’s self-hosting docs cover Docker Compose deployment and upgrades; TGI and other serving frameworks expose metrics and tracing hooks already, and OpenTelemetry is the standard layer for Python and service instrumentation. For security and quality red-teaming, add a repeatable **Promptfoo** suite before every model or prompt release. citeturn9search0turn9search11turn9search3turn24view2turn6search2turn6search6

A sane release workflow is:
1. Pin model revisions, container tags, and prompt versions in git.
2. Run offline evals and red-team scenarios on a **staging** stack.
3. Compare traces and failure rates in Langfuse.
4. Promote to production only if hallucination rate, sandbox escapes, cost, and latency stay within target.
5. Keep rollback to the previous model revision one command away.

That workflow is mostly architecture and process rather than vendor magic, but it aligns well with the official upgrade and self-hosting story of Langfuse and with the observability surfaces exposed by modern serving engines. citeturn9search0turn24view2turn24view3

### Privacy, updates, and cost table

Self-hosting is strongest when you keep **documents, embeddings, logs, and conversation history** inside your environment. Open WebUI, Qdrant, pgvector, and Langfuse can all be self-hosted; if you do that and keep your LLM local, your data does not need to leave your infrastructure. The main privacy exceptions are any external APIs or identity providers you choose to integrate. This is also why unmanaged plugins and unofficial wrappers are so risky: they bypass exactly the boundary you were trying to control. citeturn20search4turn8search0turn8search1turn9search0turn22search0turn22search10

| Deployment option | Typical capability envelope | Marginal or rental cost | Practical note |
|---|---|---|---|
| **Local workstation with RTX 4090** | Best local target for 24B dense or aggressive 30B-class quantized use; Mistral Small 3.1 and Devstral explicitly target this class. citeturn36view1turn28view1 | About **$0.08/h GPU-only** at 17.65¢/kWh and 450 W, roughly **$0.09–$0.12/h** including host power. citeturn17view0turn14search1 | Lowest recurring cost; hardware purchase dominates. |
| **Local workstation with 12–16 GB GPU** | Comfortable for 8B-class chat/code models, lighter retrieval, and IDE workflows. citeturn28view6turn34view3 | Typically well under **$0.05/h** electricity. | Best for Granite/Llama/smaller Qwen. |
| **Lambda A100 40 GB** | Good entry cloud tier for many 24B–32B deployments. | **$1.99/GPU-hour**. citeturn11search1 | Excellent testing/staging target. |
| **Lambda A100 80 GB** | Comfortable 32B+ or higher concurrency. | **$2.79/GPU-hour**. citeturn11search1 | Strong production inference tier. |
| **Lambda H100 80 GB** | Best single-GPU cloud tier in this list for high-throughput vLLM serving. | **$3.99/GPU-hour**. citeturn11search1 | Use when concurrency and latency matter. |
| **AWS G6e with L40S 48 GB** | Strong inference fit for 24B–32B-class models; AWS markets it as cost-efficient for gen-AI inference. | Region-dependent on AWS pricing. citeturn11search0turn12search14 | Good if you want the AWS ecosystem. |

## Suggested repo structure and API contract

The best long-lived repository layout is one that keeps **serving**, **retrieval**, **agenting**, **sandboxing**, and **policy** separate. That makes model swaps much easier and prevents your “AI app” from collapsing into a single giant monolith.

```text
selfhosted-agent/
  README.md
  .env.example
  infra/
    docker/
      docker-compose.local.yml
      docker-compose.cloud.yml
    kubernetes/
      namespace.yaml
      vllm.yaml
      open-webui-values.yaml
      qdrant.yaml
      ingress.yaml
      networkpolicies.yaml
  gateway/
    caddy/
      Caddyfile
    auth/
      oidc.md
  services/
    llm-router/
      app.py
      providers/
    retrieval/
      ingest.py
      chunking.py
      rerank.py
    agent/
      planner.py
      tools.py
      policies.py
    sandbox/
      runner.py
      docker/
      nsjail/
  models/
    model-manifest.yaml
    prompts/
      system/
      tools/
      evals/
  ui/
    continue/
      config.yaml
    webui/
      branding.md
  observability/
    langfuse/
    prometheus/
    grafana/
    otel/
  tests/
    smoke/
    evals/
    redteam/
  docs/
    architecture.md
    runbooks.md
    security.md
```

The API should be **OpenAI-compatible wherever possible**, because that is the interchange format already supported by **vLLM**, **TGI**, **llama.cpp server**, Continue’s self-hosting model path, and many downstream developer tools. Anthropic-style message compatibility can be delegated to **llama.cpp** when you specifically want that surface. Build your custom agent features as a thin layer around the standard serving API rather than inventing a completely new inference protocol. citeturn24view3turn24view2turn23search3turn21search1

### Suggested API surface

| Endpoint | Purpose | Notes |
|---|---|---|
| `POST /v1/chat/completions` | Main chat and code-generation path | OpenAI-compatible; served by vLLM/llama.cpp/TGI |
| `POST /v1/embeddings` | Embedding creation for RAG | Back with BGE/Jina/Nomic embedding model |
| `POST /v1/retrieval/search` | Hybrid retrieval + rerank | Custom service over Qdrant/pgvector |
| `POST /v1/agents/runs` | Start an agent job | Returns run ID and status |
| `GET /v1/agents/runs/{id}` | Poll agent status | Include tool traces and sandbox logs |
| `POST /v1/sandboxes/execute` | Execute code or shell in sandbox | Never expose directly to end users |
| `GET /v1/healthz` | Health check | UI uses this for readiness |
| `GET /metrics` | Prometheus metrics | Scraped by Prometheus |
| `POST /v1/evals/run` | Regression and red-team suite | Triggered in CI before promotion |

A practical request format for agent jobs is:

```json
{
  "goal": "Refactor the auth module to support OIDC login",
  "repo": "file:///workspace/project",
  "model": "Qwen/Qwen3-Coder-30B-A3B-Instruct",
  "retrieval": {
    "enabled": true,
    "top_k": 8,
    "rerank": true
  },
  "sandbox": {
    "mode": "docker",
    "network": "restricted",
    "time_limit_sec": 120,
    "cpu_limit": "2",
    "memory_limit_mb": 4096
  },
  "approval_mode": "require_for_shell_and_git_push"
}
```

### Recommended final build choices

If I were implementing this today with no additional constraints, I would choose these two reference builds:

**Best fully local build**
- Runner: **Ollama** or **llama.cpp**
- Browser UI: **Open WebUI**
- IDE UX: **Continue**
- Retrieval: **Qdrant**
- Chat model: **Mistral Small 3.1** or **Qwen3-32B** depending hardware
- Code model: **Devstral Small 1.0** or smaller **Qwen2.5-Coder** on lighter hardware
- Safety posture: no automatic execution, no arbitrary Open WebUI plugins, localhost-only by default. citeturn23search1turn23search3turn20search4turn21search0turn8search0turn36view1turn31view1turn28view1turn20search2

**Best cloud or small-team build**
- Runner: **vLLM**
- Browser UI: **Open WebUI** or **LibreChat**
- Agent layer: **OpenHands**
- Retrieval: **Qdrant** or **pgvector**
- Observability: **Langfuse + OpenTelemetry + Prometheus/Grafana**
- Auth: **OIDC via authentik or Keycloak**
- Sandbox: **Docker sandbox minimum**, **gVisor/Firecracker preferred**
- Chat model: **Qwen3-32B**
- Code model: **Qwen3-Coder-30B-A3B-Instruct**
- Safety posture: staged evals, sandbox-only execution, ingress auth, private model network, NetworkPolicies. citeturn24view3turn20search4turn3search10turn19search2turn8search0turn8search1turn9search0turn9search11turn9search5turn9search2turn10search12turn10search1turn5search0turn5search1turn31view1turn31view0turn25search3

### Open questions and limitations

Some details remain deployment-dependent rather than vendor-fixed. Exact **tokens/second** for many open models vary heavily by quantization, context length, and serving engine, and only some vendors publish standardized throughput numbers. Exact **Ollama registry tags** also change over time, so the example commands above should be treated as operational patterns rather than a guarantee of today’s exact model names. Finally, a fully self-hosted open stack can get close to hosted ChatGPT/Cursor functionality, but **exact frontier-model parity** is still unrealistic on consumer hardware; the strongest strategy is to optimize for architecture modularity so you can keep swapping in better open models as they arrive. citeturn36view2turn23search0turn24view0