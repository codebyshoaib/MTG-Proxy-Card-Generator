"""The structural verify step, and the retry it drives.

Every case here fired on a real card during the 2026-08-10/11 batches. The point of the module is
that each was caught only because a human happened to be looking at the output.
"""

from django.test import SimpleTestCase

from generation import check

CREATURE = {"power": "5", "toughness": "4"}
SPELL = {"power": None}
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


class RetryWiringTests(SimpleTestCase):
    def test_the_command_repaints_on_a_fault_and_stops_at_the_attempt_limit(self):
        """One retry, not more: measured across the batches, about one card in five needs a
        second attempt and a card that fails twice usually keeps failing. `--from` must never
        repaint, because there is nothing to repaint — the art came off disk."""
        import inspect as _inspect

        from generation.management.commands import compose_card

        source = _inspect.getsource(compose_card)
        self.assertIn("problems = check.inspect(", source)
        self.assertIn("if not problems or source or attempt >= max(1, attempts)", source)
        self.assertIn('"--attempts"', source)
