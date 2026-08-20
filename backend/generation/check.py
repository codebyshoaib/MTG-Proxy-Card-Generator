"""Is this card structurally sound, or should the art be regenerated?

WHAT THIS IS NOT — for the COMPOSITED mode. `HANDOVER-2026-08-09.md` describes a `check.py` that
grades the card's printed TEXT field by field against Scryfall, because at that point the model
was lettering the card itself and a fabricated subtype in the right font was invisible. On the
composited path that is still unnecessary: we set Scryfall's own text (`cards.compositor`), so the
wording is correct by construction. What can still be wrong there is the FURNITURE the model
painted, and that is what `inspect`, `contrast`, `matted` and `colour_identity` grade.

`proofread` IS that text grader, brought back for the lettered mode where the model letters every
field but the cost. Nothing else in this module changed: the two modes differ in which guarantee
they buy by construction and which one has to be measured. The one lettered-only exception is
`type_end_mark`: a set symbol is a graphic, not words, so comparing transcriptions cannot see it.

Every check here fired on a real card during the 2026-08-10/11 batches, and each one is something
a human eye caught only because someone was looking:

- Terror of the Peaks and Raphael came back with the name plate halfway down the card. Detection
  succeeds, compositing succeeds, and the card is simply wrong.
- Sol Ring came back with no name plate at all, so its name went unprinted.
- Several cards came back with a slab too small for their text, which `compositor` already
  reports but nothing acted on.

The cost model is what makes this worth having. A regeneration is one credit; a structurally
broken card that reaches a customer is a refund and a reputation. Measured across the eight-card
batch and the runs after it, roughly one card in five needs a second attempt — so a single
automatic retry is the right shape, and a second would mostly burn credits on cards that are
going to keep failing.
"""

import unicodedata
from typing import NamedTuple

from PIL import ImageStat

from cards import compositor


class Problem(NamedTuple):
    """One structural fault, with a code a caller can branch on."""

    code: str
    detail: str


# A plate this far down the card is not a title plate, whatever the detector called it. The ten
# reference-site generations of one card put it at the top on 10 of 10 while everything else about
# the layout moved, so the order is the one thing safe to assert.
TITLE_MAX_Y = 0.25

TYPE_MIN_WIDTH = 0.45
"""Share of the card the type plate must span before the type line can be set on it.

MEASURED 2026-08-17 across all 45 composited faces the project has stored. Phyrexian Obliterator,
job 60265c75 and card 05 of the sign-off pack, came back with the narrow strip painted as THREE
riveted segments in a row instead of one bar. `panels.detect` reported the leftmost segment, so
`Creature - Phyrexian Horror` was set at roughly a third of its proper size, tucked into the left
third, with two empty metal segments beside it. It graded SOUND on every gate: `TYPE_SIZE` is a
fraction of the detected box HEIGHT and the segment is the right height — it is the WIDTH that is
wrong, and nothing read the type plate's width against the card.

    0.253  Phyrexian Obliterator  60265c75   <- the segmented bar
    0.562  Elesh Norn             82157ad6
    0.716  Phyrexian Obliterator  50bc4beb
    0.736 ... 0.804 median ... 0.911         everything else

Two populations with a 2.2x gap and one member below it, so the floor sits in the gap rather than
at a number chosen for looking round. This is a GATE on the symptom, not the cure: the brief
already forbids splitting a surface into a row of smaller ones, twice over, and the model did it
anyway (bd mtg-atl). Reporting a row of segments as `spare` at detection time is the fix that
fires on the cause; this is what stops one shipping in the meantime.
"""

TITLE_MIN_WIDTH = 0.60
"""Share of the card the title plate must span before the name can be set on it.

The same gate as `TYPE_MIN_WIDTH` on the plate above it, and it exists for the same reason one
step further on. Sizing the name off the CARD instead of off the plate's height (2026-08-17, bd
mtg-6bb) took the spread out of every card whose name fits its plate — Sol Ring 1.48x -> 1.00x,
Terror of the Peaks 1.24x -> 1.00x over repeat generations of the identical string. What it could
not touch is a name too long for the plate it was given, because the fit-to-width loop then steps
the size back down, and the plate's WIDTH is as stochastic as its height was.

MEASURED 2026-08-17 over all 58 stored faces that kept their title box:

    0.517  Craterhoof Behemoth  bf4f16ac   <- name crushed to 0.0267 of card height
    0.681  Tree of Tales        7a7b2dc0      printed at full size
    0.729 ... 0.804 median ... 0.880          everything else, all at full size

One card, one plate, and it is the only face in 58 the loop had to cut by a third. The floor sits
between it and the narrowest plate that printed correctly. A card that trips it is one the model
painted a stunted name plate on, which is a repaint — not a name set small enough to fit it.
"""


def _strips(rules):
    """`rules` as a list of boxes, whether it arrived as one box or several.

    `cards.compositor._rules_panels` does the same normalisation for drawing. It matters twice
    here: the topmost strip is what has to clear the type plate, and the COUNT is what says whether
    a strip was painted that nothing will be printed on — and a bare 4-tuple counts as four strips
    if it is not unwrapped first.
    """
    if not rules:
        return []
    if all(isinstance(value, (int, float)) for value in rules):
        return [tuple(rules)]
    return [tuple(box) for box in rules]


