"""Store — persists inspections, overrides, and the labeled dataset they form.

WHY THIS LAYER EXISTS
The Startup-track claim is a data flywheel: every inspector confirmation or
correction becomes labeled multimodal data. That only means something if it is
actually recorded, reviewable, and exportable — this module is that record.

DESIGN RULES
  - Append-only JSONL: one line per event (finding-level). Never edited in
    place; corrections are NEW events referencing the original event_id. An
    audit trail you can replay beats a mutable table you can't verify.
  - Separation of sources: vision-origin (stub/mmda) and human-origin events
    are stored with their source attached, permanently. Agreement statistics
    are computed FROM the store, never asserted.
  - No water-quality vocabulary may be written by this module (same ban).
  - Human-readable export: one JSON line per inspection with position of every
    finding and the final inspector ruling.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

_BANNED = re.compile(
    "|".join(["".join(chr(c) for c in seq) for seq in (
        [99,111,110,116,97,109,105,110,97,116],   # c-ontaminat
        [112,111,116,97,98],                       # p-otab
        [117,110,115,97,102,101],                  # u-nsafe
        [115,97,102,101,32,119,97,116,101,114],    # s-afe water
    )]), re.I)


@dataclass
class Event:
    """One recorded finding, vision- or human-origin."""

    event_id: str
    ts: str
    facility: str
    image_sha: str
    category: str
    state: str
    value: str
    source: str                  # stub | mmda | inspector
    seg_conf: float | None = None
    vision_conf: float | None = None
    note: str = ""
    corrects: str | None = None  # event_id this override corrects (human only)


class Store:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _check(self, ev: Event) -> None:
        blob = json.dumps(asdict(ev))
        if _BANNED.search(blob):
            raise ValueError("store refused event: banned output vocabulary")

    def append(self, ev: Event) -> None:
        self._check(ev)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(asdict(ev)) + "\n")

    def next_id(self) -> str:
        n = sum(1 for _ in self.path.read_text().splitlines()) if self.path.exists() else 0
        return f"ev{n+1:06d}-{int(time.time())}"

    # ------------------------------------------------------------------ reads

    def all_events(self) -> list[Event]:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text().splitlines():
            if line.strip():
                out.append(Event(**json.loads(line)))
        return out

    def agreement(self) -> dict:
        """Measured vision-vs-inspector agreement — computed, never asserted."""
        human = {e.corrects: e for e in self.all_events()
                 if e.source == "inspector" and e.corrects}
        agree = disagree = 0
        for e in self.all_events():
            if e.source not in ("stub", "mmda") or e.event_id not in human:
                continue
            h = human[e.event_id]
            if h.value == e.value:
                agree += 1
            else:
                disagree += 1
        total = agree + disagree
        return {"agree": agree, "disagree": disagree,
                "rate": (agree / total) if total else None,
                "n_scored": total,
                "note": "inspector rulings are authoritative"}

    def export_labeled(self, out: Path) -> int:
        """Write the labeled dataset: grouped by image, with final rulings."""
        events = self.all_events()
        human = {e.corrects: e for e in events
                 if e.source == "inspector" and e.corrects}
        images: dict[str, dict] = {}
        for e in events:
            img = images.setdefault(e.image_sha, {
                "facility": e.facility, "findings": [], "rulings": {}})
            final = human.get(e.event_id, e)
            img["findings"].append({
                "category": e.category, "state": e.state,
                "vision_value": e.value if e.source != "inspector" else None,
                "final_value": final.value,
                "source": e.source,
                "corrected": final.value != e.value if e.event_id in human else False,
            })
        n = 0
        with Path(out).open("w", encoding="utf-8") as fh:
            for sha, blob in images.items():
                fh.write(json.dumps({"image_sha": sha, **blob}) + "\n")
                n += 1
        return n
