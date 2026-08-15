"""Where did the AI put the blank surfaces, and what did it paint that it should not have?

One vision call: four surfaces to print into, plus the two defects that call for a repaint.

This is BUILD-SPEC §5.1 option C, which was rated expensive when it assumed classical CV
hunting for rectangles. A VLM returns bounding boxes directly, against art we already have and
without regenerating it, so it costs one cheap call and does not touch the one-pass credit
model (bd mtg-yp3).

It has to be asked per card because there is no fixed geometry to assume. Measured across 24
reference-site cards with one card appearing ten times, the rules panel landed anywhere from
y≈0.20 to y≈0.85 — full width, a narrow right-hand float, sometimes two.
"""

import json

from google.genai import types

from generation import gemini

MODEL = "gemini-3.6-flash"

SINGLE = ("title", "type", "pt")
KEYS = ("title", "type", "rules", "pt")
# Keys whose value is a LIST of boxes rather than one box. Everything `detect` returns is a box or
# a list of boxes, so a caller can draw the whole dict without special-casing each key.
LISTS = ("rules", "spare", "marks")
# What the compositor prints into. `spare` and `marks` are faults for `generation.check` to act on,
# never surfaces to print on.
FAULTS = ("spare", "marks")

# Gemini reports boxes normalised to 0-1000 as [ymin, xmin, ymax, xmax]. Asking for that order
# explicitly, in its own convention, beats asking for x0/y0/x1/y1 and hoping the axes line up.
BOX = {
    "type": "array",
    "items": {"type": "integer"},
    "minItems": 4,
    "maxItems": 4,
}
# `rules` is a LIST, and that is the finding this module was rebuilt around. MEASURED 2026-08-10
# on tcggenerator.com's own full-resolution Terror of the Peaks: the three abilities sit on three
# separate pale strips. Asking for one slab is what held our body text at x-height 24px against
# their 34px on the identical 1792x2400 canvas — a strip holding two lines can be set far larger
# than a slab holding five.
SCHEMA = {
    "type": "object",
    "properties": {
        **{
            key: {**BOX, "description": f"[ymin, xmin, ymax, xmax] of the {key} surface, 0-1000"}
            for key in SINGLE
        },
        "rules": {
            "type": "array",
            "items": BOX,
            "description": "one [ymin, xmin, ymax, xmax] per pale text strip, top to bottom",
        },
        # Both added 2026-08-13 from the client's two circled defects. They ride along on the call
        # that was already being made, so detecting them costs nothing: the price of acting on them
        # is one repaint on the cards that have them, against a customer receiving a card with a
        # blank second type bar or a set symbol on it.
        "spare": {
            "type": "array",
            "items": BOX,
            "description": "one box per EXTRA blank raised surface, not counted above",
        },
        "marks": {
            "type": "array",
            "items": BOX,
            "description": "one box per patch of painted lettering, glyphs or emblem",
        },
        # Answered against the SECOND image when one is attached, in that image's own coordinates.
        # The model is not asked to map it back to the card — `_from_crop` does that, because
        # arithmetic in the answer is a second thing that can be wrong.
        "pt_detail": {
            **BOX,
            "description": "the shield in the SECOND image, in that image's own 0-1000 coordinates",
        },
    },
}

PT_CROP = (0.56, 0.56, 1.0, 1.0)
"""The corner of the card the second image is cut from.

Covers every shield in the sample with room to spare: measured across six cards they span
x 0.727-0.925, y 0.771-0.960 (spikes/measure_pt_shield.py).
"""

PT_CROP_SCALE = 2
"""How much the corner is enlarged before it is attached.

WHY A CROP AND NOT A SECOND CALL. `detect` reports the shield on 7 of 20 runs over the same
stored blanks, and three rounds of rewording never moved it — it is a resolution problem, not a
comprehension one. The smallest shield measured is 0.067 of the card wide, which is ~120px in a
1792x2400 frame the model also has to read four other surfaces out of. Cutting the corner and
doubling it makes that shield ~480px in a 394x528 frame.

This rides along in the EXISTING call as a second image part rather than adding a third AI call
to the two a card already costs. The extra image is ~0.2 megapixels against the full card's 4.3,
so it is a rounding error on the call we were making anyway — and it replaces a guess that has
no way to see the thing it is guessing at (bd mtg-1uv)."""

