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

from PIL import Image

INSET = 0.012
"""How far in from the trim to sample. Far enough to miss antialiasing on the very edge."""

LIGHT = 185
"""Darkest channel a mat pixel may have. Every mat seen so far is cream, bone or white."""

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


def matted_share(image):
    """0.0 to 1.0 — how much of the edge is one flat light colour, i.e. a mat."""
    ring = _ring(image)
    light = [p for p in ring if min(p) > LIGHT]
    if len(light) < len(ring) * MATTED:
        return len(light) / len(ring) if ring else 0.0
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


def trim(png):
    """(PNG bytes, depth as a share of the shorter side). Unchanged bytes when there is no mat.

    The crop is scaled back to the original canvas, so every downstream coordinate — the panel
    boxes, the compositor's geometry — keeps working in the units it already uses.
    """
    image = Image.open(io.BytesIO(png)).convert("RGB")
    if matted_share(image) < MATTED:
        return png, 0.0

    ring = [p for p in _ring(image) if min(p) > LIGHT]
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
