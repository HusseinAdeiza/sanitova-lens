"""mmda backend — Meta Model API: SAM 3.1 segmentation + Muse vision judgment.

IMPLEMENTED FROM THE DOCUMENTED API — VERIFIED LIVE 2026-10-26 (this file's
probe history is the evidence: 6 live calls against api.meta.ai/v1):

  TRANSPORT FACTS (each pinned empirically, not assumed):
    * client: `openai` SDK, base_url https://api.meta.ai/v1 (Responses protocol)
    * SAM 3.1 FETCHES image_url SERVER-SIDE. A base64 data: URL is accepted
      (HTTP 200) but returns EMPTY output silently — verified twice. The URL
      must be a publicly fetchable http(s) address. (A Wikimedia *thumb* URL
      returned media_url_origin_error; the direct file URL worked.)
    * SAM output arrives as text tags: per match,
        "<|box;x1=..;y1=..;x2=..;y2=..;w=..;h=..|>" and
        "<|mask;x=..;y=..;data=<w>,<h>,<rle>|>"
      Coordinates are in the IMAGE'S NATIVE PIXEL SPACE (verified: a known
      1665x1463 source returned coordinates up to x2=1658, y2=447 — native
      pixels, not the normalized 0..1000 image-understanding grid).
      The RLE mask payload is stored opaquely in v1 (box is what triage needs).
    * Empty output on a content-free image is EXPECTED (belongs to no target).

  SCOPE (binding): Muse prompts forbid water-quality/safety vocabulary; values
  outside the schema's allowed sets (or hitting the ban) degrade to "unclear",
  never a guess. The inspector's ruling remains the authority.
"""

from __future__ import annotations

import json
import os
import re

from .vision import _BANNED  # the shared vocabulary ban (lives in vision)

BASE_URL = "https://api.meta.ai/v1"
SAM_MODEL = "sam-3.1"
VLM_MODEL = os.environ.get("LENS_VLM_MODEL", "muse-spark-1.3")

# The categories our schema cares about, with the noun-phrase prompt SAM expects
# ("Prompt with a short noun phrase that names one concrete object" — docs).
SAM_TARGETS = {
    "water_point": "water tap or borehole outlet",
    "handwashing": "handwashing station or hand sanitizer dispenser",
    "excreta": "toilet or latrine",
    "waste": "waste bin or garbage pile",
    "drainage": "open drain or standing puddle",
}

_BOX_RE = re.compile(r"<\|box;x1=(\d+);y1=(\d+);x2=(\d+);y2=(\d+);w=(\d+);h=(\d+)\|>")
_MASK_RE = re.compile(r"<\|mask;[^|]*\|>")


def _client():
    key = os.environ.get("METAAI_API_KEY")
    if not key:
        raise RuntimeError("METAAI_API_KEY not set")
    from openai import OpenAI            # the documented SDK
    return OpenAI(base_url=BASE_URL, api_key=key)


def _banned(v: str) -> bool:
    return bool(_BANNED.search(v or ""))


def _segment(client, image_url: str, target: str) -> dict:
    """SAM 3.1 over /v1/responses. Returns parsed geometry for all matches."""
    if client is None:
        client = _client()
    r = client.responses.create(
        model=SAM_MODEL,
        input=[{"type": "message", "role": "user",
                "content": [{"type": "input_text", "text": target},
                            {"type": "input_image", "image_url": image_url}]}],
    )
    txt = ""
    for o in (r.output or []):
        if getattr(o, "type", "") == "message":
            for c in (o.content or []):
                txt += getattr(c, "text", "") or ""
    boxes = [{"x1": int(m[0]), "y1": int(m[1]), "x2": int(m[2]), "y2": int(m[3]),
              "w": int(m[4]), "h": int(m[5])} for m in _BOX_RE.findall(txt)]
    return {"found": bool(boxes), "n_matches": len(boxes), "boxes": boxes,
            "n_masks": len(_MASK_RE.findall(txt)), "text_len": len(txt)}


