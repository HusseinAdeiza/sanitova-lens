"""
Sanitova Lens — HF Space entrypoint.

WHY THIS FILE IS SEPARATE FROM lens/app.py
The Space runtime differs from local: model creds come from Space secrets
(not .env), the store must survive restarts (Space filesystems can be
ephemeral across rebuilds — we write to a persistent /data volume when
available), and the launch binds 0.0.0.0:7860 as HF requires.

The audit trail rule stands: every inspection and ruling is persisted,
source-stamped, and exportable — deploy or local.
"""

from __future__ import annotations

import os
from pathlib import Path

# Space persistence: HF mounts /data only if the Space has a persistent
# storage tier; fall back to a local dir so it still runs everywhere.
DATA_DIR = Path(os.environ.get("LENS_DATA_DIR", "/data" if Path("/data").exists() and os.access("/data", os.W_OK) else "."))
STORE_PATH = DATA_DIR / "lens_events.jsonl"

os.environ.setdefault("LENS_STORE", str(STORE_PATH))

import lens.app as app  # noqa: E402  (after env, so the store binds to the right path)

if __name__ == "__main__":
    # HF Spaces bind 0.0.0.0:7860 by convention and expect the app object.
    ui = app.build_ui()
    ui.launch(server_name="0.0.0.0",
              server_port=int(os.environ.get("PORT", "7860")),
              favicon_path=None)
