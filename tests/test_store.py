"""Store tests: append-only, source-separated, agreement computed not claimed,
vocabulary ban enforced at the persistence layer too."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lens.store import Event, Store  # noqa: E402


@pytest.fixture()
def store(tmp_path):
    return Store(tmp_path / "events.jsonl")


def _vis(i=1, value="yes", source="stub"):
    return Event(event_id=f"ev{i:06d}-0", ts="2026-10-26T00:00:00Z",
                 facility="demo", image_sha="abc123", category="handwashing",
                 state="soap_visible", value=value, source=source)


def test_append_and_read_back(store):
    store.append(_vis())
    assert len(store.all_events()) == 1
    assert store.all_events()[0].value == "yes"


def test_correction_is_a_new_event_referencing_the_original(store):
    """Corrections never edit history — the trail stays replayable."""
    v = _vis(1, value="no")
    store.append(v)
    h = Event(event_id="ev000002-0", ts="2026-10-26T00:01:00Z",
              facility="demo", image_sha="abc123", category="handwashing",
              state="soap_visible", value="yes", source="inspector",
              corrects=v.event_id)
    store.append(h)
    evs = store.all_events()
    assert len(evs) == 2
    assert evs[1].corrects == v.event_id
    assert evs[0].value == "no", "original finding must remain untouched"


def test_agreement_is_computed_from_stored_events(store):
    v = _vis(1, value="no")
    store.append(v)
    store.append(Event(event_id="ev000002-0", ts="t", facility="demo",
                       image_sha="abc", category="handwashing",
                       state="soap_visible", value="yes",
                       source="inspector", corrects=v.event_id))
    a = store.agreement()
    assert a["disagree"] == 1 and a["rate"] == 0.0


def test_agreement_empty_is_none_not_zero(store):
    a = store.agreement()
    assert a["rate"] is None and a["n_scored"] == 0


def test_store_refuses_banned_vocabulary(store):
    bad = _vis(value="it is not unsafe")
    with pytest.raises(ValueError):
        store.append(bad)


def test_export_groups_by_image_with_final_rulings(store):
    store.append(_vis(1, value="no"))                       # vision says no soap
    store.append(Event(event_id="ev000002-0", ts="t", facility="demo",
                       image_sha="abc123", category="handwashing",
                       state="soap_visible", value="yes",
                       source="inspector", corrects="ev000001-0"))
    out = store.path.parent / "labeled.jsonl"
    n = store.export_labeled(out)
    assert n == 1
    rec = out.read_text().splitlines()[0]
    import json
    d = json.loads(rec)
    f = d["findings"][0]
    assert f["vision_value"] == "no" and f["final_value"] == "yes"
    assert f["corrected"] is True
