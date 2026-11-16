"""
SOP retrieval: does a diagnosed fault cite the procedure that actually covers it?

This is the test the knowledge base never had. Before the fault-type SOPs
existed, the corpus held only operational-anomaly procedures (overload, theft,
miscoordination, transformer), so an SLG diagnosis cited a *theft* SOP as the
justification for its recommended actions — a citation that actively misleads.

Retrieval quality is not a property of the documents alone. Two separate bugs
found while writing these assertions, both invisible without them:

  - a bare classifier code ("LL") carries almost no semantic signal, so the
    query boilerplate dominated and sent it to the miscoordination SOP;
  - the word "distribution" in the query suffix was on its own enough to send an
    LL fault to the open-conductor procedure.

So these tests pin the QUERY as much as the corpus. They need the built vector
store (scripts/refresh_kb.py) and skip when it is absent.
"""

from pathlib import Path

import pytest

KB_DIR = Path("artifacts/kb")

requires_kb = pytest.mark.skipif(
    not KB_DIR.exists() or not any(KB_DIR.iterdir()),
    reason="SOP vector store not built; run scripts/refresh_kb.py",
)

# Every fault_type the classifier can emit (the `target_fault_type` values in the
# testbed data), and the procedure that covers it. LLL and LLLG share one: the
# three-phase SOP covers both, since the ground path does not change the
# response.
EXPECTED_SOP = {
    "SLG": "SOP-SLG-005",
    "LL": "SOP-LL-006",
    "LLG": "SOP-LLG-007",
    "LLL": "SOP-3PH-008",
    "LLLG": "SOP-3PH-008",
    "OPEN_1PH": "SOP-OPEN-009",
    "OPEN_2PH": "SOP-OPEN-009",
    "OPEN_3PH": "SOP-OPEN-009",
}


def test_every_classifier_label_has_query_terms():
    """
    A code with no expansion falls back to raw boilerplate, which retrieves badly.

    Cheap to check, and it fails the moment someone trains the classifier on a
    new label without adding the vocabulary to match.
    """
    from app.faults.constants import FAULT_QUERY_TERMS

    missing = set(EXPECTED_SOP) - set(FAULT_QUERY_TERMS)
    assert not missing, f"fault types with no KB query terms: {sorted(missing)}"


def test_query_expansion_replaces_bare_codes():
    from app.faults.service import _kb_query

    query = _kb_query("SLG near b671 (~0.4 km)", "ieee13")
    assert "single line-to-ground" in query
    assert "b671" not in query, "bus id in the query adds noise, not signal"

    # An already-descriptive heuristic phrase is passed through untouched.
    passthrough = _kb_query("Balanced three-phase fault near b632", "ieee13")
    assert "Balanced three-phase fault" in passthrough


@requires_kb
@pytest.mark.parametrize(("fault_type", "expected"), sorted(EXPECTED_SOP.items()))
def test_fault_type_retrieves_its_own_sop(fault_type: str, expected: str):
    """The citation on a ticket has to be the procedure for that fault."""
    from app.faults.service import _kb_query
    from app.rag.retriever import kb_retrieve_impl

    hits = kb_retrieve_impl(query=_kb_query(f"{fault_type} near b671", "ieee13"), k=1)

    assert hits, f"no SOP retrieved for {fault_type}"
    assert hits[0]["source_id"] == expected, (
        f"{fault_type} cited {hits[0]['source_id']} ({hits[0].get('title')}), expected {expected}"
    )


@requires_kb
def test_short_circuit_faults_no_longer_cite_operational_sops():
    """
    The regression that motivated the whole set.

    Overload, theft, miscoordination and transformer procedures describe slow
    load-related conditions. None of them tells an operator what to do about a
    line-to-ground fault, and citing one as the basis for a recommendation is
    worse than citing nothing.
    """
    from app.faults.service import _kb_query
    from app.rag.retriever import kb_retrieve_impl

    operational = {"SOP-OVLD-001", "SOP-THFT-003", "SOP-MISC-002", "SOP-TRF-004"}

    for fault_type in EXPECTED_SOP:
        hits = kb_retrieve_impl(query=_kb_query(f"{fault_type} near b671", "ieee13"), k=1)
        cited = hits[0]["source_id"]
        assert cited not in operational, f"{fault_type} still cites the operational SOP {cited}"


