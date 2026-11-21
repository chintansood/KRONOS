#!/bin/zsh
# QLoRA fine-tune of Llama 3.1 8B Instruct for KRONOS (Apple Silicon / MLX). ~16 GB RAM: Ollama's copy of the model is
# unloaded first so the two 8B models are never resident together.
set -e
cd "$(dirname "$0")/../.."
ollama stop llama3.1:8b 2>/dev/null || true
ollama stop kronos-llama3.1-8b 2>/dev/null || true
.venv-ft/bin/python -m mlx_lm lora -c scripts/finetune/lora.yaml "$@"
