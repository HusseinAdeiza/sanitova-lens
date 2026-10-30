# Sanitova Lens

I inspect water and sanitation facilities for a living. I run [Sanitova EHS](https://sanitovaehs.com), an environmental health services company in Nigeria, and over the years I have walked through hundreds of facilities — boreholes, handwashing stations, latrine blocks, waste yards, drainage lines. The slowest part of the job has never been the inspection itself. It is everything around it: writing up what I saw, deciding what needs a revisit today versus next month, and explaining to a client why one finding matters more than another.

Sanitova Lens is the tool I wanted on those site visits. Point a phone at a facility, take a photo or a short walk-through video, and get a structured pre-screen: which of the five checklist categories are visible, what condition they are in, and what should be prioritised — before I write a single line of my report.

## What it is, and what it deliberately is not

This is a **triage and prioritisation tool for licensed inspectors**. It reads what is *visible in a photograph*: whether a water point is present, whether a waste bin is overflowing, whether an open dump is in view, whether a drainage channel looks blocked.

It does **not** test water. It does not measure anything, and it will never tell you water is safe to drink — that is a laboratory's job, and the tool's output says so on every run.

Two rules I insisted on while building this, because they come from doing this work in the field:

- **Uncertainty must say "unclear."** If the model cannot see it, the report says it cannot see it. A dark corner or a partly cropped latrine must never be recorded as "absent" — a missing tap in a photo does not mean there is no tap on site. This sounds obvious; the first version of the pipeline got it wrong (it reported five absences on a photo showing an open dump) and I rebuilt the judging layer around this rule.
- **Damaged is not critical.** A cracked slab is a maintenance item. The tool ranks confirmed severe problems above damaged-but-present ones, and the licensed inspector always has the final word — the tool feeds the inspection, it does not replace it.

## How it works

The pipeline uses Meta's models end to end:

1. **SAM 3.1** finds evidence regions in the frame — where the tap, the bin, the dump actually are. (Since the October rebuild, SAM is used for evidence geometry rather than as a gate: on cluttered real-world scenes its prompt matching proved to be the weak link, and judging directly on the frame worked better. The misfire is documented in the git history.)
2. **Muse** (Meta's open-weights vision-language model via the [Meta Model API](https://dev.meta.ai)) judges each checklist category's visible states directly — strict JSON, constrained to the schema, and anything outside the allowed set degrades to `unclear` rather than passing through.
3. The **scorer** turns the findings into a tier — GREEN / AMBER / RED — with a plain-language action line, and the vocabulary is fenced by tests: the codebase physically cannot express water-quality judgements.
4. Every run lands in an append-only store. When the inspector afterwards confirms or corrects a finding, that ruling is recorded against the vision output — so agreement and disagreement are *measured*, not anecdotal. My first full cycle — one real facility photo, fourteen findings, my own ruling as a licensed officer — is in the repo's evidence directory: the model and I agreed on all fourteen.

There is also a video path: a short walk-through clip is split into keyframes, each frame is judged against the same checklist, and the frames are aggregated worst-case-wins into one triage for the site.

## Verify it yourself, offline, in one minute

You do not need API keys or credits to check that this works. The repository ships the real model responses captured from live runs:

```
git clone https://github.com/HusseinAdeiza/sanitova-lens
cd sanitova-lens
pip install gradio pillow   # only for the optional web UI
python3 docs/verify_demo.py
```

That replays the committed responses through the scorer, checks every value against the schema, confirms no out-of-scope vocabulary exists anywhere in the evidence or the output, and prints the reproduced triage. On my last run: 21 checks, all passing, zero network access.

The full test suite (40 tests) also runs offline: `python3 -m pytest tests/`

## Running it for real

With a `METAAI_API_KEY` in `.env` (never committed), the CLI runs the live pipeline:

```
python3 -m lens.inspect --image <photo-or-url> --facility "Kubwa clinic"
python3 -m lens.inspect --video <clip.mp4> --facility "Kubwa clinic"
```

The web UI (scope statement first, live triage on upload) starts with:

```
python3 -m lens.serve
```

## Where this is going

The labelled store is the point. Every inspection photo, every model finding, every inspector ruling accumulates into a dataset that belongs to the inspection company that generated it — and each disagreement between model and inspector is a future improvement to the scorer, measured rather than guessed. The ambition is a pre-screen that gets better every working week, in the hands of the people who do the inspections.

## Honest limitations

- **Small n.** One fully-validated photo and one video so far, fourteen findings, one inspector. The flywheel has turned exactly once. I would rather show one honest cycle than twenty fabricated ones.
- **Single-environment testing.** All live runs so far are Nigerian peri-urban facilities. Nothing here claims generalisation to other regions yet.
- **The models can be wrong.** Muse has shown both correct judgement (the dump photo) and arguable calls (whether an uncontained pile counts as "overflow"). That is exactly why the inspector ruling is part of every cycle, and why disagreements are recorded as first-class data.
- **Vehicle: work laptop, phone camera.** Photo quality in the field will vary more than my test set does. The `unclear` semantics are the answer to that, not a guarantee.

## Repository notes

- `lens/` — the pipeline: scoring, vision backends, storage, CLI, web UI
- `schema/checklist.schema.json` — the five-category checklist with allowed states
- `docs/evidence/` — committed responses from real model runs (redacted to model output only)
- `docs/verify_demo.py` — the offline verification described above
- `tests/` — 40 offline tests, including the ones that enforce the scoped vocabulary and the honest-uncertainty semantics
- Facility photos and inspector rulings are **not** in this repository, deliberately — inspection data stays with the inspection company. Public media copies exist only in a separate media repository.
