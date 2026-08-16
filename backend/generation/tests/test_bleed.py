"""Cutting the margin the model paints despite being told not to.

MEASURED on job 9f16e827 (the first frontend run, borderless on): three of five faces came back
matted, at 100% of the sampled edge ring, while the two clean ones sat at 29% and 6% — a snowy
scene lights its own edges, which is why the test is flatness and not brightness.
"""

import io

from django.test import SimpleTestCase
from PIL import Image, ImageDraw

from generation import bleed, check

CANVAS = (448, 600)  # a quarter of the real 1792x2400, same 3:4 proportion


def _scene(size=CANVAS):
    """Something no flat test can pass by accident: noise, not a colour."""
    image = Image.new("RGB", size)
    draw = ImageDraw.Draw(image)
    for y in range(size[1]):
        for x in range(0, size[0], 7):
            draw.point((x, y), fill=((x * 5 + y) % 256, (y * 3) % 256, (x + y * 2) % 256))
        draw.line((0, y, size[0], y), fill=((y * 7) % 200, (y * 3) % 180, (y * 11) % 220))
    return image


def _matted(depth, colour=(244, 239, 227)):
    card = Image.new("RGB", CANVAS, colour)
    art = _scene((CANVAS[0] - depth * 2, CANVAS[1] - depth * 2))
    card.paste(art, (depth, depth))
    return card


def _wash(size=CANVAS):
    """A pale watercolour sky: light at every single edge pixel, but never one flat colour.

    The drift is deliberately smaller than TOLERANCE, because that is the bug — a wash sits well
    inside the tolerance of its own median, so nearness alone cannot tell it from a printed mat.
    """
    image = Image.new("RGB", size)
    pixels = image.load()
    for y in range(size[1]):
        for x in range(size[0]):
            drift = (x * 7 + y * 11) % 40
            pixels[x, y] = (205 + drift, 208 + drift, 214 + drift)
    return image


def _png(image):
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


class MeasureTests(SimpleTestCase):
    def test_a_painted_mat_reads_as_matted(self):
        self.assertGreaterEqual(bleed.matted_share(_matted(18)), bleed.MATTED)

    def test_full_bleed_art_does_not(self):
        self.assertLess(bleed.matted_share(_scene()), bleed.MATTED)

    def test_a_light_scene_is_not_a_mat(self):
        """The card that made this a measurement rather than a threshold: a snow scene is light
        at every edge and must still pass, because its edge is not FLAT."""
        snow = _scene()
        snow = Image.blend(snow, Image.new("RGB", CANVAS, (235, 240, 248)), 0.75)
        self.assertLess(bleed.matted_share(snow), bleed.MATTED)

    def test_a_pale_watercolour_sky_is_not_a_mat(self):
        """MEASURED 2026-08-16, bd mtg-fsw. A correct full-bleed watercolour Serra Angel — cloud
        painted to all four edges, no border anywhere — scored 0.63 against a 0.55 gate and was
        graded UNSOUND for a defect it does not have. Brightness was never the test and neither is
        nearness: a wash varies by less than TOLERANCE, so it reads flat. Flatness itself is what
        separates the two populations — the mats measure 1.0, the washes 9.5 to 16.5.
        """
        wash = _wash()
        self.assertGreater(
            min(min(pixel) for pixel in bleed._ring(wash)),
            bleed.LIGHT,
            "the repro is only honest if every edge pixel really is light",
        )
        self.assertLess(bleed.matted_share(wash), bleed.MATTED)


class TrimTests(SimpleTestCase):
    def test_the_margin_is_cut_and_the_canvas_is_preserved(self):
        png, depth = bleed.trim(_png(_matted(18)))
        trimmed = Image.open(io.BytesIO(png))
        self.assertEqual(trimmed.size, CANVAS, "downstream geometry is in canvas units")
        self.assertGreater(depth, 0)
        self.assertLess(bleed.matted_share(trimmed.convert("RGB")), bleed.MATTED)

    def test_art_that_already_bleeds_is_returned_untouched(self):
        original = _png(_scene())
        png, depth = bleed.trim(original)
        self.assertEqual(png, original)
        self.assertEqual(depth, 0.0)

    def test_a_margin_deeper_than_the_limit_is_left_alone_and_reported(self):
        """Past MAX_DEPTH it is not a margin, it is the picture — cropping it would crop the art,
        so the card is failed instead of quietly mangled."""
        deep = _matted(int(min(CANVAS) * bleed.MAX_DEPTH) + 12)
        png, depth = bleed.trim(_png(deep))
        self.assertEqual(depth, 0.0)
        self.assertIsNotNone(check.matted(Image.open(io.BytesIO(png))))


class GradeTests(SimpleTestCase):
    def test_a_card_that_still_has_a_border_is_a_problem(self):
        problem = check.matted(_matted(18))
        self.assertIsNotNone(problem)
        self.assertEqual(problem.code, "matted")

    def test_a_full_bleed_card_is_not(self):
        self.assertIsNone(check.matted(_scene()))
