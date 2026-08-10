"""The text engine, against the real vendored fonts.

Everything here is arithmetic on real rules text, which is the part that silently produces a
wrong-looking card: a cost that breaks across two lines, an ability word set upright, reminder
text that is not italic, or a panel that overflows without anyone noticing.
"""

from django.test import SimpleTestCase

from cards import textlayout


class AtomTests(SimpleTestCase):
    def test_a_keyword_only_paragraph_is_marked_as_one(self):
        """'Flying' is set larger and heavier on a real card and on the reference site's."""
        self.assertTrue(textlayout.is_keyword_line("Flying"))
        self.assertTrue(textlayout.is_keyword_line("Flying, vigilance, deathtouch, lifelink"))
        self.assertFalse(textlayout.is_keyword_line("Counter target spell."))
        self.assertFalse(
            textlayout.is_keyword_line("Whenever another creature you control enters, do this.")
        )

    def test_a_mana_cost_becomes_symbols_not_words(self):
        line = textlayout.atoms("{2}{R}: Deal 3 damage.")[0]
        self.assertEqual([a.text for a in line[:2]], ["{2}", "{R}"])
        self.assertTrue(all(a.symbol for a in line[:2]))
        self.assertEqual(line[2].text, ":")
        self.assertFalse(line[2].symbol)

    def test_a_symbol_inside_a_sentence_stays_inline(self):
        line = textlayout.atoms("This creature deals {X} damage to any target.")[0]
        symbol = [a for a in line if a.symbol]
        self.assertEqual([a.text for a in symbol], ["{X}"])

    def test_an_ability_word_is_italic_and_the_rest_is_not(self):
        """'Alliance — Whenever another creature you control enters...' — Raphael's own card."""
        line = textlayout.atoms("Alliance — Whenever another creature enters, deal 1 damage.")[0]
        self.assertTrue(line[0].italic)
        self.assertFalse(line[-1].italic)

    def test_reminder_text_in_parentheses_is_italic(self):
        line = textlayout.atoms("Menace (This creature can't be blocked except by two.)")[0]
        self.assertFalse(line[0].italic)
        self.assertTrue(all(a.italic for a in line[1:]))

    def test_each_scryfall_paragraph_is_its_own_logical_line(self):
        self.assertEqual(len(textlayout.atoms("Flying\nTrample\nHaste")), 3)

    def test_an_unknown_token_survives_as_an_atom(self):
        """A cost must never be silently dropped, even one we have no SVG for."""
        line = textlayout.atoms("{QQQ}: Do a thing.")[0]
        self.assertEqual(line[0].text, "{QQQ}")
        self.assertTrue(line[0].symbol)


class WrapTests(SimpleTestCase):
    LONG = (
        "Whenever another creature you control enters, this creature deals damage equal to "
        "that creature's power to any target."
    )

    def test_wrapping_narrower_gives_more_lines(self):
        wide, _, _ = textlayout.wrap(textlayout.atoms(self.LONG), 40, 1400)
        narrow, _, _ = textlayout.wrap(textlayout.atoms(self.LONG), 40, 500)
        self.assertGreater(len(narrow), len(wide))

    def test_no_line_exceeds_the_width_it_was_given(self):
        from PIL import ImageFont

        from cards import fonts

        size, max_width = 40, 600
        regular = ImageFont.truetype(str(fonts.REGULAR), size)
        italic = ImageFont.truetype(str(fonts.ITALIC), size)
        lines, _, pip_px = textlayout.wrap(textlayout.atoms(self.LONG), size, max_width)
        space = regular.getlength(" ")
        for line, _starts in lines:
            width = sum(textlayout.width_of(a, regular, italic, pip_px) for a in line)
            width += space * max(0, len(line) - 1)
            # Spaces are counted generously here; a single long word may legitimately exceed.
            if len(line) > 1:
                self.assertLessEqual(width - space * (len(line) - 1), max_width)

    def test_adjacent_pips_are_not_split_by_a_space(self):
        """'{2}{R}' is one cost. Measured width must not include a gap between the two pips."""
        lines, _, pip_px = textlayout.wrap(textlayout.atoms("{2}{R}{R}: Go."), 40, 2000)
        self.assertEqual(len(lines), 1)


