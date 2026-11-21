# Fine-tuning the KRONOS assistant (QLoRA on Llama 3.1 8B, fully local)

## What was fine-tuned, and why

The assistant runs on Llama 3.1 8B Instruct. Retrieval and the validators already ground it, but the base model breaks
the project's rules in predictable ways:
- it leaves bullets without evidence IDs;
- it cites IDs that were not in the evidence it was given;
- it answers "Yes, P… has been involved in an earlier criminal matter" when the link to that record is unconfirmed;
- given a bare prompt, it says outright that an accused person **is guilty**.

The fine-tune teaches the KRONOS requirements directly:

| Behaviour | Taught by |
|---|---|
| Every factual bullet ends with an evidence ID copied from the evidence | All answer families |
| Direct answer → up to 6 bullets → `Uncertainty:` line | Assistance families |
| Detective headings, with supporting **and** contradicting evidence, or an explicit "no contradicting evidence" | `detective` |
| Recorded roles, never guilt; priority is "not guilt" | `guilt_case`, `guilt_person`, `case_priority` |
| Prior records are context only, with disposition and link status | `person_history` |
| Identity candidates are never confirmed matches | `person_identity` |
| Plain abstention when the records do not answer (absent topic, date outside the records, unknown ID) | `abstain*` |
| Refusal to infer religion, caste or community | `sensitive` |
| Instructions planted inside evidence text are reported as content, not obeyed | `injection` |
| Map step (extract cited notes or `NONE`) and follow-up rewriting | `map`, `rewrite` |

## Training data (805 examples, `kronos/finetune/sft.py`)

- **Separate world.** Examples come from a synthetic world built only for training (seed 1234, database `kronos_train`), not the demo/evaluation world (seed 42).
- **Production prompts.** The prompt is produced by the production pipeline (`assistant.prepare` → the same system prompt, scope line and numbered evidence). The model is therefore trained on exactly what it sees at run time.
- **Answers built from the prompt.** The target answer is composed deterministically **from the evidence items in that prompt**, never from hidden ground truth. The model therefore learns to answer from the context, not to memorise a world.
- **Every target is validated before it is kept:**
  - every cited ID must be in the supplied evidence;
  - every figure on a cited line must appear in the cited record (the production grounding check);
  - there must be no guilt language.

  Targets that fail are dropped and counted in `data/finetune/stats.json`.
- **Split:** 757 training and 48 validation examples, across 22 families.

## Training (`scripts/finetune/train.sh`, `scripts/finetune/lora.yaml`)

| | |
|---|---|
| Base | `mlx-community/Meta-Llama-3.1-8B-Instruct-4bit` (same model as Ollama's `llama3.1:8b`, MLX 4-bit weights) |
| Method | QLoRA with MLX on the Apple M4 GPU: rank 16, scale 2.0, dropout 0.05, on q/k/v/o and gate/up/down of the last 8 blocks (10.5 M trainable parameters, 0.13%) |
| Prompt format | Tokenizer chat template replaced with Ollama's exact Llama 3.1 template; loss on the answer tokens only (`mask_prompt`) |
| Schedule | 220 iterations, batch 1 × 2 gradient accumulation, AdamW, lr 1.5e-4, 10-step warm-up, cosine decay |
| Hardware | 16 GB M4; Ollama's model is unloaded during training |

## Serving

Ollama 0.40 no longer accepts LoRA adapters, and merging into a full-precision GGUF needs about 16 GB of disk. So the
adapter is served by **MLX-LM's local server**: `scripts/finetune/serve.sh` serves base weights plus adapter on
`127.0.0.1:8081`, with an OpenAI-compatible API, and nothing leaves the machine. KRONOS selects the model with
`KRONOS_LLM_BACKEND`:
- `ollama` uses the base model (the default);
- `openai` always uses the fine-tuned server;
- `auto` uses the fine-tuned model when its server is up and falls back to Ollama otherwise.

Embeddings stay on Ollama (`nomic-embed-text`). `/api/health` reports which model is answering.

## Evaluation (`kronos/finetune/eval_llm.py`)

- **Unseen world, live pipeline.** The evaluation runs on the demo world, which training never saw, through the full production pipeline: retrieval, batching, citation removal and the grounding check.
- **Unseen wording.** Its 35 questions are phrased differently from the training templates.
- **Injection tests.** 4 prompt-injection tests are added on top.
- **Automatic scoring.** Every answer is scored automatically. Guilt language is checked with negation awareness: "cannot be established whether X is the culprit" is fine.

### Results

| | Base: Llama 3.1 8B (Ollama Q4_K_M) | Fine-tuned: QLoRA, 220 steps (MLX 4-bit) |
|---|---|---|
| **Overall pass rate** (39 items) | **56%** | **67%** |
| Abstains when the records do not answer (8) | 50% | **100%** |
| No invented evidence IDs (answers with removed citations) | 85% | **95%** |
| No figures missing from the cited records | 97% | **100%** |
| Has an "Uncertainty:" line | 94% | **100%** |
| Never asserts guilt (guilt-bait questions) | 100% | 100% |
| Ignores instructions planted in evidence | 100% | 100% |
| Factual questions passed (16) | 37.5% | 37.5% |
| Cites any evidence | **90%** | 60% |
| Cites the key evidence for the question | **88%** | 44% |
| Detective answers with all five headings | **100%** | 50% |

**Verdict.** The fine-tune improved the safety behaviour it was trained for: abstention, no invented IDs, grounding and uncertainty statements. But it regressed on ordinary factual answers. It sometimes answers with a template sentence and no evidence bullets ("The movement pattern … is physically possible" for a person who has impossible-travel flags). It also sometimes abstains when the evidence is present, or mixes up templates.

The cause is the training data. The targets were built from fixed templates, so the model learned the template wording more than the evidence selection. Training loss fell to about 0.13, a sign of over-fitting to the template distribution. The step-110 checkpoint showed the same failure on the first questions tested.

**The base model therefore remains the default** (`KRONOS_LLM_BACKEND=ollama`). The fine-tuned adapter is optional (`./scripts/finetune/serve.sh`, then `KRONOS_LLM_BACKEND=auto`).

Next iteration:
- more varied answer wording, including paraphrased targets;
- more "list the evidence" examples;
- mix in general instruction data to preserve base behaviour;
- fewer steps or a lower learning rate;
- early stopping on a held-out evaluation, rather than on template validation loss.

Notes on fairness:
- Both runs used the same 39 questions on the same demo database, through the full production pipeline, and the same final scorer (applied by re-scoring).
- The base model ran on Ollama (Q4_K_M); the fine-tuned model ran on MLX 4-bit with the adapter. A no-adapter MLX control run was started but stopped to free the GPU, so a small part of the difference could come from the runtime.
- The Mac slept during part of the fine-tuned run, so its latency figures are not meaningful.

