"""Cutting the margin the model paints despite being told not to.

MEASURED on job 9f16e827 (the first frontend run, borderless on): three of five faces came back
matted, at 100% of the sampled edge ring, while the two clean ones sat at 29% and 6% — a snowy
scene lights its own edges, which is why the test is flatness and not brightness.
"""

import io
import unittest
from pathlib import Path

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


def _rounded(radius=22, size=CANVAS):
    """Full-bleed art with the model's own rounded card silhouette cut out of it, on paper white.

    This is bd mtg-w31 as the model actually paints it: the four straight edges bleed correctly and
    only the corner arcs are paper. Nothing about it is a mat, which is exactly why `matted_share`
    scores it near zero.
    """
    card = _scene(size)
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius, fill=255)
    paper = Image.new("RGB", size, (255, 255, 255))
    paper.paste(card, (0, 0), mask)
    return paper


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


class RoundedCornerTests(SimpleTestCase):
    """bd mtg-w31. The model paints the card as an OBJECT — a rounded card on paper — instead of
    an image that IS the card. Measured on 2 of 74 stored cards, and card 03 of
    FIXVERIFY-2026-08-17 shipped one.
    """

    def test_a_ring_test_cannot_see_a_corner(self):
        """Why this needed new machinery rather than a tuned threshold. Obliterator measured
        matted_share 0.014 against a 0.55 gate with a plainly visible white wedge at every
        corner: `_ring` walks a line one INSET in from each edge, which is flat scene."""
        self.assertLess(bleed.matted_share(_rounded()), bleed.MATTED)

    def test_the_arcs_are_cut_and_the_canvas_is_preserved(self):
        png, depth = bleed.trim(_png(_rounded()))
        trimmed = Image.open(io.BytesIO(png))
        self.assertEqual(trimmed.size, CANVAS, "downstream geometry is in canvas units")
        self.assertGreater(depth, 0)
        self.assertFalse(bleed._rounded_card(trimmed.convert("RGB")))

    def test_all_four_corners_are_required_not_one(self):
        """A snow scene or a white robe touches the trim on plenty of correct cards. An earlier
        version took the deepest paper run anywhere along any edge and fired on 27 of 84 stored
        images, most of them Elesh Norn. A card silhouette has four rounded corners, so one
        corner is noise and four is the signature."""
        one = _scene()
        one.paste(Image.new("RGB", (30, 30), (255, 255, 255)), (0, 0))
        self.assertFalse(bleed._rounded_card(one))
        self.assertEqual(bleed.corner_depth(one), 0)

    def test_a_pale_wash_to_the_edge_is_not_a_rounded_card(self):
        """`LIGHT` (185) is the wrong threshold here — PAPER is 242, fitted between the model's
        own ground at 254-255 and the palest real scene measured at 231."""
        self.assertFalse(bleed._rounded_card(_wash()))

    def test_an_arc_deeper_than_the_ceiling_is_left_for_the_grade(self):
        """Past CORNER_MAX_DEPTH it is a picture inset in a background, not a rounded corner, and
        cropping it would take art."""
        deep = _rounded(radius=int(min(CANVAS) * bleed.CORNER_MAX_DEPTH) + 40)
        self.assertEqual(bleed.corner_depth(deep), 0)


class GradeTests(SimpleTestCase):
    def test_a_card_that_still_has_a_border_is_a_problem(self):
        problem = check.matted(_matted(18))
        self.assertIsNotNone(problem)
        self.assertEqual(problem.code, "matted")

    def test_a_full_bleed_card_is_not(self):
        self.assertIsNone(check.matted(_scene()))