def _judge(client, image_url: str, category: str, states: dict[str, set]) -> dict:
    """Muse: judge the photo for this category's visible states. Strict JSON.

    The image here goes over chat-completions image_url — Muse's
    image-understanding path (data: URLs ARE accepted there per the doc's
    input_image spec; SAM is the transport-restricted one).
    """
    if client is None:
        client = _client()
    allowed_json = json.dumps({s: sorted(v) for s, v in states.items()})
    prompt = (
        "You are assisting a licensed environmental-health inspector. Look at "
        f"the facility photo and judge ONLY these VISIBLE aspects of the "
        f"{category.replace('_', ' ')}: {json.dumps(list(states))}.\n"
        "Answer with a single JSON object mapping each state name to ONE value "
        f"from its allowed set exactly as given: {allowed_json}\n"
        "Rules: judge only what is visibly present in the photograph; if the "
        "photo cannot show a state clearly, answer \"unclear\". Do not use any "
        "words about water quality or safety. Output ONLY the JSON object."
    )
    r = client.chat.completions.create(
        model=VLM_MODEL,
        messages=[{"role": "user",
                   "content": [{"type": "text", "text": prompt},
                               {"type": "image_url",
                                "image_url": {"url": image_url}}]}],
    )
    txt = r.choices[0].message.content or ""
    try:
        return json.loads(txt)
    except Exception:                    # noqa: BLE001 — strip prose/fences
        m = re.search(r"\{.*\}", txt, re.S)
        return json.loads(m.group(0)) if m else {}


def detect_mmda(image_url: str) -> list:
    """Muse-first pipeline (corrected 2026-10-27 after the first real run).

    WHY THE ORDER FLIPPED: the original flow gated Muse behind SAM's noun-phrase
    segmentation. On the first real facility photo (cluttered outdoor scene), SAM
    matched nothing and the pass reported five false absences — while a direct
    Muse call on the same photo returned the visibly-correct answer (waste:
    bin_present=yes, overflow=yes, open_dumping=yes). Conclusion from evidence:
    Muse reads cluttered field scenes reliably; SAM's prompt matching is the
    weaker path there. SAM stays for pixel geometry (evidence crops), available
    via segment_for_evidence() — not as the gate for whether judgment happens.

    Flow: Muse judges every category's visible states directly on the photo →
    strict JSON → out-of-set/banned values degrade to "unclear" → Findings.
    """
    from .vision import Detection      # local import: avoids a cycle

    if not image_url:
        raise ValueError(
            "mmda backend needs image_url (publicly fetchable) — SAM fetches "
            "server-side; data: URLs return empty output (verified 2026-10-26)")

    client = _client()
    out: list = []
    for category in SAM_TARGETS:        # same keys = checklist categories
        states = schema_states_for(category)
        js = _judge(client, image_url, category, states)
        for state, allowed in states.items():
            val = str(js.get(state, "unclear")).lower().strip()
            if _banned(val) or val not in allowed:
                val = "unclear"
            out.append(Detection(
                category, state, val, seg_conf=None, vision_conf=None,
                note=f"muse {VLM_MODEL} direct judgment"))
    return out


def segment_for_evidence(image_url: str, category: str) -> dict:
    """SAM geometry for a category the report wants to crop/highlight.
    Optional post-pass — not on the judgment critical path anymore."""
    client = _client()
    return _segment(client, image_url, SAM_TARGETS[category])


def schema_states_for(category: str) -> dict[str, set]:
    """Load the checklist from the shipped schema — single source of truth."""
    from pathlib import Path
    p = Path(__file__).resolve().parents[1] / "schema" / "checklist.schema.json"
    sch = json.loads(p.read_text())
    for c in sch["categories"]:
        if c["id"] == category:
            return {s: set(v["options"]) for s, v in c["checkable_states"].items()}
    return {}
