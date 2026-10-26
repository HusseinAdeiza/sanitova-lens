---
title: Sanitova Lens
emoji: 🧪
colorFrom: green
colorTo: blue
sdk: gradio
app_file: space_app.py
pinned: false
license: mit
short_description: Visible-conditions sanitation pre-screen for licensed inspectors — never a safety test.
---

# Sanitova Lens

An AI-assisted **pre-screening tool for licensed environmental-health inspectors**:
a facility photo goes in, a prioritized triage report comes out — which sites need
a field visit and lab sampling first.

**Scope, stated on every report the tool renders:**

- It inspects **visible conditions only** — presence and physical state of
  infrastructure (water points, handwashing stations, latrines, waste, drainage).
- It **never asserts water safety or quality.** Water safety is a laboratory
  result, not a photograph reading.
- The **inspector's ruling is authoritative**; machine findings are corrected or
  confirmed by a licensed human, and every correction is recorded.

## Pipeline

photo → **SAM 3.1** segmentation (Meta) → **Muse** vision judgment (Meta) →
pure-code triage scorer → report → inspector confirmation/correction →
append-only labeled dataset.

## Verification

- 30 tests, including falsification tests (properties any correct triage must
  hold: monotonicity, worst-case-wins, conservative `unclear`, no overstate)
- Vocabulary ban enforced at runtime: the tool **cannot emit** water-quality
  language, by test.
- Every report carries its **backend provenance** (heuristic stub vs Meta models).