def inspect(face, panels, overflowed):
    """Faults in a composited card, worst first. Empty means it is fit to ship.

    `panels` is `generation.panels.detect`'s output and `overflowed` is the second value from
    `cards.compositor.compose`, so this adds no AI call and no cost — it grades what the pipeline
    already knows.
    """
    problems = []

    for key, why in (
        ("title", "the card's name has nowhere to print"),
        ("type", "the type line has nowhere to print"),
        ("rules", "the rules text has nowhere to print"),
    ):
        if not panels.get(key):
            problems.append(Problem(f"missing_{key}", f"no {key} surface was painted — {why}"))

    if face.get("power") is not None and not panels.get("pt"):
        problems.append(
            Problem("missing_pt", "a creature with no power/toughness surface — P/T is unprinted")
        )

    title = panels.get("title")
    if title and title[1] > TITLE_MAX_Y:
        problems.append(
            Problem(
                "title_out_of_order",
                f"the name plate is at y={title[1]:.2f}, not at the top of the card",
            )
        )

    # Order, not just position: a type plate above the title reads as a card assembled wrong even
    # when both are in the upper half.
    strips = _strips(panels.get("rules"))
    top_rule = min((strip[1] for strip in strips), default=None)
    type_panel = panels.get("type")
    if title and type_panel and type_panel[1] < title[1]:
        problems.append(Problem("type_above_title", "the type plate sits above the name plate"))
    if type_panel and top_rule is not None and top_rule < type_panel[1]:
        problems.append(Problem("rules_above_type", "the rules panel sits above the type plate"))

    if title and title[2] - title[0] < TITLE_MIN_WIDTH:
        problems.append(
            Problem(
                "title_too_narrow",
                f"the name plate is only {title[2] - title[0]:.0%} of the card wide — the name has "
                "to be set small to fit it, so this card's title would not match the rest of a deck",
            )
        )

    if type_panel and type_panel[2] - type_panel[0] < TYPE_MIN_WIDTH:
        problems.append(
            Problem(
                "type_too_narrow",
                f"the type plate is only {type_panel[2] - type_panel[0]:.0%} of the card wide — "
                "the strip was painted as a row of segments, so the type line is set small in one "
                "of them with the rest left bare",
            )
        )

    if overflowed:
        problems.append(
            Problem(
                "text_too_small",
                "the rules text does not fit its panel at a size readable across a table",
            )
        )

    # CLIENT 2026-08-13, circling the second dark strip under Raphael's type line: "on one of them
    # it has 2 creature type text boxes, here it looks kind of natural but i have seen these as
    # errors many times".
    #
    # A painted surface with nothing printed on it is the defect, and it arrives two ways. Either
    # the detector calls the extra one `spare`, or it lists it among the pale `rules` strips and the
    # compositor prints into only as many as the card has paragraphs (`compositor._rules`, which
    # slices `boxes[: len(paragraphs)]`) — so on that path the surplus is silently left bare. Both
    # are the same fault to a customer, so both carry the same code.
    #
    # There is a THIRD way in, and it is the one that shipped. MEASURED 2026-08-17 over all 75
    # stored faces: Sol Ring, card 03 of the sign-off pack, has an empty metal SHIELD painted at
    # bottom-right. It is an artifact, so the compositor correctly prints nothing into it and the
    # shield goes out blank. `detect` did not miss it — job 40c627d1 reports a `pt` box on a face
    # with no power, and `problems` came back empty. 2 of 2: both Creative Full runs of the only
    # non-creature ever composited through the UI did this, and both graded clean.
    #
    # Nothing fired because a `pt` box is never a candidate to be spare — the detector's job is to
    # FIND the shield, not to ask whether the card is entitled to one. That entitlement is free:
    # the face already carries `power`, which `missing_pt` above reads for the mirror case.
    blank = len(panels.get("spare") or [])
    if face.get("power") is None and panels.get("pt"):
        blank += 1
    paragraphs = len([p for p in (face.get("oracle_text") or "").split("\n") if p.strip()])
    blank += max(0, len(strips) - max(1, paragraphs))
    if blank:
        problems.append(
            Problem(
                "blank_surface",
                f"{blank} painted surface(s) more than this card has anything to print in — an "
                "empty second bar reads as a printing error, which is how the client reported it",
            )
        )

    # CLIENT 2026-08-13 on set symbols: "these are proxies that dont have a set so its just a
    # random symbol and actually sometimes ive seen it put a real symbol on the card which isnt
    # good". The brief has banned painted writing since the first Creative Full card and Raphael
    # still came back with a band of runes, so the ban is not enough on its own: anything the
    # model letters or stamps collides with the text we print, and a REAL expansion symbol is a
    # Wizards mark on a proxy. Neither may ship on the strength of a prompt alone.
    #
    # Graded by WHERE it lands, not by whether it exists. Presence alone over-rejects twice over:
    # a mark under a plate we print into is covered by our own text and never reaches the
    # customer, and a card whose subject is magic — Delver of Secrets, measured, twice — carries
    # arcane script in its artwork as a matter of illustration. Both failed the whole card and
    # bought a repaint that changed nothing.
    #
    # What is still a defect is writing that imitates card furniture: it sits ON or AGAINST a
    # plate, or it runs as a long flat line the way a type line does. That is the shape the
    # client circled, and a real expansion symbol arrives the same way, at the type line's end.
    offenders = _offending_marks(panels)
    if offenders:
        problems.append(
            Problem(
                "painted_marks",
                f"{len(offenders)} patch(es) of painted lettering, runes or insignia on or "
                "against the printed surfaces — fake card text or a set symbol on a card that "
                "has no set",
            )
        )
    return problems


