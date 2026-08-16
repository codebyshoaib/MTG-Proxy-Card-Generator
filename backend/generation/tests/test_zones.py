"""The measurement behind bd mtg-9ww, which failed in two opposite directions at once.

Both directions are tested here. A metric that only caught dead space would have scored the third
failure — a lower third BUSIER than the card average — as a success.

The numbers asserted against are the ones measured over all 56 stored blanks on 2026-08-16:
`substance` 4.30 to 50.21 on real cards against 0.29 for a painted-blank control, `liveliness`
0.58 to 1.14. The gap between a quiet lower third and a dead one is 15x, which is why the module
draws no threshold and neither does this file.
"""

from django.test import SimpleTestCase
from PIL import Image, ImageDraw

from generation import zones

CANVAS = (300, 420)
SPLIT = round(CANVAS[1] * 2 / 3)


def _card(lower_third):
    """A card whose top two thirds are always busy, and whose lower third is what varies."""
    image = Image.new("RGB", CANVAS, (30, 30, 40))
    draw = ImageDraw.Draw(image)
    for y in range(0, SPLIT, 3):
        draw.line((0, y, CANVAS[0], y), fill=(200, 190, 170))
    lower_third(draw)
    return image


def _blank(draw):
    """The dead-space failure: the model stopped painting and left a flat panel."""
    draw.rectangle([0, SPLIT, CANVAS[0], CANVAS[1]], fill=(60, 58, 55))


def _continues(draw):
    """The scene going quiet — still material, at low contrast. What the brief now asks for."""
    for y in range(SPLIT, CANVAS[1], 3):
        draw.line((0, y, CANVAS[0], y), fill=(70, 68, 64))


def _clutter(draw):
    for y in range(SPLIT, CANVAS[1], 2):
        draw.line((0, y, CANVAS[0], y), fill=(255, 255, 255))


class SubstanceTests(SimpleTestCase):
    """The dead-space direction, which is the one `liveliness` alone cannot see."""

    def test_a_quiet_lower_third_and_a_dead_one_are_far_apart(self):
        """Not a threshold — the point is the size of the gap. Measured 15x on real cards."""
        self.assertGreater(zones.substance(_card(_continues)), zones.substance(_card(_blank)) * 10)

    def test_a_lower_third_that_stopped_into_a_panel_has_almost_nothing_in_it(self):
        self.assertLess(zones.substance(_card(_blank)), 1.0)

    def test_going_quiet_is_not_the_same_as_going_blank(self):
        """The trap this whole module exists to avoid: the brief ASKS for a quiet lower third, so
        quiet must not read as a fault. This card is compliant and must measure as having
        material in it."""
        self.assertGreater(zones.substance(_card(_continues)), 4.0)


class LivelinessTests(SimpleTestCase):
    """The opposite direction: a band competing with the subject."""

    def test_a_lower_third_busier_than_the_card_reads_above_one(self):
        self.assertGreater(zones.liveliness(_card(_clutter)), 1.05)

    def test_a_compliant_quiet_lower_third_reads_below_one(self):
        self.assertLess(zones.liveliness(_card(_continues)), 1.0)

    def test_a_card_with_no_edges_at_all_does_not_divide_by_zero(self):
        self.assertEqual(zones.liveliness(Image.new("RGB", CANVAS, (10, 10, 10))), 0.0)
