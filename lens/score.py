"""Triage scorer: visible conditions -> follow-up priority. Pure stdlib.

DESIGN RULES (from the project's framing corrections):
  - VISIBLE conditions only. This module has no vocabulary for water quality
    and must never grow one: water safety is a lab result, not a photograph
    reading. The test suite enforces that ban literally.
  - Thresholds are explicit, inspectable judgements collected here in one
    block - not truth. The inspector override is the authority; the scorer only
    decides WHERE scarce attention (field visits, lab sampling) goes first.
  - "unclear" is a first-class answer: photo quality limits what vision can
    legitimately assert, so unclear triages conservatively, never silently.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Tier(Enum):
    GREEN = "GREEN"   # routine - nothing below-threshold visible
    AMBER = "AMBER"   # follow-up inspection advisable
    RED = "RED"       # priority field visit + lab sampling recommendation


# Per-category triage: which (state, value) pairs push the report up.
# The report takes the highest tier any single item earns.
TRIAGE_RULES: dict[str, dict[tuple[str, str], Tier]] = {
    "water_point": {
        ("present", "no"): Tier.RED,
        ("present", "unclear"): Tier.AMBER,
        ("structural_condition", "damaged"): Tier.AMBER,
        ("structural_condition", "unclear"): Tier.AMBER,
        ("drainage_present", "no"): Tier.AMBER,
    },
    "handwashing": {
        ("present", "no"): Tier.AMBER,
        ("water_available_visible", "no"): Tier.AMBER,
        ("water_available_visible", "unclear"): Tier.AMBER,
        ("soap_visible", "no"): Tier.AMBER,
    },
    "excreta": {
        ("present", "no"): Tier.RED,
        ("slab_condition", "damaged"): Tier.AMBER,
        ("privacy_enclosure", "absent"): Tier.AMBER,
    },
    "waste": {
        ("bin_present", "no"): Tier.AMBER,
        ("overflow_visible", "yes"): Tier.AMBER,
        ("open_dumping_within_view", "yes"): Tier.RED,
    },
    "drainage": {
        ("standing_water_within_view", "yes"): Tier.AMBER,
        ("channel_blocked_visible", "yes"): Tier.AMBER,
    },
}


@dataclass
class Finding:
    """One documented state, as the vision stage reported it."""

    category: str
    state: str
    value: str
    seg_conf: float | None = None   # SAM mask confidence if available
    vision_conf: float | None = None
    note: str = ""

    def line(self) -> str:
        conf = ""
        if self.seg_conf is not None:
            conf = f" (seg {self.seg_conf:.2f})"
        return f"  [{self.category}] {self.state} = {self.value}{conf}"


@dataclass
class Report:
    facility: str
    findings: list[Finding] = field(default_factory=list)
    inspector_overrides: list[dict] = field(default_factory=list)

    def tier(self) -> Tier:
        earned = [TRIAGE_RULES.get(f.category, {}).get((f.state, f.value))
                  for f in self.findings]
        earned = [t for t in earned if t is not None]
        if Tier.RED in earned:
            return Tier.RED
        if Tier.AMBER in earned:
            return Tier.AMBER
        return Tier.GREEN

    def action(self) -> str:
        """The required next step. Every tier ends in human work - the tool
        determines priority, never outcome."""
        return {
            Tier.RED: "Priority field visit; collect water/surface samples for lab testing.",
            Tier.AMBER: "Schedule follow-up inspection; verify flagged items on site.",
            Tier.GREEN: "Routine monitoring cycle; no visible risks flagged this pass.",
        }[self.tier()]

    def render(self) -> str:
        lines = [
            f"SANITOVA LENS — visible-conditions pre-screen (NOT a safety test)",
            f"facility: {self.facility}",
            f"triage  : {self.tier().value}",
            f"action  : {self.action()}",
            f"scope   : presence & visible condition only; water quality requires lab analysis",
            "-" * 74,
        ]
        for f in self.findings:
            lines.append(f.line())
        if self.inspector_overrides:
            lines.append("-" * 74)
            lines.append("  inspector overrides (authoritative, collected as labeled data):")
            for o in self.inspector_overrides:
                lines.append(f"    {o['category']}.{o['state']}: vision said "
                             f"{o['vision_value']!r} -> inspector says {o['human_value']!r}")
        return "\n".join(lines)


def triage(findings: list[Finding], facility: str = "unnamed facility") -> Report:
    """Pure function: findings -> Report. No I/O, no clock, no model."""
    return Report(facility=facility, findings=list(findings))
