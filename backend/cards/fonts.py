"""Typefaces for the composited information layer.

Fonts are vendored into assets/fonts/ and pinned. Never load a system font: Debian
ships EBGaramond12-Bold.ttf as a 127-glyph stub with no em dash, and an em dash is in
every single type line ("Legendary Creature — Kavu Pilot"), so a system Bold would
render a tofu box on every card in the deck. tests/test_fonts.py asserts coverage.

Mana pips are not a font — see cards/symbols.py.
The card NAME is painted by the AI and is not composited at all — BUILD-SPEC §6.1.
"""

from pathlib import Path

FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"

REGULAR = FONT_DIR / "EBGaramond-Regular.ttf"   # rules text, P/T, loyalty numbers
ITALIC = FONT_DIR / "EBGaramond-Italic.ttf"     # ability words, reminder text, flavour
BOLD = FONT_DIR / "EBGaramond-Bold.ttf"         # type line

FACES = {"regular": REGULAR, "italic": ITALIC, "bold": BOLD}
