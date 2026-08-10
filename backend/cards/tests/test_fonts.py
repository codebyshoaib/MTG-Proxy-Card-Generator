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

    def test_the_superseded_family_is_still_present(self):
        """Kept so cards generated before the 2026-08-10 font change stay reproducible."""
        for name, path in fonts.SUPERSEDED.items():
            self.assertTrue(path.is_file(), f"superseded {name} missing at {path}")

    def test_every_vendored_face_is_either_licensed_or_flagged(self):
        """A face may ship under its OFL, or be a known debt in fonts.UNLICENSED. It may not
        be neither: Beleren is Wizards' own commissioned face and this repo is handed to the
        client at Milestone 3, so an unlicensed .ttf arriving unnoticed is a release problem,
        not a style one. Failing here means adding the OFL or adding the face to UNLICENSED."""
        for path in set(fonts.FACES.values()) | set(fonts.SUPERSEDED.values()):
            with self.subTest(face=path.name):
                if path in fonts.UNLICENSED:
                    continue
                family = path.name.split("-")[0]
                licence = path.parent / f"OFL-{family}.txt"
                self.assertTrue(
                    licence.is_file(), f"{path.name} has no licence at {licence.name}"
                )

    def test_each_unlicensed_face_records_why_it_cannot_ship(self):
        """The debt has to be readable at handover by someone who was not in this session."""
        for path in fonts.UNLICENSED:
            family = path.name.split("-")[0]
            note = path.parent / f"LICENCE-{family}.txt"
            self.assertTrue(note.is_file(), f"{path.name} has no note at {note.name}")
            self.assertIn("NOT CLEARED FOR REDISTRIBUTION", note.read_text())

    def test_a_cleanly_licensed_display_face_stays_vendored(self):
        """Beleren's replacement has to be one line away, not a re-run of the 2026-08-10
        eight-candidate comparison, or the handover swap will not happen."""
        self.assertTrue(fonts.DISPLAY_SHIPPABLE.is_file())
        self.assertNotIn(fonts.DISPLAY_SHIPPABLE, fonts.UNLICENSED)

    def test_faces_cover_required_characters(self):
        for name, path in fonts.FACES.items():
            cmap = TTFont(path, lazy=True).getBestCmap()
            missing = {c: why for c, why in REQUIRED.items() if ord(c) not in cmap}
            self.assertFalse(missing, f"{name} ({path.name}) is missing {missing}")

    def test_bold_is_not_the_debian_stub(self):
        """The stub has 127 glyphs. The threshold is 400 rather than 1000 because it is testing
        for the stub, not for a glyph count: PT Serif Bold is a real face with 723, while the
        original 1000 was calibrated to EB Garamond's ~2000 and rejected it."""
        cmap = TTFont(fonts.BOLD, lazy=True).getBestCmap()
        self.assertGreater(len(cmap), 400, "Bold looks like the 127-glyph system stub")
