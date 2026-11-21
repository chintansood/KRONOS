"""Ingest the five CSV datasets into PostgreSQL. Usage: python scripts/ingest.py [source_dir]"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kronos.ingestion.pipeline import ingest
print(json.dumps(ingest(Path(sys.argv[1]) if len(sys.argv) > 1 else None), indent=1, default=str))
