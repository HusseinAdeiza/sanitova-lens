"""Falsification tests for the Sanitova Lens triage scorer.

The scorer ranks VISIBLE conditions into follow-up tiers. These tests prove the
properties that must hold for ANY correct implementation of the triage —
including two that came directly out of the project's framing corrections:
(1) scope — the system NEVER asserts water safety/contamination;
(2) honesty — "unclear" triages conservatively, never silently.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lens.score import Finding, Tier, triage  # noqa: E402

F = Finding
LOG = {Tier.GREEN: 0, Tier.AMBER: 1, Tier.RED: 2}


# ---------------------------------------------------------------- scope guard

def test_module_contains_no_contamination_vocabulary():
    """The framing correction, enforced: this tool never asserts safety or
    contamination. The word must not appear anywhere in the module — not in
    enums, rules, actions, or strings it can print."""
    src = Path(__file__).resolve().parents[1].joinpath("lens", "score.py").read_text()
    for bad in ("contaminat", "potab", "safe to", "safe water", "unsafe"):
        assert bad not in src.lower(), f"banned vocabulary in scorer: {bad!r}"


def test_every_output_is_an_action_not_a_verdict():
    """All tiers resolve to human work to do, never a verdict about the sight's
    actual safety."""
    cases = [
        [F("water_point", "present", "no")],
        [F("handwashing", "soap_visible", "no")],
        [F("waste", "overflow_visible", "no")],
        [F("handwashing", "present", "yes")],
    ]
    for findings in cases:
        r = triage(findings)
        assert r.action(), "every tier must carry a next action"
        assert any(w in r.action() for w in
                   ("visit", "inspection", "monitoring", "sampling")), (
                   f"action reads as a verdict, not a next step: {r.action()!r}")


# ------------------------------------------------------- the tier properties

def test_missing_water_point_is_red():
    assert triage([F("water_point", "present", "no")]).tier() is Tier.RED


def test_open_dumping_is_red():
    assert triage([F("waste", "open_dumping_within_view", "yes")]).tier() is Tier.RED


def test_damaged_tap_does_not_overstate_to_red():
    """A damaged-but-present water point is an AMBER maintenance flag. Calling
    it RED would overstate what a photograph can know — the exact overclaim the
    framing corrections banned."""
    r = triage([F("water_point", "present", "yes"),
                F("water_point", "structural_condition", "damaged")])
    assert r.tier() is Tier.AMBER


def test_monotonicity_worse_condition_never_lowers_tier():
    assert (LOG[triage([F("water_point", "present", "yes")]).tier()]
            <= LOG[triage([F("water_point", "present", "no")]).tier()])


def test_unclear_triages_conservatively_never_silently():
    """'unclear' is honest about photo limits. It must never be scored as
    though the inspector never asked."""
    unclear = LOG[triage([F("water_point", "present", "unclear")]).tier()]
    looks_fine = LOG[triage([F("water_point", "present", "yes")]).tier()]
    assert unclear > looks_fine, (
        "unclear must triage more conservatively than a clear 'present'")


def test_green_carries_no_flags():
    r = triage([F("handwashing", "present", "yes"),
                F("handwashing", "soap_visible", "yes"),
                F("waste", "bin_present", "yes")])
    assert r.tier() is Tier.GREEN


def test_highest_single_item_wins_not_average():
    """Averaging would let three greens dilute one red. A facility report is
    not a portfolio: the worst visible condition sets follow-up urgency."""
    r = triage([F("water_point", "present", "no"),    # RED
                F("handwashing", "present", "yes"),   # GREEN
                F("waste", "bin_present", "yes")])    # GREEN
    assert r.tier() is Tier.RED


# ------------------------------------------------------------ meta-test

def test_the_suite_can_actually_fail():
    """A falsification suite that cannot fail is decoration."""
    with pytest.raises(AssertionError):
        assert triage([F("water_point", "present", "no")]).tier() is Tier.GREEN, \
            "deliberately wrong"
