#!/bin/zsh
# Register the trained LoRA adapter with Ollama on top of the same base model (llama3.1:8b) — no merged copy of the
# 8B weights is written. MLX applies `scale` directly; llama.cpp applies alpha/rank, so alpha = scale × rank.
set -e
cd "$(dirname "$0")/../.."
SRC=data/finetune/adapters
OUT=data/finetune/ollama_adapter
NAME=${1:-kronos-llama3.1-8b}
mkdir -p $OUT
cp $SRC/adapters.safetensors $OUT/adapters.safetensors
.venv-ft/bin/python -I - "$SRC/adapter_config.json" "$OUT/adapter_config.json" <<'PY'
import json, sys
c = json.load(open(sys.argv[1]))
lp = c.get("lora_parameters", {})
r, s = lp.get("rank", 8), lp.get("scale", 20.0)
c["lora_parameters"] = {**lp, "alpha": s * r}
c.update({"lora_alpha": s * r, "r": r})
json.dump(c, open(sys.argv[2], "w"), indent=1)
print("rank", r, "scale", s, "-> alpha", s * r)
PY
cat > $OUT/Modelfile <<MF
FROM llama3.1:8b
ADAPTER $PWD/$OUT
PARAMETER temperature 0.1
PARAMETER num_ctx 4096
MF
ollama create $NAME -f $OUT/Modelfile
ollama show $NAME | head -12
