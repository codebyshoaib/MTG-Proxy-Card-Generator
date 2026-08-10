"""Where did the AI put the blank surfaces? One vision call, four boxes.

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
  card's edge decoration rather than on a strip.

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


def detect(png, paragraphs=None):
    """{'title': box, 'rules': [box, ...], ...} in 0-1 fractions of the canvas.

    Fractions rather than pixels so the result survives the print-resolution upscale, and so a
    stored detection stays valid if the canvas size ever changes.

    `rules` is always a list, because the reference site paints one pale strip per ability rather
    than one slab (see SCHEMA). `paragraphs` is how many abilities Scryfall says the card has —
    a hint, not a constraint, because the model paints what it paints and the compositor already
    packs leftovers into the last strip.
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
    strips = [box for box in map(_usable, raw.get("rules") or []) if box]
    if strips:
        panels["rules"] = sorted(strips, key=lambda box: box[1])
    return panels
