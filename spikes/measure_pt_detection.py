"""How often does `panels.detect` find the P/T shield, and does a wording change move it?

bd mtg-wfp: the shield is PAINTED and comes back undetected, so `check` fires `missing_pt` and the
pipeline burns a full repaint on a card that was fine. It was measured once on 2026-08-13 at 1 of
4, but that measurement had to generate a fresh card each time, so model variance and detector
variance were mixed together and each arm cost real money.

They are separable now. Unsound cards keep their empty-furniture PNG (bd mtg-57t), so the same
blank can be put through `detect` as many times as we like: the image is FIXED, and everything
that moves is the detector. Each run is one gemini-3.6-flash vision call, which is the cheap half
of the pipeline — no image is generated.

    uv run python ../spikes/measure_pt_detection.py            # baseline, current PROMPT
    uv run python ../spikes/measure_pt_detection.py --runs 8

Point it at a candidate wording by editing `generation.panels.PROMPT` and running it again; the
comparison that matters is the same blanks at the same n.
"""

import argparse
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

import django  # noqa: E402

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from generation import panels  # noqa: E402
from generation.models import Job  # noqa: E402


def failing_blanks():
    """(label, png bytes) for every stored blank whose card was graded `missing_pt`.

    These are exactly the cards the bug is about: the shield is on the card and the detector did
    not report it. A blank kept from a card that graded clean would measure the easy case.
    """
    out = []
    for job in Job.objects.order_by("created"):
        for result in job.results or []:
            if not result.get("blank"):
                continue
            if not any(p["code"] == "missing_pt" for p in result["problems"]):
                continue
            path = BACKEND / result["blank"].lstrip("/").replace("media/", "media/", 1)
            if not path.exists():
                continue
            out.append((f"{str(job.pk)[:8]} {result['name'][:24]}", path.read_bytes()))
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=5, help="detections per blank")
    args = parser.parse_args()

    blanks = failing_blanks()
    if not blanks:
        print("No stored blanks from a missing_pt card. Generate one and try again.")
        return

    print(f"{len(blanks)} blanks x {args.runs} runs — the image is fixed, so all variance is the "
          f"detector's.\n")
    found = total = 0
    for label, png in blanks:
        hits = []
        for _ in range(args.runs):
            try:
                detected = panels.detect(png)
            except Exception as failure:  # noqa: BLE001 — a dead run is not a detection
                hits.append(f"ERR:{type(failure).__name__}")
                continue
            hits.append("pt" if detected.get("pt") else ".")
        got = sum(1 for h in hits if h == "pt")
        found += got
        total += len(hits)
        print(f"  {label:36} {got}/{len(hits)}  {' '.join(hits)}")

    print(f"\n  P/T detected: {found}/{total} = {found / total:.0%}")
    print("  Every miss costs one full repaint on a card that was already correct.")


if __name__ == "__main__":
    main()
