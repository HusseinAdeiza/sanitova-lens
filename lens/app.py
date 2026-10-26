"""Review UI — the inspector's screen. Gradio, minimal, honest by construction.

DESIGN RULES
  - The inspector is the authority. This UI exists to SHOW the machine's
    findings and RECORD the human's rulings — never to nudge, never to bury.
  - Every report names its backend; stub output is labeled DEMO-GRADE on screen.
  - The scope banner is rendered top of every report; the vocabulary ban is
    enforced on every string this UI emits (shared check with the store).
  - Corrections become store events (human source, corrects=<original id>).
  - Runs anywhere: `python3 -m lens.app` → local URL; the same app is what a
    HF Space wraps for the public demo URL.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import gradio as gr

from .score import triage
from .store import Event, Store
from .vision import backend_name, detect

_STORE_PATH = Path(os.environ.get("LENS_STORE", "./lens_events.jsonl"))
_store = Store(_STORE_PATH)

_SCOPE_BANNER = (
    "VISIBLE CONDITIONS ONLY - pre-screen triage for licensed inspectors. "
    "This tool never asserts water safety or quality; water quality requires "
    " laboratory testing. The inspector's ruling is authoritative."
)


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()[:16]


def inspect(image, facility_name: str):
    """Photo -> vision -> scorer -> report. Returns (report_md, state)."""
    if image is None:
        return "No image supplied.", gr.update()
    img_bytes = Path(image).read_bytes() if isinstance(image, (str, Path)) else image
    sha = _sha(img_bytes)
    findings, backend = detect(img_bytes)
    report = triage(findings, facility=facility_name or "unnamed facility")

    # persist vision events (source-stamped)
    ids = []
    for f in findings:
        ev = Event(event_id=_store.next_id(), ts=_now(), facility=report.facility,
                   image_sha=sha, category=f.category, state=f.state,
                   value=f.value, source=backend, seg_conf=f.seg_conf,
                   vision_conf=f.vision_conf, note=f.note)
        _store.append(ev)
        ids.append(ev.event_id)

    md = report.render()
    md += f"\n  detected by : {backend}"
    if backend == "stub":
        md += "  ( DEMO-GRADE heuristic - not a vision model )"
    md += f"\n  event ids   : {', '.join(ids)}"
    md += f"\n\n_{_SCOPE_BANNER}_"
    return md, (sha, ids)


def rule(sha_ids, category, state, human_value, note):
    """Record the inspector's ruling for a finding. The human is the source."""
    sha, ids = sha_ids or (None, [])
    if not sha_ids or not ids:
        return "Run an inspection first — nothing to rule on."
    # one ruling per recorded finding of that category+state from the last run
    evs = _store.all_events()
    target = None
    for e in reversed(evs):
        if (e.image_sha == sha and e.category == category and e.state == state
                and e.source != "inspector"):
            target = e
            break
    if target is None:
        return f"No recorded {category}.{state} finding to rule on for this image."
    ev = Event(event_id=_store.next_id(), ts=_now(), facility=target.facility,
               image_sha=sha, category=category, state=state,
               value=human_value, source="inspector", corrects=target.event_id,
               note=note or "")
    _store.append(ev)
    a = _store.agreement()
    rate = "n/a" if a["rate"] is None else f"{a['rate']*100:.0f}%"
    return (f"Ruling recorded: {category}.{state} = {human_value!r} "
            f"(corrects {target.event_id}). "
            f"Measured agreement so far: {rate} of {a['n_scored']} scored.")


def _now() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def build_ui():
    with gr.Blocks(title="Sanitova Lens — visible-conditions pre-screen") as ui:
        gr.Markdown(
            "## Sanitova Lens\n" + _SCOPE_BANNER)
        with gr.Row():
            with gr.Column():
                img = gr.Image(type="filepath", label="Facility photo",
                               sources=["upload", "webcam"])
                fac = gr.Textbox(label="Facility name / ID", placeholder="e.g. BH-014")
                btn = gr.Button("Run pre-screen", variant="primary")
            with gr.Column():
                out_md = gr.Markdown("Report appears here.")
        state = gr.State()

        btn.click(inspect, inputs=[img, fac], outputs=[out_md, state])

        gr.Markdown("---\n### Inspector ruling (authoritative)")
        with gr.Row():
            cat = gr.Dropdown(["water_point", "handwashing", "excreta",
                               "waste", "drainage"], label="Category")
            st = gr.Dropdown(["present", "structural_condition", "slab_condition",
                              "drainage_present", "privacy_enclosure",
                              "water_available_visible", "soap_visible",
                              "bin_present", "overflow_visible",
                              "open_dumping_within_view",
                              "standing_water_within_view",
                              "channel_blocked_visible"], label="State")
            hv = gr.Dropdown(["yes", "no", "unclear", "intact", "damaged",
                              "absent"], label="Inspector value")
        note = gr.Textbox(label="Note (optional)")
        rbtn = gr.Button("Record ruling")
        rtxt = gr.Markdown()
        rbtn.click(rule, inputs=[state, cat, st, hv, note], outputs=[rtxt])

        gr.Markdown(
            "### Data\nEvery run and every ruling is recorded as labeled data "
            "(append-only). Export happens from the CLI: `lens.store.export_labeled`.")
    return ui


if __name__ == "__main__":
    build_ui().launch(server_name=os.environ.get("LENS_HOST", "127.0.0.1"),
                       server_port=int(os.environ.get("LENS_PORT", "7860")))
