"""Evaluate KRONOS analytics against synthetic ground truth (synthetic data only)."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kronos.config import settings
from kronos.engines.multimodal import financial
from kronos.engines.temporal import travel
from kronos.engines.identity import history, resolver
from kronos.engines.graph import gnn
from kronos import db

gt = json.loads((settings.generated_dir / "ground_truth.json").read_text())
out = {"financial": financial.evaluate(gt), "identity": resolver.evaluate(gt), "criminalHistoryLinkage": history.evaluate(gt)}
fl = travel.detect_all()
inj = {e for x in gt["impossible_travel"] for e in x["evidence_ids"]}
hit = {f["first"]["evidenceId"] for f in fl} | {f["second"]["evidenceId"] for f in fl}
out["impossibleTravel"] = {"injected": len(gt["impossible_travel"]),
                           "detected": sum(1 for x in gt["impossible_travel"] if set(x["evidence_ids"]) & hit),
                           "flagsTotal": len(fl),
                           "flagsNotInvolvingInjected": [(f["personId"], f["verdict"]) for f in fl if not ({f["first"]["evidenceId"], f["second"]["evidenceId"]} & inj)]}
truth = {(p, c["case_id"]): set(r) for c in gt["cases"] for p, r in c["roles"].items()}
got = {}
for r in db.query("SELECT person_id, case_id, role FROM person_case_roles WHERE role <> 'RECORD_SUBJECT'"):
    got.setdefault((r["person_id"], r["case_id"]), set()).add(r["role"].replace("PRINCIPAL_", ""))
named = {k: v for k, v in truth.items() if v - {"ASSOCIATE"}}
out["firRoles"] = {"firNamedPersons": len(named), "correctRole": sum(1 for k, v in named.items() if k in got and v & got[k]),
                   "wrongRole": sum(1 for k, v in named.items() if k in got and not v & got[k]),
                   "spuriousRoles": len([k for k in got if k not in truth])}
out["gnn"] = gnn.report().get("metrics")
from kronos.engines.provenance import ledger
st = ledger.status()
out["ledger"] = {"chainValid": st["chain"]["valid"], "blocks": st["chain"]["blocks"],
                 "anchorsWithQuorum": sum(a["quorumMet"] for a in st["anchors"]), "anchors": len(st["anchors"])}
print(json.dumps(out, indent=1))
(settings.data_dir / "evaluation_report.json").write_text(json.dumps(out, indent=1))
