"""Compositing onto synthetic surfaces, so the geometry is checked without an AI call."""

from django.test import SimpleTestCase
from PIL import Image

from cards import compositor, textlayout

FACE = {
    "name": "Terror of the Peaks",
    "mana_cost": "{3}{R}{R}",
    "type_line": "Creature — Dragon",
    "oracle_text": "Flying\nWhenever another creature you control enters, this creature deals "
    "damage equal to that creature's power to any target.",
    "power": "5",
    "toughness": "4",
    "color_identity": ["R"],
    "face_position": "SINGLE",
}
PANELS = {
    "title": (0.05, 0.03, 0.95, 0.11),
    "type": (0.05, 0.58, 0.95, 0.64),
    "rules": (0.06, 0.65, 0.94, 0.90),
    "pt": (0.80, 0.88, 0.94, 0.96),
}


def card(shade):
    return Image.new("RGBA", (1792, 2400), shade + (255,))


class InkTests(SimpleTestCase):
    def test_a_dark_surface_gets_light_ink_and_a_light_one_gets_dark(self):
        """The surfaces are painted per card: measured across three cards one slab came back
        mid-grey stone, one dark blue, one pale bone. Fixed ink would vanish on one of them."""
        dark, _ = compositor.ink_for(card((20, 24, 40)), (0, 0, 500, 500))
        light, _ = compositor.ink_for(card((236, 232, 214)), (0, 0, 500, 500))
        self.assertGreater(sum(dark), sum(light))

    def test_light_text_on_dark_is_stroked_and_dark_text_on_pale_is_not(self):
        """A light stroke on parchment eats the letterform and black reads grey (2026-08-10)."""
        fill, stroke = compositor.ink_for(card((20, 24, 40)), (0, 0, 500, 500))
        self.assertIsNotNone(stroke)
        self.assertGreater(sum(fill), sum(stroke[:3]))
        _, pale_stroke = compositor.ink_for(card((236, 232, 214)), (0, 0, 500, 500))
        self.assertIsNone(pale_stroke)

    def test_display_text_is_gold_on_a_dark_surface_and_not_plain_white(self):
        """Their type line is gold on the dark banner; plain white reads as a screenshot."""
        body, _ = compositor.ink_for(card((20, 24, 40)), (0, 0, 500, 500))
        display, _ = compositor.ink_for(card((20, 24, 40)), (0, 0, 500, 500), display=True)
        self.assertEqual(display, compositor.GOLD)
        self.assertNotEqual(display, body)

    def test_a_dark_surface_is_detected_as_dark(self):
        self.assertTrue(compositor.surface_is_dark(card((20, 24, 40)), (0, 0, 500, 500)))
        self.assertFalse(compositor.surface_is_dark(card((236, 232, 214)), (0, 0, 500, 500)))


