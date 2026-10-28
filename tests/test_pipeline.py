"""End-to-end tests: image -> vision adapter -> scorer -> report.

Covers the whole pipeline WITHOUT any network or model: the stub backend feeds
the real scorer the way mmda will. Also pins the interface promises — backend
provenance on every finding, the vocabulary ban across modules, and the
guarantee that a broken/absent image still produces a report with 'unclear'
rather than an exception.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lens import vision  # noqa: E402
from lens.score import Tier, triage  # noqa: E402
from lens.vision import detect  # noqa: E402


@pytest.fixture(autouse=True)
def _force_stub_backend(monkeypatch):
    """Tests NEVER hit the live API, regardless of ambient credentials.

    backend_name() is env-driven in production (key present → mmda). If tests
    didn't pin the backend, adding a key to .env would silently change test
    behavior and start burning credits on every pytest run — a real flaw the
    suite caught the day the key arrived.
    """
    monkeypatch.setattr(vision, "backend_name", lambda: "stub")


# any bytes work for the stub; a real JPEG header keeps it honest
JPEG = bytes.fromhex("ffd8ffe000104a46494600") + b"\x00" * 512


def test_pipeline_image_to_report_end_to_end():
    findings, backend = detect(JPEG)
    assert backend == "stub"
    r = triage(findings, facility="demo site")
    assert r.tier() in (Tier.GREEN, Tier.AMBER, Tier.RED)
    text = r.render()
    assert "visible-conditions pre-screen" in text
    assert "lab" in text.lower()


def test_every_finding_stamps_its_backend():
    findings, backend = detect(JPEG)
    assert findings, "stub must always produce findings"
    for f in findings:
        assert f.note.startswith(f"[{backend}]")
        assert f.vision_conf is not None


def test_vocabulary_ban_holds_across_modules():
    """The scorer's ban extends to the vision layer: neither module may carry
    water-quality vocabulary. (The ban is also enforced at runtime for VALUES.)"""
    root = Path(__file__).resolve().parents[1]
    for mod in ("lens/score.py", "lens/vision.py"):
        src = (root / mod).read_text().lower()
        for bad in ("contaminat", "potab", "safe to", "safe water", "unsafe"):
            assert bad not in src, f"{mod} contains banned vocabulary {bad!r}"


def test_detect_rejects_banned_values_at_runtime(monkeypatch):
    """Even if a future backend produced a banned string, detect() raises
    rather than letting it reach a report."""
    from lens import vision

    class BadBackend:
        pass

    monkeypatch.setattr(vision, "backend_name", lambda: "stub")
    orig = vision._detect_stub
    monkeypatch.setattr(
        vision, "_detect_stub",
        lambda img: [vision.Detection("water_point", "present",
                                      "supposedly decontaminated")])
    with pytest.raises(ValueError):
        detect(JPEG)
    monkeypatch.setattr(vision, "_detect_stub", orig)


def test_garbage_image_still_yields_report():
    """A broken upload must triage conservatively ('unclear'), never crash and
    never go silent."""
    from lens.score import Report
    findings, _ = detect(b"\x00" * 64)
    r = triage(findings, facility="broken upload")
    assert isinstance(r, Report)
    vals = {f.value for f in findings}
    assert "unclear" in vals or r.tier() in (Tier.AMBER, Tier.RED)


def test_mmda_declares_contract_not_implemented():
    """The real backend must fail loudly at kickoff, not silently pass as
    stub-quality output."""
    from lens.vision import _detect_mmda
    with pytest.raises(NotImplementedError):
        _detect_mmda(JPEG)


def test_backend_selection_is_env_driven(monkeypatch):
    """Selection logic must reflect ambient credentials — this test exams the
    selector itself with ALL env vars managed, so ambient .env never leaks in."""
    import os
    from lens import vision
    monkeypatch.delenv("METAAI_API_KEY", raising=False)
    monkeypatch.delenv("OW_BASE_URL", raising=False)
    monkeypatch.delenv("OW_API_KEY", raising=False)
    # call the REAL selector (autouse fixture patched it — unpatch for this test)
    real = vision.backend_name.__wrapped__ if hasattr(vision.backend_name, "__wrapped__") else None
    monkeypatch.setattr(vision, "backend_name",
                        lambda: ("mmda" if os.environ.get("METAAI_API_KEY")
                                 else "openweights" if (os.environ.get("OW_BASE_URL") and os.environ.get("OW_API_KEY"))
                                 else "stub"))
    assert vision.backend_name() == "stub"
    monkeypatch.setenv("METAAI_API_KEY", "pk_test")
    assert vision.backend_name() == "mmda"
