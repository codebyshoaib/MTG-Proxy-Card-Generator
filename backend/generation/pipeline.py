"""Art Only and Creative Full as plain callables.

Both modes existed only inside their management commands, which meant the HTTP API would have
been a second copy of the same flow — and a second place for the refusal handling, the retry
count and the printing-consistency fix to drift out of step. The commands and `generation.views`
now call the same three functions here.

Every option is named for the reference site's own POST /api/ai-proxies/generate/ payload, so a
frontend maps one-to-one with no translation table in between.
"""

import io
from typing import NamedTuple

import requests

from cards import compositor, scryfall
from generation import bleed, check, gemini, panels, prompts, refusals


class Rejected(ValueError):
    """A card we will not generate, decided before any AI call is paid for."""

    def __init__(self, code, detail):
        super().__init__(detail)
        self.code, self.detail = code, detail


class Options(NamedTuple):
    """The seven inputs, under the reference site's own names."""

    art_style: str | None = None
    art_direction: str | None = None
    color_palette: str | None = None
    custom_art_notes: str | None = None
    include_flavor_text: bool = False
    use_original_art_reference: bool = True
    # Borderless is the default — client, 2026-08-13. False builds the card's edge out of the
    # scene instead of running the art full bleed.
    borderless: bool = True


class Result(NamedTuple):
    card: object          # the composited PIL image
    problems: list        # check.Problem, empty means fit to ship
    detected: dict        # panels.detect's boxes, kept for the --boxes debug overlay
    blank: bytes | None   # the empty-furniture PNG, None when composited from disk


def _noop(_message):
    pass


def faces_of(name):
    """Every face of `name`, or raise `Rejected` — no AI call is made either way."""
    found, missing = scryfall.resolve([name])
    if missing:
        raise Rejected("unknown", f"Scryfall does not know {missing[0]!r}")
    card = found[name]
    if card.layout in scryfall.UNSUPPORTED:
        raise Rejected("unsupported", f"{card.name}: layout {card.layout} is not supported")
    return scryfall.faces(card)


def prepare(face, use_reference=True):
    """(face, reference bytes, licensed) — the Scryfall side, done once per card.

    Outside any retry loop deliberately: repainting must not re-download the art or re-ask
    Scryfall which printing to use.
    """
    original = scryfall.art_reference(face)
    url, licensed = original.art_crop, original.licensed
    # The flavour text has to come from the same printing the art does. `resolve()` answers a
    # bare name with the NEWEST printing, which since June 2026 is a licensed crossover for a
    # lot of staples, while `art_reference()` deliberately goes back to the oldest
    # non-crossover one. Left unreconciled, `--flavor` printed Christopher Rush's Alpha
    # Lightning Bolt under flavour text reading "...speaks The Mighty Thor!" — one card
    # wearing two printings.
    if face["is_crossover"] and not licensed:
        face = {**face, "flavor_text": original.flavor_text}
    if not use_reference:
        url = None
    reference = None
    if url:
        response = requests.get(url, headers=scryfall.HEADERS, timeout=30)
        response.raise_for_status()
        reference = response.content
    return face, reference, licensed


def art_brief(face, options=Options(), note=_noop):
    """(prompt, reference bytes) for Art Only, without spending a generation.

    Split out so `--dry-run` prints exactly the brief that would have been sent rather than a
    reconstruction of it. It still fetches the Scryfall art, which is free.
    """
    face, reference, licensed = prepare(face, options.use_original_art_reference)
    if licensed:
        note(
            f"{face['name']} exists only as a licensed crossover. Painting its game identity "
            "from the type line, not the character."
        )
    return prompts.art_only(
        face,
        options.art_style,
        reference=bool(reference),
        licensed=licensed,
        direction=options.art_direction,
        palette=options.color_palette,
    ), reference


def art(face, options=Options(), note=_noop):
    """Art Only: one image call, encoded image bytes out. BUILD-SPEC §3 — it stops after step 3.

    The format is the model's, not ours — measured JPEG, not PNG. Anything writing these to a
    named file has to re-encode; `jobs._write_png` is what does it.
    """
    prompt, reference = art_brief(face, options, note)
    return gemini.generate(prompt, reference)