PROMPT = """This is a fantasy trading card with BLANK raised surfaces and no writing on it.

The card's outer edge is decorated with painted material — rock, wood, metal, bone — running
around all four sides. That edge decoration is NOT one of the surfaces. Ignore it, except that
the surfaces below are usually attached to it and may run under it at their ends.

Report the bounding box of each blank surface, as [ymin, xmin, ymax, xmax] normalised 0-1000:

- "title": the plate across the very top, where the card's name will be printed. It is usually
  DARK. It sits inside the edge decoration, not on it.
- "type": the NARROW horizontal strip lower down, directly above the broad slab. It is much
  shorter than the slab and usually DARK too. If the slab has a narrow rail along its top edge,
  that rail is it.
- "rules": a LIST, one box per pale text strip, ordered top to bottom. These are the LIGHTEST
  surfaces on the card — parchment, pale stone, glowing amber — and there may be one broad slab
  or several separate strips stacked down the lower part of the card. Report every one of them
  separately; do not merge two strips into one box that spans the gap between them.
- "pt": the small shield, boss or plaque near the BOTTOM-RIGHT of the card, usually overlapping
  the corner of the lowest pale strip. It is small and roughly square or shield-shaped, and it is
  not one of the pale text strips. Report it whenever one is present, even if it sits on the
  card's edge decoration rather than on a strip, and even if it looks like a badge or an emblem —
  it belongs HERE and not under "marks" below.

Then report two kinds of DEFECT, each as a list of boxes, empty if the card has none:

- "spare": every OTHER blank raised surface — a plate, bar, ledge, strip, tablet or panel wide
  enough to hold a line of text — that is not one of the four above. The commonest is a second
  narrow bar directly above or below the "type" strip. Do not list the card's edge decoration, a
  rivet, a boss, a crack, or anything that is part of the artwork rather than a raised blank
  surface for text.
- "marks": every patch of painted WRITING or STAMPED insignia — letters, words, numerals, runes,
  rune-like scratches, carved script, a signature, a watermark, or a small flat graphic symbol of
  the kind an expansion symbol or a publisher's logo is. Report it wherever it is: on a surface,
  in a corner, in the artwork. A mark lies ON the material like ink or a stamp, so a BLANK object
  with its own thickness and shadow — a shield, boss, plaque, rivet, gem — is not one, and neither
  is texture, grain or a crack.

Give the INNER usable area of each surface — the flat part text can sit on, inside its carved
rim and clear of any chipped or curled ends, not including the rim itself. Where something from
the artwork crosses in FRONT of a surface, keep that out of the box as well.

Omit a key entirely if that surface genuinely is not present on this card. Do not guess, and do
not report a region of the artwork, or the card's edge decoration, as a surface."""

PT_DETAIL_PROMPT = """
A SECOND image is attached. It is the bottom-right corner of the same card, enlarged, so the
small shield is easier to see than it is in the full card above.

This card is a creature, so it has a power/toughness value to print and a shield to print it on.

In "pt_detail", give the shield's box IN THE SECOND IMAGE'S OWN COORDINATES, 0-1000 over that
image's width and height — not the card's. Give its INNER FACE: the flat recessed area the
numbers will be printed on, INSIDE the raised rim, not the shield's outer silhouette. The rim is
often bright metal and printing on it is exactly the mistake to avoid.

If the second image shows no shield, boss or plaque at all, omit "pt_detail"."""


def _usable(box):
    """A box as (x0, y0, x1, y1) fractions, or None if it is not worth trusting.

    A degenerate or inverted box means the detector was unsure; dropping it leaves that field
    unprinted, which is visible. Trusting it would print over the art, which reads as a design
    choice — the failure has to stay the obvious way round (bd mtg-yp3).
    """
    if not box or len(box) != 4:
        return None
    ymin, xmin, ymax, xmax = (value / 1000 for value in box)
    if xmax - xmin < 0.02 or ymax - ymin < 0.005:
        return None
    return (xmin, ymin, xmax, ymax)


