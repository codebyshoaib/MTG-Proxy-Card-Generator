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
    if panels.get("marks"):
        problems.append(
            Problem(
                "painted_marks",
                f"{len(panels['marks'])} patch(es) of painted lettering, runes or insignia — "
                "fake writing or a set symbol on a card that has no set",
            )
        )
    return problems
