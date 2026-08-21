"""Pull exemplar PNGs at boot when they are not in the image.

The client's reference cards are deliberately not committed (see generation/exemplars.py).
On Render, set EXEMPLARS_URL to a zip whose top-level folders are the archetype names
(portal/, tangle/, …). Without that URL and without files already on disk, Creative Full
raises Missing rather than generating unconditioned cards.
"""

from __future__ import annotations

import io
import os
import sys
import zipfile
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent.parent / "assets" / "exemplars"


def _has_pngs(directory: Path) -> bool:
    return directory.is_dir() and any(directory.rglob("*.png"))


def main() -> int:
    if _has_pngs(ROOT):
        print(f"exemplars already present under {ROOT}", flush=True)
        return 0

    url = os.environ.get("EXEMPLARS_URL", "").strip()
    if not url:
        print(
            "WARNING: no exemplars on disk and EXEMPLARS_URL is unset. "
            "Creative Full will fail until either is fixed.",
            flush=True,
        )
        return 0

    print(f"fetching exemplars from EXEMPLARS_URL…", flush=True)
    with urlopen(url, timeout=120) as response:  # noqa: S310 — URL is operator-controlled env
        payload = response.read()

    ROOT.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        archive.extractall(ROOT)

    if not _has_pngs(ROOT):
        print(f"ERROR: zip extracted but no PNGs under {ROOT}", file=sys.stderr, flush=True)
        return 1

    print(f"exemplars ready under {ROOT}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
