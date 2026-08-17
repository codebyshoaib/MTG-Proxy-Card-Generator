"""Full bleed by construction, instead of by asking.

CLIENT 2026-08-13: "the white borders on the first card are not ideal ... if you can do that it
would be by far the best". The brief has said FULL BLEED in capitals ever since, and it is still
ignored: measured on the first frontend run (job 9f16e827, borderless on), three of five faces
came back with a cream mat around all four sides — 100% of the sampled edge ring on Lightning
Bolt, Sol Ring and Elesh Norn, against 32% and 3% for the two clean ones.

Prompting harder is not the lever; the brief is already three paragraphs of it. So the mat is
measured and cut off before anything else looks at the image, which makes the defect impossible
rather than unlikely. What the model paints inside its own margin is still the whole card, so
trimming loses nothing: the art was never in the margin.
"""

import io
import statistics

from PIL import Image

INSET = 0.012
"""How far in from the trim to sample. Far enough to miss antialiasing on the very edge."""

LIGHT = 185
"""Darkest channel a LIGHT mat pixel may have. Cream, bone and white — see `DARK_MAT_SHARE`."""

DARK_MAT_SHARE = 0.98
DARK_MAT_FLAT = 2.0
"""When the ring is one flat colour of ANY value, not just a light one.

CLIENT 2026-08-17, on the Sol Ring of the three-style run: "the sol ring comes as a card not full
bleed creative full art. as client needs." It came back as a card silhouette with rounded corners on
a flat near-black ground — the exact defect circled on 2026-08-13 — and BOTH gates passed it.

The reason is `LIGHT`, and its own docstring said so before this: "every mat seen so far is cream,
bone or white". That held over the 84 stored images it was fitted on and failed on the 85th, because
`art_deco` and every other dark-ground style mats in the dark. Sol Ring's ring measures (50, 53, 60),
so `matted_share` found no light pixels, returned early, and `trim` cut nothing.

Light-ness was only ever a PROXY for "printed rather than painted". Flatness is the real test, and
measured colour-blind over the stored 1792x2400 blanks it separates on its own:

    ring one flat colour   Sol Ring (art deco)  share 1.000  MAD 1.0   <- the mat
    partial                Obliterator 0.814 / 8.0,  Thirsting Roots 0.590 / 1.0
    genuine full bleed     every other card     share 0.000

So this is an ADDITIVE second path rather than a rewrite: the light-mat route above keeps every
threshold it was fitted with, and this only looks at rings that route already gave up on. Its two
constants are deliberately far tighter than `MATTED` (0.55) and `FLAT_MAX` (4.0) — near enough the
WHOLE ring, near enough ONE value — because a dark flat edge is a thing a night scene can approach
and a pale one is not. Nothing in the stored set except Sol Ring comes close.
"""

TOLERANCE = 26
"""How far a pixel may sit from the mat's own colour and still count as part of it."""

MATTED = 0.55
"""Share of the ring that has to be mat before we call it one.

High on purpose. A snow scene lights its own edges — the two clean cards in the measured run sat
at 32% and 3% — so the test is not "is the edge light" but "is the edge one flat colour all the
way round", which a painted scene never is.

LOWERED FROM 0.9, 2026-08-16. A Comic Book Raphael came back with a white mat on all four sides,
graded SOUND, and shipped. It measured 0.8828 — it missed the threshold by 0.017, which is a card
the client would have circled lost to a hundredth.

Re-measured over that batch, and the two populations are nowhere near each other:

    clean    Craterhoof 0.000    Sol Ring 0.107
    matted   Raphael    0.883

0.9 was not sitting in the gap, it was sitting on top of the only positive example. This sits in
the middle of the gap instead, the same way CONTRAST_MIN does. There is more than 7x the room
between the clusters that this threshold needs, so it is not tuned to the one card that failed.
"""