_PUNCTUATION = {
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", "−": "-", "‐": "-", "‑": "-",
    "•": "-", " ": " ",
}
"""Differences between what Scryfall stores and what a transcription plausibly returns.

Each entry is a distinction the read-back CANNOT reliably make — an em dash and a hyphen are two
strokes of ink at body-text size — so grading on it buys false repaints and no correctness. Every
distinction that survives normalisation is one a reader would notice: a wrong word, a missing
clause, a fabricated subtype.
"""


def _normalised(text):
    """A printed string reduced to what is worth comparing.

    Braces go because the card draws `{T}` as a tap symbol and a transcription may or may not put
    them back; case goes because a card lettered in small caps is a styling choice and not a text
    error. Whitespace collapses so that a panel transcribed as one patch and the same panel
    transcribed as three both compare equal to Scryfall's newline-separated paragraphs.
    """
    text = unicodedata.normalize("NFKC", text or "")
    for printed, stored in _PUNCTUATION.items():
        text = text.replace(printed, stored)
    return " ".join(text.replace("{", "").replace("}", "").split()).casefold()


def _expected(face):
    """(surface, what it must say, what to call it) for every surface the model lettered.

    The mana cost is absent on purpose — it is stamped by `compositor._cost` from our own vendored
    artwork and was never the model's to get wrong. See `prompts._lettering_block`.
    """
    tab = ""
    if face.get("power") is not None:
        tab = f"{face['power']}/{face['toughness']}"
    elif face.get("loyalty") is not None:
        tab = str(face["loyalty"])
    return (
        ("title_plate", face.get("name") or "", "the card's name"),
        ("type_strip", face.get("type_line") or "", "the type line"),
        ("rules_panel", face.get("oracle_text") or "", "the rules text"),
        ("tab", tab, "the power/toughness" if face.get("power") is not None else "the loyalty"),
    )


def _quote(text, limit=90):
    return repr(text if len(text) <= limit else text[: limit - 1] + "…")


def proofread(face, read, only=None):
    """Does this lettered card say what Scryfall says? Worst first, empty means it does.

    THE RULE THIS EXISTS FOR is the one `CLAUDE.md` says survived everything else: a card whose
    printed text differs from Scryfall must never ship silently. Compositing used to guarantee it
    by construction, which is why the module docstring above says there is nothing to proofread.
    In the lettered mode there is: the model sets every field but the cost, and a fabricated
    subtype in the right font is invisible to every structural gate here. Measured over 25
    generations, those gates passed 23 and caught none of the text defects in the batch.

    `read` is `panels.read_back`'s output. NOTHING in this comparison happens in the model: it
    transcribes blind and Python does every alignment, because a gate handed the answer grades the
    hint rather than the card.

    Writing painted into the ARTWORK is not graded, on the same evidence `_offending_marks` was
    narrowed on: Delver of Secrets came back twice with arcane script in its scene, which is
    illustration and not card text. What is graded is every surface a reader takes for card text.

    `only` limits which surfaces we authored by painting — the product hybrid (`name_lettered`)
    paints the name and stamps the rest, so only `title_plate` is graded as ours-to-match.
    Writing on a surface we stamp is `text_extra`: it will collide with Scryfall type.
    """
    problems = []
    patches = read.get("text") or []
    surfaces = {}
    for patch in patches:
        surfaces.setdefault(patch.get("where") or "other", []).append(patch.get("text") or "")

    # No title plate is a structural fault before it is a text one: it is where the mana cost gets
    # stamped, so the card ships with no cost at all rather than a wrong one.
    if not read.get("title"):
        problems.append(
            Problem(
                "missing_title",
                "no plate was painted across the top of the card — the card's mana cost has "
                "nowhere to be stamped and would ship missing entirely",
            )
        )

    graded = set()
    fields = _expected(face)
    if only is not None:
        fields = tuple(field for field in fields if field[0] in only)
    for where, expected, what in fields:
        graded.add(where)
        printed = " ".join(surfaces.get(where) or [])
        if not expected:
            # A surface the card has no text for, carrying text anyway: a sorcery with a P/T tab
            # lettered, a vanilla creature with a rules panel filled in. Invented, by definition.
            if printed.strip():
                problems.append(
                    Problem(
                        "text_extra",
                        f"the {where.replace('_', ' ')} carries {_quote(printed)}, and this card "
                        "has no such field — it was invented. Leave that surface bare",
                    )
                )
            continue
        if not printed.strip():
            problems.append(
                Problem(
                    "text_missing",
                    f"{what} is not printed anywhere on the card. It must read {_quote(expected)}",
                )
            )
        elif _normalised(printed) != _normalised(expected):
            problems.append(
                Problem(
                    "text_wrong",
                    f"{what} reads {_quote(printed)} and must read {_quote(expected)} exactly, "
                    "character for character, with nothing added, dropped or obscured",
                )
            )

    # Everything left: writing on a surface no field belongs on, or off the surfaces entirely.
    # Runes flanking a type line and a set symbol on a card with no set both arrive here, and both
    # are what the client reported. `artwork` is excluded above, in the docstring's terms.
    loose = [
        text
        for where, texts in surfaces.items()
        if where not in graded and where != "artwork"
        for text in texts
        if text.strip()
    ]
    if loose:
        problems.append(
            Problem(
                "text_extra",
                f"{len(loose)} patch(es) of writing that are not this card's text: "
                + "; ".join(_quote(text, 40) for text in loose[:4])
                + ". A proxy has no set symbol, no collector number and no artist credit, and "
                "carved runes beside a real line of text read as a printing error",
            )
        )
    return problems


