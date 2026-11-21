"""Graph analytics (NetworkX baseline): centrality, communities, paths, cross-case links,
candidate hidden links, and UI subgraph extraction."""
from __future__ import annotations

import math
from collections import defaultdict
from itertools import combinations

import networkx as nx

from ..store import cached, data_version
from .builder import graph

# person–person relation strength via direct edges or shared identifiers
DIRECT = {"PERSON_CALLED_PERSON": 1.0, "PERSON_MESSAGED_PERSON": 0.8, "PERSON_MENTIONED_IN_COMMUNICATION": 0.5,
          "PERSON_LINKED_TO_PERSON": 2.0}
SHARED = {"PHONE": 3.0, "DEVICE": 2.5, "SIM": 3.0, "ACCOUNT": 2.5, "COMPANY": 0.6, "FIR": 0.8}
UI_TYPE = {"PERSON": "PERSON", "CASE": "CASE", "PHONE": "DEVICE", "DEVICE": "DEVICE", "SIM": "DEVICE",
           "ACCOUNT": "ACCOUNT", "COMPANY": "ACCOUNT", "LOCATION": "LOCATION", "FIR": "EVIDENCE"}
EDGE_MOD = {"PERSON_CALLED_PERSON": "CDR", "PERSON_MESSAGED_PERSON": "COMMUNICATION", "PERSON_VISITED_LOCATION": "LOCATION",
            "ACCOUNT_SENT_TO_ACCOUNT": "FINANCIAL", "PERSON_ASSOCIATED_WITH_ACCOUNT": "FINANCIAL",
            "COMPANY_HOLDS_ACCOUNT": "FINANCIAL", "PERSON_ASSOCIATED_WITH_COMPANY": "FINANCIAL",
            "PERSON_APPEARS_IN_CASE": "CROSS_CASE", "PERSON_NAMED_IN_FIR": "FIR", "CASE_CONTAINS_EVIDENCE": "FIR",
            "PERSON_MENTIONED_IN_COMMUNICATION": "COMMUNICATION"}


def person_projection() -> nx.Graph:
    G = graph()
    P = nx.Graph()
    for n, a in G.nodes(data=True):
        if a.get("type") == "PERSON":
            P.add_node(n, label=a.get("label"))

    def bump(a, b, w, why, ev):
        if a == b:
            return
        if P.has_edge(a, b):
            d = P[a][b]
            d["weight"] += w
            if why not in d["basis"]:
                d["basis"].append(why)
            d["evidence"] = (d["evidence"] + ev)[:20]
        else:
            P.add_edge(a, b, weight=w, basis=[why], evidence=ev[:20])

    for u, v, k, d in G.edges(keys=True, data=True):
        if k in DIRECT and u in P and v in P:
            bump(u, v, DIRECT[k] * math.log1p(d["count"]), k, d["evidence"][:5])
    users = defaultdict(set)
    for u, v, k, d in G.edges(keys=True, data=True):
        t = G.nodes[v].get("type")
        if u in P and t in SHARED and k != "PERSON_APPEARS_IN_CASE":
            users[v].add(u)
    for ident, ps in users.items():
        if 1 < len(ps) <= 6:
            t = G.nodes[ident]["type"]
            for a, b in combinations(sorted(ps), 2):
                ev = (G[a][ident][next(iter(G[a][ident]))]["evidence"][:2] + G[b][ident][next(iter(G[b][ident]))]["evidence"][:2])
                bump(a, b, SHARED[t], f"SHARED_{t}:{ident}", ev)
    return P


def metrics() -> dict:
    def compute():
        P = person_projection()
        P2 = P.subgraph([n for n in P if P.degree(n) > 0]).copy()
        deg = nx.degree_centrality(P2)
        btw = nx.betweenness_centrality(P2, k=min(300, len(P2)), weight=None, seed=7)
        comms = nx.community.louvain_communities(P2, weight="weight", seed=7, resolution=1.0)
        member = {n: i for i, c in enumerate(comms) for n in c}
        G = graph()
        cases_of = {n: sorted({v for _, v, k in G.out_edges(n, keys=True) if k == "PERSON_APPEARS_IN_CASE"}) for n in P2}
        nodes = {n: {"personId": n, "name": P.nodes[n].get("label"), "degreeCentrality": round(deg[n], 4),
                     "betweenness": round(btw[n], 4), "community": member.get(n), "degree": P2.degree(n),
                     "cases": cases_of[n]} for n in P2}
        communities = []
        for i, c in enumerate(sorted(comms, key=len, reverse=True)):
            cs = defaultdict(int)
            for n in c:
                for x in cases_of[n]:
                    cs[x] += 1
            communities.append({"id": member[next(iter(c))], "size": len(c), "members": sorted(c)[:60],
                                "cases": sorted(cs, key=lambda k: -cs[k])[:10]})
        return {"nodes": nodes, "communities": communities,
                "method": "Person projection (direct communication + shared phone/device/SIM/account/company/FIR); "
                          "degree & sampled betweenness centrality; Louvain communities (seed 7)."}
    return cached("graph_metrics:v1", compute)