def creative_full(face, options=Options(), attempts=2, source=None, note=_noop):
    """Creative Full, end to end, for one face.

    One image call for the art and its blank furniture, one vision call for where the surfaces
    landed, Scryfall's own text composited into them, then a structural grade. A faulty card is
    repainted once — measured, about one card in five needs it, and a second retry would mostly
    burn credits on cards that keep failing.

    `source` composites onto an empty-furniture PNG already on disk instead of generating one,
    which is what to use while tuning the compositor: it costs nothing and keeps the layout the
    same between runs.
    """
    face, reference, licensed = prepare(face, options.use_original_art_reference)
    # The ability count is a hint for how many pale strips to look for — the brief asks for one,
    # so a second is worth knowing about rather than assuming.
    paragraphs = len([p for p in (face.get("oracle_text") or "").split("\n") if p.strip()]) or None

    attempt = 0
    while True:
        attempt += 1
        png = source if source else _paint(face, licensed, reference, options, note)

        # Before anything measures this image: cut the margin the model painted around it. Done
        # here rather than after compositing so the panel boxes and every coordinate downstream
        # are computed on the card that will actually ship.
        if options.borderless:
            png, depth = bleed.trim(png)
            if depth:
                note(f"trimmed a {depth:.1%} painted margin — the brief asked for full bleed")

        detected = panels.detect(
            png, paragraphs=paragraphs, expect_pt=face.get("power") is not None
        )
        # A guessed P/T box used to be substituted here when detection missed (bd mtg-wfp). DELETED
        # 2026-08-16 rather than tuned, which is what bd mtg-1uv asked for. The guess existed
        # because detection of this one surface was unreliable — 7 of 20 runs over the same stored
        # blanks on 2026-08-15. Re-running that identical experiment today, after the enlarged
        # corner was paired into the call (e10ba96) and the tab shape was opened away from the
        # shield, gives 24 of 24 on six creatures, plus 15 of 15 across the day's live runs.
        #
        # Its premise gone, what was left was a fitted box that is wrong whenever it does fire: it
        # overhung the painted surface on 5 of 5 undetected cards, and outside its fitted domain
        # the error flips sign (Terror of the Peaks, 0.038 high, printing the 5/4 on the rim). A
        # P/T that looks placed but is not beats a loud failure only if the alternative is silence,
        # and it is not — `check` fires missing_pt, the card is repainted, and a card that still
        # has no tab is reported UNSOUND rather than shipped with a number hanging off a rim.
        card, overflowed = compositor.compose(
            io.BytesIO(png), face, detected,
            include_flavor_text=options.include_flavor_text,
        )
        problems = check.inspect(face, detected, overflowed)
        # Both read the composited card rather than the geometry, which is why they sit here and
        # not in `inspect`. Contrast applies to every layout: a panel too dark for its own text is
        # unreadable whether or not the card runs to the edge.
        problems += [problem for problem in [check.contrast(card, detected)] if problem]
        # Graded against Scryfall's `color_identity` and NOT against `options`. The style, art
        # direction and palette the user picked on the UI are the thing this guards against — a
        # mono-red Lightning Bolt under the `ice` palette came back blue-white (bd mtg-5pb) — so
        # a gate that took them as input could be talked out of firing by the very selection that
        # caused the fault. CLAUDE.md: colour identity comes from Scryfall, never from the style.
        problems += [problem for problem in [check.colour_identity(card, face)] if problem]
        if options.borderless:
            problems += [problem for problem in [check.matted(card)] if problem]
        if not problems or source or attempt >= max(1, attempts):
            return Result(card, problems, detected, None if source else png)
        note(
            f"attempt {attempt}: "
            + "; ".join(problem.detail for problem in problems)
            + " — repainting"
        )


def _paint(face, licensed, reference, options, note):
    """One image call: the card's art and its blank furniture, as PNG bytes.

    Tries the card's own NAME first and falls back to its game identity only once the model has
    actually refused (bd mtg-kx4). Measured on ten licensed-only cards: eight painted the real
    character first try and only the two Marvel ones were refused, so treating every crossover as
    unpaintable loses the likeness the client asked for on eight of them. The reference site's
    gallery agrees — its Raphael, Gimli, Sephiroth and Y'shtola are all named and all at full
    likeness, and in 3265 cards it holds no Marvel card at all.
    """
    def brief(as_identity):
        return prompts.creative_full(
            face, options.art_style, reference=bool(reference), licensed=as_identity,
            direction=options.art_direction, palette=options.color_palette,
            notes=options.custom_art_notes, borderless=options.borderless,
        )

    if not (licensed and refusals.is_refused(face["name"])):
        try:
            return gemini.generate(brief(False), reference)
        except gemini.NoImage as refusal:
            # A refusal repeats for this prompt forever, so the only useful response is a
            # different prompt. A transient miss is neither remembered nor retried here: it costs
            # the same generation either way and the caller can run it again.
            if not (licensed and refusal.refused):
                raise
            refusals.remember(face["name"])
            note(
                f"{face['name']}: refused under its own name ({refusal.finish_reason}) — "
                "repainting from the card's game identity instead. Remembered, so this is "
                "paid once."
            )
    return gemini.generate(brief(True), reference)