COST_GAP = 0.01
"""Clear space between the name's last letter and the cost's first pip, as a share of the card.

Below this they read as one run of marks rather than two fields. The reference site's own cards
sit at 0.02-0.05; this is the floor, not the target — the target is stated to the model by
`prompts._cost_room` and this only catches the cards that ignored it.
"""


def cost_collides(face, read):
    """The mana cost about to be stamped over the card's own name, or None.

    MEASURED on the first live lettered run, 2026-08-17. `Progenitus` had a dragon's head crossing
    the right half of its title plate; `read_back` reported the plate as the unobstructed left half
    only, x 0.09-0.56; the ten pips were right-aligned to 0.56 and landed squarely on the word
    "Progenitus". The read-back had already passed the card — it transcribed the name before the
    pips existed — so no text gate could ever see this. It is the worst defect this mode can ship
    and it arrived on the first card, which is why it is gated rather than prompted away.

    The prompt was fixed too (`panels.READ_PROMPT` now asks for the plate's full extent, crossings
    included). This is the guarantee under it: a plate box that is wrong in the other direction, or
    a name lettered further right than the brief asked, arrives here instead of at a customer.
    """
    title, name = read.get("title"), read.get("name")
    if not title or not name or not (face.get("mana_cost") or "").strip():
        return None
    # Both are (x0, y0, x1, y1). The cost is right-aligned inside the plate, so its left edge is
    # the plate's right end less what the pips take.
    starts_at = title[2] - compositor.cost_width(face, title, name)
    if starts_at >= name[2] + COST_GAP:
        return None
    return Problem(
        "cost_no_room",
        f"the name runs to {name[2]:.2f} across the card and the mana cost has to start at "
        f"{starts_at:.2f} to fit the plate — the cost would be stamped on top of the name. Paint "
        "the name shorter so it stops before the reserved end. That end is the same stone, wood "
        "or metal as the rest of the name object — not a second box, not a pale cutout.",
    )


def cost_off_rim(image, face, read):
    """The inner face of the title plate is too short for this cost, or None.

    CLIENT-PACK 2026-08-19: `_cost` shrank to the floor and stamped onto the bevel when
    `_plate_face_right` had treated the outer frame as face. `cost_collides` cannot see this —
    it only compares name-box to plate-box fractions, with no pixels. Graded on the BLANK,
    before the stamp, same as `obstructed`.
    """
    title = read.get("title")
    if not title or not (face.get("mana_cost") or "").strip():
        return None
    box = compositor._box(title, image.size)
    name = compositor._box(read["name"], image.size) if read.get("name") else None
    if compositor.cost_fits(image, face, box, name):
        return None
    return Problem(
        "cost_no_room",
        "the inner face of the title plate is too short for this mana cost — the last pip "
        "would sit on the rim. Stop the name sooner so the reserved end of the name object "
        "is the same material as the rest of it, empty of letters, not a second box.",
    )


# SIGNOFF 2026-08-19, Elesh Norn, lettered. The type line transcribed as
# "Legendary Creature — Phyrexian Praetor" and graded clean. A red Phyrexian phi sat in the
# set-symbol slot. `proofread` never saw it: the mark is a graphic, and `read_back` is blind on
# purpose (a yes/no "is there a set symbol" grades the hint). `detect`'s `marks` list cannot be
# reused — on a lettered card every surface has writing. So the slot is graded in Python, on the
# pixels, the same way `cost_collides` grades a collision the transcription cannot see.
#
# MEASURED on that card's type strip (inner face, deviation-from-plate-median mask):
#
#     phi     cx 0.92  aspect 1.54  height 0.82 of the strip  fill 0.18
#     letters cx 0.43  aspect 56      height 0.10               fill 0.98
#
# and on Craterhoof's wrapping vine in the same slot, which must not fire:
#
#     vine    cx 0.83  aspect 1.33  height 0.74 of the strip  fill 0.08
#
# The gap is fill, not position: a badge is a compact body of ink, a vine is a sparse crossing.
# Thresholds sit in those gaps. A box that is not returned is not guessed at — same rule as
# `cost_collides` and `panels._usable`.
TYPE_END_MIN_CX = 0.80
TYPE_END_MIN_HFILL = 0.55
TYPE_END_MIN_ASPECT = 0.40
TYPE_END_MAX_ASPECT = 2.2
TYPE_END_MIN_FILL = 0.12
TYPE_END_MIN_SHARE = 0.010


