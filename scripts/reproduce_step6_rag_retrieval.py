"""
reproduce_step6_rag_retrieval.py
==================================
Reproduces Table 6 in the MAFD paper: RAG retrieval evaluation using
TF-IDF simulation as a conservative proxy for ChromaDB dense vector retrieval.

Paper section:  5.8, Table 6
Prerequisites:  data/sop/ directory must contain the four SOP documents.
                (No generated datasets or ML models required.)

Methodology (Section 5.8):
    - 24 fault diagnostic scenarios constructed across 8 fault type classes
      and operational anomaly scenarios.
    - Ground truth SOP relevance established from fault physics:
        SLG, LL, LLG  → SOP-MISC-002 (relay miscoordination) +
                         SOP-TRF-004 (transformer overcurrent)
        LLL, LLLG     → SOP-TRF-004 + SOP-OVLD-001 (thermal overload)
        OPEN_1PH/2PH  → SOP-MISC-002 (nuisance/relay trip)
        OPEN_3PH      → SOP-TRF-004 + SOP-MISC-002
        OVERLOAD      → SOP-OVLD-001 + SOP-THFT-003 (theft-related)
    - Retrieval simulated via TF-IDF sparse cosine similarity, top-k=2.
    - TF-IDF is a conservative lower-bound proxy for the deployed
      BAAI/bge-small-en-v1.5 dense embeddings, which capture semantic
      similarity beyond keyword overlap.
    - Faithfulness evaluation requires expert-validated ground-truth
      diagnostic plans and is not computed here (see Section 5.8 note).

Metrics:
    Context Precision = |retrieved ∩ relevant| / |retrieved|
    Context Recall    = |retrieved ∩ relevant| / |relevant|

Usage:
    python scripts/reproduce_step6_rag_retrieval.py
"""

from __future__ import annotations

import math
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SOP_DIR   = REPO_ROOT / "data" / "sop"

TOP_K = 2  # number of SOPs retrieved per query (matches deployed system)


# ── Ground truth: fault type → relevant SOP IDs ──────────────────────────────
GROUND_TRUTH: dict[str, list[str]] = {
    "SLG":      ["SOP-MISC-002", "SOP-TRF-004"],
    "LL":       ["SOP-MISC-002", "SOP-TRF-004"],
    "LLG":      ["SOP-MISC-002", "SOP-TRF-004"],
    "LLL":      ["SOP-TRF-004", "SOP-MISC-002"],
    "LLLG":     ["SOP-TRF-004", "SOP-OVLD-001"],
    "OPEN_1PH": ["SOP-MISC-002"],
    "OPEN_2PH": ["SOP-MISC-002"],
    "OPEN_3PH": ["SOP-TRF-004", "SOP-MISC-002"],
    "OVERLOAD": ["SOP-OVLD-001", "SOP-THFT-003"],
}

