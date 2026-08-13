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
    },
}

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


def detect(png, paragraphs=None):
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
    response = gemini.client().models.generate_content(
        model=MODEL,
        contents=[types.Part.from_bytes(data=png, mime_type="image/png"), prompt],
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
    return panels
