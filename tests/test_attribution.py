"""
Feature attribution: does the verdict come with the measurements behind it?

docs/System_Architecture.md calls this system explainable. Before attribution
the only explanation was LLM prose written downstream of the verdict, which
could say anything and could not be checked against a meter. These tests pin
the properties that make the attribution worth putting in front of an operator.
"""

import pandas as pd
import pytest

from app.ml import attribution


@pytest.fixture(autouse=True)
def _clean_baseline():
    attribution.reset_baseline()
    yield
    attribution.reset_baseline()


def _baseline(**cols: tuple[float, float]) -> dict[str, tuple[float, float]]:
    return dict(cols)


def test_a_normal_row_attributes_nothing():
    """Attribution explains anomalies. A quiet feeder has nothing to explain."""
    base = _baseline(max_I0_I1_fault_b671=(0.003, 0.001), min_Va_fault_pu_b671=(0.999, 0.001))
    row = {"max_I0_I1_fault_b671": 0.0031, "min_Va_fault_pu_b671": 0.9991}

    assert attribution.attribute(row, baseline=base) == []


def test_deviation_below_the_threshold_is_not_reported():
    """
    Every real row has six mildly unusual numbers in it.

    Reporting them all is how an explanation becomes noise, so a feature has to
    clear MIN_SIGMA before it earns a line.
    """
    base = _baseline(max_Ia_fault_b650=(500.0, 10.0))
    just_under = {"max_Ia_fault_b650": 500.0 + (attribution.MIN_SIGMA - 0.5) * 10.0}
    just_over = {"max_Ia_fault_b650": 500.0 + (attribution.MIN_SIGMA + 0.5) * 10.0}

    assert attribution.attribute(just_under, baseline=base) == []
    assert len(attribution.attribute(just_over, baseline=base)) == 1


def test_one_line_per_quantity_at_its_worst_bus():
    """
    A bus with a narrow healthy spread dominates every ranking.

    Without the per-family collapse the list is four rows about b675 — true, and
    it tells an operator one thing four times instead of four things once.
    """
    base = _baseline(
        max_I0_I1_fault_b650=(0.003, 0.001),
        max_I0_I1_fault_b671=(0.003, 0.001),
        max_I0_I1_fault_b675=(0.002, 0.001),
        min_Va_fault_pu_b671=(0.999, 0.001),
    )
    row = {
        "max_I0_I1_fault_b650": 0.30,
        "max_I0_I1_fault_b671": 0.40,  # worst of the three
        "max_I0_I1_fault_b675": 0.20,
        "min_Va_fault_pu_b671": 0.90,
    }

    out = attribution.attribute(row, baseline=base)
    families = [item["family"] for item in out]

    assert families == sorted(set(families), key=families.index), "a family appeared twice"
    ground = next(i for i in out if i["family"] == "max_I0_I1_fault")
    assert ground["bus"] == "b671", "reported a bus other than the worst one"


def test_results_are_ranked_by_how_far_out_they_are():
    base = _baseline(
        max_I0_I1_fault_b671=(0.003, 0.001),
        min_Va_fault_pu_b671=(0.999, 0.001),
    )
    row = {"max_I0_I1_fault_b671": 0.10, "min_Va_fault_pu_b671": 0.99}

    sigmas = [abs(item["sigma"]) for item in attribution.attribute(row, baseline=base)]
    assert sigmas == sorted(sigmas, reverse=True)


def test_a_sag_is_reported_as_below_normal():
    """Direction matters: a collapsed voltage and a current spike are not the same event."""
    base = _baseline(min_Va_fault_pu_b684=(0.999, 0.001))
    out = attribution.attribute({"min_Va_fault_pu_b684": 0.79}, baseline=base)

    assert out[0]["direction"] == "below"
    assert out[0]["sigma"] < 0


def test_every_feature_family_carries_an_operator_readable_meaning():
    """
    A raw column name in front of an operator is not an explanation.

    If a family is ever added to the extractor without a label here, the ticket
    would show `max_I0_I1_fault` and this catches it.
    """
    for family, label in attribution.FAMILY_LABELS.items():
        assert label and not label.startswith("max_"), family
        assert attribution.FAMILY_MEANING.get(family), f"{family} has no physical meaning"


def test_a_missing_baseline_costs_the_explanation_not_the_verdict():
    """Enrichment must never be able to take a ticket down with it."""
    assert attribution.attribute({"max_Ia_fault_b650": 5000.0}, baseline={}) == []


def test_non_finite_features_are_skipped():
    """De-energized buses arrive as inf/nan (docs §11) and must not be ranked."""
    base = _baseline(max_Ia_fault_b675=(1.0, 0.1), max_I0_I1_fault_b675=(0.002, 0.001))
    row = {"max_Ia_fault_b675": float("inf"), "max_I0_I1_fault_b675": 2.0}

    out = attribution.attribute(row, baseline=base)
    assert [i["feature"] for i in out] == ["max_I0_I1_fault_b675"]


def test_a_real_fault_row_explains_itself_against_the_trained_baseline():
    """
    The end-to-end shape, against the same normal rows the detector trained on.

    Skipped rather than failed when the training CSV is absent: it is generated
    by scripts/generate_normal_data.py, not committed.
    """
    if not attribution.NORMAL_TRAIN_CSV.exists():
        pytest.skip("normal_train_013.csv not generated; run step 1")

    frame = pd.read_csv("data/generated/validation_013.csv")
    slg = frame[frame["target_fault_type"] == "SLG"].iloc[0]

    out = attribution.attribute(slg)
    assert out, "an SLG explained nothing"
    # A single line-to-ground fault is defined by current returning through
    # ground, so that family has to be in the explanation.
    assert any(i["family"] == "max_I0_I1_fault" for i in out)
