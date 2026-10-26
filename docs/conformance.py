"""Rules-conformance checklist — filled from the OFFICIAL Rules/T&Cs text only.

PURPOSE (the user's standing instruction): verify what we build is IN SCOPE,
during the build and after. Each row = one rule requirement, the artifact or
action that satisfies it, and status. Nothing here is asserted from memory —
every row carries the source line it came from.

HOW TO USE
  1. At rules publication, transcribe requirements into REQUIREMENTS below.
  2. For each, link the artifact in this repo (or an action + owner).
  3. `python3 docs/check_conformance.py` must print all PENDING → MET or N/A.
Anything still PENDING at submission time blocks the submission.
"""

from __future__ import annotations

# status: MET | PENDING | N/A | ACTION(user)
REQUIREMENTS: list[dict] = [
    # --- confirmed from cerebralvalley.ai event md (2026-10-26) ---
    {"id": "dates", "source": "cerebralvalley event .md: Key Dates",
     "rule": "submit by Nov 4, 9:00 PM EST",
     "ours": "submission window tracked; artifacts complete before Nov 3",
     "status": "PENDING"},
    {"id": "track", "source": "cerebralvalley event .md: Participant Tracks",
     "rule": "every project enters ONE track; startup = teams/founders, real product",
     "ours": "STARTUP track; entrant Hussein Adeiza Yunusa (Sanitova EHS co-founder)",
     "status": "PENDING"},  # confirm startup eligibility wording in Official Rules
    {"id": "theme", "source": "cerebralvalley event .md: Project Themes",
     "rule": "project fits Theme 1 (Build for Your World) or Theme 2",
     "ours": "Theme 1 — domain problem firsthand (licensed EHS inspector's workflow)",
     "status": "PENDING"},
    {"id": "meta-models", "source": "event md: About — models named",
     "rule": "use Meta's newest models (Muse Spark series, Muse Wonder, Muse Image, "
             "SAM 3.1 via Meta Model API) and/or Meta open weights",
     "ours": "SAM 3.1 segmentation + Muse vision judgment = core loop "
             "(lens/vision.py mmda + openweights backends)",
     "status": "PENDING"},
    {"id": "eligibility", "source": "event md: eligibility bullets",
     "rule": "18+, country eligibility, no Meta/CV staff, no sanctioned regions",
     "ours": "user confirmed eligible at application",
     "status": "MET"},
    {"id": "rules-accept", "source": "event md: 'must be accepted by selected participants'",
     "rule": "accept Official Rules when published",
     "ours": "ACTION(user): read + accept at kickoff",
     "status": "PENDING"},
    # --- to transcribe from the Official Rules when they publish ---
    {"id": "submit-format", "source": "Official Rules (pending)",
     "rule": "submission format: fields, links, video length",
     "ours": "TBD from rules",
     "status": "PENDING"},
    {"id": "prior-work", "source": "Official Rules (pending)",
     "rule": "disclosure requirements for prior work (SanitovaCheck app, Sanitova EHS company)",
     "ours": "disclose SanitovaCheck as prior domain product; Lens built during event",
     "status": "PENDING"},
    {"id": "team-size", "source": "Official Rules (pending)",
     "rule": "startup track team size cap",
     "ours": "confirm solo-founder allowed + list cofounder if entering as team",
     "status": "PENDING"},
    {"id": "credits-terms", "source": "partner blurbs (Baseten/Modal/Fireworks)",
     "rule": "per-partner credit application/usage terms if used",
     "ours": "ACTION(user): apply for partner credits in Discord/details",
     "status": "PENDING"},
    {"id": "product-scope", "source": "project's own framing (enforced by tests)",
     "rule": "no safety/contamination claims; inspector authority; visible conditions only",
     "ours": "enforced: vocab ban + action-language tests (tests/test_triage.py, "
             "tests/test_pipeline.py, tests/test_store.py)",
     "status": "MET"},
]


def pending() -> list[str]:
    return [r["id"] for r in REQUIREMENTS if r["status"] == "PENDING"]


if __name__ == "__main__":
    for r in REQUIREMENTS:
        print(f"  [{r['status']:7s}] {r['id']:14s} {r['rule'][:70]}")
    p = pending()
    print(f"\n  {len(p)} pending: {', '.join(p)}")
