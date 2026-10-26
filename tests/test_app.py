"""App-layer tests: the review UI's contract, headless (no Gradio server).

Covers the functions the UI binds to — inspect() and rule() — because a judge
or an inspector experiences THOSE behaviors, and 'holds up in production'
starts with the store being right when a human corrects the machine.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import lens.app as app  # noqa: E402
from lens.score import Tier  # noqa: E402


@pytest.fixture()
def tmp_store(monkeypatch, tmp_path):
    p = tmp_path / "events.jsonl"
    monkeypatch.setattr(app, "_STORE_PATH", p)
    monkeypatch.setattr(app, "_store", app.Store(p))
    return p


def test_inspect_produces_report_and_persists_events(tmp_store, tmp_path):
    img = tmp_path / "p.jpg"
    img.write_bytes(bytes.fromhex("ffd8ffe000104a46494600") + b"\x11" * 256)
    md, state = app.inspect(str(img), "BH-014")
    assert "SANITOVA LENS" in md
    assert "visible-conditions" in md
    evs = app._store.all_events()
    assert evs, "inspection events must be persisted"
    assert all(e.facility == "BH-014" for e in evs)
    assert state[0]  # image sha recorded


def test_ruling_records_human_source_and_reference(tmp_store, tmp_path):
    img = tmp_path / "p.jpg"
    img.write_bytes(bytes.fromhex("ffd8ffe000104a46494600") + b"\x11" * 256)
    md, state = app.inspect(str(img), "BH-001")
    cat, st = "handwashing", "soap_visible"
    out = app.rule(state, cat, st, "yes", "soap dispenser visible on wall")
    assert "Ruling recorded" in out
    evs = app._store.all_events()
    human = [e for e in evs if e.source == "inspector"]
    assert human, "inspector event must be stored"
    assert human[0].corrects, "human ruling must reference the vision event"


def test_ruling_without_inspection_is_refused(tmp_store, tmp_path):
    out = app.rule(None, "water_point", "present", "yes", "")
    assert "Run an inspection first" in out


def test_ruling_for_missing_finding_is_refused(tmp_store, tmp_path):
    img = tmp_path / "p.jpg"
    img.write_bytes(bytes.fromhex("ffd8ffe000104a46494600") + b"\x11" * 256)
    _, state = app.inspect(str(img), "BH-002")
    out = app.rule(state, "excreta", "slab_condition", "damaged", "")
    # the stub never produces excreta findings; a ruling on them must be refused
    assert "No recorded" in out


def test_agreement_shown_after_ruling(tmp_store, tmp_path):
    img = tmp_path / "p.jpg"
    img.write_bytes(bytes.fromhex("ffd8ffe000104a46494600") + b"\x11" * 256)
    _, state = app.inspect(str(img), "BH-003")
    out = app.rule(state, "handwashing", "soap_visible", "yes", "")
    assert "Measured agreement" in out


def test_scope_banner_is_on_the_page(tmp_store):
    """The banner constant is used in the page header and in every report."""
    ui = app.build_ui()
    texts = [getattr(b, "value", "") for b in ui.blocks.values()
             if hasattr(b, "value") and isinstance(getattr(b, "value", None), str)]
    assert any(app._SCOPE_BANNER in t for t in texts), \
        "scope banner must appear as static page text"


def test_no_banned_strings_in_ui_markdown(tmp_store, tmp_path):
    img = tmp_path / "p.jpg"
    img.write_bytes(bytes.fromhex("ffd8ffe000104a46494600") + b"\x11" * 256)
    md, _ = app.inspect(str(img), "BH-004")
    for bad in ("unsafe", "contaminat", "potab"):
        assert bad not in md.lower(), f"UI emitted banned vocabulary: {bad}"
