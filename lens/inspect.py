"""Sanitova Lens — entrypoint.

    python3 -m lens.inspect photo1.jpg [photo2.jpg ...]

Produces one triage report per photo. VISIBLE CONDITIONS ONLY; every report
names its backend (stub/mmda) and ends in human action. Water quality is a lab
result and is never asserted here.
"""

from __future__ import annotations

import sys
from pathlib import Path

from .vision import backend_name, detect  # noqa: E402
from .score import triage  # noqa: E402


def inspect_file(path: Path) -> int:
    img = path.read_bytes()
    findings, backend = detect(img)
    report = triage(findings, facility=path.stem)
    print(report.render())
    print(f"  detected by : {backend}" + ("  (DEMO-GRADE — not a vision model)"
                                       if backend == "stub" else ""))
    print(f"  findings    : {len(findings)}")
    return 0


def main(argv: list[str]) -> int:
    files = [Path(a) for a in argv[1:] if not a.startswith("-")]
    if not files:
        print(__doc__)
        return 2
    rc = 0
    for f in files:
        if not f.exists():
            print(f"missing file: {f}", file=sys.stderr)
            rc = 1
            continue
        rc |= inspect_file(f)
        print()
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
