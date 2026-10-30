"""Integration tests for the mmda backend — mocked transport, real logic.

The SAM/Muse probes on 2026-10-26 verified the LIVE transport (live: HTTP 200,
237k-char payloads with 9 boxes+9 masks; Muse strict-JSON). Those probes cost
credits and need network. These tests re-play the SAME response shapes through
mocked clients so the parsing, casting, ban-handling, and uncertainty degrading
are verified offline — loudly, every run, no credits burned.

Fixtures encode the exact shapes observed live: SAM's <|box|>/<|mask|> tag text
and Muse's JSON-in-prose output.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import lens.mmda as mmda  # noqa: E402
from lens.vision import Detection  # noqa: E402

URL = "https://raw.githubusercontent.com/HusseinAdeiza/lens-media/master/test_facility.jpg"


# ------------------------------------------------------------------ fixtures

class FakeMessage:
    def __init__(self, text):
        self.type = "message"
        self.content = [FakeContent(text)]


class FakeContent:
    def __init__(self, text):
        self.type = "output_text"
        self.text = text


class FakeResponses:
    def __init__(self, text):
        self._text = text

    def create(self, **kw):
        return FakeResp(self._text)


class FakeResp:
    def __init__(self, text):
        self.output = [FakeMessage(text)]


class _CompletionsAPI:
    """The client.chat.completions surface."""
    def __init__(self, payload):
        self._payload = payload

    def create(self, **kw):
        content = (self._payload if isinstance(self._payload, str)
                   else json.dumps(self._payload))
        m = type("Msg", (), {"content": content})
        ch = type("Choice", (), {"message": m})
        r = type("Resp", (), {"choices": [ch]})
        return r


class FakeCompletions:
    """Assign to fake.chat — code calls fake.chat.completions.create(...)."""
    def __init__(self, payload: dict | str):
        self.completions = _CompletionsAPI(payload)


SAM_DOG_TEXT = (
    '<0f>0<|box;x1=1303;y1=26;x2=1658;y2=447;w=1665;h=1463|>'
    '<|mask;x=0;y=0;data=422,356,~!!$(&#L*1Lpy9|>'
)


class Fake:
    def __init__(self):
        self.responsesCalled = 0
        self.responses = None
        self.chat = None


@pytest.fixture()
def fake_client(monkeypatch):
    """A controllable fake client injected as lens.mmda._client."""
    fake = Fake()
    monkeypatch.setattr(mmda, "_client", lambda: fake)
    return fake


# ----------------------------------------------------------------- segment --

def test_segment_parses_boxes_and_masks(fake_client):
    fake_client.responses = FakeResponses(SAM_DOG_TEXT)
    seg = mmda._segment(None, URL, "dog")
    assert seg["found"] is True
    assert seg["n_matches"] == 1
    assert seg["boxes"][0]["x2"] == 1658, "native-pixel coords parsed"


def test_segment_empty_text_is_not_found():
    """The verified live behavior: SAM returns empty text on data-URLs and
    content-free images. Must parse as found=False, never raise."""
    fake = Fake()
    fake.responses = FakeResponses("")
    seg = mmda._segment(fake, URL, "handwashing station")
    assert seg["found"] is False and seg["n_matches"] == 0


# ------------------------------------------------------------------- judge --

def test_judge_parses_strict_json(fake_client):
    fake_client.chat = FakeCompletions(
        {"present": "yes", "structural_condition": "intact",
         "drainage_present": "unclear"})
    js = mmda._judge(None, URL, "water_point",
                     mmda.schema_states_for("water_point"))
    assert js["present"] == "yes"


def test_judge_recovers_from_prose_wrapped_json(fake_client):
    """Muse sometimes wraps JSON in prose/fences — the parser must recover."""
    fake_client.chat = FakeCompletions(
        'Sure! Here is the assessment:\n```json\n{"present": "yes"}\n```')
    js = mmda._judge(None, URL, "water_point",
                     mmda.schema_states_for("water_point"))
    assert js["present"] == "yes"


def test_judge_prompt_carries_the_scope_forbiddance(fake_client):
    """The framing corrections must reach the model: the prompt passed to Muse
    contains the JSON contract and the 'do not use water quality words' rule."""
    captured = {}

    class _CapAPI:
        def create(self, **kw):
            captured["prompt"] = kw["messages"][0]["content"][0]["text"]
            m = type("Msg", (), {"content": '{"present": "unclear"}'})
            ch = type("Choice", (), {"message": m})
            r = type("Resp", (), {"choices": [ch]})
            return r

    class CapChat:
        def __init__(self):
            self.completions = _CapAPI()

    fake_client.chat = CapChat()
    mmda._judge(fake_client, URL, "water_point",
                mmda.schema_states_for("water_point"))
    assert "json" in captured["prompt"].lower()
    assert "water quality" in captured["prompt"].lower()


# ------------------------------------------------------- detect (full flow) --

def test_detect_full_flow_missing_target_becomes_unclear(fake_client):
    """SAM finds nothing → the category's judgment comes from Muse with the
    NULL-transport semantics (miss ≠ absence): unjudged states 'unclear'
    rather than a fabricated 'no'. (Rewritten 2026-10-30: the old assertion
    'present=no' encoded the false-absence bug the Muse-first fix removed.)"""
    fake_client.responses = FakeResponses("")   # SAM: nothing anywhere
    fake_client.chat = FakeCompletions({})      # Muse: no usable JSON
    det = mmda.detect_mmda(URL)
    # Muse-first: every schema state for every category gets a finding (14 here)
    n_states = sum(len(mmda.schema_states_for(cat)) for cat in mmda.SAM_TARGETS)
    assert len(det) == n_states
    # a miss must NOT be recorded as a confident absence
    nos = [d for d in det if d.value == "no"]
    assert nos == [], f"false absences recorded: {[(d.category, d.state) for d in nos]}"
    unclear = [d for d in det if d.value == "unclear"]
    assert unclear, "expected unclear (honest 'can't judge') somewhere"


def test_detect_full_flow_judges_states_within_schema(fake_client):
    """When SAM finds a target, Muse's JSON fills the states; out-of-set or
    banned values degrade to unclear — never pass through."""
    fake_client.responses = FakeResponses(
        "<|box;x1=10;y1=10;x2=90;y2=90;w=80;h=80|>")
    fake_client.chat = FakeCompletions({
        "present": "bogus-value",            # not in allowed set → unclear
        "structural_condition": "damaged",   # valid → passes
        "drainage_present": "yes",           # valid → passes
    })
    det = mmda.detect_mmda(URL)
    wp = {(d.state): d.value for d in det if d.category == "water_point"}
    assert wp["structural_condition"] == "damaged"
    assert wp["drainage_present"] == "yes"
    assert wp["present"] == "unclear", "out-of-set model value must degrade"


def test_detect_values_never_carry_banned_vocabulary(fake_client):
    fake_client.responses = FakeResponses(
        "<|box;x1=10;y1=10;x2=90;y2=90;w=80;h=80|>")
    fake_client.chat = FakeCompletions({
        "present": "yes",
        "structural_condition": "decontaminated surface",   # banned → unclear
        "drainage_present": "yes"})
    det = mmda.detect_mmda(URL)
    for d in det:
        assert not mmda._banned(d.value), f"banned value passed through: {d.value}"


def test_detect_missing_url_raises_with_guidance():
    with pytest.raises(ValueError, match="publicly fetchable"):
        mmda.detect_mmda(None)


# -------------------------------------------------------------- schema ------

def test_schema_states_loads_from_checklist():
    s = mmda.schema_states_for("water_point")
    assert "present" in s and "unclear" in s["present"]
    assert mmda.schema_states_for("does_not_exist") == {}
