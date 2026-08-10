"""Typefaces for the composited information layer.

Fonts are vendored into assets/fonts/ and pinned. Never load a system font: Debian
ships EBGaramond12-Bold.ttf as a 127-glyph stub with no em dash, and an em dash is in
every single type line ("Legendary Creature — Kavu Pilot"), so a system Bold would
render a tofu box on every card in the deck. tests/test_fonts.py asserts coverage.

WHICH FAMILY — DECIDED 2026-08-10, DISPLAY ROLE REVISED 2026-08-10
------------------------------------------------------------------
Real Magic cards set the name, type line and P/T in **Beleren** and the rules text in
**Plantin MT Pro**.

The display role is now Beleren itself, at the client's direction. It is the actual card
face, so composited names and type lines match the reference site exactly instead of
approximately, which is what "make it look like theirs" turned out to mean. It carries a
licensing debt rather than a licence — see `UNLICENSED` below and
assets/fonts/LICENCE-Beleren2016.txt. PlayfairDisplay-Bold stays vendored as the
cleanly-licensed swap-in for handover, so the decision stays reversible in one line.

The TEXT role is still a lookalike, because Plantin is Monotype's and no free extraction of
it exists the way one does for Beleren.

**PT Serif** (SIL OFL, ParaType) is that face. Chosen by comparison against the reference
site's own Terror of the Peaks, rendering the same type line and rules line in eight
candidates: EB Garamond, PT Serif, Spectral, Cardo, Vollkorn, Alegreya, Cinzel, Marcellus.
Two things decide it, because they are what made our text read lighter than theirs at the
same point size:

- **x-height.** Their body text has a large one; EB Garamond is an oldstyle face with a
  small x-height, so at any given size it looks smaller and more delicate than theirs.
- **Stroke weight.** PT Serif's regular is sturdy and its bold is genuinely heavy, which is
  what their flat black text on parchment needs. Cardo and EB Garamond are too light,
  Alegreya and Spectral too narrow, Cinzel is small-caps only, Marcellus has one weight.

EB Garamond stays vendored rather than deleted: it is what every card generated before
2026-08-10 used, so removing it would make earlier output unreproducible.

Mana pips are not a font — see cards/symbols.py.
"""

from pathlib import Path

FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"

REGULAR = FONT_DIR / "PTSerif-Regular.ttf"  # rules text
ITALIC = FONT_DIR / "PTSerif-Italic.ttf"    # ability words, reminder text, flavour
BOLD = FONT_DIR / "PTSerif-Bold.ttf"        # keyword lines inside the rules text
# The DISPLAY role — card name, type line, P/T. A real card pairs a display face with a text
# face (Beleren with Plantin); using one face for both is a large part of why composited text
# reads flat.
DISPLAY = FONT_DIR / "Beleren2016-Bold.ttf"
# The reference site sets some card names in small caps ("TERROR OF MOUNT VELUS", "VALAKUT
# STONEFORGE") and others mixed case, on cards otherwise identical. Mixed case is the modern
# card standard, so DISPLAY is the default; this is here for when the look is offered.
DISPLAY_SMALL_CAPS = FONT_DIR / "Beleren2016SmallCaps-Bold.ttf"
# The cleanly-licensed swap-in for DISPLAY at handover. Playfair Display Bold carries the
# stroke contrast and slightly condensed forms that PT Serif Bold has none of, chosen against
# seven candidates 2026-08-10. Vendored as a static instance pinned at wght=700 from the
# variable font, so nothing sets axes at runtime.
DISPLAY_SHIPPABLE = FONT_DIR / "PlayfairDisplay-Bold.ttf"

FACES = {"regular": REGULAR, "italic": ITALIC, "bold": BOLD, "display": DISPLAY}

# Faces vendored WITHOUT a licence that permits redistribution. Beleren was extracted from
# magicthegathering.com and republished for non-commercial use; the package's MIT LICENSE.md
# covers its CSS wrapper, not the typeface. This repo is handed to the client at Milestone 3,
# so every entry here is a release blocker, not a footnote. tests/test_fonts.py fails if a
# face is vendored that is neither OFL-covered nor listed here — the list is the checklist.
UNLICENSED = {DISPLAY, DISPLAY_SMALL_CAPS}

# The family used before 2026-08-10, kept so earlier output stays reproducible.
SUPERSEDED = {
    "regular": FONT_DIR / "EBGaramond-Regular.ttf",
    "italic": FONT_DIR / "EBGaramond-Italic.ttf",
    "bold": FONT_DIR / "EBGaramond-Bold.ttf",
}
