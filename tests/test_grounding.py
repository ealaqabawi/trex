"""Numeric-grounding check — rejects LLM commentary that invents figures."""

from utils.grounding import ungrounded_numbers, vet_commentary


def test_fabricated_number_rejected():
    bad = ungrounded_numbers("whale influence 47.31%", source="volume 1500 oi 2200")
    assert "47.31" in bad


def test_rounding_within_tolerance_accepted():
    # 30.5 is a rounding of 30.45 — should pass as grounded.
    bad = ungrounded_numbers("mid 30.5", source="mid 30.45")
    assert bad == []


def test_small_integers_ignored():
    bad = ungrounded_numbers("two reasons: 1) weak flow 2) wide spread",
                              source="volume 1500")
    assert bad == []


def test_vet_commentary_drops_everything_on_fabrication():
    safe, bad = vet_commentary("the setup won 73% of the time",
                                 source="volume 500 strike 450")
    assert bad != []
    assert safe == ""


def test_vet_commentary_passes_grounded():
    safe, bad = vet_commentary("flow sits at 1500 contracts",
                                 source="volume 1500")
    assert bad == []
    assert "1500" in safe
