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
x 0.727-0.925, y 0.771-0.960, measured off the stored blanks.
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
- "pt": the small raised tab near the BOTTOM-RIGHT of the card, usually overlapping the corner of
  the lowest pale strip. ANY shape counts — a rounded rectangle, a disc, a shield, a boss, a
  plaque, a banner end, an irregular slab of the scene's own material — and it is not one of the
  pale text strips. Report it whenever one is present, even if it sits on the card's edge
  decoration rather than on a strip, and even if it looks like a badge or an emblem — it belongs
  HERE and not under "marks" below.

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
rim and clear of any chipped or curled ends, not including the rim itself.

Make it the LARGEST rectangle that fits inside that flat part. Do not report a cautious box
tucked well inside the surface: every bit of width left out is width the text cannot use, and
text set into two thirds of a panel leaves the rest of it standing visibly empty. Push all four
edges out to where the flat face actually stops.

A THIN thing crossing in FRONT of the face does not clip the box — a vine, a root, a chain, a
wingtip, a curl of smoke. The face runs on behind it and comes out the other side, so keep that
part IN. What clips the box is where the flat face itself ENDS: its rim, a curled rod, a torn or
chipped corner, a raised tab sitting over one of its ends, or a solid mass covering the face
right through to its edge.

Omit a key entirely if that surface genuinely is not present on this card. Do not guess, and do
not report a region of the artwork, or the card's edge decoration, as a surface."""

PT_DETAIL_PROMPT = """
A SECOND image is attached. It is the bottom-right corner of the same card, enlarged, so the
small tab is easier to see than it is in the full card above.

This card is a creature, so it has a power/toughness value to print and a small raised tab to
print it on. That tab may be ANY shape — a rounded rectangle, a disc, a shield, a boss, a plaque,
a banner end, an irregular slab of the scene's own material.

In "pt_detail", give that tab's box IN THE SECOND IMAGE'S OWN COORDINATES, 0-1000 over that
image's width and height — not the card's. Give its INNER FACE: the flat area the numbers will be
printed on, INSIDE any raised rim, not the tab's outer silhouette. The rim is often bright metal
and printing on it is exactly the mistake to avoid.

If the second image shows no such tab at all, omit "pt_detail"."""


SURFACES = ("title_plate", "type_strip", "rules_panel", "tab", "artwork", "edge", "other")
"""Where a patch of writing sits, as the read-back is allowed to answer.

An enum rather than free text so `check.proofread` can group by surface without parsing prose.
"""

READ_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {**BOX, "description": "[ymin, xmin, ymax, xmax] of the plate across the top"},
        # The mana cost is stamped against the plate's right end, so the one thing it can collide
        # with is the name the model lettered on the same plate. Asked for here rather than
        # inferred, because inferring it means guessing at a font we did not choose.
        "name": {**BOX, "description": "[ymin, xmin, ymax, xmax] of the card's name lettering"},
        # SIGNOFF 2026-08-19, Elesh Norn. The lettered grader transcribed the type line correctly
        # and never saw the red Phyrexian phi at the strip's right-hand end, because that mark is
        # a graphic, not words. `check.type_end_mark` grades the slot in Python; it needs this
        # box the same way `cost_collides` needs the title plate. Asked as geometry, not as
        # "is there a set symbol" — a yes/no here would grade the hint.
        "type": {**BOX, "description": "[ymin, xmin, ymax, xmax] of the type-line strip, full width"},
        "rules": {
            "type": "array",
            "items": BOX,
            "description": "one [ymin, xmin, ymax, xmax] per pale text strip, top to bottom",
        },
        "text": {
            "type": "array",
            "description": "every separate patch of writing on the card",
            "items": {
                "type": "object",
                "properties": {
                    "where": {"type": "string", "enum": list(SURFACES)},
                    "text": {"type": "string"},
                },
            },
        },
    },
}

