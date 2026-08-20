"""Score a card's STRUCTURE against the client's own corpus.

Phase 0 of `../PLAN-EXEMPLAR-PIVOT-2026-08-20.md`, and it exists because every metric this
project had before today reads colour or texture, and the defect the client reported is
geometry. MEASURED 2026-08-20 across his 19 favorites
(`Project Material/CLIENT-FAVORITES-2026-08-19/`) against our two batches: saturation 96 to
our 93, contrast 68 to 84, dark-ink share 33% to 27%, pixel-scale edge energy 5.4 to 9.6.
Same canvas, same model. Six statistics, all in range, and all blind to "looks pasted on".

What separates the corpora is straight lines. See `ruled_rows`.

Deliberately NOT a ship gate. `generation.check` decides whether a card may ship; this decides
whether a BATCH is closer to his corpus than the last one, which is a different question asked
at a different time. Nothing here costs an AI call, so it can run over every stored PNG we have.

Pure PIL, no numpy, matching `check` and `bleed`. Per-row statistics come from BOX-resizing a
thresholded mask to one column, which is a C-level reduction: 35 cards at full canvas in 8
seconds.
"""

import math
from pathlib import Path

from PIL import Image, ImageChops

from generation.check import Problem

CANVAS = (1792, 2400)
"""Every card is measured at the canvas we generate at, so thresholds are absolute.

Measuring at half resolution would be four times cheaper and would move every threshold, which
is the kind of saving that costs a day the first time a number is compared across a rescale.
"""

EDGE_SIGMA = 2.5
"""How far above the image's own mean gradient a pixel must sit to count as a hard edge.

Relative to the image rather than absolute, because a flat-graphic card and a painterly card
have completely different baseline gradient energy and a fixed threshold would measure medium
rather than structure.
"""

RULED_SHARE = 0.35
"""Share of the card's width a hard horizontal edge must span before the row counts as ruled.

A third of the card. Below that, a row of hard edges is illustration — a horizon, a branch, the
top of a wall. At and above it, on a trading card, it is the rim of a plate: the client's title
bars span 0.85 of the width and his scroll ends stop at about 0.6.
"""


def _stats(histogram):
    """(mean, standard deviation) of an L-mode histogram, without materialising the pixels."""
    total = sum(histogram) or 1
    mean = sum(value * count for value, count in enumerate(histogram)) / total
    variance = sum((value - mean) ** 2 * count for value, count in enumerate(histogram)) / total
    return mean, math.sqrt(variance)


def _grey(image):
    """The card as L at `CANVAS`, whatever it arrived as."""
    grey = image.convert("L")
    return grey if grey.size == CANVAS else grey.resize(CANVAS, Image.LANCZOS)


def _vertical_gradient(grey):
    """|d/dy| as an L image, one row shorter than its input.

    Vertical only, and that is the whole point rather than an economy: a plate rim is a
    HORIZONTAL edge, and its signature is a long run of large vertical differences. Adding the
    horizontal gradient would mix in every vertical rim and ornament and bury the signal.
    """
    width, height = grey.size
    return ImageChops.difference(
        grey.crop((0, 0, width, height - 1)), grey.crop((0, 1, width, height))
    )


def _gradient_mean(grey):
    """Mean |d/dy| over a crop. Near zero on a flat mat, high on carved or painted detail."""
    if grey.size[1] < 2:
        return 0.0
    return _stats(_vertical_gradient(grey).histogram())[0]


def _row_shares(grey):
    """Per row, the share of the card's width that is a hard horizontal edge.

    The BOX resize to a single column is a per-row mean of the thresholded mask, done in C.
    Looping the rows in Python is the same arithmetic and roughly a hundred times slower.
    """
    gradient = _vertical_gradient(grey)
    mean, deviation = _stats(gradient.histogram())
    mask = gradient.point(lambda value: 255 if value > mean + EDGE_SIGMA * deviation else 0)
    column = mask.resize((1, mask.size[1]), Image.BOX)
    return [pixel / 255 for pixel in column.getdata()]


BAND_SHARE = 0.055
"""Depth of the outer band, as a share of the card, used for `band_structure`."""


def _band_structure(grey):
    """Mean |d/dy| in the least detailed of the four outer bands.

    Low means at least one edge of the card is flat — a mat, a printed margin, or a dark
    surround. MEASURED on the client's 19: it ranges 0.33 to 5.45, and 7 of the 19 sit below
    1.0, because his Avacyn, both Command Towers, Hullbreaker, Aurelia, Force of Will and
    Brainstealer all place an illustrated frame INSIDE a flat dark surround.

    That is why this is reported and not gated, and it corrects an assumption made earlier the
    same day: his frames are closed on all four sides, but they do not all bleed to the trim.
    His own words allow it — "id be okay with black borders or black going around" — so a dark
    surround is a taste, and only a PALE mat is the defect `check.matted` exists for.
    """
    width, height = grey.size
    band_width, band_height = int(width * BAND_SHARE), int(height * BAND_SHARE)
    sides = (
        grey.crop((0, 0, width, band_height)),
        grey.crop((0, height - band_height, width, height)),
        grey.crop((0, 0, band_width, height)),
        grey.crop((width - band_width, 0, width, height)),
    )
    return min(_gradient_mean(side) for side in sides)


