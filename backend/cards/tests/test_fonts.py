"""The vendored fonts must cover every character real MTG cards use.

This exists because the packaged EBGaramond12-Bold.ttf on Debian/Ubuntu is a 127-glyph
stub missing the em dash. Vendoring fixed it; this test is what keeps it fixed after a
font bump. Run it after any change under assets/fonts/.
"""

from django.test import SimpleTestCase
from fontTools.ttLib import TTFont

from cards import fonts

# Each character, and the real card feature that would break without it.
REQUIRED = {
    "—": "type line: 'Legendary Creature — Kavu Pilot'",
    "−": "planeswalker loyalty cost: '−3:'",
    "•": "modal spells: 'Choose one •'",
    "Æ": "Æther Vial",
    "û": "Lim-Dûl's Vault",
    "á": "Márton Stromgald",
    "í": "Ríen",
    "ö": "Björke",
    "’": "flavour text apostrophe",
    "“": "flavour text open quote",
    "”": "flavour text close quote",
}


class VendoredFontsTest(SimpleTestCase):
    def test_faces_exist(self):
        for name, path in fonts.FACES.items():
            self.assertTrue(path.is_file(), f"{name} font missing at {path}")

    def test_faces_cover_required_characters(self):
        for name, path in fonts.FACES.items():
            cmap = TTFont(path, lazy=True).getBestCmap()
            missing = {c: why for c, why in REQUIRED.items() if ord(c) not in cmap}
            self.assertFalse(missing, f"{name} ({path.name}) is missing {missing}")

    def test_bold_is_not_the_debian_stub(self):
        """The stub has 127 glyphs; the real face has ~2000."""
        cmap = TTFont(fonts.BOLD, lazy=True).getBestCmap()
        self.assertGreater(len(cmap), 1000, "Bold looks like the 127-glyph system stub")
