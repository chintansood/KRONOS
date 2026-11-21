"""Generate the five interlinked synthetic KRONOS datasets.
Usage: python scripts/generate_data.py [--cases 40 --people 420 --seed 42 ...]"""
import argparse, json, sys
from dataclasses import fields
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kronos.synth.generator import SynthConfig, generate
from kronos.config import settings

ap = argparse.ArgumentParser()
for f in fields(SynthConfig):
    ap.add_argument("--" + f.name.replace("n_", "", 1).replace("_", "-") if f.name.startswith("n_") else "--" + f.name.replace("_", "-"),
                    dest=f.name, type=type(f.default), default=f.default)
cfg = SynthConfig(**vars(ap.parse_args()))
if cfg.out_dir == "data/generated":
    cfg.out_dir = str(settings.generated_dir)
print(json.dumps(generate(cfg), indent=1))
print("written to", cfg.out_dir)
