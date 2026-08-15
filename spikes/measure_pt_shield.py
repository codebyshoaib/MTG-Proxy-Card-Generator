"""How big is the P/T shield on the cards where the detector MISSES it? (bd mtg-wfp, round 2)

WHY THIS EXISTS. `panels.PT_SIZE` was fitted on 2026-08-15 over "every stored detection that DID
find a shield". But `pipeline` only calls `infer_pt` when `detected["pt"]` is ABSENT — so the
constant was fitted on exactly the population it never serves, and applied to exactly the
population it was never measured on. If detection is at all size-dependent, that is a biased fit
by construction.

It is size-dependent. Measured 2026-08-15 by drawing a labelled 0.02 grid over the bottom-right
corner of every stored card and reading the painted surface's edges off it by eye (+-0.005):

  DETECTED   n=5, from generation/tests/test_panels.py MEASURED   width 0.143 - 0.156
  UNDETECTED n=5, hand-labelled below                             width 0.067 - 0.130

The two populations do not overlap. The detector finds big shields and misses small ones, which
also explains the 35% hit rate that three rounds of prompt rewriting never moved. So the old
constant is the median of the LARGE tail, applied only to the small tail.

    uv run python ../spikes/measure_pt_shield.py          # print the fit
    uv run python ../spikes/measure_pt_shield.py --draw   # re-draw the grid overlays to check by eye

Re-read the overlays before trusting the numbers below: they are hand-labelled, not segmented, and
this file is the only record of where they came from.
"""

import argparse
import os
import statistics
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

import django  # noqa: E402

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from generation import panels  # noqa: E402

# (job, card, lowest rules strip as stored, the surface actually PAINTED, read off the grid).
# Every one of these is a card whose `pt` came back None, i.e. one `infer_pt` really runs on.
UNDETECTED = [
    ("5f34234d", "Craterhoof", (0.101, 0.712, 0.904, 0.906), (0.838, 0.855, 0.905, 0.945)),
    ("bf4f16ac", "Craterhoof", (0.061, 0.774, 0.928, 0.943), (0.845, 0.868, 0.925, 0.960)),
    ("e359dc35", "Elesh Norn", (0.100, 0.622, 0.900, 0.898), (0.795, 0.820, 0.905, 0.945)),
    # NOT a shield. This one painted a horizontal plaque, which is why nothing was reported in the
    # corner at all — the brief asks for "a small shield-shaped boss" and the model answered with
    # different furniture. Kept in the sample: it is a card a customer would have got.
    ("92de37eb", "Elesh Norn", (0.077, 0.788, 0.919, 0.929), (0.775, 0.888, 0.905, 0.945)),
    ("6a76f665", "Elesh Norn", (0.136, 0.684, 0.862, 0.906), (0.785, 0.828, 0.895, 0.945)),
    # ADDED 2026-08-15 from job 519273ac, and it is the one that breaks the model rather than
    # widening it. Every card above has its lowest rules strip ending at 0.898-0.943, so the
    # shield is pinned into the little room left below it and the offset cannot be far wrong.
    # Terror's strip ends at 0.831 — OUTSIDE that range — and the shield is painted 0.195 wide,
    # wider than anything in either population. The guess lands 0.038 high and 3.3x too small by
    # area, which puts the printed 5/4 on the shield's upper rim instead of its body.
    #
    # So `infer_pt` is being EXTRAPOLATED, and the sign flips when you do: shield centre minus
    # strip bottom is -0.006 to -0.029 on all five above and +0.024 here.
    ("519273ac", "Terror", (0.108, 0.620, 0.892, 0.831), (0.727, 0.771, 0.922, 0.940)),
]


