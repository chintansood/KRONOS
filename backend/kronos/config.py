"""Central configuration for KRONOS. Every threshold that affects an investigative
finding is configurable via environment variables (prefix KRONOS_) or .env."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _env(name: str, default):
    raw = os.getenv(f"KRONOS_{name}")
    if raw is None:
        return default
    if isinstance(default, bool):
        return raw.lower() in ("1", "true", "yes", "on")
    return type(default)(raw)


_DATA = Path(_env("DATA_DIR", str(ROOT / "data")))     # a separate data dir + DB is used for the fine-tuning world


@dataclass(frozen=True)
class Settings:
    # --- storage ---
    database_url: str = _env("DATABASE_URL", "dbname=kronos")
    data_dir: Path = _DATA
    generated_dir: Path = _DATA / "generated"
    summaries_dir: Path = _DATA / "summaries"
    models_dir: Path = _DATA / "models"
    public_records_dir: Path = ROOT / "data" / "public_records"   # real court records (pseudonymised), shared

    # --- LLM (local Ollama only; no data leaves the machine) ---
    ollama_url: str = _env("OLLAMA_URL", "http://localhost:11434")
    llm_model: str = _env("LLM_MODEL", "llama3.1:8b")
    # "ollama" (base model), "openai" (local OpenAI-compatible server — the fine-tuned model served by mlx_lm.server),
    # or "auto" (use the fine-tuned server when it is running, otherwise Ollama). Embeddings always use Ollama.
    llm_backend: str = _env("LLM_BACKEND", "ollama")
    llm_url: str = _env("LLM_URL", "http://127.0.0.1:8081/v1")
    llm_ft_name: str = _env("LLM_FT_NAME", "kronos-llama3.1-8b-ft (QLoRA)")
    embed_model: str = _env("EMBED_MODEL", "nomic-embed-text")
    embed_dim: int = _env("EMBED_DIM", 768)
    llm_timeout_s: float = _env("LLM_TIMEOUT_S", 180.0)
    llm_context_tokens: int = _env("LLM_CONTEXT_TOKENS", 4096)
    llm_evidence_budget_tokens: int = _env("LLM_EVIDENCE_BUDGET", 1700)  # per batch
    llm_max_batches: int = _env("LLM_MAX_BATCHES", 3)

    # --- financial anomaly detection (independently switchable) ---
    fin_use_isolation_forest: bool = _env("FIN_USE_IFOREST", True)
    fin_iforest_contamination: float = _env("FIN_IFOREST_CONTAMINATION", 0.03)
    fin_use_iqr: bool = _env("FIN_USE_IQR", True)
    fin_iqr_k: float = _env("FIN_IQR_K", 3.0)
    fin_rapid_window_min: int = _env("FIN_RAPID_WINDOW_MIN", 360)
    fin_structuring_threshold: float = _env("FIN_STRUCT_THRESHOLD", 50000.0)
    fin_structuring_min_count: int = _env("FIN_STRUCT_MIN_COUNT", 4)

    # --- temporal / impossible travel ---
    travel_max_ground_kmh: float = _env("TRAVEL_MAX_GROUND_KMH", 150.0)
    travel_max_air_kmh: float = _env("TRAVEL_MAX_AIR_KMH", 950.0)
    travel_min_distance_km: float = _env("TRAVEL_MIN_DISTANCE_KM", 5.0)
    travel_default_accuracy_m: float = _env("TRAVEL_DEFAULT_ACCURACY_M", 1500.0)
    routine_gap_hours: float = _env("ROUTINE_GAP_HOURS", 3.0)

    # --- identity resolution ---
    identity_high: float = _env("IDENTITY_HIGH", 0.75)
    identity_medium: float = _env("IDENTITY_MEDIUM", 0.55)
    identity_low: float = _env("IDENTITY_LOW", 0.35)

    # --- hosting (scripts/host.sh): serve the built website and require an access code ---
    access_code: str = _env("ACCESS_CODE", "")          # empty = no gate (local development)
    static_dir: str = _env("STATIC_DIR", "")            # e.g. ../kronos-app/dist

    # --- API ---
    cors_origins: tuple = field(default_factory=lambda: tuple(
        _env("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")))


settings = Settings()
for _d in (settings.generated_dir, settings.summaries_dir, settings.models_dir):
    _d.mkdir(parents=True, exist_ok=True)
