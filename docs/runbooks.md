# Runbooks

## Fresh install

```bash
git clone https://github.com/karl-kiser/faux_code.git
cd faux_code

# 1. Install Ollama (macOS or Linux)
./infra/scripts/install_ollama.sh

# 2. Pull default models (~10 GB total)
./infra/scripts/pull_models.sh

# 3. Boot dev stack (creates .venv, installs deps, starts both servers)
./infra/scripts/dev.sh
```

Open http://localhost:3000.

## Add a free remote provider

1. Get a free API key from one of:
   - Groq: https://console.groq.com/keys
   - OpenRouter: https://openrouter.ai/keys (look for `:free` models)
   - Google Gemini: https://aistudio.google.com/app/apikey
   - Cerebras: https://cloud.cerebras.ai/
   - HuggingFace: https://huggingface.co/settings/tokens
2. Open http://localhost:3000/settings and paste the key.
3. The provider toggles on and its models appear in the model picker.

## Use a smaller model to save RAM

On a 16 GB machine, the defaults will run, but feel free to use lighter models:
```bash
export OLLAMA_DEFAULT_CHAT=llama3.2:3b
export OLLAMA_DEFAULT_CODE=qwen2.5-coder:3b
./infra/scripts/dev.sh
```

## Use a remote vLLM server

If you self-rent a GPU and run vLLM:
```bash
# On the GPU host:
vllm serve Qwen/Qwen3-Coder-30B-A3B-Instruct --host 0.0.0.0 --port 8000 \
  --api-key change-me --max-model-len 32768

# Locally, in Settings, set:
VLLM_BASE_URL=http://your-host:8000
VLLM_API_KEY=change-me
```

Models from your vLLM server show up under the `vllm` provider.

## Reset everything

```bash
rm -rf .venv frontend/node_modules backend/data workspaces logs
./infra/scripts/dev.sh   # re-installs and re-creates the SQLite db
```

## Run the eval suite

```bash
./.venv/bin/python -m tests.evals.run_evals --model qwen2.5-coder:7b-instruct
```

## Backend-only restart

```bash
lsof -ti :8765 | xargs kill -9
./.venv/bin/python -m backend.app.main
```

## Run unit tests

```bash
./.venv/bin/python -m pytest backend/tests -v
```