def cross_case() -> list[dict]:
    def compute():
        G = graph()
        links = defaultdict(lambda: {"via": [], "evidence": []})
        # shared persons, and shared identifiers used in different cases
        for n, a in G.nodes(data=True):
            t = a.get("type")
            if t == "PERSON":
                cs = sorted({v for _, v, k in G.out_edges(n, keys=True) if k == "PERSON_APPEARS_IN_CASE"})
                for x, y in combinations(cs, 2):
                    links[(x, y)]["via"].append({"type": "PERSON", "id": n, "label": a.get("label")})
            elif t in ("PHONE", "DEVICE", "SIM", "ACCOUNT"):
                cs = set()
                for u, _, d in G.in_edges(n, data=True):
                    cs |= set(d.get("cases", []))
                cs = sorted(cs)
                if 1 < len(cs) <= 6:
                    for x, y in combinations(cs, 2):
                        links[(x, y)]["via"].append({"type": t, "id": n, "label": a.get("label")})
        out = []
        for (x, y), d in links.items():
            types = {v["type"] for v in d["via"]}
            out.append({"cases": [x, y], "links": d["via"][:12], "linkCount": len(d["via"]),
                        "strength": round(sum(3 if v["type"] in ("PHONE", "DEVICE", "SIM", "ACCOUNT") else 1 for v in d["via"]), 1),
                        "summary": f"{x} and {y} share {len(d['via'])} entit{'y' if len(d['via']) == 1 else 'ies'} "
                                   f"({', '.join(sorted(types))})"})
        return sorted(out, key=lambda o: -o["strength"])
    return cached("cross_case:v1", compute)


def hidden_links(top: int = 40) -> list[dict]:
    """Candidate links: non-adjacent person pairs with strong shared neighbourhoods (Adamic–Adar).
    These are hypotheses for investigation, not verified relationships."""
    def compute():
        P = person_projection()
        P2 = P.subgraph([n for n in P if 0 < P.degree(n) <= 80])
        scored = []
        pairs = [(u, v) for u in P2 for v in P2 if u < v and not P2.has_edge(u, v) and set(P2[u]) & set(P2[v])]
        for u, v, s in nx.adamic_adar_index(P2, pairs):   # list, not generator (networkx exhausts generators)
            cn = sorted(set(P2[u]) & set(P2[v]))
            scored.append({"persons": [u, v], "names": [P.nodes[u].get("label"), P.nodes[v].get("label")],
                           "adamicAdar": round(s, 3), "commonNeighbours": cn[:8], "commonCount": len(cn),
                           "status": "CANDIDATE — not a verified relationship"})
        scored = [x for x in scored if x["adamicAdar"] >= 0.4]
        return sorted(scored, key=lambda x: -x["adamicAdar"])[:top]
    return cached(f"hidden_links:{top}", compute)


def path(a: str, b: str, exclude_types=("LOCATION", "CASE"), max_len: int = 6) -> dict:
    G = graph()
    U = nx.Graph()
    for u, v, k, d in G.edges(keys=True, data=True):
        if G.nodes[u].get("type") in exclude_types or G.nodes[v].get("type") in exclude_types:
            continue
        w = 1.0 / (1 + math.log1p(d["count"]))
        if not U.has_edge(u, v) or U[u][v]["weight"] > w:
            U.add_edge(u, v, weight=w, type=k, evidence=d["evidence"][:4], cases=d["cases"])
    if a not in U or b not in U:
        return {"found": False, "reason": "one of the nodes has no qualifying connections"}
    try:
        p = nx.shortest_path(U, a, b, weight="weight")
    except nx.NetworkXNoPath:
        return {"found": False, "reason": f"no path without passing through {', '.join(exclude_types)} nodes"}
    if len(p) - 1 > max_len:
        return {"found": False, "reason": f"shortest path has {len(p) - 1} hops (> {max_len})"}
    hops = [{"from": p[i], "to": p[i + 1], "type": U[p[i]][p[i + 1]]["type"], "evidenceIds": U[p[i]][p[i + 1]]["evidence"],
             "cases": U[p[i]][p[i + 1]]["cases"]} for i in range(len(p) - 1)]
    return {"found": True, "nodes": [{"id": n, "type": G.nodes[n].get("type"), "label": G.nodes[n].get("label")} for n in p],
            "hops": hops, "length": len(hops),
            "note": "A path shows recorded connections between entities; indirect association is not evidence of involvement."}