class DarkMatTests(SimpleTestCase):
    """CLIENT 2026-08-17: "the sol ring comes as a card not full bleed creative full art".

    It came back as a card silhouette on a flat near-black ground — the defect circled on
    2026-08-13 — and both gates passed it, because `LIGHT` only ever looked for a cream, bone or
    white mat. Its own docstring said so: "every mat seen so far is cream, bone or white". That held
    over the 84 images it was fitted on and failed on the 85th, since `art_deco` mats in the dark.
    """

    DARK = (50, 53, 60)  # the measured ring on that card

    def test_a_dark_mat_is_seen(self):
        image = _matted(60, colour=self.DARK)
        self.assertGreaterEqual(bleed.matted_share(image), bleed.MATTED)

    def test_a_dark_mat_is_cut(self):
        """20 and not 60: on this canvas MAX_DEPTH is 44px, and a mat deeper than the ceiling is
        one `trim` refuses on purpose and leaves for `matted` — the case below."""
        _, depth = bleed.trim(_png(_matted(20, colour=self.DARK)))
        self.assertGreater(depth, 0.0)

    def test_a_dark_mat_too_deep_to_cut_is_left_for_the_grader(self):
        _, depth = bleed.trim(_png(_matted(60, colour=self.DARK)))
        self.assertEqual(depth, 0.0)
        self.assertGreaterEqual(bleed.matted_share(_matted(60, colour=self.DARK)), bleed.MATTED)

    def test_a_light_mat_still_goes_through_the_light_route(self):
        """The additive path must not disturb the one with every fitted threshold behind it."""
        self.assertGreaterEqual(bleed.matted_share(_matted(60)), bleed.MATTED)

    def test_a_painted_scene_is_not_a_mat_however_dark_it_is(self):
        """The reason the dark route is far tighter than the light one: a night scene can approach
        a flat dark edge where nothing approaches a flat pale one."""
        self.assertLess(bleed.matted_share(_scene()), bleed.MATTED)
        self.assertLess(bleed.matted_share(_wash()), bleed.MATTED)

    def test_the_grey_ground_this_route_was_built_for_still_fails(self):
        """Paired with `BlackSurroundTests` on purpose: standing down on black must not stand down
        on the 50-60 grey that bought this route in the first place."""
        self.assertGreater(max(self.DARK), bleed.BLACK)
        self.assertGreaterEqual(bleed.matted_share(_matted(60, colour=self.DARK)), bleed.MATTED)

    def test_a_dark_wash_is_not_a_dark_mat(self):
        """DARK_MAT_FLAT is 2.0 against FLAT_MAX's 4.0, because a night sky can approach a flat
        dark edge where nothing approaches a flat pale one. A gradient is the case that must not
        read as a printed border."""
        image = Image.new("RGB", CANVAS)
        pixels = image.load()
        for y in range(CANVAS[1]):
            for x in range(CANVAS[0]):
                drift = (x * 7 + y * 11) % 40
                pixels[x, y] = (34 + drift, 37 + drift, 44 + drift)
        self.assertLess(bleed.matted_share(image), bleed.MATTED)


class BlackSurroundTests(SimpleTestCase):
    """CLIENT 2026-08-13: "id be okay with black borders or black going around".

    The dark route above was fitted to one card on 2026-08-17 and, until this, fired on three of
    the client's nineteen favorites — Avacyn, Hullbreaker and Howling Mine all ring 1.000 flat at a
    peak channel of 1, 1 and 3. Each one sets an illustrated frame inside a flat black surround,
    which is the look he asked for, and each would have been repainted for having it.

    `Phase 4` of PLAN-EXEMPLAR-PIVOT. The axis is pale-versus-dark and, within dark,
    black-versus-grey — see `bleed.BLACK` for the calibration and for the one card above it.
    """

    BLACK = (1, 1, 1)  # his Avacyn and his Hullbreaker, measured
    NEARLY = (2, 3, 2)  # his Howling Mine

    def test_a_black_surround_is_not_a_mat(self):
        for colour in (self.BLACK, self.NEARLY, (0, 0, 0)):
            with self.subTest(colour=colour):
                self.assertLess(bleed.matted_share(_matted(60, colour=colour)), bleed.MATTED)

    def test_a_black_surround_is_not_cut(self):
        """His run 11-23% deep, past MAX_DEPTH, so `trim` already left them alone. A shallow one
        is the case that would have been cropped, and it is the one worth asserting."""
        png = _png(_matted(20, colour=self.BLACK))
        trimmed, depth = bleed.trim(png)
        self.assertEqual(depth, 0.0)
        self.assertEqual(trimmed, png, "the bytes came back changed — something cropped it")

    def test_a_black_surround_is_not_reported(self):
        """The gate that carried the entire cost of this bug: `trim` left these cards whole and
        `matted` failed them anyway, which is a paid repaint per card."""
        self.assertIsNone(check.matted(_matted(60, colour=self.BLACK)))

    def test_a_white_mat_still_fails(self):
        """The whole point of the module. Standing down on black must cost nothing here."""
        self.assertIsNotNone(check.matted(_matted(18)))
        self.assertIsNotNone(check.matted(_matted(60, colour=(255, 255, 255))))

    def test_a_grey_ground_still_fails(self):
        self.assertIsNotNone(check.matted(_matted(60, colour=(50, 53, 60))))


class ClientCorpusTests(SimpleTestCase):
    """All nineteen of his favorites, against the gates that judge our own cards.

    This is the test that was missing. Every threshold in this module was fitted on OUR output, so
    nothing ever asked whether the gates would pass the cards the client actually chose — and three
    of them did not. A corpus test is the only shape of check that could have caught it.
    """

    CLIENT = (
        Path(__file__).resolve().parents[4] / "Project Material" / "CLIENT-FAVORITES-2026-08-19"
    )

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if not cls.CLIENT.is_dir():
            raise unittest.SkipTest(f"{cls.CLIENT} is not checked out — client art is not code")

    def test_not_one_of_his_favorites_reads_as_matted(self):
        failed = []
        cards = sorted(self.CLIENT.rglob("*.png"))
        self.assertEqual(19, len(cards), "the folder changed — recalibrate before trusting this")
        for path in cards:
            with Image.open(path) as image:
                if check.matted(image.convert("RGB")) is not None:
                    failed.append(path.name)
        self.assertEqual([], failed, "cards the client picked, which we would repaint")