def draw():
    """Re-draw the overlays these labels were read off, so the numbers can be re-checked by eye."""
    from PIL import Image, ImageDraw

    from generation.models import Job

    out = Path(__file__).resolve().parent / "pt-shield-overlays"
    out.mkdir(exist_ok=True)
    x0, y0 = 0.62, 0.70
    wanted = {job for job, _, _, _ in UNDETECTED}
    for job in Job.objects.order_by("created"):
        key = str(job.pk)[:8]
        if key not in wanted:
            continue
        for result in job.results or []:
            source = result.get("blank") or result.get("image")
            detected = result.get("panels") or {}
            if not source or detected.get("pt") or not detected.get("rules"):
                continue
            path = BACKEND / source.lstrip("/")
            if not path.exists():
                continue
            image = Image.open(path).convert("RGB")
            width, height = image.size
            crop = image.crop((int(width * x0), int(height * y0), width, height))
            crop = crop.resize((crop.width * 3 // 2, crop.height * 3 // 2))
            pen = ImageDraw.Draw(crop)
            fx = lambda v: (v - x0) / (1 - x0) * crop.width  # noqa: E731
            fy = lambda v: (v - y0) / (1 - y0) * crop.height  # noqa: E731
            for step in range(20):
                gx, gy = x0 + 0.02 * step, y0 + 0.02 * step
                if gx <= 1:
                    pen.line([(fx(gx), 0), (fx(gx), crop.height)], fill=(0, 200, 255))
                    pen.text((fx(gx) + 2, 2), f"{gx:.2f}", fill=(0, 200, 255))
                if gy <= 1:
                    pen.line([(0, fy(gy)), (crop.width, fy(gy))], fill=(0, 200, 255))
                    pen.text((2, fy(gy) + 2), f"{gy:.2f}", fill=(0, 200, 255))
            guess = panels.infer_pt(detected)
            if guess:
                pen.rectangle(
                    [fx(guess[0]), fy(guess[1]), fx(guess[2]), fy(guess[3])],
                    outline=(255, 0, 0), width=4,
                )
            name = result["name"].split(",")[0].replace(" ", "")[:12]
            crop.save(out / f"{key}_{name}.png")
            print(f"  wrote {out.name}/{key}_{name}.png")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--draw", action="store_true", help="re-draw the grid overlays")
    args = parser.parse_args()
    if args.draw:
        draw()
        return

    offsets_x, offsets_y, widths, heights = [], [], [], []
    print(f"{'job':10} {'card':11} {'painted w x h':>15} {'offset from strip corner':>26}")
    for job, card, strip, real in UNDETECTED:
        cx, cy = (real[0] + real[2]) / 2, (real[1] + real[3]) / 2
        offsets_x.append(cx - strip[2])
        offsets_y.append(cy - strip[3])
        widths.append(real[2] - real[0])
        heights.append(real[3] - real[1])
        print(
            f"{job:10} {card:11} {widths[-1]:7.3f} x{heights[-1]:6.3f} "
            f"{offsets_x[-1]:12.3f},{offsets_y[-1]:7.3f}"
        )

    median = (
        round(statistics.median(offsets_x), 3),
        round(statistics.median(offsets_y), 3),
        round(statistics.median(widths), 3),
        round(statistics.median(heights), 3),
    )
    print(f"\n  median offset {median[0]:+.3f},{median[1]:+.3f}   median size {median[2]}x{median[3]}")
    print(f"  shipping      {panels.PT_OFFSET[0]:+.3f},{panels.PT_OFFSET[1]:+.3f}   "
          f"shipping size  {panels.PT_SIZE[0]}x{panels.PT_SIZE[1]}")

    # WHY MEDIAN SIZE AND NOT MEAN, AND WHY THIS MATTERS MORE THAN THE OFFSET. `_display` sets the
    # glyphs at half the box HEIGHT and centres them in it, so a box bigger than the painted surface
    # prints a P/T that overhangs the shield, and a box smaller than it prints one that sits safely
    # inside. The cost is asymmetric, so the statistic should not be symmetric either — but the
    # offset is already unbiased on this sample, and it is only the SIZE that was fitted on the
    # wrong population.
    # WHAT THIS OVERHANG NUMBER DOES NOT CATCH, found on Terror 2026-08-15. It compares the guess
    # against the shield's OUTER SILHOUETTE, and Terror scores +0.000 — the box is entirely inside
    # the painted shape. The card still looks wrong, because a shield is a rim around a recessed
    # INNER FACE and only the inner face is printable. Terror's silhouette starts at y=0.771 and
    # its inner face at about y=0.801; `_display` put the glyphs at 0.794-0.840, so they open on
    # the bright metallic rim and only finish on the face.
    #
    # Measure the inner face, not the silhouette, when this is next fitted — and note that the
    # rim's share is not constant either, because it scales with a shield that ranges 0.067-0.195
    # wide. That is the case against ever fixing this with another constant (bd mtg-1uv).
    print("\n  how far outside the painted surface does each guess reach today?")
    for job, card, strip, real in UNDETECTED:
        guess = panels.infer_pt({"rules": [strip]})
        over = max(real[0] - guess[0], real[1] - guess[1], guess[2] - real[2], guess[3] - real[3])
        print(f"    {job:10} {card:11} {over:+.3f}" + ("   spills off the surface" if over > 0 else ""))


if __name__ == "__main__":
    main()