READ_PROMPT = """This is a finished fantasy trading card. Unlike a blank, it HAS writing on it.

Two jobs.

FIRST, transcribe. Find every separate patch of writing anywhere on this card and report it in
"text", one entry per patch. For each one give:

- "text": exactly what it says, CHARACTER FOR CHARACTER. Transcribe what is actually printed, not
  what you expect a card like this to say. Do not correct spelling, do not expand abbreviations,
  do not tidy punctuation, and do not fill in a word you cannot read — if a word is obscured or
  illegible, write it as [?]. Keep line breaks out: run each patch together as one line.
  Write any mana, tap or loyalty symbol in brace notation — {T}, {G}, {2}, {G/W} — one pair of
  braces per symbol drawn, and if a symbol is drawn that you cannot name write {?}.
- "where": which surface it sits on, one of:
    title_plate  the plate across the very top
    type_strip   the narrow horizontal strip lower down
    rules_panel  the broad pale strip holding body text
    tab          the small raised tab near the bottom-right corner
    artwork      painted into the scene itself
    edge         on the card's outer decorated edge
    other        any other surface

Report EVERY patch, including runes, rune-like scratches, carved script, a signature, a set or
expansion symbol, a collector number and a copyright line. If a surface carries writing twice,
that is two entries. Do not merge writing from two different surfaces into one entry.

SECOND, report bounding boxes as [ymin, xmin, ymax, xmax] normalised 0-1000:

- "title": the plate across the very top, the one the card's name is printed on. Give the plate's
  FULL extent from its left end to its right end, inside its carved rim or riveted border. If a
  branch, chain or creature crosses in FRONT of part of the plate, the plate still runs behind it
  — keep that part IN the box. What must stay OUT is anything past where the plate itself stops.
- "name": the box of the card's NAME as it is lettered on that plate — the printed letters only,
  from the first letter to the last, not the whole plate.
- "type": the narrow strip the type line sits on, FULL extent from its left end to its right end,
  inside its carved rim. If a badge, vine or creature crosses in FRONT of part of it, the strip
  still runs behind — keep that part IN the box.
- "rules": a LIST, one box per pale body-text strip, top to bottom. Give the INNER usable area —
  the flat part the text sits on, inside any rim and clear of anything crossing in front of it."""


NAMED_SCHEMA = {
    "type": "object",
    "properties": {
        **SCHEMA["properties"],
        "name": {**BOX, "description": "[ymin, xmin, ymax, xmax] of the card's name lettering"},
        "text": READ_SCHEMA["properties"]["text"],
    },
}

NAMED_PROMPT = """This is a fantasy trading card. The NAME is lettered into the top object. The type strip, the pale rules strip, and the P/T tab are BLANK — no writing on them.

Two jobs.

FIRST, transcribe. Find every separate patch of writing anywhere on this card and report it in
"text", one entry per patch. For each one give:

- "text": exactly what it says, CHARACTER FOR CHARACTER. Transcribe what is actually printed, not
  what you expect a card like this to say. Do not correct spelling, do not expand abbreviations,
  do not tidy punctuation, and do not fill in a word you cannot read — if a word is obscured or
  illegible, write it as [?]. Keep line breaks out: run each patch together as one line.
- "where": which surface it sits on, one of:
    title_plate  the plate across the very top
    type_strip   the narrow horizontal strip lower down
    rules_panel  the broad pale strip holding body text
    tab          the small raised tab near the bottom-right corner
    artwork      painted into the scene itself
    edge         on the card's outer decorated edge
    other        any other surface

The name on the top object is expected. Still report EVERY other patch — writing on the type
strip, the rules panel, the tab, the edge, or extra words besides the name.

SECOND, report bounding boxes as [ymin, xmin, ymax, xmax] normalised 0-1000:

- "title": the plate across the very top, the one the card's name is lettered on. Give the plate's
  FULL extent from its left end to its right end, inside its carved rim.
- "name": the box of the card's NAME as it is lettered on that plate — the printed letters only,
  from the first letter to the last, not the whole plate.
- "type": the NARROW horizontal strip lower down, directly above the broad slab. It is BLANK.
- "rules": a LIST, one box per pale text strip, top to bottom. These are BLANK.
- "pt": the small raised tab near the BOTTOM-RIGHT, if one is present. It is BLANK.

Then report two kinds of DEFECT:

- "spare": every OTHER blank raised surface not counted above.
- "marks": every patch of painted WRITING that is NOT the card's name on the title plate. Do not
  list the name as a mark. Do list a type line, rules text, a set symbol, runes, a signature.

Give the INNER usable area of each surface. A THIN thing crossing in FRONT of the face does not
clip the box.

The card's outer edge decoration is NOT one of the surfaces. Omit a key if that surface is not
present. Do not guess."""


NAMED_SCHEMA = {
    "type": "object",
    "properties": {
        **SCHEMA["properties"],
        "name": {**BOX, "description": "[ymin, xmin, ymax, xmax] of the card's name lettering"},
        "text": READ_SCHEMA["properties"]["text"],
    },
}

