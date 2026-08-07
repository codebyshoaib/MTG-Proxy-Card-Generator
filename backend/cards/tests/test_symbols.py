"""Every symbol a real card can carry must resolve to vendored artwork.

A missing pip is a wrong card, not a cosmetic defect — the client already reported one
(a stray {G}). These assertions are the cheap guard against a symbol silently vanishing
after a Scryfall refresh.
"""

from django.test import SimpleTestCase

from cards import symbols

# Everything that appears in a mana cost or in oracle text, by category.
BASIC = ["{W}", "{U}", "{B}", "{R}", "{G}", "{C}", "{X}", "{Y}", "{Z}"]
GENERIC = [f"{{{n}}}" for n in range(0, 21)] + ["{100}", "{1000000}", "{½}", "{∞}"]
HYBRID = ["{W/U}", "{U/B}", "{B/R}", "{R/G}", "{G/W}",
          "{W/B}", "{U/R}", "{B/G}", "{R/W}", "{G/U}"]
TWOBRID = ["{2/W}", "{2/U}", "{2/B}", "{2/R}", "{2/G}"]
COLOURLESS_HYBRID = ["{C/W}", "{C/U}", "{C/B}", "{C/R}", "{C/G}"]
PHYREXIAN = ["{W/P}", "{U/P}", "{B/P}", "{R/P}", "{G/P}"]
NON_MANA = ["{T}", "{Q}", "{S}", "{E}", "{A}", "{P}"]

ALL = BASIC + GENERIC + HYBRID + TWOBRID + COLOURLESS_HYBRID + PHYREXIAN + NON_MANA


class VendoredSymbolsTest(SimpleTestCase):
    def test_every_symbol_is_vendored(self):
        missing = [t for t in ALL if symbols.path_for(t) is None]
        self.assertEqual(missing, [], "run: manage.py fetch_symbols")

    def test_unknown_symbol_returns_none_rather_than_a_wrong_pip(self):
        self.assertIsNone(symbols.path_for("{NOPE}"))
        self.assertIsNone(symbols.pip("{NOPE}", 32))


class PipRenderingTest(SimpleTestCase):
    def test_pip_renders_at_the_requested_size_with_transparency(self):
        im = symbols.pip("{W}", 64)
        self.assertEqual(im.size, (64, 64))
        self.assertEqual(im.mode, "RGBA")
        self.assertTrue(any(px[3] == 0 for px in im.getdata()), "pip has no alpha edge")

    def test_hybrid_pip_is_two_coloured_halves(self):
        """{W/U} must be a split pip, not a plain one — the Mana font could not do this."""
        im = symbols.pip("{W/U}", 128)
        left, right = im.getpixel((30, 64)), im.getpixel((98, 64))
        self.assertNotEqual(left[:3], right[:3])
        self.assertGreater(left[0], left[2], "left half should read as white mana (warm)")
        self.assertGreater(right[2], right[0], "right half should read as blue mana (cool)")

    def test_pips_are_cached_not_re_rasterised(self):
        self.assertIs(symbols.pip("{G}", 48), symbols.pip("{G}", 48))


class SplitTextTest(SimpleTestCase):
    def test_keeps_text_and_symbols_in_order(self):
        runs = symbols.split_text("{T}: Add {G}{G}.")
        self.assertEqual(
            runs,
            [("symbol", "{T}"), ("text", ": Add "),
             ("symbol", "{G}"), ("symbol", "{G}"), ("text", ".")],
        )

    def test_leaves_an_unknown_token_as_literal_text(self):
        self.assertEqual(symbols.split_text("costs {NOPE} less"),
                         [("text", "costs {NOPE} less")])

    def test_plain_text_is_one_run(self):
        self.assertEqual(symbols.split_text("Flying"), [("text", "Flying")])

    def test_real_oracle_text_with_an_inline_cost(self):
        runs = symbols.split_text("Revolt — Pay {2}{R}: Deal 3 damage.")
        self.assertEqual([t for k, t in runs if k == "symbol"], ["{2}", "{R}"])
        self.assertTrue(runs[0] == ("text", "Revolt — Pay "))