# ── 24 evaluation scenarios ───────────────────────────────────────────────────
SCENARIOS = [
    # SLG
    {"id": "T01", "fault_type": "SLG",
     "query": "single line to ground fault elevated zero sequence current ground involvement relay trip protection"},
    {"id": "T02", "fault_type": "SLG",
     "query": "SLG fault high I0/I1 ratio voltage collapse phase A protection relay operation"},
    {"id": "T03", "fault_type": "SLG",
     "query": "ground fault single phase voltage sag 0.021 pu transformer protection relay sequence components"},
    # LL
    {"id": "T04", "fault_type": "LL",
     "query": "line to line fault negative sequence elevated I2/I1 no ground path overcurrent relay"},
    {"id": "T05", "fault_type": "LL",
     "query": "phase to phase fault two phase disturbance relay coordination overcurrent breaker operation"},
    {"id": "T06", "fault_type": "LL",
     "query": "LL fault high current two phases transformer relay miscoordination feeder trip breaker"},
    # LLG
    {"id": "T07", "fault_type": "LLG",
     "query": "line to line ground fault elevated both I0 I2 two phases collapse ground path overcurrent"},
    {"id": "T08", "fault_type": "LLG",
     "query": "LLG mixed fault sequence ratios ground and phase involvement transformer protection relay"},
    # LLL
    {"id": "T09", "fault_type": "LLL",
     "query": "three phase balanced fault all phases drop deep voltage sag near zero sequence balanced high current"},
    {"id": "T10", "fault_type": "LLL",
     "query": "LLL fault balanced symmetrical overcurrent transformer protection all phases faulted"},
    # LLLG
    {"id": "T11", "fault_type": "LLLG",
     "query": "three phase to ground fault severe all phases collapse elevated zero sequence high current thermal overload transformer"},
    {"id": "T12", "fault_type": "LLLG",
     "query": "LLLG bolted fault all phases high current ground path thermal limit transformer differential protection"},
    {"id": "T13", "fault_type": "LLLG",
     "query": "complete three phase ground fault feeder overcurrent thermal rating exceeded balanced high load"},
    # OPEN_1PH
    {"id": "T14", "fault_type": "OPEN_1PH",
     "query": "single phase open conductor voltage imbalance one phase loss current asymmetry nuisance relay operation"},
    {"id": "T15", "fault_type": "OPEN_1PH",
     "query": "open circuit single phase partial voltage loss relay miscoordination investigation upstream downstream"},
    {"id": "T16", "fault_type": "OPEN_1PH",
     "query": "phase open conductor current loss relay trip nuisance investigation coordination settings"},
    # OPEN_2PH
    {"id": "T17", "fault_type": "OPEN_2PH",
     "query": "two phase open conductor voltage severe imbalance two phases lost relay spurious operation coordination"},
    {"id": "T18", "fault_type": "OPEN_2PH",
     "query": "double open phase partial outage relay miscoordination investigation no clear fault cause trip"},
    # OPEN_3PH
    {"id": "T19", "fault_type": "OPEN_3PH",
     "query": "three phase open complete outage all phases lost transformer protection overcurrent trip investigation"},
    {"id": "T20", "fault_type": "OPEN_3PH",
     "query": "complete three phase open conductor all phases lost transformer relay trip protection operation"},
    # OVERLOAD operational
    {"id": "T21", "fault_type": "OVERLOAD",
     "query": "feeder overload sustained current above thermal rating continuous load 100 percent trip criteria time-current"},
    {"id": "T22", "fault_type": "OVERLOAD",
     "query": "thermal overload feeder current trending above 80 percent rating gradual heating SCADA monitoring"},
    {"id": "T23", "fault_type": "OVERLOAD",
     "query": "suspected theft irregular load pattern overload without billing growth non-technical loss revenue"},
    {"id": "T24", "fault_type": "OVERLOAD",
     "query": "unauthorized connection suspected overload persistent high loading no corresponding billed demand theft investigation"},
]


# ── TF-IDF retrieval ──────────────────────────────────────────────────────────

def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _tf(tokens: list[str]) -> dict[str, float]:
    counts: dict[str, int] = defaultdict(int)
    for t in tokens:
        counts[t] += 1
    n = len(tokens)
    return {k: v / n for k, v in counts.items()}


def _idf(corpus: list[list[str]]) -> dict[str, float]:
    n = len(corpus)
    df: dict[str, int] = defaultdict(int)
    for doc in corpus:
        for term in set(doc):
            df[term] += 1
    return {term: math.log(n / (1 + count)) for term, count in df.items()}


def _tfidf_score(q_tokens: list[str], d_tokens: list[str],
                 idf_map: dict[str, float]) -> float:
    q_tf = _tf(q_tokens)
    d_tf = _tf(d_tokens)
    return sum(q_tf[t] * d_tf[t] * idf_map.get(t, 0.0)
               for t in q_tf if t in d_tf)


