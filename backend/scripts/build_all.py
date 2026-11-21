"""One-shot KRONOS build: [generate] -> ingest -> analytics -> identity -> summaries -> retrieval index -> GNN -> federated.
Usage: python scripts/build_all.py [--generate] [--seed N] [--public-records] [--llm-summaries] [--no-embed]"""
import argparse, json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kronos.config import settings

ap = argparse.ArgumentParser()
ap.add_argument("--generate", action="store_true", help="regenerate synthetic datasets first")
ap.add_argument("--llm-summaries", action="store_true", help="also write LLM narratives for each case (slow)")
ap.add_argument("--no-embed", action="store_true")
ap.add_argument("--seed", type=int, default=42, help="synthetic world seed (42 = demo world)")
ap.add_argument("--public-records", action="store_true", help="also ingest the pseudonymised real court records")
a = ap.parse_args()

def step(name, fn):
    t = time.time(); print(f"==> {name}", flush=True); r = fn(); print(f"    done in {time.time() - t:.1f}s", flush=True); return r

if a.generate:
    from kronos.synth.generator import SynthConfig, generate
    step("generate synthetic datasets", lambda: print(generate(SynthConfig(seed=a.seed, out_dir=str(settings.generated_dir)))))
from kronos.ingestion.pipeline import ingest
step("ingest", lambda: ingest())
from kronos.engines.multimodal import financial
from kronos.engines.temporal import timeline, travel
step("financial anomaly detection", financial.analysis)
step("bursts & co-location", lambda: (timeline.bursts(), timeline.colocations()))
from kronos.engines.identity import resolver
step("identity resolution", resolver.generate_candidates)
from kronos.engines.identity import history
step("criminal-history linkage", history.link_all)
from kronos.engines.graph import analytics, gnn
step("graph analytics", lambda: (analytics.metrics(), analytics.cross_case(), analytics.hidden_links()))
from kronos.engines.multimodal import summarizer
from kronos import db
cases = [r["case_id"] for r in db.query("SELECT case_id FROM cases ORDER BY 1")]
step(f"case summaries ({len(cases)})", lambda: [summarizer.generate_case_summary(c, use_llm=a.llm_summaries) for c in cases])
if a.public_records:
    from kronos.ingestion.public_records import ingest_public_records
    step("real public records (pseudonymised court orders)", lambda: print(ingest_public_records(index=False)))
from kronos.engines.llm import retrieval
step("retrieval index", lambda: print(retrieval.build_index(embed=not a.no_embed)))
step("GNN training/evaluation", lambda: print(gnn.train()["comparison"]))
gt_file = settings.generated_dir / "ground_truth.json"
if gt_file.exists():
    from kronos.engines.federated import fedavg
    gt = json.loads(gt_file.read_text())
    step("federated learning simulation", lambda: fedavg.run(gt))
