"""The structural verify step, and the retry it drives.

Every case here fired on a real card during the 2026-08-10/11 batches. The point of the module is
that each was caught only because a human happened to be looking at the output.
"""

from django.test import SimpleTestCase

from generation import check, panels as panels_module

CREATURE = {"power": "5", "toughness": "4", "oracle_text": "Trample"}
SPELL = {"power": None, "oracle_text": "Counter target spell."}
SOUND = {
    "title": (0.10, 0.06, 0.90, 0.12),
    "type": (0.10, 0.60, 0.90, 0.66),
    "rules": [(0.10, 0.67, 0.90, 0.90)],
    "pt": (0.80, 0.85, 0.93, 0.95),
}


def codes(face, panels, overflowed=False):
    return [problem.code for problem in check.inspect(face, panels, overflowed)]


class SoundCardTests(SimpleTestCase):
    def test_a_well_formed_card_reports_nothing(self):
        self.assertEqual(check.inspect(CREATURE, SOUND, False), [])

    def test_a_spell_needs_no_power_toughness_surface(self):
        panels = {k: v for k, v in SOUND.items() if k != "pt"}
        self.assertEqual(check.inspect(SPELL, panels, False), [])


class MissingSurfaceTests(SimpleTestCase):
    def test_a_missing_name_plate_is_a_fault(self):
        """Sol Ring came back with no top plate at all, so its name went unprinted — and the run
        looked successful."""
        panels = {k: v for k, v in SOUND.items() if k != "title"}
        self.assertIn("missing_title", codes(CREATURE, panels))

    def test_a_creature_with_no_pt_surface_is_a_fault(self):
        panels = {k: v for k, v in SOUND.items() if k != "pt"}
        self.assertIn("missing_pt", codes(CREATURE, panels))

    def test_every_missing_text_surface_is_reported_not_just_the_first(self):
        """A caller deciding whether to repaint wants the whole picture, not one symptom."""
        self.assertEqual(
            sorted(codes(SPELL, {})),
            ["missing_rules", "missing_title", "missing_type"],
        )


class OrderTests(SimpleTestCase):
    def test_a_name_plate_below_the_top_is_a_fault(self):
        """Terror of the Peaks and Raphael both came back with it halfway down the card. The ten
        reference-site generations of one card put it at the top on 10 of 10 while everything
        else about the layout moved, so the order is the one thing safe to assert."""
        panels = {**SOUND, "title": (0.10, 0.58, 0.90, 0.65)}
        self.assertIn("title_out_of_order", codes(CREATURE, panels))

    def test_the_threshold_allows_the_normal_range_of_top_plates(self):
        for y in (0.03, 0.09, 0.14, 0.24):
            with self.subTest(y=y):
                panels = {**SOUND, "title": (0.10, y, 0.90, y + 0.06)}
                self.assertNotIn("title_out_of_order", codes(CREATURE, panels))

    def test_a_type_plate_above_the_name_plate_is_a_fault(self):
        panels = {**SOUND, "title": (0.10, 0.20, 0.90, 0.26), "type": (0.10, 0.08, 0.90, 0.14)}
        self.assertIn("type_above_title", codes(CREATURE, panels))

    def test_a_rules_panel_above_the_type_plate_is_a_fault(self):
        panels = {**SOUND, "rules": [(0.10, 0.30, 0.90, 0.55)]}
        self.assertIn("rules_above_type", codes(CREATURE, panels))

    def test_the_topmost_strip_is_what_counts_when_there_are_several(self):
        """The model paints a second pale strip on a fair share of cards even though the brief
        asks for one, and it is the highest of them that has to clear the type plate."""
        panels = {**SOUND, "rules": [(0.10, 0.70, 0.90, 0.80), (0.10, 0.40, 0.90, 0.55)]}
        self.assertIn("rules_above_type", codes(CREATURE, panels))


class OverflowTests(SimpleTestCase):
    def test_text_that_does_not_fit_is_a_fault(self):
        """compositor already computed this; nothing acted on it before."""
        self.assertIn("text_too_small", codes(CREATURE, SOUND, overflowed=True))