def type_end_mark(card, read):
    """A painted badge in the type line's set-symbol slot, or None.

    The brief already forbids this, twice, and Elesh Norn still grew one. The retry is what
    makes the ban real: this code is the one that asks again.
    """
    strip = read.get("type")
    if not strip:
        return None
    box = compositor._box(strip, card.size)
    width, height = box[2] - box[0], box[3] - box[1]
    if width < 24 or height < 12:
        return None
    mask = _plate_ink(card, box)
    area = width * height
    for mass, x0, y0, x1, y1 in _islands(mask):
        bw, bh = x1 - x0, y1 - y0
        if bh <= 0 or bw <= 0:
            continue
        cx = (x0 + x1) / 2 / width
        aspect = bw / bh
        fill = mass / (bw * bh)
        if (
            cx >= TYPE_END_MIN_CX
            and bh / height >= TYPE_END_MIN_HFILL
            and TYPE_END_MIN_ASPECT <= aspect <= TYPE_END_MAX_ASPECT
            and fill >= TYPE_END_MIN_FILL
            and mass / area >= TYPE_END_MIN_SHARE
        ):
            return Problem(
                "painted_marks",
                "the right-hand end of the type line carries a painted badge or set mark — a "
                "proxy has no set, so that slot stays empty. Paint the type line's words alone, "
                "left-aligned, and leave the right-hand end of the narrow strip bare",
            )
    return None


def _plate_ink(image, box):
    """Binary mask of ink sitting on this plate: letters, badges, anything off the material.

    Both directions, because gold on a dark strip and a red phi on the same strip are both
    'not the plate', and `crossing_mask` only sees things brighter than a quiet dark surface —
    it returned empty on Elesh's type line. The threshold sits on the plate's own spread so a
    grainy Sol Ring does not become one giant component of noise.
    """
    grey = image.crop(box).convert("L")
    values = sorted(grey.getdata())
    if not values:
        return grey.point(lambda _: 0)
    median = values[len(values) // 2]
    spread = sorted(abs(value - median) for value in values)[len(values) // 2]
    thresh = max(18, spread * 3)
    return grey.point(lambda v: 255 if abs(v - median) >= thresh else 0)


def _islands(mask, ink=40):
    """Connected components of ink, as (mass, x0, y0, x1, y1) in the mask's pixels, largest first."""
    width, height = mask.size
    pixels = mask.load()
    seen = [[False] * width for _ in range(height)]
    found = []
    for y in range(height):
        for x in range(width):
            if seen[y][x] or pixels[x, y] <= ink:
                continue
            stack = [(x, y)]
            seen[y][x] = True
            min_x = max_x = x
            min_y = max_y = y
            mass = 0
            while stack:
                cx, cy = stack.pop()
                mass += 1
                min_x, max_x = min(min_x, cx), max(max_x, cx)
                min_y, max_y = min(min_y, cy), max(max_y, cy)
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = cx + dx, cy + dy
                    if (
                        0 <= nx < width and 0 <= ny < height
                        and not seen[ny][nx] and pixels[nx, ny] > ink
                    ):
                        seen[ny][nx] = True
                        stack.append((nx, ny))
            found.append((mass, min_x, min_y, max_x + 1, max_y + 1))
    found.sort(reverse=True)
    return found


NEAR = 0.015
"""How close to a plate a mark may sit, as a share of the card, before it reads as part of it."""

BANNER = (0.35, 3.0)
"""Width share and aspect above which a mark is a line of writing wherever it sits.

A band of runes across open art is still fabricated text if it is shaped like a line of it —
that is how Raphael came back, and it is the shape a type line has.
"""


def _area(box):
    return max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])


def _inside(mark, surface):
    """Share of `mark` that lies within `surface`."""
    overlap = (
        max(mark[0], surface[0]),
        max(mark[1], surface[1]),
        min(mark[2], surface[2]),
        min(mark[3], surface[3]),
    )
    return _area(overlap) / _area(mark) if _area(mark) else 0.0


def _grown(box, by=NEAR):
    return (box[0] - by, box[1] - by, box[2] + by, box[3] + by)


def _printed(panels):
    """Every surface we print our own text into — the ones a mark can hide under or imitate."""
    from generation.panels import SINGLE

    surfaces = [panels[key] for key in SINGLE if panels.get(key)]
    return surfaces + _strips(panels.get("rules"))