FLAT_MAX = 4.0
"""How far the light edge pixels may stray from their own median and still be a mat.

Median absolute deviation, worst channel, over the light ring pixels only.

ADDED 2026-08-16, bd mtg-fsw. `MATTED` alone cannot do the job this module's own docstring
describes. The test is "is the edge ONE FLAT COLOUR all the way round", but the implementation
only asked whether the edge pixels sit within `TOLERANCE` of each other — and a pale watercolour
sky varies by less than that, so a correct full-bleed painting read as a mat:

    printed mat  Raphael 0.883 share / 1.00 MAD    reference-site white border 1.000 / 1.00
    pale wash    Serra   0.634 share / 16.50 MAD   Serra 0.614 / 15.50   Swords 0.741 / 11.00

Both watercolour Serras and the watercolour Swords are CORRECT cards, painted to all four edges.
Raising `MATTED` past 0.741 was not available: the only real mat measured sits at 0.883 and the
client rejected that exact card, so the constant would have been fitted to a 0.14 gap. Flatness
opens a 9x one instead, and this sits in the middle of it — 4x above every mat measured, 2.4x
below the palest correct painting.

Median rather than standard deviation on purpose: a cream mat around a bright snow scene puts
light SCENE pixels in the same sample, and a mean-based spread would be dragged up by them into
calling a real mat a painting. The median ignores them while the mat is the bulk of the ring.
"""

MAX_DEPTH = 0.10
"""Deepest margin we will cut, as a share of the shorter side.

Past this it is not a margin, it is the picture, and cutting it would crop the art. A card that
matted deeper than this is reported instead — see `check.matted`.
"""