class BlankSurfaceTests(SimpleTestCase):
    """CLIENT 2026-08-13, circling the second dark bar under Raphael's type line: "on one of them
    it has 2 creature type text boxes, here it looks kind of natural but i have seen these as
    errors many times". The defect is a painted surface with nothing printed on it, and the brief
    had already been told the count twice."""

    def test_a_spare_surface_the_detector_reports_is_a_fault(self):
        panels = {**SOUND, "spare": [(0.10, 0.66, 0.90, 0.70)]}
        self.assertIn("blank_surface", codes(CREATURE, panels))

    def test_more_pale_strips_than_paragraphs_is_the_same_fault(self):
        """The other way in. `compositor._rules` slices `boxes[: len(paragraphs)]`, so a third
        strip on a one-ability card is not printed into and is left bare — identical to a customer,
        so it carries the same code rather than passing as a layout the compositor coped with."""
        panels = {**SOUND, "rules": [(0.10, 0.67, 0.90, 0.78), (0.10, 0.80, 0.90, 0.90)]}
        self.assertIn("blank_surface", codes(CREATURE, panels))

    def test_a_strip_per_paragraph_is_not_a_fault(self):
        """The brief asks for one slab, but the model paints one strip per ability on a fair share
        of cards and the compositor deals paragraphs across them by capacity. Two strips for two
        abilities is a card that prints correctly, not a defect."""
        two = {**CREATURE, "oracle_text": "Flying\nTrample"}
        panels = {**SOUND, "rules": [(0.10, 0.67, 0.90, 0.78), (0.10, 0.80, 0.90, 0.90)]}
        self.assertNotIn("blank_surface", codes(two, panels))

    def test_a_legacy_single_box_is_not_counted_as_four_strips(self):
        """Every stored detection and several hand-written tests carry `rules` as a bare 4-tuple.
        Counted without unwrapping it that is four strips on a one-ability card, which would
        repaint every one of them."""
        panels = {**SOUND, "rules": (0.10, 0.67, 0.90, 0.90)}
        self.assertNotIn("blank_surface", codes(CREATURE, panels))


class PaintedMarkTests(SimpleTestCase):
    def test_painted_lettering_or_a_set_symbol_is_a_fault(self):
        """CLIENT 2026-08-13: "these are set symbols ... but these are proxies that dont have a set
        so its just a random symbol and actually sometimes ive seen it put a real symbol on the card
        which isnt good". The brief has banned painted writing since the first Creative Full card
        and Raphael still came back with a band of runes, so the ban alone does not hold — and a
        REAL expansion symbol is a Wizards mark printed on a proxy."""
        panels = {**SOUND, "marks": [(0.80, 0.61, 0.88, 0.66)]}
        self.assertIn("painted_marks", codes(CREATURE, panels))

    def test_a_clean_card_reports_neither_new_fault(self):
        self.assertEqual(check.inspect(CREATURE, {**SOUND, "spare": [], "marks": []}, False), [])

    def test_a_mark_in_the_pt_corner_is_the_shield_and_is_dropped(self):
        """MEASURED 2026-08-13 on the first two borderless creatures: the detector reported the
        blank P/T shield as a painted mark on 4 of 4 runs before the wording was tightened and 1 of
        4 after — it is the same object every time, a small blank badge in the bottom-right corner.
        A real set symbol sits at the right-hand end of the TYPE LINE, nowhere near this region, so
        dropping it here costs nothing a repaint would have bought."""
        self.assertTrue(panels_module._in_pt_corner((0.76, 0.82, 0.94, 0.96)))
        # The type line's right-hand end — where a real expansion symbol goes — must still count.
        self.assertFalse(panels_module._in_pt_corner((0.78, 0.61, 0.90, 0.66)))

    def test_every_fault_the_check_acts_on_is_both_asked_for_and_explained(self):
        """The silent-failure mode for this whole mechanism: a key in the response schema that the
        prompt never describes comes back empty on every card, and the two defects the client
        reported stop being detected with nothing anywhere saying so."""
        for key in panels_module.FAULTS:
            with self.subTest(key=key):
                self.assertIn(key, panels_module.SCHEMA["properties"])
                self.assertIn(f'"{key}"', panels_module.PROMPT)


class MarkPlacementTests(SimpleTestCase):
    """Where a mark lands decides whether it is a defect.

    MEASURED on Delver of Secrets, job 9f16e827 and c66d6b93: the arcane script around the
    wizard's hands failed the card on both runs and the repaint painted it again, because a card
    about reading magic has writing in its art. Meanwhile the marks the client actually reported
    — a rune band under a type line, a set symbol at the type line's end — are all ON furniture.
    """

    def test_script_out_in_the_artwork_is_illustration_and_not_a_fault(self):
        art = {**SOUND, "marks": [(0.30, 0.22, 0.42, 0.34)]}
        self.assertNotIn("painted_marks", codes(CREATURE, art))

    def test_a_set_symbol_at_the_type_line_end_is_still_a_fault(self):
        """The client's own report: "these are proxies that dont have a set so its just a random
        symbol". Our type line is centred, so the plate's right end is not covered by our text."""
        panels = {**SOUND, "marks": [(0.80, 0.61, 0.88, 0.66)]}
        self.assertIn("painted_marks", codes(CREATURE, panels))

    def test_writing_pressed_against_a_plate_is_still_a_fault(self):
        """Raphael's band of runes sat directly under the type line rather than on it."""
        panels = {**SOUND, "marks": [(0.20, 0.665, 0.50, 0.685)]}
        self.assertIn("painted_marks", codes(CREATURE, panels))

    def test_a_long_flat_band_is_a_fault_wherever_it_sits(self):
        """Shaped like a line of card text, in open art, well clear of every plate."""
        panels = {**SOUND, "marks": [(0.15, 0.35, 0.85, 0.40)]}
        self.assertIn("painted_marks", codes(CREATURE, panels))
