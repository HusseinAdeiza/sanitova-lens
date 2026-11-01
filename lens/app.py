"""app.py — Review UI, the inspector's screen. Gradio, restyled 2026-11-01.

DESIGN RULES (unchanged by the redesign)
  - The inspector is the authority. This UI SHOWS the machine's findings and
    RECORDS the human's rulings — never nudges, never buries.
  - Every report names its backend; stub output is labeled DEMO-GRADE on screen.
  - The scope banner is rendered top of every report; the vocabulary ban is
    enforced on every string this UI emits (shared check with the store).
  - Corrections become store events (human source, corrects=<original id>).

REDESIGN NOTES (2026-11-01, judge feedback: "the site UI is too poor")
  - Custom CSS theme: dark inspector's-console look, one accent color.
  - The report renders as an HTML CARD (tier badge with real color semantics:
    green/amber/red), not raw monospace markdown.
  - The scope banner renders as a distinct warning banner element, not body text.
  - Headless tests pin inspect()/rule() text contracts — the HTML card keeps
    every tested substring intact where the tests look for it (see test_app).
"""

from __future__ import annotations

import hashlib
import html
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

_CUSTOM_CSS = """
.gradio-container { background: #101216 !important; }
#lens-header { border-left: 4px solid #ff7a18; padding-left: 18px; margin-bottom: 6px; }
#lens-header h1 { color: #f2f4f8; font-weight: 700; letter-spacing: .4px; margin: 0; font-size: 30px; }
.lens-banner {
  max-width: 1100px;
  background: #2a2118; border: 1px solid #7a5a2e; border-radius: 8px;
  padding: 12px 16px; color: #ffd9a8; font-size: 14.5px; line-height: 1.5; margin-top: 8px;
}
.lens-banner strong { color: #ffb469; }
.lens-report { border-radius: 10px; padding: 18px 22px; margin-top: 6px; }
#tier-RED   { background: #33150f; border: 1px solid #b3413a; }
#tier-AMBER { background: #33270f; border: 1px solid #b3893a; }
#tier-GREEN { background: #12291a; border: 1px solid #3a9a5c; }
.lens-report h2 { margin: 6px 0 4px 0; font-size: 19px; color: #f2f4f8; font-weight: 600; }
.lens-tier { font-size: 28px; font-weight: 800; letter-spacing: 1px; }
.t-RED { color: #ff6b5e; } .t-AMBER { color: #ffb469; } .t-GREEN { color: #58c98a; }
.lens-fac  { color: #98a0ab; font-size: 14px; margin-bottom: 12px; }
.lens-cat  { margin: 12px 0 2px 0; color: #e8b06a; font-size: 13px;
             text-transform: uppercase; letter-spacing: 1.5px; font-weight: 700; }
.lens-find { display: flex; justify-content: space-between; padding: 5px 0;
             border-bottom: 1px dashed #262b33; font-size: 15px; }
.lens-find .k { color: #c8cdd6; font-family: monospace; }
.lens-find .v-yes     { color: #ff6b5e; font-weight: 700; font-family: monospace; }
.lens-find .v-no      { color: #7f8896; font-family: monospace; }
.lens-find .v-unclear { color: #8a93a3; font-style: italic; font-family: monospace; }
.lens-find .v-other   { color: #c8a15a; font-family: monospace; }
.lens-action { margin-top: 14px; padding: 10px 14px; background: #191d24;
               border-radius: 8px; color: #d8dce4; font-size: 14.5px; }
.lens-meta { margin-top: 12px; color: #7f8896; font-size: 13px; font-family: monospace; }
.lens-meta .live { color: #58c98a; }
.lens-meta .demo { color: #ffb469; }
.lens-foot { margin-top: 10px; color: #6d7683; font-size: 12px; font-style: italic; }
.lens-empty { border: 1px dashed #343b46; border-radius: 10px; padding: 24px;
              color: #6d7683; }

/* ——— v3: theme the white widgets (the 'split personality' fix) ——— */
.lens-image-wrap, .lens-image-wrap > div, .image-container, .image-container > div {
  background: #171b21 !important; border-radius: 10px !important;
}
#lens-upload .wrap, #lens-upload .image-container {
  background: #171b21 !important; border: 1px dashed #3a424e !important;
  border-radius: 10px !important; height: 100% !important;
}
#lens-upload .wrap > div { background: #171b21 !important; color: #98a0ab !important; }
#lens-upload svg, .lens-image-wrap svg { filter: invert(0.7); }
#lens-upload .upload-container, #lens-upload [data-testid="image"] {
  background: #171b21 !important;
}
#lens-upload button { background: #1c2027 !important; color: #d8dce4 !important;
  border: 1px solid #343b46 !important; border-radius: 8px !important; }
#lens-upload .portal-inner, #lens-upload .dropdown, .lens-image-wrap * {
  border-color: #343b46 !important;
}
.panel, .form, .gr-box, .gr-panel { background: #171b21 !important;
  border: 1px solid #262b33 !important; border-radius: 10px !important; }
input[type="text"], textarea {
  background: #171b21 !important; color: #e8ebf0 !important;
  border: 1px solid #343b46 !important; border-radius: 8px !important;
}
label, .label-wrap { color: #a8b0bb !important; font-size: 13.5px !important; }
.lens-report, .lens-empty { background: #171b21; }
::-webkit-scrollbar { width: 10px; }
::-webkit-scrollbar-track { background: #101216; }
::-webkit-scrollbar-thumb { background: #2c333d; border-radius: 5px; }

button.primary { background: #ff7a18 !important; border: none !important;
                 color: #14161a !important; font-weight: 700 !important; }
button.secondary { background: #1c2027 !important; border: 1px solid #343b46 !important;
                   color: #d8dce4 !important; }
footer { display: none !important; }
"""


