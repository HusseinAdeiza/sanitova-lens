"""Photo host — serves uploaded facility photos at publicly-fetchable URLs.

WHY THIS EXISTS
SAM 3.1 fetches images server-side (verified empirically 2026-10-26: data: URLs
return empty output; a public http(s) URL returns the full box+mask payload).
Until the HF Space deployment exists, this tiny stdlib server is the transport:
the Review UI (or the user via Telegram) saves a photo here, SAM fetches it by
URL, and detection proceeds.

SECURITY RULES
  * Binds 0.0.0.0 but serves ONLY the photos directory — never the filesystem.
  * Filenames are server-generated (sha prefix + timestamp + ext): no path
    traversal, no user-controlled paths.
  * Size cap 8MB (matches mmda.MAX_IMAGE_BYTES).
  * Read-only GETs. No listing, no directory index.
  * Photos contain facility interiors: this is a NEEDS-TO-BE-PUBLIC artifact
    for the duration of a detection run. The server is stopped after use in
    local testing; in production the HF Space's file hosting replaces it.
"""

from __future__ import annotations

import hashlib
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PHOTOS_DIR = Path(__file__).resolve().parent.parent / "photos"
PHOTOS_DIR.mkdir(exist_ok=True)
MAX_UPLOAD = 8 * 1024 * 1024
MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):        # quiet: SAM polls; no noisy stdout
        pass

    def _file(self) -> Path | None:
        name = self.path.strip("/").split("?")[0]
        if not name or "/" in name or ".." in name or "\\" in name:
            return None
        p = PHOTOS_DIR / name
        return p if p.is_file() and p.suffix in MIME else None

    def do_GET(self):
        # robots.txt: Meta's media fetcher (and other crawlers) check this.
        # Allow everything on this host — it serves only posted inspection
        # photos, and a 404 here makes SAM refuse to download ("could not be
        # checked"). Verified empirically 2026-10-27.
        if self.path.strip("/") == "robots.txt":
            body = b"User-agent: *\nAllow: /\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        p = self._file()
        if p is None:
            self.send_response(404)
            self.end_headers()
            return
        body = p.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", MIME[p.suffix])
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path.rstrip("/") != "/upload":
            self.send_response(404)
            self.end_headers()
            return
        try:
            n = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            n = 0
        if not 0 < n <= MAX_UPLOAD:
            self.send_response(413)
            self.end_headers()
            return
        body = self.rfile.read(n)
        ext = ".jpg" if body[:3] == b"\xff\xd8\xff" else (
            ".png" if body[:8] == b"\x89PNG\r\n\x1a\n" else "")
        if not ext:
            self.send_response(415)
            self.end_headers()
            return
        name = f"{hashlib.sha256(body).hexdigest()[:12]}-{int(time.time())}{ext}"
        (PHOTOS_DIR / name).write_bytes(body)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("X-Filename", name)
        self.send_header("Content-Length", "0")
        self.end_headers()


def serve(port: int = 8765):
    srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"serving {PHOTOS_DIR} on 0.0.0.0:{port}  (POST /upload, GET /<file>)")
    srv.serve_forever()


if __name__ == "__main__":
    import sys
    serve(int(sys.argv[1]) if len(sys.argv) > 1 else 8765)