NAMED_PROMPT = """This is a fantasy trading card. The NAME is lettered into the top object. The type strip, the pale rules strip, and the P/T tab are BLANK — no writing on them.

Two jobs.

FIRST, transcribe. Find every separate patch of writing anywhere on this card and report it in
"text", one entry per patch. For each one give:

- "text": exactly what it says, CHARACTER FOR CHARACTER. Transcribe what is actually printed, not
  what you expect a card like this to say. Do not correct spelling, do not expand abbreviations,
  do not tidy punctuation, and do not fill in a word you cannot read — if a word is obscured or
  illegible, write it as [?]. Keep line breaks out: run each patch together as one line.
- "where": which surface it sits on, one of:
    title_plate  the plate across the very top
    type_strip   the narrow horizontal strip lower down
    rules_panel  the broad pale strip holding body text
    tab          the small raised tab near the bottom-right corner
    artwork      painted into the scene itself
    edge         on the card's outer decorated edge
    other        any other surface

The name on the top object is expected. Still report EVERY other patch — writing on the type
strip, the rules panel, the tab, the edge, or extra words besides the name.

SECOND, report bounding boxes as [ymin, xmin, ymax, xmax] normalised 0-1000:

- "title": the plate across the very top, the one the card's name is lettered on. Give the plate's
  FULL extent from its left end to its right end, inside its carved rim.
- "name": the box of the card's NAME as it is lettered on that plate — the printed letters only,
  from the first letter to the last, not the whole plate.
- "type": the NARROW horizontal strip lower down, directly above the broad slab. It is BLANK.
- "rules": a LIST, one box per pale text strip, top to bottom. These are BLANK.
- "pt": the small raised tab near the BOTTOM-RIGHT, if one is present. It is BLANK.

Then report two kinds of DEFECT:

- "spare": every OTHER blank raised surface not counted above.
- "marks": every patch of painted WRITING that is NOT the card's name on the title plate. Do not
  list the name as a mark. Do list a type line, rules text, a set symbol, runes, a signature.

Give the INNER usable area of each surface. A THIN thing crossing in FRONT of the face does not
clip the box.

The card's outer edge decoration is NOT one of the surfaces. Omit a key if that surface is not
present. Do not guess."""


def read_back(png, face):
    """What does this card ACTUALLY say, plus the boxes we still print into.

    THE GATE THE LETTERED MODE CANNOT SHIP WITHOUT. `check.py` opens by saying it deliberately does
    not proofread, because compositing made the wording correct by construction. Let the model
    letter the card and that guarantee is gone, and `CLAUDE.md`'s surviving rule is the one it
    breaks: a card whose printed text differs from Scryfall must never ship silently. Measured over
    25 lettered generations, the existing structural gates passed 23 and were blind to every text
    defect in the batch — runes flanking a type line, a chain obscuring four words of rules text, a
    name clipped by its own plate.

    ONE call, replacing `detect` rather than adding to it, so the mode costs the same two calls a
    composited card does. `detect` cannot be reused: its prompt opens "BLANK raised surfaces and no
    writing on it" and its `marks` list means "any painted lettering", which on a lettered card is
    every surface.

    DELIBERATELY BLIND. The expected strings are NOT in this prompt. Handing the model what the
    card should say and asking whether it says it is how an OCR gate learns to read the hint
    instead of the card — and a gate that agrees with itself is worse than no gate, because it
    ships the same defects wearing a pass. Every comparison happens in `check.proofread`, in
    Python, against Scryfall.
    """
    contents = [types.Part.from_bytes(data=png, mime_type="image/png"), READ_PROMPT]
    response = gemini.client().models.generate_content(
        model=MODEL,
        contents=contents,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=READ_SCHEMA,
            temperature=0,
        ),
    )
    raw = json.loads(response.text or "{}")

    read = {"text": [
        {"where": patch.get("where") or "other", "text": patch.get("text") or ""}
        for patch in (raw.get("text") or [])
        if (patch.get("text") or "").strip()
    ]}
    for key in ("title", "name", "type"):
        box = _usable(raw.get(key))
        if box:
            read[key] = box
    rules = [box for box in map(_usable, raw.get("rules") or []) if box]
    if rules:
        read["rules"] = sorted(rules, key=lambda box: box[1])
    return read