def _ring(image, inset=INSET):
    """Pixels one inset in from all four edges, walking the whole way round."""
    width, height = image.size
    depth = int(min(width, height) * inset)
    pixels = image.load()
    step = max(1, width // 60)
    return (
        [pixels[x, depth] for x in range(0, width, step)]
        + [pixels[x, height - 1 - depth] for x in range(0, width, step)]
        + [pixels[depth, y] for y in range(0, height, step)]
        + [pixels[width - 1 - depth, y] for y in range(0, height, step)]
    )


def _near(pixel, colour):
    return all(abs(a - b) <= TOLERANCE for a, b in zip(pixel, colour))


def _deviation(pixels):
    """Worst channel's median absolute deviation — how far these pixels stray from one colour."""
    return max(
        statistics.median([abs(value - statistics.median(channel)) for value in channel])
        for channel in zip(*pixels)
    )


def _dark_mat(ring):
    """0.0, or the share of a ring that is one flat colour too dark for the light route.

    Only ever consulted when the light route found nothing — see `DARK_MAT_SHARE`.
    """
    if not ring:
        return 0.0
    colour = tuple(sorted(channel)[len(channel) // 2] for channel in zip(*ring))
    same = [p for p in ring if _near(p, colour)]
    share = len(same) / len(ring)
    if share < DARK_MAT_SHARE or _deviation(same) > DARK_MAT_FLAT:
        return 0.0
    return share


def matted_share(image):
    """0.0 to 1.0 — how much of the edge is one flat colour, i.e. a mat."""
    ring = _ring(image)
    light = [p for p in ring if min(p) > LIGHT]
    if len(light) < len(ring) * MATTED:
        # A mat the light route cannot see, because it is not light. Falls back to the share it
        # would have reported, so a partly-light edge is unchanged.
        return _dark_mat(ring) or (len(light) / len(ring) if ring else 0.0)
    if _deviation(light) > FLAT_MAX:
        # Light all the way round, but a wash rather than a printed colour — see FLAT_MAX. None of
        # this edge is ONE flat colour, so none of it is mat.
        return 0.0
    # The mat's own colour, taken from the ring rather than assumed to be white — the ones
    # measured are cream (#f4efe3), not #ffffff.
    colour = tuple(sorted(channel)[len(channel) // 2] for channel in zip(*light))
    return sum(1 for p in ring if _near(p, colour)) / len(ring)


def _depth(image, colour, axis, forward):
    """How many rows (or columns) in from one edge are still mat."""
    width, height = image.size
    pixels = image.load()
    span, across = (height, width) if axis == "y" else (width, height)
    limit = int(min(width, height) * MAX_DEPTH)
    step = max(1, across // 40)

    for offset in range(limit):
        index = offset if forward else span - 1 - offset
        line = [
            pixels[position, index] if axis == "y" else pixels[index, position]
            for position in range(0, across, step)
        ]
        # One line of scene ends the margin. 0.9 rather than 1.0 because the plates the model
        # paints sometimes clip the very edge of its own mat.
        if sum(1 for p in line if _near(p, colour)) < len(line) * 0.9:
            return offset
    return limit


CORNER_MAX_DEPTH = 0.05
"""Deepest corner arc we will cut, as a share of the shorter side.

MEASURED 2026-08-17 over all 74 composited cards. A SECOND way the full bleed fails, and one
`matted_share` structurally cannot see: the model paints the card as an OBJECT — a rounded-corner
card standing on a white ground — rather than as an image that IS the card. The four straight
edges bleed correctly; only the corner arcs are white.

`_ring` walks a line one INSET in from each edge, so it samples the flat sides and barely clips
the arcs. Phyrexian Obliterator, which has a plainly visible white wedge at every corner, scores
`matted_share` 0.014 against a 0.55 gate. The ring test is right about what it measures and blind
to this, the same way `MATTED` was blind to a pale wash before `FLAT_MAX` — a gate fitted to one
shape of a defect does not see the next shape of it.

Rate is 2 of 74, and both arcs are SHALLOW:

    Lightning Bolt c66d6b93   0.007 deep  (0.037 along the top edge)
    Obliterator    f082a662   0.028 deep

Against 0.040, the trim the brief already reserves ("keep every raised surface and every important
detail inside the middle 92%"), and 0.048, a real Magic card's 3mm corner radius over its 63mm
width. So the arc lands where the card is cut anyway: this is a defect of the PREVIEW, not of the
printed card. It is cut here rather than repainted because a repaint would spend a credit undoing
something the guillotine removes for free.

0.05 sits just above the deeper of the two and just under the physical corner radius. A card whose
arc runs deeper than this is not a rounded corner, it is a picture inset in a background, and
cutting it would crop art — so it is left whole and `check.matted` decides.
"""


PAPER = 242
"""Darkest channel a corner pixel may have and still be the model's own white ground.

`LIGHT` (185) is the wrong threshold here and firing it was measured: it called 22 of 84 stored
images matted, most of them Elesh Norn, whose card is snow and white robe. This module's own
docstring warns about exactly that — "a snow scene lights its own edges" — and a 1% corner box is
small enough that a smooth pale gradient passes `FLAT_MAX` too, which is trap 2 in
`docs/HANDOFF-2026-08-16.md`.

MEASURED 2026-08-17, median min-channel of the whitest corner across all 84 stored images:

    rounded card on white   Lightning Bolt 255 (MAD 0)   Obliterator 254 (MAD 1)
    palest real scene       Sol Ring 231   Lightning Bolt 230   Elesh Norn 229   Delver 225

Two populations 23 apart with nothing between them, so this sits in the middle rather than at a
round number. The reason they separate so cleanly is that the model's ground is PAPER — an
untouched canvas colour, not a lit surface — and nothing it paints deliberately reaches it.
"""


CORNER_BOX = 8
"""Side of the square sampled at each of the four corners, in pixels.

Small on purpose. The question is only "is the outermost point of this corner the model's paper",
and a larger box starts sampling the arc's curve and the scene behind it.
"""


def _rounded_card(image):
    """Are ALL FOUR corners the model's paper ground — i.e. did it paint a card-shaped object?

    Requiring all four is what makes this specific. Paper somewhere on an edge is common and
    innocent: a snow scene or a white robe touches the trim on plenty of correct cards, and an
    earlier version of this that took the deepest paper run anywhere along any edge fired on 27 of
    84 stored images, most of them Elesh Norn, whose card is snow. A card silhouette has four
    rounded corners by construction, so all four is the signature and any one of them is noise.

    MEASURED 2026-08-17 over all 84 stored images — this does not need a threshold fitted, it is
    binary:

        rounded card on white   Obliterator [1.0, 1.0, 1.0, 1.0]   Lightning Bolt [1.0, 1.0, 1.0, 1.0]
        every other card        [0.0, 0.0, 0.0, 0.0]
    """
    width, height = image.size
    pixels = image.load()
    for x0, y0 in (
        (0, 0),
        (width - CORNER_BOX, 0),
        (0, height - CORNER_BOX),
        (width - CORNER_BOX, height - CORNER_BOX),
    ):
        paper = sum(
            1
            for x in range(x0, x0 + CORNER_BOX)
            for y in range(y0, y0 + CORNER_BOX)
            if min(pixels[x, y]) > PAPER
        )
        if paper <= CORNER_BOX * CORNER_BOX * 0.5:
            return False
    return True


def corner_depth(image):
    """Pixels to cut off every side to clear the arcs of a rounded card. 0 when there is none.

    Measured directly rather than by trying crops: within each corner's own stretch of edge, how
    many paper pixels run inward before the scene starts. The deepest of those is exactly the crop
    that leaves no paper at any edge.

    Scanned only NEAR the corners, which is where an arc is. Two earlier versions failed on either
    side of that. Sampling one small box AT each corner under-cut, because an arc is shallow but
    wide — Lightning Bolt's runs 0.037 of the card along the top edge and 0.007 deep — so clearing
    the corner point left the tail behind and took Obliterator from 0.240 white to 0.049 instead of
    to zero. Scanning the WHOLE edge then over-cut, picking up bright scene mid-edge on cards with
    nothing wrong with them.

    Returns 0 for an arc deeper than `CORNER_MAX_DEPTH`, because at that point cropping would take
    art rather than margin — see the constant.
    """
    if not _rounded_card(image):
        return 0
    width, height = image.size
    pixels = image.load()
    limit = int(min(width, height) * CORNER_MAX_DEPTH)
    reach = int(min(width, height) * 0.20)  # how far along each edge an arc can still be running
    step = 4  # an arc is hundreds of pixels wide, never four

    def run(fixed, axis, forward):
        for offset in range(limit):
            index = offset if forward else (height if axis == "y" else width) - 1 - offset
            pixel = pixels[fixed, index] if axis == "y" else pixels[index, fixed]
            if min(pixel) <= PAPER:
                return offset
        return limit

    runs = []
    for x in list(range(0, reach, step)) + list(range(width - reach, width, step)):
        runs += [run(x, "y", True), run(x, "y", False)]
    for y in list(range(0, reach, step)) + list(range(height - reach, height, step)):
        runs += [run(y, "x", True), run(y, "x", False)]

    # The 98th percentile rather than the maximum. An arc is a smooth curve, so its depth is a
    # plateau; a single deep spike is white ART reaching the trim near a corner, and taking the max
    # let one such spike on Lightning Bolt read as a 89px-deep margin and disqualify the whole
    # card. Measured on that card: median run 2-3px, max 73px on one edge and over the ceiling at
    # one point. Dropping the top 2% keeps the curve and discards the spike.
    runs.sort()
    deepest = runs[int(len(runs) * 0.98)] if runs else 0
    if deepest >= limit:
        return 0  # not an arc — a picture inset in a background. `check.matted` owns that.
    return deepest


def trim(png):
    """(PNG bytes, depth as a share of the shorter side). Unchanged bytes when there is no mat.

    The crop is scaled back to the original canvas, so every downstream coordinate — the panel
    boxes, the compositor's geometry — keeps working in the units it already uses.
    """
    image = Image.open(io.BytesIO(png)).convert("RGB")
    if matted_share(image) < MATTED:
        # No mat, but the corners may still be the model's own rounded card standing on white.
        # Cut evenly on all four sides: the arc is symmetric by construction, and an even cut is
        # the one that cannot slide the art off centre.
        depth = corner_depth(image)
        if not depth:
            return png, 0.0
        width, height = image.size
        cropped = image.crop((depth, depth, width - depth, height - depth)).resize(
            (width, height), Image.LANCZOS
        )
        out = io.BytesIO()
        cropped.save(out, format="PNG")
        return out.getvalue(), depth / min(width, height)

    # The mat's own colour, from the LIGHT pixels when there are enough of them and from the whole
    # ring when the mat is a dark one (`DARK_MAT_SHARE`). Taking the median of an empty list is
    # what a dark mat used to reach here as, before it was detected at all.
    ring = _ring(image)
    light = [p for p in ring if min(p) > LIGHT]
    if len(light) >= len(ring) * MATTED:
        ring = light
    colour = tuple(sorted(channel)[len(channel) // 2] for channel in zip(*ring))
    width, height = image.size
    top = _depth(image, colour, "y", True)
    bottom = _depth(image, colour, "y", False)
    left = _depth(image, colour, "x", True)
    right = _depth(image, colour, "x", False)
    if not (top and bottom and left and right):
        # A margin on three sides is not a mat, and cropping it would slide the art off centre.
        return png, 0.0
    ceiling = int(min(width, height) * MAX_DEPTH)
    if max(top, bottom, left, right) >= ceiling:
        # `_depth` stops counting at the ceiling, so a side that reaches it has not been measured
        # — it has run out of room. Cropping by the ceiling would cut art, not margin, so this
        # card is left whole for `check.matted` to fail.
        return png, 0.0

    cropped = image.crop((left, top, width - right, height - bottom)).resize(
        (width, height), Image.LANCZOS
    )
    out = io.BytesIO()
    cropped.save(out, format="PNG")
    return out.getvalue(), max(top, bottom, left, right) / min(width, height)
