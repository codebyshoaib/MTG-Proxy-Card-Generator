"""Does the painting CONTINUE through the lower third, or does it stop there?

This exists because of bd mtg-9ww. Asked to keep the lower third calm, the model failed in BOTH
directions at once — two cards stopped painting and left dead space, a third came back busier than
the card average — and one sentence in the brief produced all three. Neither failure is visible to
`check`: a blank lower third grades perfectly sound, and still loses the client's "not a rectangle
inside a frame" requirement, because the art visibly stops where the furniture starts.

TWO NUMBERS, BECAUSE ONE CANNOT DO IT. The brief asks the lower third to go QUIET — "low contrast
and low detail" — so a band quieter than the card average is the goal, not the fault. A relative
measure alone therefore cannot tell success from the dead-space failure; both read low. What
separates them is whether there is any material there at all, which is `substance`. `liveliness`
is kept for the opposite failure, where the band competes with the subject.

MEASURED over all 56 stored blanks, 2026-08-16:

    substance    real cards 4.30 to 50.21, median 15.74    a painted-blank control 0.29
    liveliness   real cards 0.58 to 1.14,  median 0.78

No threshold is fitted here on purpose. `substance` needs none — the quietest real card sits 15x
above a genuinely blank panel, so the populations are not close enough to need a line drawn
between them. `liveliness` cannot honestly carry one: it is a ratio against the whole card, so a
calm sky in the upper two thirds raises it without anything cluttering the lower third, which is
exactly what the 1.14 card is.

DIAGNOSTIC, NOT A GATE. Nothing in the pipeline calls this and nothing should. A card is not
faulty for being lively; this measures whether a WORDING change moved the population, which is a
question about the brief rather than about any one card. Wiring it into `check` would repaint
cards over an aesthetic property and cost a credit every time.

It lives in the repo, rather than in a scratchpad, on purpose. Two earlier measurement scripts
were written into a session directory, quoted in a handover as though the next reader could run
them, and were gone by the time anyone tried. A number nobody can reproduce is not evidence.
"""

from PIL import ImageFilter, ImageStat

LOWER_THIRD = (2 / 3, 1.0)
"""The band the brief makes a promise about — see `prompts.creative_full`."""


def _edges(card):
    """Edge strength per pixel. Zero on a flat wash, high on grain, cracks and clutter.

    Cropped one pixel in: FIND_EDGES lights up the outermost ring regardless of content, and left
    in it would flatter every card by the same amount.
    """
    grey = card.convert("L")
    width, height = grey.size
    return grey.filter(ImageFilter.FIND_EDGES).crop((1, 1, width - 1, height - 1))


def _band(edges, band):
    width, height = edges.size
    top, bottom = (round(height * edge) for edge in band)
    return edges.crop((0, top, width, bottom))


def substance(card, band=LOWER_THIRD):
    """How much material the band carries, in absolute edge strength.

    This is the dead-space test. A lower third that stopped into a flat panel has nothing in it
    to measure; a lower third that went quiet still has ground, haze, smoke or water in it.
    """
    return ImageStat.Stat(_band(_edges(card), band)).mean[0]


def liveliness(card, band=LOWER_THIRD):
    """How busy the band is against the whole card. 1.0 means exactly as busy as the card average.

    Read it downward only — the brief asks for a value under 1.0, so a low reading is compliance
    and needs `substance` to say whether it is also dead. Read upward it flags the other failure,
    a band competing with the subject, but see the module docstring before trusting a high one.
    """
    edges = _edges(card)
    whole = ImageStat.Stat(edges).mean[0]
    if not whole:
        return 0.0
    return ImageStat.Stat(_band(edges, band)).mean[0] / whole