def _overlap_share(inner, outer):
    """How much of `inner` sits inside `outer`, 0-1. Boxes are (x0, y0, x1, y1)."""
    x0 = max(inner[0], outer[0])
    y0 = max(inner[1], outer[1])
    x1 = min(inner[2], outer[2])
    y1 = min(inner[3], outer[3])
    if x1 <= x0 or y1 <= y0:
        return 0.0
    area = (inner[2] - inner[0]) * (inner[3] - inner[1])
    return 0.0 if area <= 0 else ((x1 - x0) * (y1 - y0)) / area


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


# A mark in the P/T corner is dropped only if it is THE TAB, not something painted ON the tab.
# Below this share of the tab's own area it is ink, not the object.
#
# CLIENT 2026-08-16, on a staged Craterhoof: "that too blank without any symbol in it, craterhoof
# has spiral in it" — the model carved a spiral into the P/T tab and we printed 5/5 straight over
# it. The brief already bans it by name ("no ... sigil, rune-circle, SPIRAL or logo at either end
# of any surface"), the detector's "marks" list is exactly the mechanism for catching it, and
# `_in_pt_corner` threw it away, because that filter exists to drop the BLANK tab which the
# detector kept reporting as a mark (4 of 4 runs, 2026-08-13).
#
# The two are easy to tell apart once you ask the right question. The false positive IS the tab —
# same box, same size. A spiral is a small thing well inside it. So the filter now compares the
# mark against the tab we detected rather than against a region of the card.
PT_MARK_SHARE = 0.55


def _is_the_pt_tab(mark, tab):
    """True if this mark is just the blank tab being reported again.

    Falls back to the old region test when no tab was detected: with nothing to compare against,
    dropping the mark is the behaviour this filter has had since 2026-08-13, and a false repaint
    is worse than a missed spiral on the one card in ten where detection misses the tab entirely.
    """
    if not tab:
        return _in_pt_corner(mark)
    area = (mark[2] - mark[0]) * (mark[3] - mark[1])
    tab_area = (tab[2] - tab[0]) * (tab[3] - tab[1])
    return tab_area > 0 and area >= tab_area * PT_MARK_SHARE


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


def detect(png, paragraphs=None, expect_pt=False, named=False):
    """{'title': box, 'rules': [box, ...], ...} in 0-1 fractions of the canvas.

    Fractions rather than pixels so the result survives the print-resolution upscale, and so a
    stored detection stays valid if the canvas size ever changes.

    `rules` is always a list, because the reference site paints one pale strip per ability rather
    than one slab (see SCHEMA). `paragraphs` is how many abilities Scryfall says the card has —
    a hint, not a constraint, because the model paints what it paints and the compositor already
    packs leftovers into the last strip.

    `spare` and `marks` are the two FAULTS, also lists: extra blank surfaces nothing will be
    printed on, and painted lettering or insignia. `generation.check` turns them into a repaint.

    `named=True` is the product hybrid: the top object already has the name lettered into it.
    The blank-furniture prompt would report that name as `marks` and miss the title. This keeps
    one vision call — it adds the name box and a transcription, it does not call `read_back`.
    """
    prompt = NAMED_PROMPT if named else PROMPT
    schema = NAMED_SCHEMA if named else SCHEMA
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
            response_schema=schema,
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
            # Only the tab itself is dropped now, never something painted on it (the client's
            # spiral, 2026-08-16). `panels["pt"]` is already set: SINGLE is walked above.
            boxes = [
                box
                for box in boxes
                if not (_in_pt_corner(box) and _is_the_pt_tab(box, panels.get("pt")))
            ]
        if boxes:
            panels[key] = sorted(boxes, key=lambda box: box[1])

    # The enlarged corner OUTRANKS the full-card answer for this one surface: both look at the
    # same shield, and one of them can actually see it. When the corner finds nothing the
    # full-card `pt` still stands, so this can only add a detection, never lose one.
    detail = _usable(raw.get("pt_detail"))
    if detail:
        panels["pt"] = _from_crop(detail)
    if named:
        name = _usable(raw.get("name"))
        if name:
            panels["name"] = name
            # The name is expected writing on the title. `inspect` treats marks ON a plate as
            # painted_marks, so a name reported as a mark would fail every hybrid card.
            overlap = []
            for mark in panels.get("marks") or []:
                if _overlap_share(mark, name) < 0.5:
                    overlap.append(mark)
            if overlap:
                panels["marks"] = overlap
            elif "marks" in panels:
                del panels["marks"]
        panels["text"] = [
            {"where": patch.get("where") or "other", "text": patch.get("text") or ""}
            for patch in (raw.get("text") or [])
            if (patch.get("text") or "").strip()
        ]
    return panels
