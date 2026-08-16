"""Is this card structurally sound, or should the art be regenerated?

WHAT THIS IS NOT. `HANDOVER-2026-08-09.md` describes a `check.py` that grades the card's printed
TEXT field by field against Scryfall, because at that point the model was lettering the card
itself and a fabricated subtype in the right font was invisible. That mode is gone: we composite
Scryfall's own text (`cards.compositor`), so the wording is correct by construction and there is
nothing to proofread. What can still be wrong is the FURNITURE the model painted, and that is
what this grades.

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

from typing import NamedTuple


class Problem(NamedTuple):
    """One structural fault, with a code a caller can branch on."""

    code: str
    detail: str


# A plate this far down the card is not a title plate, whatever the detector called it. The ten
# reference-site generations of one card put it at the top on 10 of 10 while everything else about
# the layout moved, so the order is the one thing safe to assert.
TITLE_MAX_Y = 0.25


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
    blank = len(panels.get("spare") or [])
    paragraphs = len([p for p in (face.get("oracle_text") or "").split("\n") if p.strip()])
    blank += max(0, len(strips) - max(1, paragraphs))
    if blank:
        problems.append(
            Problem(
                "blank_surface",
                f"{blank} painted surface(s) more than this card has text for — an empty second "
                "bar reads as a printing error, which is how the client reported it",
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
        f"{share:.0%} of the card's edge is one flat light colour — a border on a card asked to "
        "run full bleed",
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
    colour, top = max(by_mana.items(), key=lambda kv: kv[1])
    if top < DOMINANT_SHARE or colour in identity:
        return None
    reads = {"W": "white", "U": "blue", "B": "purple", "R": "red", "G": "green"}[colour]
    return Problem(
        "colour_identity",
        f"the card reads {reads} ({top:.0%} of its colour) but its identity is "
        f"{''.join(sorted(identity)) or 'colourless'} — the palette has outranked the cost",
    )
