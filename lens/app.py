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

# Spend guard: every live vision run draws against the project's Meta credits.
# A public URL invites curiosity (and bots); without a cap, one enthusiastic
# judge costs nothing measurable but a scraper at 3am costs real money.
# After the daily cap the app falls back to the demo-grade stub and SAYS SO —
# an honest degradation, never a fake pass. The cap resets at midnight UTC.
_LIVE_RUNS_PER_DAY = int(os.environ.get("LENS_LIVE_RUNS_PER_DAY", "40"))
EXAMPLE_URL = "https://raw.githubusercontent.com/HusseinAdeiza/lens-media/master/open_dump_real.jpg"


class _DailyCap:
    """Counts live runs per UTC day; tiny, in-memory, honest."""

    def __init__(self, limit: int):
        self.limit = limit
        self.day = None
        self.n = 0

    def try_spend(self) -> bool:
        import datetime
        today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
        if today != self.day:
            self.day, self.n = today, 0
        if self.n >= self.limit:
            return False
        self.n += 1
        return True

    def left(self) -> int:
        import datetime
        today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
        if today != self.day:
            return self.limit
        return max(0, self.limit - self.n)


_cap = _DailyCap(_LIVE_RUNS_PER_DAY)

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

    # Spend guard FIRST: decide which backend this run may use.
    if os.environ.get("METAAI_API_KEY") and _cap.try_spend():
        os.environ["LENS_FORCE_BACKEND"] = "mmda"
        note = (f"live run — {_cap.left()} live runs left today (resets 00:00 UTC)")
    else:
        os.environ["LENS_FORCE_BACKEND"] = "stub"
        note = ("DEMO-GRADE fallback — daily live-run cap reached (or no API key "
                "configured). The heuristic below is NOT a vision model; come "
                "back after 00:00 UTC for live inference.")

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
    md += f"\n  {note}"
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
                ex = gr.Button("Try the published example (real photo, live models)",
                               variant="secondary")
            with gr.Column():
                out_md = gr.Markdown("Report appears here.")
        state = gr.State()

        def run_example():
            """Fetch the committed public example into a temp file and inspect it.
            Download (not URL passthrough) so the run exercises the same path a
            judge's own upload would — one honest code path for everyone."""
            import tempfile, urllib.request
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tf:
                with urllib.request.urlopen(EXAMPLE_URL, timeout=30) as r:
                    tf.write(r.read())
                path = tf.name
            return inspect(path, "published example — roadside open dump")

        btn.click(inspect, inputs=[img, fac], outputs=[out_md, state])
        ex.click(run_example, inputs=None, outputs=[out_md, state])

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
    import threading, subprocess, sys
    # the photo host must be up before the UI accepts traffic: detect(mmda)
    # round-trips uploads through it (see vision._host_bytes).
    threading.Thread(
        target=lambda: subprocess.run([sys.executable, "-m", "lens.serve", "8765"]),
        daemon=True).start()
    import time; time.sleep(1.5)
    build_ui().launch(server_name=os.environ.get("LENS_HOST", "127.0.0.1"),
                       server_port=int(os.environ.get("LENS_PORT", "7860")))