@requires_kb
def test_operational_conditions_still_retrieve_their_own_sops():
    """The new documents must not have displaced what already worked."""
    from app.rag.retriever import kb_retrieve_impl

    cases = {
        "feeder loading above continuous thermal rating for several minutes": "SOP-OVLD-001",
        "high loading with no matching billed demand, suspected unauthorized connection": "SOP-THFT-003",
        "upstream device tripped for a downstream fault, coordination curves violated": "SOP-MISC-002",
        "transformer winding temperature elevated, overcurrent relay operated": "SOP-TRF-004",
    }

    for query, expected in cases.items():
        hits = kb_retrieve_impl(query=query, k=1)
        assert hits and hits[0]["source_id"] == expected, (
            f"{expected} no longer retrieved for its own condition; got "
            f"{hits[0]['source_id'] if hits else 'nothing'}"
        )


@requires_kb
def test_every_synthetic_sop_declares_its_provenance():
    """
    These are generated references, not approved utility procedures.

    The marker lives in the BODY rather than the header so it travels with the
    retrieved snippet — an operator reading a citation sees the caveat, not just
    whoever opens the file.
    """
    from app.rag.kb_loader import load_sop_documents

    generated = set(EXPECTED_SOP.values()) | {"SOP-FLISR-011", "SOP-REC-012", "SOP-HIZ-010"}
    by_id = {d["metadata"]["source_id"]: d for d in load_sop_documents()}

    for source_id in sorted(generated):
        assert source_id in by_id, f"{source_id} did not load"
        assert "SYNTHETIC REFERENCE" in by_id[source_id]["content"], (
            f"{source_id} does not declare that it is generated"
        )


# ── citations composed by the LLM ────────────────────────────────────────────


@requires_kb
def test_agent_written_snippets_are_replaced_with_the_real_document():
    """
    The agent composes `kb_citations`, so its `snippet` is model output.

    Two things go wrong if it is trusted: the SYNTHETIC REFERENCE provenance is
    dropped (it is the first thing in every generated SOP and the agent
    paraphrases past it), and a snippet the model wrote is a fabricated quotation
    of a real document — which Agent_Prompt_Guide.md already forbids and which is
    harder to spot than a fabricated source id.
    """
    from app.faults.service import _restore_citation_snippets

    ticket = {
        "kb_citations": [
            {
                "source_id": "SOP-SLG-005",
                "title": "Some title the model chose",
                "snippet": "A paraphrase the model wrote that is not in the document.",
            }
        ]
    }

    restored = _restore_citation_snippets(ticket)["kb_citations"]

    assert len(restored) == 1
    assert restored[0]["source_id"] == "SOP-SLG-005"
    assert "paraphrase the model wrote" not in restored[0]["snippet"]
    assert "SYNTHETIC REFERENCE" in restored[0]["snippet"], (
        "the provenance notice must survive into the ticket an operator reads"
    )
    # Title comes back from the KB too, so a plausible-sounding wrong title
    # cannot ride along with a correct id.
    assert restored[0]["title"] == "Single Line-to-Ground Fault Response"


@requires_kb
def test_a_citation_of_a_nonexistent_sop_is_dropped():
    """A hallucinated source id must not appear with unverifiable text beside it."""
    from app.faults.service import _restore_citation_snippets

    ticket = {
        "kb_citations": [
            {"source_id": "SOP-DOES-NOT-EXIST-999", "snippet": "invented"},
            {"source_id": "SOP-SLG-005", "snippet": "also invented"},
        ]
    }

    restored = _restore_citation_snippets(ticket)["kb_citations"]

    assert [c["source_id"] for c in restored] == ["SOP-SLG-005"]


def test_restore_is_a_no_op_when_there_are_no_citations():
    """Retrieval degrading to [] must not turn into an exception in the ticket path."""
    from app.faults.service import _restore_citation_snippets

    assert _restore_citation_snippets({"kb_citations": []})["kb_citations"] == []
    assert "kb_citations" not in _restore_citation_snippets({})