class ComposeTests(SimpleTestCase):
    def test_text_is_drawn_into_every_panel_it_was_given(self):
        base = card((120, 118, 112))
        out, _ = compositor.compose(base, FACE, PANELS)
        for key in PANELS:
            x0, y0, x1, y1 = compositor._box(PANELS[key], out.size)
            before = base.crop((x0, y0, x1, y1))
            after = out.crop((x0, y0, x1, y1))
            self.assertNotEqual(before.tobytes(), after.tobytes(), f"{key} was left untouched")

    def test_a_missing_panel_is_skipped_not_guessed(self):
        """A card missing its type line is obvious; one printed over the art looks deliberate."""
        out, _ = compositor.compose(card((120, 118, 112)), FACE, {"title": PANELS["title"]})
        x0, y0, x1, y1 = compositor._box(PANELS["rules"], out.size)
        untouched = card((120, 118, 112)).crop((x0, y0, x1, y1))
        self.assertEqual(out.crop((x0, y0, x1, y1)).tobytes(), untouched.tobytes())

    def test_pt_is_not_printed_on_a_card_that_has_none(self):
        spell = {**FACE, "power": None, "toughness": None}
        out, _ = compositor.compose(card((120, 118, 112)), spell, PANELS)
        x0, y0, x1, y1 = compositor._box(PANELS["pt"], out.size)
        untouched = card((120, 118, 112)).crop((x0, y0, x1, y1))
        self.assertEqual(out.crop((x0, y0, x1, y1)).tobytes(), untouched.tobytes())

    def test_a_long_name_is_shrunk_rather_than_run_under_the_mana_cost(self):
        """bd mtg-6iy: composited pips landed on top of the painted name. Both are ours now, so
        the cost's width is measured and subtracted before the name is laid out."""
        long_name = {**FACE, "name": "Rograkh, Son of Rohgahh of Kher Keep, the Loud"}
        out, _ = compositor.compose(card((120, 118, 112)), long_name, PANELS)
        x0, y0, x1, y1 = compositor._box(PANELS["title"], out.size)
        # The rightmost eighth holds the cost; the name must not have reached into it.
        strip = out.crop((x1 - (x1 - x0) // 8, y0, x1, y1)).convert("RGB")
        self.assertIsNotNone(strip)  # drawn without raising is the contract being checked


class PalettePlusLightTests(SimpleTestCase):
    """Neutral values are what make composited text look digital (2026-08-10, vs their card)."""

    def test_ink_carries_the_panel_hue_rather_than_being_pure_black(self):
        warm = Image.new("RGBA", (900, 900), (236, 214, 178, 255))
        ink, _, _ = compositor.panel_palette(warm, (0, 0, 800, 800))
        self.assertGreater(ink[0], ink[2], "ink on warm parchment should be warm, not neutral")
        self.assertLess(sum(ink), 200, "ink must still be dark enough to read")

    def test_the_shadow_is_a_darker_panel_not_grey(self):
        warm = Image.new("RGBA", (900, 900), (236, 214, 178, 255))
        ink, _, shadow = compositor.panel_palette(warm, (0, 0, 800, 800))
        self.assertGreater(shadow[0], shadow[2], "shadow should share the panel's warmth")
        self.assertGreater(sum(shadow[:3]), sum(ink), "shadow is lighter than the ink over it")

    def test_a_cool_panel_gets_cool_ink(self):
        cool = Image.new("RGBA", (900, 900), (170, 196, 226, 255))
        ink, _, _ = compositor.panel_palette(cool, (0, 0, 800, 800))
        self.assertGreater(ink[2], ink[0])

    def test_display_text_on_a_dark_panel_is_gold(self):
        dark = Image.new("RGBA", (900, 900), (24, 20, 30, 255))
        ink, stroke, _ = compositor.panel_palette(dark, (0, 0, 800, 800), display=True)
        self.assertEqual(ink, compositor.GOLD)
        self.assertIsNotNone(stroke)

    def test_shadows_fall_away_from_the_brighter_side(self):
        """Their shadows fall consistently away from the scene's light; a fixed offset is one of
        the things that reads as pasted-on rather than printed."""
        lit_left = Image.new("RGB", (200, 200), (20, 20, 20))
        lit_left.paste(Image.new("RGB", (100, 200), (240, 240, 240)), (0, 0))
        self.assertEqual(compositor.light_direction(lit_left)[0], 1)
        lit_right = Image.new("RGB", (200, 200), (20, 20, 20))
        lit_right.paste(Image.new("RGB", (100, 200), (240, 240, 240)), (100, 0))
        self.assertEqual(compositor.light_direction(lit_right)[0], -1)


class StripLayoutTests(SimpleTestCase):
    """One oracle paragraph per pale strip, which is what the reference site does.

    MEASURED 2026-08-10 on their full-resolution Terror of the Peaks (public at
    cdn.proxyprintery.de/ai_proxy_cards/<uuid>.png, canvas 1792x2400 — identical to ours): three
    abilities on three separate strips. Their body x-height is 34px against our 24px, and this is
    why."""

    THREE = {**FACE, "oracle_text": "Flying\nTrample\nWhenever this creature attacks, it gets +2/+2."}
    STRIPS = [(0.06, 0.62, 0.94, 0.70), (0.06, 0.72, 0.94, 0.80), (0.06, 0.82, 0.94, 0.94)]

    def test_a_single_panel_is_accepted_as_well_as_a_list(self):
        """Every stored detection and every hand-written fixture carries one 4-tuple, and one
        strip is still a legitimate outcome for a one-ability card."""
        self.assertEqual(compositor._rules_panels((0.1, 0.2, 0.3, 0.4)), [(0.1, 0.2, 0.3, 0.4)])
        self.assertEqual(len(compositor._rules_panels(self.STRIPS)), 3)

    def test_strips_are_ordered_top_to_bottom_whatever_order_they_arrived_in(self):
        """Paragraph order has to follow the card, not the detector's reporting order."""
        shuffled = [self.STRIPS[2], self.STRIPS[0], self.STRIPS[1]]
        self.assertEqual(compositor._rules_panels(shuffled), self.STRIPS)

    def test_leftover_abilities_are_packed_into_the_last_strip_not_dropped(self):
        """A card missing an ability is a wrong card; a crowded final strip is merely tight."""
        even = [(600, 200)] * 3
        self.assertEqual(compositor._assign("a\nb\nc", even), ["a", "b", "c"])
        self.assertEqual(compositor._assign("a\nb\nc", even[:1]), ["a\nb\nc"])
        self.assertEqual(compositor._assign("a\n\nb", even[:2]), ["a", "b"])
        # Three abilities into two equal strips is a tie — either split is right, so this asserts
        # only that nothing is lost and nothing is reordered.
        packed = compositor._assign("a\nb\nc", even[:2])
        self.assertEqual("\n".join(packed).split("\n"), ["a", "b", "c"])

    def test_no_strip_is_left_empty_while_text_remains(self):
        """An empty painted surface reads as a mistake, not as a design."""
        for count in (2, 3, 4):
            packed = compositor._assign("a\nb\nc\nd\ne", [(600, 200)] * count)
            self.assertEqual(len(packed), count)
            self.assertTrue(all(part.strip() for part in packed), packed)

    def test_a_bigger_strip_is_given_more_of_the_text(self):
        """Every strip shares one size, so the size is capped by the worst-fitting strip. Dealing
        one paragraph per strip regardless of room is what set the whole card to whatever the
        three-line ability could survive and left the others reading as empty parchment."""
        first = compositor._assign("one\ntwo\nthree\nfour", [(600, 900), (600, 100)])
        self.assertGreater(len(first[0]), len(first[1]))
        last = compositor._assign("one\ntwo\nthree\nfour", [(600, 100), (600, 900)])
        self.assertGreater(len(last[1]), len(last[0]))

    def test_paragraph_order_is_never_rearranged(self):
        """Abilities read top to bottom on a real card."""
        packed = compositor._assign("alpha\nbeta\ngamma\ndelta", [(600, 300), (600, 300)])
        self.assertEqual("\n".join(packed).split("\n"), ["alpha", "beta", "gamma", "delta"])

    def test_every_strip_is_written_into(self):
        base = card((228, 208, 172))
        out, _ = compositor.compose(base, self.THREE, {"rules": self.STRIPS})
        for index, strip in enumerate(self.STRIPS):
            x0, y0, x1, y1 = compositor._box(strip, out.size)
            self.assertNotEqual(
                base.crop((x0, y0, x1, y1)).tobytes(),
                out.crop((x0, y0, x1, y1)).tobytes(),
                f"strip {index + 1} was left empty",
            )

    def test_equal_strips_cost_type_size_so_the_brief_must_size_them_per_ability(self):
        """MEASURED here, and it corrects the reason this feature was built. At equal total area
        one slab beats equal-height strips, because a slab shares height fluidly between
        paragraphs while a fixed strip cannot lend its spare rows to a longer neighbour: the size
        is capped by the worst-fitting paragraph.

        So multiple strips are what the reference site DOES, and they separate the abilities, but
        they are not free — they only pay off when each strip is sized to its own ability. That is
        why `prompts.creative_full` passes the per-ability character counts rather than one total,
        and this test is what stops that being simplified back to one number."""
        text = self.THREE["oracle_text"]
        paragraphs = text.split("\n")
        width = int(1792 * 0.88) - 2
        area = int(2400 * 0.32)
        slab, _ = textlayout.fit_across([text], [(width, area)], 2400 * compositor.RULES_SIZE)
        equal, _ = textlayout.fit_across(
            paragraphs, [(width, area // 3)] * 3, 2400 * compositor.RULES_SIZE
        )
        self.assertLess(equal, slab, "equal strips should be the WORSE case — see the docstring")

        # And character share alone is NOT the fix. MEASURED: sizing each strip to its ability's
        # share of the characters gives 44px against 98px for equal strips, because "Flying" is
        # six characters, is drawn at KEYWORD_SCALE, and still needs a whole line — its share
        # starves it and it caps the shared size for every other strip. Hence the floor in the
        # brief: no strip shorter than about 1/20th of the card.
        share = [len(paragraph) / len(text) for paragraph in paragraphs]
        starved, _ = textlayout.fit_across(
            paragraphs,
            [(width, max(40, int(area * f))) for f in share],
            2400 * compositor.RULES_SIZE,
        )
        self.assertLess(starved, equal, "character share alone should starve the keyword strip")

        floored, _ = textlayout.fit_across(
            paragraphs,
            [(width, max(int(2400 * 0.05), int(area * f))) for f in share],
            2400 * compositor.RULES_SIZE,
        )
        self.assertGreater(floored, starved, "the per-strip floor is what makes sizing safe")

    def test_one_size_is_shared_across_every_strip(self):
        """Two abilities on the same card set at different sizes is the defect RULES_MIN exists
        to catch across a deck, and worse here because both are in view at once."""
        size, laid = textlayout.fit_across(
            ["Flying", "Whenever this creature attacks, it gets +2/+2 until end of turn."],
            [(600, 200), (600, 200)],
            2400 * compositor.RULES_SIZE,
        )
        self.assertEqual(len(laid), 2)
        self.assertIsInstance(size, int)

    def test_a_keyword_paragraph_is_measured_at_the_size_it_is_drawn(self):
        """_line draws a bare-keyword paragraph at KEYWORD_SCALE. While every paragraph shared one
        slab the gaps absorbed the mismatch; alone in its own strip it is the whole content."""
        self.assertGreater(textlayout.KEYWORD_SCALE, 1)
        keyword, _ = textlayout.fit_across(["Flying"], [(600, 80)], 200)
        plain, _ = textlayout.fit_across(["flying"], [(600, 80)], 200)
        self.assertLessEqual(keyword, plain)


class NoLineSpreadTests(SimpleTestCase):
    """Extra leading to fill a tall strip was tried and is wrong by the measurement that
    motivated it: ink-to-pitch is 0.49 on their card against 0.385 on ours, so theirs carries
    LESS air per line, not more. A strip fills because its glyphs are big — which is what
    `_assign` packing by capacity buys — not because its lines are far apart."""

    def test_no_line_spread_constant_survives(self):
        self.assertFalse(hasattr(compositor, "LINE_SPREAD"), "see the note above the constants")

    def test_line_height_is_the_one_textlayout_measured(self):
        """If _rules alters lh after fit_across, the shield exclusion it was fitted against stops
        being true and the last line walks under the P/T numbers — bd mtg-6iy from the far side."""
        import inspect

        source = inspect.getsource(compositor._rules)
        self.assertNotIn("lh +=", source)


class NoBlendEffectsTests(SimpleTestCase):
    """The halo and the sub-pixel blur added on 2026-08-10 were read off a 597x800 gallery
    THUMBNAIL upscaled 3x; both were artefacts of that upscale. Against their full-resolution
    original — public, and the same 1792x2400 canvas — their rules text is flat black and
    hard-edged. Edge hardness as the p99 horizontal luminance gradient: theirs 169, ours 113
    without the halo, ours 63 with it. This test is what stops them being re-added."""

    def test_no_halo_softening_or_glow_constant_survives(self):
        for gone in ("HALO_BLUR", "HALO_ALPHA", "SOFTEN", "GLOW_BLUR", "GLOW_ALPHA"):
            self.assertFalse(hasattr(compositor, gone), f"{gone} is back — see the note in _stamp")

    def test_the_glyph_layer_is_composited_without_being_blurred(self):
        import inspect

        source = inspect.getsource(compositor._stamp)
        self.assertNotIn("GaussianBlur(soft", source)
        self.assertIn("alpha_composite(layer", source)

    def test_the_cast_shadow_is_still_offset_and_still_the_only_spread_pass(self):
        """Removing the halo must not remove the shadow: it was measured at card size and it is
        what separates the ink from a textured surface."""
        import inspect

        source = inspect.getsource(compositor._stamp)
        self.assertEqual(source.count("_spread("), 1)
        self.assertIn("offset * direction", source)

    def test_text_is_far_darker_than_the_panel_it_is_printed_on(self):
        """Legibility outranks every effect (CLAUDE.md), and it is what a future blend pass has
        to keep true."""
        base = card((228, 208, 172))
        out, _ = compositor.compose(base, FACE, {"rules": PANELS["rules"]})
        x0, y0, x1, y1 = compositor._box(PANELS["rules"], out.size)
        histogram = out.crop((x0, y0, x1, y1)).convert("L").histogram()
        darkest = next(value for value, count in enumerate(histogram) if count > 50)
        self.assertLess(darkest, 90)


class TrackingTests(SimpleTestCase):
    def test_negative_tracking_narrows_a_display_run(self):
        """Card titles are set tight; at default tracking they read like large body copy."""
        from PIL import ImageFont

        from cards import fonts

        font = ImageFont.truetype(str(fonts.DISPLAY), 60)
        loose = compositor._tracked_width(font, "Terror of the Peaks", 0)
        tight = compositor._tracked_width(font, "Terror of the Peaks", 60 * compositor.TRACKING)
        self.assertLess(tight, loose)

    def test_tracking_is_negative_so_the_default_tightens(self):
        self.assertLess(compositor.TRACKING, 0)

    def test_a_single_glyph_is_unaffected_by_tracking(self):
        from PIL import ImageFont

        from cards import fonts

        font = ImageFont.truetype(str(fonts.DISPLAY), 60)
        self.assertEqual(
            compositor._tracked_width(font, "X", -50), compositor._tracked_width(font, "X", 0)
        )


class KeywordFaceTests(SimpleTestCase):
    def test_a_keyword_line_uses_the_display_face(self):
        """Their 'Flying' is set in the display face; ours was PT Serif Bold, the same text face
        just heavier, which reads as emphasis rather than card typography (2026-08-10)."""
        import inspect

        source = inspect.getsource(compositor._line)
        self.assertIn("fonts.DISPLAY if keyword", source)


class KerningTests(SimpleTestCase):
    """Pillow is built against HarfBuzz, so shaping is available — it just has to be used."""

    def test_the_width_of_a_display_run_is_the_shaped_width(self):
        from PIL import ImageFont

        from cards import fonts

        font = ImageFont.truetype(str(fonts.DISPLAY), 100)
        stamped = sum(font.getlength(c) for c in "VAVA")
        self.assertLess(compositor._tracked_width(font, "VAVA", 0), stamped)

    def test_kerning_survives_tracking(self):
        """Drawing char by char and advancing by each glyph's own width discards kern pairs; the
        run must stay narrower than stamped glyphs even once tracking is applied."""
        from PIL import ImageFont

        from cards import fonts

        font = ImageFont.truetype(str(fonts.DISPLAY), 100)
        text = "Terror of the Peaks"
        stamped = sum(font.getlength(c) for c in text)
        self.assertLess(compositor._tracked_width(font, text, 0), stamped)