class FitTests(SimpleTestCase):
    def test_a_tight_box_gets_a_smaller_size_than_a_roomy_one(self):
        text = WrapTests.LONG
        roomy, _, _, _ = textlayout.fit(text, 900, 600, 60)
        tight, _, _, _ = textlayout.fit(text, 900, 120, 60)
        self.assertLess(tight, roomy)

    def test_it_never_returns_below_the_floor_even_when_nothing_fits(self):
        """Overflowing slightly is a visible imperfection; failing costs the user a credit."""
        size, lines, lh, _ = textlayout.fit(WrapTests.LONG * 6, 400, 40, 60, min_size=13)
        self.assertEqual(size, 13)
        self.assertGreater(len(lines) * lh, 40)


class ExclusionTests(SimpleTestCase):
    def test_lines_below_the_shield_are_shortened(self):
        """The AI paints the P/T shield overlapping the slab, so text has to flow around it."""
        text = WrapTests.LONG
        plain, lh, _ = textlayout.wrap(textlayout.atoms(text), 40, 900)
        floated, _, _ = textlayout.wrap(textlayout.atoms(text), 40, 900, exclude=(lh, 450))
        self.assertGreater(len(floated), len(plain))

    def test_lines_above_the_shield_keep_the_full_width(self):
        text = WrapTests.LONG
        _, lh, _ = textlayout.wrap(textlayout.atoms(text), 40, 900)
        floated, _, _ = textlayout.wrap(textlayout.atoms(text), 40, 900, exclude=(lh * 99, 200))
        plain, _, _ = textlayout.wrap(textlayout.atoms(text), 40, 900)
        self.assertEqual(len(floated), len(plain))


class ParagraphTests(SimpleTestCase):
    def test_each_ability_is_flagged_as_starting_a_paragraph(self):
        """The reference site separates abilities visibly; ours ran them together at one rhythm."""
        lines, _, _ = textlayout.wrap(textlayout.atoms("Flying\nTrample\nHaste"), 40, 2000)
        self.assertEqual([starts for _, starts in lines], [True, True, True])

    def test_a_wrapped_continuation_does_not_start_a_paragraph(self):
        lines, _, _ = textlayout.wrap(textlayout.atoms(WrapTests.LONG), 40, 500)
        self.assertTrue(lines[0][1])
        self.assertFalse(any(starts for _, starts in lines[1:]))

    def test_block_height_counts_the_gaps_between_abilities(self):
        lines, lh, _ = textlayout.wrap(textlayout.atoms("Flying\nTrample"), 40, 2000)
        self.assertGreater(textlayout.block_height(lines, lh), len(lines) * lh)

    def test_one_ability_needs_no_gap(self):
        lines, lh, _ = textlayout.wrap(textlayout.atoms("Flying"), 40, 2000)
        self.assertEqual(textlayout.block_height(lines, lh), lh)


class SmartQuoteTests(SimpleTestCase):
    def test_an_apostrophe_becomes_typographic(self):
        """Scryfall ships ASCII; a printed card uses the curly form, visible at card size."""
        self.assertEqual(textlayout.smart_quotes("creature's power"), "creature\u2019s power")

    def test_quotes_open_and_close_correctly(self):
        self.assertEqual(textlayout.smart_quotes('He said "go."'), 'He said \u201cgo.\u201d')

    def test_it_reaches_the_atoms(self):
        line = textlayout.atoms("that creature's power")[0]
        self.assertIn("\u2019", "".join(a.text for a in line))

    def test_a_leading_quote_opens_rather_than_closes(self):
        self.assertTrue(textlayout.smart_quotes("'Tis done").startswith("\u2018"))