# Where the P/T shield lives, as (x, y) fractions a mark's centre must clear to be believed.
# MEASURED 2026-08-13 on the first two borderless creatures: the shield came back at x0.76-0.94,
# y0.82-0.96 on both, and the detector called it a `marks` patch rather than a `pt` surface on 4 of
# 4 runs before the marks wording was tightened and on 1 of 4 after. It is the same object every
# time — a small blank badge in the bottom-right corner is what a P/T boss IS — so the last quarter
# is closed by position instead of by more words.
#
# What this gives up: a set symbol painted in the bottom-right CORNER goes unreported. A real one
# never lives there — on every printed Magic card it sits at the right-hand end of the type line,
# which is well clear of this region — and the brief bans it in either place. A false repaint costs
# a credit on a fair share of every creature card, so the trade is not close.
PT_CORNER = (0.68, 0.72)


def _in_pt_corner(box):
    x0, y0, x1, y1 = box
    return (x0 + x1) / 2 > PT_CORNER[0] and (y0 + y1) / 2 > PT_CORNER[1]


# WHERE THE SHIELD IS, when the detector does not report one (bd mtg-wfp).
#
# The OFFSET from the lowest pale strip's bottom-right corner holds up: measured first over the
# five stored detections that found a shield, and again over five cards where nothing was reported
# at all, both come out at about (-0.045,-0.015). The shield sits just inside and just above that
# corner, which is where the brief asks for it.
#
# THE SIZE DOES NOT, AND THE FIRST FIT OF IT WAS BIASED BY CONSTRUCTION. It was taken from those
# same five DETECTIONS — but `pipeline` only calls `infer_pt` when `detected["pt"]` is absent, so
# the constant was fitted on the one population it never runs on. Re-measured 2026-08-15 over five
# cards where detection actually missed, by reading the painted surface off a labelled grid
# (spikes/measure_pt_shield.py):
#
#   detected, n=5     width 0.143 - 0.156     <- what the old 0.152x0.127 was fitted on
#   undetected, n=5   width 0.067 - 0.130     <- what it is applied to
#
# The two do not overlap. The detector finds big shields and misses small ones — which is also the
# likeliest reason the 35% hit rate never moved for any wording — so the old size was the median of
# the large tail applied only to the small tail, and it overhung the painted surface on 5 of 5.
#
# The statistic is a median but the cost around it is NOT symmetric: `compositor._display` sets the
# glyphs at half the box height and centres them, so a box smaller than the shield prints a P/T
# safely inside it, while a box larger than the shield prints one hanging off the edge. When this
# is next re-measured, err small.
#
# THE DOMAIN THIS HOLDS ON, added 2026-08-15 after Terror of the Peaks broke it (job 519273ac).
# Every card the offset was fitted on has its lowest rules strip ending at 0.898-0.943, where the
# little room left below pins the shield in place and the offset cannot be far wrong. Terror's
# strip ends at 0.831 and its shield is painted 0.195 wide — wider than anything in either
# population — so the guess landed 0.038 high and the printed 5/4 opened on the shield's rim.
# The residual even flips sign outside the range: centre-minus-strip-bottom is -0.006 to -0.029
# on all five fitted cards and +0.024 on Terror.
#
# Do not answer this with another constant. The shield varies 0.067-0.195 wide, the printable
# INNER FACE is a rim's width inside the silhouette, and that rim scales with the shield — so
# there is no fixed box that tracks it (bd mtg-1uv). It needs the surface observed: either the
# detector made to see it, or a second cropped ask at the corner where it missed.
PT_OFFSET = (-0.046, -0.014)
PT_SIZE = (0.110, 0.092)


def infer_pt(panels):
    """The box the P/T shield must occupy, or None if there is no strip to anchor to.

    WHY GUESS AT ALL. Detection of this one surface is genuinely unreliable: measured 2026-08-15 by
    running `detect` repeatedly over the SAME stored blanks, it reported the shield on 7 of 20 runs
    on cards where the shield is plainly painted — verified by eye. It is not a wording problem.
    Restating the bullet at length made it worse (4 of 20), and the shield is not being misfiled
    either: on 7 misses in a row nothing was reported anywhere in that corner. The detector simply
    does not see it on some images.

    What a miss costs today is not a smaller failure than guessing. `check` fires `missing_pt`, the
    pipeline burns a full extra image call repainting art that was already correct, and if the
    repaint misses too the customer gets a CREATURE WITH NO POWER OR TOUGHNESS — an unusable card.

    So the trade is: a card whose P/T lands a few percent off the middle of its shield, against a
    card missing a printed value it cannot be played without. The residual risk is a model that
    painted no shield at all, in which case the P/T is printed over artwork — which the compositor
    strokes and shadows for legibility, and which is still a complete card.
    """
    rules = panels.get("rules")
    if not rules:
        return None  # nothing to anchor to; leaving it unprinted stays the honest failure
    lowest = max(rules, key=lambda box: box[3])
    cx = lowest[2] + PT_OFFSET[0]
    cy = lowest[3] + PT_OFFSET[1]
    width, height = PT_SIZE
    box = (cx - width / 2, cy - height / 2, cx + width / 2, cy + height / 2)
    # Never off the card, and never into the margin the printer trims (bd mtg-cjx).
    return tuple(min(0.96, max(0.04, value)) for value in box)


