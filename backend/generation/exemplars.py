"""Reference cards attached to the image request, so the look is SHOWN and not described.

Phase 1 of `../PLAN-EXEMPLAR-PIVOT-2026-08-20.md`, and the reason it is the highest-leverage
change in that plan: until it landed, `gemini.generate` accepted exactly ONE image — always
Scryfall's `art_crop` — and `prompts.REFERENCE` instructed the model to take *"nothing of how it
is drawn: not its palette, not its lighting, not its period, not its level of realism."* The
model had never been shown the target look. Not once, across 2,245 lines of brief.

MEASURED 2026-08-20, which is why prose was never going to do it: brief elasticity on panel
geometry is 0.10 over 58 faces (`bd mtg-469`), and the client's cards average 2.32 straight plate
rims against our composited pack's 12.80. Every previous fix was another sentence arguing with
the sentences above it.

## The assets are deliberately NOT committed

`backend/assets/exemplars/` is excluded via `.git/info/exclude`, alongside `.beads/` and for a
related reason: the client's reference cards are third-party proxy art, and this repo is handed
to him at Milestone 3. Naming the directory in `.gitignore` would announce in the handover
exactly what is missing.

The consequence is real and is handled rather than hidden: a clean clone cannot reproduce the
look, so `load` RAISES on a missing archetype instead of quietly returning nothing. A silent
empty list would generate an unconditioned card that scores badly for a reason nobody could see
from the output.

**An owned exemplar set — commissioned, or generated and curated — is Milestone 2 work and a
hard prerequisite for shipping to real users.** Conditioning every customer's card on art we do
not own is not a thing to discover at launch.

## Prepare them with `manage.py prepare_exemplars`

Held out on purpose: none of the cards used as exemplars may be a card we then generate and
score. The seven in the client's own target sheet (`Project Material/5 (1).png`) are the
evaluation set, so the exemplars come from `CLIENT-FAVORITES-2026-08-19/`, which shares no card
with it. Teaching to the test would make the go/no-go meaningless.
"""

from pathlib import Path

from django.conf import settings

ROOT = Path(settings.BASE_DIR) / "assets" / "exemplars"

# The five frame archetypes, and which of the client's 19 favorites define each one.
#
# MEASURED 2026-08-20: his corpus clusters into five ways of building a card, and the cluster is
# what governs GEOMETRY. The 48 art styles keep governing PAINT. Two orthogonal axes, which is
# why 48 adjectives never controlled layout — they were never the layout knob, and ten different
# styles kept returning the same three stacked rectangles.
#
# The filenames are documentation, not a contract: `load` reads whatever is in the directory, so
# a curated replacement set drops in without touching this table.
ARCHETYPES = {
    "portal": "an architectural arch, gate or window, with the art in an aperture inside it",
    "tangle": "organic growth — vine, thorn, root, tentacle — closing all four sides",
    "banner": "vignette art with a hanging banner for the name and a scroll for the rules",
    "panel": "flat graphic: bold ink outline, screen colour, outlined display type",
    "mural": "one continuous scene with no aperture, text set into it on found surfaces",
}

SOURCES = {
    "portal": ("Command_Tower", "Force_of_Will", "Avacyn_Angel_of_Hope", "giada_of_hope"),
    # Phase 1 set (2026-08-20). Restored same-day evening after pixel Dryad/Azusa + dark_fantasy
    # produced black-void Tower Winders; LETTERED-DAILY / EXEMPLAR-TANGLE Toski had scene at the
    # trim under comic_book + these refs.
    "tangle": ("Cyclonic_Rift", "Brainstealer_Dragon", "Hullbreaker_Horror"),
    "banner": ("Aurelia_the_Warleader", "Lyra_Dawnbringer"),
    "panel": ("Counterspell", "Memory_Jar", "Arcane_Signet", "Howling_Mine"),
    "mural": ("kaalia_of_teh_vast", "1-A", "5-A"),
}
"""Which of `CLIENT-FAVORITES-2026-08-19/` seeds each archetype. Used by `prepare_exemplars`."""

LONG_EDGE = 900
"""Long edge the exemplars are stored at.

Enough to carry frame construction, surface treatment and lettering style; small enough that
three of them do not dominate the request. The cards are 1792x2400, so this is 672x900 — a
quarter of the linear resolution and a sixteenth of the tokens.
"""


class Missing(RuntimeError):
    """No exemplars for an archetype that was asked for. Never silently unconditioned."""


def available():
    """The archetypes that actually have files on this machine."""
    if not ROOT.is_dir():
        return set()
    return {
        directory.name
        for directory in ROOT.iterdir()
        if directory.is_dir() and any(directory.glob("*.png"))
    }


def paths(archetype):
    """Every exemplar file for `archetype`, in a stable order.

    Sorted, so two runs of the same card attach the same images in the same order. Anything else
    makes a rerun incomparable with the run before it, which is the one thing this project leans
    on to tell a fix from noise.
    """
    if archetype not in ARCHETYPES:
        raise Missing(
            f"{archetype!r} is not a frame archetype. Known: {', '.join(sorted(ARCHETYPES))}"
        )
    found = sorted((ROOT / archetype).glob("*.png")) if ROOT.is_dir() else []
    if not found:
        raise Missing(
            f"no exemplar images in {ROOT / archetype}. The client's reference cards are not "
            f"committed — see generation/exemplars.py. Build them with:\n"
            f"    uv run python manage.py prepare_exemplars "
            f"'../../Project Material/CLIENT-FAVORITES-2026-08-19' --archetype {archetype}"
        )
    return found


def load(archetype, count=None):
    """[bytes] for the first `count` exemplars of `archetype`, or all of them.

    `count` exists for the A/B that decides how many are worth attaching: more images cost more
    tokens and may dilute rather than reinforce, and that is a measurement rather than a guess.
    """
    chosen = paths(archetype)
    if count is not None:
        chosen = chosen[:count]
    return [path.read_bytes() for path in chosen]