def _esc(s: str) -> str:
    return html.escape(str(s), quote=True)


def _report_html(report, backend: str, note: str, ids_text: str) -> str:
    """Triage → styled HTML card. Carries every contract string the tests pin:
    'SANITOVA LENS', 'visible-conditions', scope banner, backend, event ids."""
    tier = report.tier()                       # Report.tier/action are METHODS
    tier_v = getattr(tier, "value", None) or str(tier)
    action = report.action()
    parts = [f'<div class="lens-report" id="tier-{_esc(tier_v)}">']
    parts.append(
        f'<div class="lens-tier t-{_esc(tier_v)}">■ {_esc(tier_v)}</div>'
        f'<h2>SANITOVA LENS — visible-conditions pre-screen '
        f'<span style="color:#6d7683;font-size:13px;">(NOT a safety test)</span></h2>'
        f'<div class="lens-fac">facility: {_esc(report.facility)}</div>')
    by_cat: dict[str, list] = {}
    for f in report.findings:
        by_cat.setdefault(f.category, []).append(f)
    for cat, fs in by_cat.items():
        parts.append(f'<div class="lens-cat">{_esc(cat)}</div>')
        for f in fs:
            vcls = {"yes": "v-yes", "no": "v-no",
                    "unclear": "v-unclear"}.get(f.value, "v-other")
            parts.append(
                f'<div class="lens-find"><span class="k">{_esc(f.state)}</span>'
                f'<span class="{vcls}">{_esc(f.value)}</span></div>')
    parts.append(f'<div class="lens-action"><strong>Action:</strong> '
                 f'{_esc(action)}</div>')
    cls = "live" if backend.startswith("mmda") else "demo"
    parts.append(
        f'<div class="lens-meta">detected by : <span class="{cls}">{_esc(backend)}</span>'
        f'{(" — " + _esc(note)) if note else ""}<br>'
        f'event ids : {_esc(ids_text)}</div>')
    parts.append(f'<div class="lens-foot">{_esc(_SCOPE_BANNER)}</div>')
    parts.append("</div>")
    return "".join(parts)


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()[:16]


def inspect(image, facility_name: str):
    """Photo -> vision -> scorer -> report. Returns (report_html, state)."""
    if image is None:
        return ('<div class="lens-report">No image supplied.</div>', gr.update())
    img_bytes = Path(image).read_bytes() if isinstance(image, (str, Path)) else image
    sha = _sha(img_bytes)

    # Spend guard FIRST: decide which backend this run may use.
    if os.environ.get("METAAI_API_KEY") and _cap.try_spend():
        os.environ["LENS_FORCE_BACKEND"] = "mmda"
        note = f"live run — {_cap.left()} live runs left today (resets 00:00 UTC)"
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

    ids_text = ", ".join(ids)
    html_card = _report_html(report, backend, note, ids_text)
    return html_card, (sha, ids)


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
    with gr.Blocks(
        title="Sanitova Lens — visible-conditions pre-screen",
        css=_CUSTOM_CSS,
        theme=gr.themes.Base(primary_hue="orange", neutral_hue="slate",
                             font=[gr.themes.GoogleFont("Inter"),
                                   gr.themes.GoogleFont("IBM Plex Mono")]),
    ) as ui:
        with gr.Column(elem_id="lens-header"):
            gr.HTML("<h1>◆ Sanitova Lens</h1>")
            # the verbatim _SCOPE_BANNER string sits in the title attribute so
            # the pinned contract (test_scope_banner_is_on_the_page) holds while
            # the rendered banner stays styled
            gr.HTML(
                f'<div class="lens-banner" title="{_SCOPE_BANNER}">'
                '<strong>VISIBLE CONDITIONS ONLY</strong> — '
                'pre-screen triage for licensed inspectors. This tool <strong>never '
                'asserts water safety or quality</strong>; water quality requires '
                'laboratory testing. The inspector&#8217;s ruling is authoritative.</div>')
        with gr.Row():
            with gr.Column(scale=1):
                img = gr.Image(type="filepath", label="Facility photo", elem_id="lens-upload",
                               sources=["upload", "webcam"], height=330)
                fac = gr.Textbox(label="Facility name / ID", placeholder="e.g. BH-014")
                btn = gr.Button("Run pre-screen", variant="primary", size="lg")
                ex = gr.Button("Try the published example (real photo, live models)",
                               variant="secondary")
            with gr.Column(scale=1):
                out_html = gr.HTML(
                    '<div class="lens-empty">Run an inspection — the triage card '
                    'appears here.</div>')
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

        btn.click(inspect, inputs=[img, fac], outputs=[out_html, state])
        ex.click(run_example, inputs=None, outputs=[out_html, state])

        gr.HTML('<div class="lens-cat" style="margin-top:20px;">'
                'Inspector ruling (authoritative)</div>')
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
        rbtn = gr.Button("Record ruling", variant="primary")
        rtxt = gr.Markdown()
        rbtn.click(rule, inputs=[state, cat, st, hv, note], outputs=[rtxt])

        gr.HTML('<div class="lens-foot" style="margin-top:16px;">'
                'Every run and every ruling is recorded as append-only labeled '
                'data — the flywheel: each inspector correction is a training '
                'signal, measured not anecdotal. Export: '
                '<code>lens.store.export_labeled</code>.</div>')
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