def _offending_marks(panels):
    """The marks that read as card text rather than as illustration.

    Boxes are (x0, y0, x1, y1) normalised, the convention `panels.detect` returns.

    Being ON a plate is enough on its own — a mark there is either writing imitating the field or
    a set symbol at the type line's right end, and our own printed text does not cover the whole
    plate, which is exactly how the client saw the set symbol he reported. What is NOT a defect is
    script out in the artwork: on a card about arcane writing that is the illustration, and
    failing it bought a repaint that came back with the same thing.
    """
    surfaces = _printed(panels)
    offenders = []
    for mark in _strips(panels.get("marks")):
        width, height = mark[2] - mark[0], mark[3] - mark[1]
        line_shaped = width >= BANNER[0] and height > 0 and width / height >= BANNER[1]
        if line_shaped or any(_inside(mark, _grown(surface)) > 0 for surface in surfaces):
            offenders.append(mark)
    return offenders


CONTRAST_MIN = 5.0
"""Contrast ratio the rules panel must give the near-black text printed on it.

MEASURED on the eight-card Ice batch, job 10746c0b (2026-08-15) — the first time anyone ran bd
mtg-cjx's acceptance test, which is to look at a finished card at arm's length and try to read it:

    Elesh Norn 12.3   Sol Ring 11.1   Swords 10.7   Vampiric Tutor 9.9   Counterspell 9.4
    Giant Growth 5.0        Lightning Bolt 4.5        Terror of the Peaks 3.6

All eight graded SOUND. The five above 9 are readable across a table; Terror and Bolt are not,
and Giant Growth is borderline. So the structural checks were passing cards whose rules text
cannot be read, which is the one defect that makes a proxy useless at the thing it is for.

The split is clean and it has a cause: the brief's list of LIGHT materials for the broad strip
includes "glowing amber stone", the only mid-value entry among cream parchment, bleached bone and
aged ivory. On a red or green card the model reaches for the amber because it matches the scene,
and the slab lands near L=110-133 instead of 185-210. The wording is fixed alongside this, but a
prompt is a request and this is a measurement — the same reason `matted` exists.

5.0 sits in the gap between the two clusters rather than at a standards number. WCAG's 4.5 is for
a backlit screen at reading distance; a printed card read across a table is a harder case, and
the measured cards either clear 9 or fail. Anything landing between is worth a repaint.
"""


def _luminance(value):
    """sRGB channel 0-255 to its linear contribution, per WCAG."""
    channel = value / 255
    return channel / 12.92 if channel <= 0.03928 else ((channel + 0.055) / 1.055) ** 2.4


def contrast(card, panels, ink=20):
    """The rules panel too dark for the text printed on it, or None.

    `ink` is the near-black the compositor prints at. Measured on the panel the DETECTOR reported
    rather than on the whole card, so a dark scene around a pale slab does not fail a good card.
    """
    strips = _strips(panels.get("rules"))
    if not strips:
        return None  # `missing_rules` already covers this; two codes for one fault helps nobody.
    grey = card.convert("L")
    width, height = grey.size
    worst = None
    for strip in strips:
        box = (
            int(strip[0] * width), int(strip[1] * height),
            int(strip[2] * width), int(strip[3] * height),
        )
        if box[2] <= box[0] or box[3] <= box[1]:
            continue
        pixels = grey.crop(box).getdata()
        mean = sum(pixels) / len(pixels)
        ratio = (_luminance(mean) + 0.05) / (_luminance(ink) + 0.05)
        worst = ratio if worst is None else min(worst, ratio)
    if worst is None or worst >= CONTRAST_MIN:
        return None
    return Problem(
        "panel_too_dark",
        # Two decimals because one rounds a card sitting just under the floor to the floor itself,
        # and "only 5.0:1, below 5.0:1" reads as a broken check rather than a near miss.
        f"the rules panel gives its text only {worst:.2f}:1 contrast — below {CONTRAST_MIN}:1 the "
        "text stops being readable at arm's length, which is what a proxy is for",
    )


OBSTRUCTION_MAX = 0.05
"""Share of the rules panel's interior that may be painted OVER before the art is repainted.

MEASURED 2026-08-19 night on COMPOSITED-OBJECT. At 0.15 the gate shipped unreadable rules —
Thirsting Roots and Triumph have vines and a dragon through the words. His crops: the TEXT BAND
has to stay readable. 0.05 over-fires on a corner vine; that costs a repaint. 0.15 ships a card
nobody can play. Repaint is the cheaper mistake.

A thin vine on a CORNER can still pass. A mass through "Proliferate" cannot.
"""