def subgraph(focus: str | None, depth: int = 2, limit: int = 90, include_locations: bool = False) -> dict:
    """Ego network for the 3D explorer, returned in the frontend GraphNode/GraphEdge shape."""
    G = graph()
    mets = metrics()["nodes"]
    from ..multimodal.financial import flagged_ids
    flagged = set(flagged_ids())
    if not focus or focus not in G:
        # default: most central persons and their cases
        top = sorted(mets.values(), key=lambda m: -m["betweenness"])[:12]
        seeds = [m["personId"] for m in top]
    else:
        seeds = [focus]
    U = G.to_undirected(as_view=True)
    keep, frontier = set(seeds), list(seeds)
    for _ in range(depth):
        nxt = []
        for n in frontier:
            nbrs = []
            for m in U[n]:
                t = G.nodes[m].get("type")
                if t == "LOCATION" and not include_locations:
                    continue
                if t == "SIM":
                    continue
                w = sum(d.get("count", 1) for d in U[n][m].values())
                pri = 3 if t in ("CASE", "ACCOUNT", "DEVICE", "PHONE") else 2 if t == "PERSON" else 1
                nbrs.append((pri, w, m))
            nbrs.sort(reverse=True)
            for _, _, m in nbrs[: 14 if n in seeds else 6]:
                if m not in keep and len(keep) < limit:
                    keep.add(m); nxt.append(m)
        frontier = nxt
    nodes = []
    for n in keep:
        a = G.nodes[n]
        t = a.get("type", "UNKNOWN")
        m = mets.get(n, {})
        nodes.append({"id": n, "label": a.get("label") or n,
                      "sublabel": {"PHONE": "Phone number", "DEVICE": "Handset (IMEI)", "SIM": "SIM",
                                   "COMPANY": "Company", "FIR": "FIR record", "ACCOUNT": "Bank account"}.get(t,
                                  a.get("offence") if t == "CASE" else (f"{n} · community {m.get('community')}" if t == "PERSON" else None)),
                      "type": UI_TYPE.get(t, "EVIDENCE"), "entityType": t,
                      "val": round(4 + 40 * m.get("betweenness", 0) + 0.3 * min(m.get("degree", 0), 20), 2) if t == "PERSON" else (8 if t == "CASE" else 5),
                      "role": f"community {m['community']}" if m else None,
                      "evidenceId": a.get("evidenceId")})
    edges = []
    for u, v, k, d in G.edges(keys=True, data=True):
        if u in keep and v in keep:
            edges.append({"source": u, "target": v, "label": k.replace("_", " ").lower(), "type": k,
                          "modality": EDGE_MOD.get(k, "CROSS_CASE"), "weight": d["count"],
                          "isAnomaly": any(e in flagged for e in d["evidence"]),
                          "evidenceIds": d["evidence"][:6], "cases": d["cases"], "reliability": d["reliability"],
                          "first": d["first"], "last": d["last"]})
    return {"focus": focus, "nodes": nodes, "edges": edges, "depth": depth,
            "stats": {"totalNodes": G.number_of_nodes(), "totalEdges": G.number_of_edges()}}


def node_detail(nid: str) -> dict:
    G = graph()
    if nid not in G:
        return {}
    a = G.nodes[nid]
    rels = []
    for u, v, k, d in list(G.out_edges(nid, keys=True, data=True)) + list(G.in_edges(nid, keys=True, data=True)):
        other = v if u == nid else u
        rels.append({"type": k, "direction": "out" if u == nid else "in", "peer": other,
                     "peerType": G.nodes[other].get("type"), "peerLabel": G.nodes[other].get("label"),
                     "count": d["count"], "evidenceIds": d["evidence"][:8], "cases": d["cases"],
                     "first": d["first"], "last": d["last"], "reliability": d["reliability"],
                     **{k2: d[k2] for k2 in ("roles", "role", "basis") if k2 in d}})
    return {"id": nid, **a, "metrics": metrics()["nodes"].get(nid), "relationships": sorted(rels, key=lambda r: -r["count"])[:120]}