def _interior_energy(grey):
    """Mean |d/dy| over the middle of the card, clear of any frame or surround.

    MEASURED 2026-08-20 and the cleanest separator found after `ruled_rows`: the client's 19 run
    2.75 to 9.43, our lettered batch 9.26 to 12.01. Almost disjoint, and it is the number behind
    `QUALITY`'s "an even field of fine detail across the whole card is the one thing that makes
    it look cheap" — measured at last, on his corpus rather than the reference site's.
    """
    width, height = grey.size
    inset_x, inset_y = int(width * BAND_SHARE * 3), int(height * BAND_SHARE * 3)
    return _gradient_mean(grey.crop((inset_x, inset_y, width - inset_x, height - inset_y)))


class Metrics(dict):
    """A card's structure, as a plain dict so `--json` needs no encoder.

    A dict rather than a NamedTuple because the set of metrics is expected to change while the
    archetypes are being calibrated, and every consumer here reads by name.
    """

    __getattr__ = dict.__getitem__


def measure(source):
    """`Metrics` for one card — a path, or an already-open PIL image."""
    image = Image.open(source) if isinstance(source, (str, Path)) else source
    grey = _grey(image)
    shares = _row_shares(grey)
    return Metrics(
        ruled_rows=sum(1 for share in shares if share > RULED_SHARE),
        widest_edge=round(max(shares), 3),
        band_structure=round(_band_structure(grey), 2),
        interior_energy=round(_interior_energy(grey), 2),
    )


# MEASURED 2026-08-20 on the client's 19, per archetype. The thresholds are his corpus's own
# range, not a target we invented, so "passes" means "indistinguishable from his cards on this
# axis" rather than "better than last week".
#
# `panel` is exempt from the straight-edge gates and that is not a loophole. His flat-graphic
# cards — Counterspell, Memory Jar, Arcane Signet and the two token murals — carry boxed
# captions with genuinely straight rims, and they score 3, 3, 1, 4 and 11 ruled rows against a
# corpus mean of 2.3. Rectangles are correct in that idiom and wrong in the other four, which is
# exactly why the archetype has to be an input to the grade. Gating them all at one number would
# have failed a fifth of his own favorites.
GATES = {
    "default": {"ruled_rows": 4, "widest_edge": 0.62, "interior_energy": 9.5},
    "panel": {"ruled_rows": 12, "widest_edge": 0.85, "interior_energy": 9.5},
}


def gates(archetype=None):
    return GATES.get(archetype or "default", GATES["default"])


def grade(metrics, archetype=None):
    """`check.Problem`s for a card that sits outside the client corpus's range. Empty means in.

    Shares `check.Problem` deliberately: "what is wrong with this card" should have one
    vocabulary whether the answer came from a ship gate or from an evidence run.
    """
    limits = gates(archetype)
    problems = []
    if metrics["ruled_rows"] > limits["ruled_rows"]:
        problems.append(
            Problem(
                "ruled",
                f"{metrics['ruled_rows']} rows carry a hard edge across more than "
                f"{RULED_SHARE:.0%} of the card, against at most {limits['ruled_rows']} in the "
                "client's corpus — the card's surfaces are rectangles rather than drawn objects",
            )
        )
    if metrics["widest_edge"] > limits["widest_edge"]:
        problems.append(
            Problem(
                "wide_rim",
                f"a single straight edge spans {metrics['widest_edge']:.0%} of the width, "
                f"against at most {limits['widest_edge']:.0%} in the client's corpus — a plate "
                "rim running the full width reads as chrome laid over the art",
            )
        )
    if metrics["interior_energy"] > limits["interior_energy"]:
        problems.append(
            Problem(
                "busy",
                f"interior detail energy is {metrics['interior_energy']}, against "
                f"{limits['interior_energy']} at the top of the client's corpus — an even field "
                "of fine detail across the whole card is what makes it read as cheap",
            )
        )
    return problems


def corpus(paths):
    """[(name, Metrics)] for a directory's worth of cards, skipping the blanks we store beside them."""
    return [
        (path.name, measure(path))
        for path in sorted(Path(p) for p in paths)
        if path.suffix.lower() == ".png" and not path.stem.endswith("-blank")
    ]


def summarise(measured):
    """{metric: {mean, min, max, median}} across a corpus, for comparing batch to batch."""
    summary = {}
    for key in ("ruled_rows", "widest_edge", "band_structure", "interior_energy"):
        values = sorted(metrics[key] for _name, metrics in measured if key in metrics)
        if not values:
            continue
        summary[key] = {
            "mean": round(sum(values) / len(values), 2),
            "min": values[0],
            "max": values[-1],
            "median": values[len(values) // 2],
        }
    return summary