def obstructed(blank, panels, face=None):
    """Something painted across the words the rules panel has to carry, or None.

    Graded on the BLANK and not the composited card, for the same reason `overflowed` is: it is a
    fault in what the model painted, and the remedy is to repaint the art rather than anything the
    compositor can do. `cards.compositor._occlude` makes the crossing pass in front of the text
    instead of behind it, which is what stops a mild one reading as a sticker — this is what refuses
    the ones too heavy for that to save.

    `face` is accepted and unused: the text-band measurement it was added for is reverted above, and
    the parameter is kept so the pipeline call site does not have to churn again when that is
    finished properly.
    """
    strips = _strips(panels.get("rules"))
    if not strips:
        return None  # `missing_rules` already covers this.
    width, height = blank.size
    worst = None
    for strip in strips:
        box = (
            int(strip[0] * width), int(strip[1] * height),
            int(strip[2] * width), int(strip[3] * height),
        )
        surface = blank.crop(box)
        if surface.width < 8 or surface.height < 8:
            continue
        if compositor.surface_is_dark(surface, (0, 0) + surface.size):
            continue  # `foreground_mask` is for light surfaces only; see its docstring.
        inset_x = round(surface.width * compositor.RULES_PAD)
        inset_y = round(surface.height * compositor.RULES_PAD)
        region = surface.crop(
            (inset_x, inset_y, surface.width - inset_x, surface.height - inset_y)
        )
        if region.width < 8 or region.height < 8:
            continue
        mask = compositor.foreground_mask(region)
        mass = ImageStat.Stat(mask).mean[0] / 255
        worst = mass if worst is None else max(worst, mass)
    if worst is None or worst <= OBSTRUCTION_MAX:
        return None
    return Problem(
        "panel_obstructed",
        f"{worst:.1%} of the rules panel is painted over — keep vines, branches, chains and the "
        "subject OFF the TEXT BAND so the rules can be read across a table. A crossing may hook a "
        "rim or a corner; it may not run through the words",
    )


def matted(card):
    """A mat the trim could not cut, or None.

    `bleed.trim` removes an even margin before the card is composited, so anything still here is
    a margin it refused to touch — deeper than `bleed.MAX_DEPTH`, or on three sides rather than
    four, where cropping would slide the art off centre. Either way the client circled this exact
    defect on 2026-08-13, so it is reported rather than shipped.
    """
    from generation import bleed

    share = bleed.matted_share(card.convert("RGB"))
    if share < bleed.MATTED:
        return None
    return Problem(
        "matted",
        f"{share:.0%} of the card's edge is one flat colour — a border on a card asked to run "
        "full bleed",
    )


# COLOUR IDENTITY, graded against Scryfall and never against the user's UI selections.
#
# CLAUDE.md calls this correctness, not preference: "Colour identity comes from Scryfall
# `color_identity`, never from the art style. Purple reads as black mana in MTG's visual language,
# so a style palette that injects purple into a mono-green card misstates the card's colour
# identity. This is a bug the client reported, not a preference."
#
# Until now that rule lived only in the brief. `prompts._palette` and `_palette_clause` argue for
# it and NOTHING measured the result, which is exactly why bd mtg-5pb is intermittent — `ice` on
# a mono-red Lightning Bolt came back blue-white on one run and red on a rerun with identical
# inputs. An argument that wins four times in five is a gate that is not there.
#
# It takes the FINISHED card and the Scryfall face. It deliberately does not take the style,
# direction or palette the user picked: those are the thing being guarded against, so a gate that
# knew about them could be talked out of firing.
#
# MEASURED 2026-08-16 over the six-card VERIFY2 batch, sampling pixels with s>0.30 and v>0.25:
#
#   Craterhoof   G   23% saturated   green 95%
#   Tower Winder G   47% saturated   green 72%
#   Raphael      R   39% saturated   red   88%
#   Terror       R   51% saturated   red   89%
#   Elesh Norn   W    7% saturated   (red 78% of a very small share — her cloak)
#   Sol Ring     C    1% saturated
#
# Two populations, and they need two different rules. A card with a hue carries it at 23-51% of
# the frame and the dominant bucket is its own colour at 72-95%. White and colourless have NO hue,
# so for them the signal is the absence of one — 1% and 7% — and asking "is the dominant hue
# correct" of a card with no hue would fail every one of them on whatever scrap of colour it has.
NEUTRAL_SHARE = 0.15
"""Below this share of saturated pixels the card is making no colour claim at all.

Sits in the gap between the hueless cards (1%, 7%) and the coloured ones (23-51%)."""

DOMINANT_SHARE = 0.60
"""Share of the saturated pixels one bucket needs before we call it the card's colour.

Every correct card in the batch ran 72-95%, so this has room under all of them — a card that only
LEANS wrong is left alone and a card that reads wrong is caught."""

OWN_SHARE_MIN = 0.40
"""Share of the saturated pixels a card must show of its OWN colour, once it claims any colour.

`DOMINANT_SHARE` asks whether the LEADER is a colour the card lacks. It cannot catch a card whose
wrong colour is split across two mana colours, because neither leader clears the bar. MEASURED
2026-08-16: mono-black Vampiric Tutor under `rick_and_morty` came back a plainly green card — G
43%, U 38%, B 16%, at 0.463 saturation — and passed with its own colour in third place.

Fitted between the two measured populations, which are far apart: correct cards above
NEUTRAL_SHARE ran 73-100% own colour (n=8, R/G/U over four batches) and that failure sat at 16%.

Only applies to identities with a hue to show. `_HUE_BUCKETS` maps hues to R, G, U and B alone —
white is signalled by the absence of hue and colourless claims none — so white and colourless have
an own-share of 0 by construction, and this test would fail every saturated one of them."""

