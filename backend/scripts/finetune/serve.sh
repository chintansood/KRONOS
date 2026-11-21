#!/bin/zsh
# Serve the fine-tuned model locally (OpenAI-compatible API on 127.0.0.1:8081; nothing leaves the machine).
# Then run the API with  KRONOS_LLM_BACKEND=auto  (fine-tuned when this server is up, Ollama base otherwise).
cd "$(dirname "$0")/../.."
exec .venv-ft/bin/python -m mlx_lm server --model data/external/hf/Meta-Llama-3.1-8B-Instruct-4bit \
     --adapter-path data/finetune/adapters --host 127.0.0.1 --port 8081 --temp 0.1 --log-level WARNING