def _load_sops() -> dict[str, dict]:
    if not SOP_DIR.exists():
        print(f"[ERROR] SOP directory not found: {SOP_DIR}", file=sys.stderr)
        sys.exit(1)
    sops = {}
    for f in sorted(SOP_DIR.glob("*.md")):
        text = f.read_text()
        m_id    = re.search(r"ID:\s*([\w-]+)", text)
        m_title = re.search(r"TITLE:\s*(.+)", text)
        if not m_id or not m_title:
            continue
        sop_id = m_id.group(1).strip()
        sops[sop_id] = {"title": m_title.group(1).strip(),
                         "text": text, "file": f.name}
    if not sops:
        print("[ERROR] No SOP files found in data/sop/", file=sys.stderr)
        sys.exit(1)
    return sops


def main() -> None:
    print("=" * 70)
    print("MAFD — Step 6: RAG retrieval evaluation  (Table 6, Section 5.8)")
    print("=" * 70)

    sops = _load_sops()
    print(f"\n[step6] SOPs loaded: {list(sops.keys())}")

    sop_ids    = list(sops.keys())
    sop_tokens = [_tokenize(sops[sid]["text"]) for sid in sop_ids]
    idf_map    = _idf(sop_tokens)

    results = []
    for sc in SCENARIOS:
        q_tokens  = _tokenize(sc["query"])
        scores    = {sid: _tfidf_score(q_tokens, sop_tokens[i], idf_map)
                     for i, sid in enumerate(sop_ids)}
        ranked    = sorted(scores, key=scores.get, reverse=True)  # type: ignore[arg-type]
        retrieved = set(ranked[:TOP_K])
        gt        = set(GROUND_TRUTH[sc["fault_type"]])
        cp = len(retrieved & gt) / len(retrieved) if retrieved else 0.0
        cr = len(retrieved & gt) / len(gt)        if gt        else 0.0
        results.append({**sc, "retrieved": sorted(retrieved),
                         "gt": sorted(gt), "cp": cp, "cr": cr})

    # ── Per-scenario output ────────────────────────────────────────────────────
    print()
    print(f"{'ID':>4} {'FaultType':>9} {'CP':>6} {'CR':>6}  "
          f"{'Retrieved':32}  {'Ground Truth'}")
    print("-" * 90)
    for r in results:
        print(f"{r['id']:>4} {r['fault_type']:>9} {r['cp']:>6.2f} {r['cr']:>6.2f}  "
              f"{str(r['retrieved']):32}  {r['gt']}")

    # ── Aggregate ──────────────────────────────────────────────────────────────
    cp_mean = sum(r["cp"] for r in results) / len(results)
    cr_mean = sum(r["cr"] for r in results) / len(results)

    print()
    print("=" * 70)
    print("TABLE 6 — RAG retrieval evaluation summary")
    print("=" * 70)
    print(f"{'Fault Type':<12} {'n':>4} {'Context Precision':>18} {'Context Recall':>15}")
    print("-" * 55)
    by_type: dict[str, list] = defaultdict(list)
    for r in results:
        by_type[r["fault_type"]].append(r)
    for ft in sorted(by_type):
        rs   = by_type[ft]
        cp_t = sum(r["cp"] for r in rs) / len(rs)
        cr_t = sum(r["cr"] for r in rs) / len(rs)
        print(f"{ft:<12} {len(rs):>4} {cp_t:>18.4f} {cr_t:>15.4f}")
    print("-" * 55)
    print(f"{'Mean':<12} {len(results):>4} {cp_mean:>18.4f} {cr_mean:>15.4f}")

    print()
    print("Retrieval method : TF-IDF sparse similarity (conservative lower bound)")
    print("Deployed system  : ChromaDB + BAAI/bge-small-en-v1.5 dense embeddings")
    print("k (top-k)        :", TOP_K)
    print("Scenarios        :", len(results))
    print("SOP corpus size  :", len(sops))
    print()
    print("Note: Faithfulness evaluation requires expert-validated ground-truth")
    print("      diagnostic plans per scenario and is not computed here.")
    print("      See Section 5.8 for the planned RAGAS evaluation methodology.")
    print("\n[step6] Done.")


if __name__ == "__main__":
    main()