PURPLE_SHARE = 0.15
"""Purple and magenta together, above which a non-black card is misstating its cost.

Every card in the batch measured 0%. This is the client's own reported bug and the brief already
calls it absolute, so it is held to a tighter number than the dominant-hue rule."""

# Hue buckets in degrees, and the mana colour each one reads as. Yellow maps to nothing: gold and
# torchlight are what a white or colourless card is lit by as often as anything else, and failing
# on it would fire on half the Dark Fantasy catalogue.
_HUE_BUCKETS = (
    ("red", 345, 25, "R"),
    ("orange", 25, 45, "R"),
    ("yellow", 45, 70, None),
    ("green", 70, 170, "G"),
    ("cyan", 170, 200, "U"),
    ("blue", 200, 255, "U"),
    ("purple", 255, 300, "B"),
    ("magenta", 300, 345, "B"),
)


_HUED = {mana for _name, _low, _high, mana in _HUE_BUCKETS if mana}
"""The mana colours a hue can actually express — R, G, U, B. See `OWN_SHARE_MIN`."""


def _hue_bucket(degrees):
    for name, low, high, colour in _HUE_BUCKETS:
        if low > high:  # red straddles 0
            if degrees >= low or degrees < high:
                return name, colour
        elif low <= degrees < high:
            return name, colour
    return "red", "R"


def colour_profile(card, sample=280):
    """(share of the card that is saturated, {bucket: share of those pixels}).

    Sampled off a downscale: this runs on every card and the answer is a distribution, which a
    thumbnail preserves and which costs 50x less to compute at 280px than at 1792px.
    """
    import colorsys

    image = card.convert("RGB")
    image = image.resize((sample, round(sample * image.height / image.width)))
    tally, saturated, total = {}, 0, 0
    for red, green, blue in image.getdata():
        total += 1
        hue, sat, value = colorsys.rgb_to_hsv(red / 255, green / 255, blue / 255)
        if sat > 0.30 and value > 0.25:
            saturated += 1
            name, _ = _hue_bucket(hue * 360)
            tally[name] = tally.get(name, 0) + 1
    if not saturated:
        return 0.0, {}
    return saturated / total, {k: v / saturated for k, v in tally.items()}


def colour_identity(card, face):
    """The finished card reading as a colour its cost does not have, or None."""
    identity = set(face.get("color_identity") or [])
    share, buckets = colour_profile(card)

    # Purple first: it is the reported bug, it is absolute in the brief, and it fires even on a
    # card that is otherwise neutral enough to make no claim.
    purple = buckets.get("purple", 0.0) + buckets.get("magenta", 0.0)
    if "B" not in identity and share >= NEUTRAL_SHARE and purple >= PURPLE_SHARE:
        return Problem(
            "colour_identity",
            f"{purple:.0%} of this card's colour is purple on a card that is not black — "
            "purple reads as black mana, so the card misstates its own cost",
        )

    if share < NEUTRAL_SHARE:
        return None  # white, colourless, or a scene lit neutrally: no claim to be wrong about

    # Summed PER MANA COLOUR, not per hue bucket. MEASURED 2026-08-16: Counterspell under the
    # `fire` palette came back blue 53% + cyan 38%, and passed only because neither bucket alone
    # cleared DOMINANT_SHARE — a red card at 53% would have passed identically. Blue and cyan are
    # one mana colour to a player, and so are red and orange; splitting them let a card that
    # plainly reads one colour slip through the dominance test.
    by_mana = {}
    for bucket, _low, _high, mana in _HUE_BUCKETS:
        if mana:
            by_mana[mana] = by_mana.get(mana, 0.0) + buckets.get(bucket, 0.0)
    if not by_mana:
        return None
    names = {"W": "white", "U": "blue", "B": "purple", "R": "red", "G": "green"}
    colour, top = max(by_mana.items(), key=lambda kv: kv[1])
    if colour in identity:
        return None  # the card leads on a colour it actually has
    if top >= DOMINANT_SHARE:
        return Problem(
            "colour_identity",
            f"the card reads {names[colour]} ({top:.0%} of its colour) but its identity is "
            f"{''.join(sorted(identity)) or 'colourless'} — the palette has outranked the cost",
        )

    # No single wrong colour dominates, and the leader is still not one of this card's. That is
    # the case dominance cannot see: two wrong colours sharing the frame, each under the bar.
    # Asked the other way round — how much of this card is its OWN colour — it is obvious.
    own = sum(by_mana.get(one, 0.0) for one in identity)
    if identity & _HUED and own < OWN_SHARE_MIN:
        return Problem(
            "colour_identity",
            f"only {own:.0%} of this card's colour is its own "
            f"({'/'.join(names[one] for one in sorted(identity))}) — it reads "
            f"{names[colour]} at {top:.0%} on a card that is not",
        )
    return None