def _corner(png, region=PT_CROP, scale=PT_CROP_SCALE):
    """The card's bottom-right corner, enlarged, as PNG bytes."""
    import io

    from PIL import Image

    card = Image.open(io.BytesIO(png))
    width, height = card.size
    crop = card.crop((
        int(region[0] * width), int(region[1] * height),
        int(region[2] * width), int(region[3] * height),
    ))
    crop = crop.resize((crop.width * scale, crop.height * scale), Image.LANCZOS)
    out = io.BytesIO()
    crop.convert("RGB").save(out, format="PNG")
    return out.getvalue()


def _from_crop(box, region=PT_CROP):
    """A box in the crop's own fractions back into the card's fractions."""
    span_x, span_y = region[2] - region[0], region[3] - region[1]
    return (
        region[0] + box[0] * span_x,
        region[1] + box[1] * span_y,
        region[0] + box[2] * span_x,
        region[1] + box[3] * span_y,
    )


def detect(png, paragraphs=None, expect_pt=False):
    """{'title': box, 'rules': [box, ...], ...} in 0-1 fractions of the canvas.

    Fractions rather than pixels so the result survives the print-resolution upscale, and so a
    stored detection stays valid if the canvas size ever changes.

    `rules` is always a list, because the reference site paints one pale strip per ability rather
    than one slab (see SCHEMA). `paragraphs` is how many abilities Scryfall says the card has —
    a hint, not a constraint, because the model paints what it paints and the compositor already
    packs leftovers into the last strip.

    `spare` and `marks` are the two FAULTS, also lists: extra blank surfaces nothing will be
    printed on, and painted lettering or insignia. `generation.check` turns them into a repaint.
    """
    prompt = PROMPT
    if paragraphs:
        prompt += (
            f"\n\nFor reference, this card's rules text has {paragraphs} separate "
            f"{'ability' if paragraphs == 1 else 'abilities'}, so {paragraphs} pale "
            "strip(s) is the likely answer — but report what you actually see, not what "
            "this number predicts."
        )
    # The corner rides along in THIS call, not a third one. Only for creatures: a card with no
    # power has no shield to find, and attaching the crop anyway only invites a false positive on
    # a rivet or a boss.
    contents = [types.Part.from_bytes(data=png, mime_type="image/png")]
    if expect_pt:
        prompt += PT_DETAIL_PROMPT
        contents.append(types.Part.from_bytes(data=_corner(png), mime_type="image/png"))
    contents.append(prompt)

    response = gemini.client().models.generate_content(
        model=MODEL,
        contents=contents,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=SCHEMA,
            temperature=0,
        ),
    )
    raw = json.loads(response.text or "{}")

    panels = {}
    for key in SINGLE:
        box = _usable(raw.get(key))
        if box:
            panels[key] = box
    for key in ("rules", *FAULTS):
        boxes = [box for box in map(_usable, raw.get(key) or []) if box]
        if key == "marks":
            boxes = [box for box in boxes if not _in_pt_corner(box)]
        if boxes:
            panels[key] = sorted(boxes, key=lambda box: box[1])

    # The enlarged corner OUTRANKS the full-card answer for this one surface: both look at the
    # same shield, and one of them can actually see it. When the corner finds nothing the
    # full-card `pt` still stands, so this can only add a detection, never lose one.
    detail = _usable(raw.get("pt_detail"))
    if detail:
        panels["pt"] = _from_crop(detail)
    return panels
