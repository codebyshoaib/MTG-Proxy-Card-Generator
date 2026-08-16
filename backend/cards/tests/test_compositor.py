"""Compositing onto synthetic surfaces, so the geometry is checked without an AI call."""

from django.test import SimpleTestCase
from PIL import Image, ImageDraw

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


class PTSizeTests(SimpleTestCase):
    """CLIENT 2026-08-16: "some P/T are large some small".

    `_display` sized the P/T at `box_height * PT_SIZE`. PT_SIZE is fixed, the box is not: across
    nine cards generated that day `panels.detect` returned P/T boxes from 0.050 to 0.180 of the
    card's height, so the numerals ran 74 to 268 px on identically sized cards — a 3.6x spread of
    the same field. Nothing tied the P/T to the CARD; it was sized by whatever tab the model
    happened to paint, and moving PT_SIZE moves every card together without narrowing the spread.

    The size is now taken from the card and only clamped to fit the box, so a tiny tab no longer
    drags the numerals down with it.
    """

    def _pt_height(self, pt_box):
        return compositor._pt_size(compositor._box(pt_box, (1792, 2400)), 2400)

    def test_the_spread_across_the_measured_boxes_is_far_below_the_old_one(self):
        heights = [self._pt_height((0.80, y0, 0.94, y1)) for y0, y1 in (
            (0.890, 0.940), (0.880, 0.940), (0.840, 0.940),
            (0.820, 0.930), (0.860, 0.980), (0.780, 0.960),
        )]
        self.assertLess(max(heights) / min(heights), 2.2, heights)

    def test_the_numerals_still_fit_the_tab_they_are_printed_on(self):
        for y0, y1 in ((0.890, 0.940), (0.780, 0.960)):
            box = compositor._box((0.80, y0, 0.94, y1), (1792, 2400))
            self.assertLessEqual(compositor._pt_size(box, 2400), box[3] - box[1])


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

    def test_the_cost_shrinks_with_the_name_instead_of_crowding_it(self):
        """CLIENT 2026-08-16, on Craterhoof ({5}{G}{G}{G}): "the mana symbols are a bit large on
        this card." The pips were not drawn bigger — the name was drawn smaller, because the pip
        was sized once from the plate and the name then shrank around it. Four pips crushed the
        name; Raphael's two did not, which is why only one of the two cards drew the complaint.

        So the check is a RATIO, not a size. Both are allowed to shrink as the cost grows; what
        may not change is how big the pips are next to the letters. Measuring the total ink in the
        plate is what this test did first and it passed against the bug, because the bounding box
        is set by whichever of the two is taller — the two have to be measured apart."""
        def name_and_pip(mana_cost):
            face = {**FACE, "name": "Craterhoof Behemoth", "mana_cost": mana_cost}
            out, _ = compositor.compose(card((28, 30, 34)), face, PANELS)
            x0, y0, x1, y1 = compositor._box(PANELS["title"], out.size)
            width = x1 - x0

            def ink_height(start, end):
                """Everything drawn is lighter than the dark plate it was drawn onto."""
                band = out.crop((x0 + int(width * start), y0, x0 + int(width * end), y1))
                rows = [y for y in range(band.height) for x in range(band.width)
                        if band.convert("L").getpixel((x, y)) > 120]
                self.assertTrue(rows, f"nothing drawn in {start}-{end} of the title plate")
                return max(rows) - min(rows)

            # The name always starts at the left pad; the last pip always ends at the right one.
            return ink_height(0, 0.30), ink_height(0.90, 1.0)

        ratios = []
        for cost in ("{G}", "{5}{G}{G}{G}", "{2}{G}{G}{G}{G}{G}{G}{G}"):
            name, pip = name_and_pip(cost)
            ratios.append(pip / name)
        # MEASURED: 1.24 / 1.23 / 1.22 after the fix, against 1.24 / 1.45 / 1.88 before it — the
        # pips held full height while the name alone gave way, and that is what the client saw.
        self.assertLess(max(ratios) - min(ratios), 0.10,
                        f"pip-to-name proportion drifts with cost length: {ratios}")

    def test_a_cost_of_many_pips_still_fits_inside_its_plate(self):
        """The pips are sized off the plate, so a cost long enough to force the loop down must
        still land inside it — an eight-pip cost is the worst real case (Emrakul-class)."""
        face = {**FACE, "name": "Craterhoof Behemoth", "mana_cost": "{2}{G}{G}{G}{G}{G}{G}{G}"}
        out, _ = compositor.compose(card((28, 30, 34)), face, PANELS)
        x0, y0, x1, y1 = compositor._box(PANELS["title"], out.size)
        above = out.crop((x0, max(0, y0 - 12), x1, y0)).convert("L")
        below = out.crop((x0, y1, x1, min(out.height, y1 + 12))).convert("L")
        for name, band in (("above", above), ("below", below)):
            self.assertLess(max(band.getdata()), 120,
                            f"the cost spilled {name} the title plate")


class PrintableFaceTests(SimpleTestCase):
    """`panels.detect` reports the painted OBJECT; only its flat interior can be printed on.

    MEASURED 2026-08-16 on Craterhoof's scroll — the card whose rules text came back printed onto
    the curled rod, with "Haste", "control" and "end of turn" all beginning off the parchment.
    Scanning that box column by column in grey levels gave two populations that do not touch:

        parchment face   median 244-245   sd 0.4 - 2.7
        the curled rod   median 131-234   sd 64  - 90

    So the test is built the way the constant was: a flat face with structured ornament at its
    ends, and the scan has to keep the first and drop the second.
    """

    @staticmethod
    def surface(width=800, height=300, rod=90, pale=245, ink=(70, 60, 50)):
        """A flat pale face with a hatched rod at each end, like a scroll.

        The hatching runs ACROSS the rod, which is how the real ones are drawn and is the whole
        point: the scan reads a column's spread down its own length, so a rod hatched with
        vertical strokes would be as uniform as the parchment and rightly kept.
        """
        image = Image.new("RGBA", (width, height), (pale, pale - 4, pale - 18, 255))
        draw = ImageDraw.Draw(image)
        for y in range(0, height, 6):
            draw.line([(0, y), (rod, y)], fill=ink + (255,), width=3)
            draw.line([(width - rod, y), (width, y)], fill=ink + (255,), width=3)
        return image

    def test_ornament_at_the_ends_is_peeled_and_the_flat_face_is_kept(self):
        image = self.surface()
        face = compositor.printable_face(image, (0, 0, 800, 300))
        self.assertGreaterEqual(face[0], 80, f"the left rod was not peeled: {face}")
        self.assertLessEqual(face[2], 720, f"the right rod was not peeled: {face}")
        # And it must not eat the face it was protecting.
        self.assertLess(face[0], 130)
        self.assertGreater(face[2], 670)

    def test_height_is_never_peeled_because_height_is_the_type_size(self):
        """MEASURED 2026-08-16: peeling top and bottom as well took run1's rules panel from 360px
        to 242px and its text from 49 to 35, under the 48px RULES_MIN — a card that was fine
        became UNSOUND [text_too_small]. `fit_across` steps the size down until the block fits the
        box HEIGHT, so every pixel off the top or bottom comes straight out of the type.

        And nothing was gained: every observed defect was horizontal, text beginning on a left or
        right rod. Vertical rims are left to `check.contrast` and `panel_palette`, which cost no
        pixels."""
        image = self.surface()
        rimmed = ImageDraw.Draw(image)
        for x in range(0, 800, 5):  # a heavy hatched rim along the top and bottom edges
            rimmed.line([(x, 0), (x, 60)], fill=(60, 50, 40, 255), width=2)
            rimmed.line([(x, 240), (x, 300)], fill=(60, 50, 40, 255), width=2)
        face = compositor.printable_face(image, (0, 0, 800, 300))
        self.assertEqual((face[1], face[3]), (0, 300), f"height was peeled: {face}")

    def test_a_clean_plate_is_left_exactly_as_it_was_found(self):
        """The scan runs on every surface, so its no-op case is the one that has to be free."""
        flat = Image.new("RGBA", (800, 300), (30, 34, 40, 255))
        self.assertEqual(compositor.printable_face(flat, (0, 0, 800, 300)), (0, 0, 800, 300))

    def test_a_dark_plate_peels_the_same_way_a_pale_one_does(self):
        """Only the rules strip is pale — `check.contrast` enforces that — while the title and
        type plates are briefed DARK. A scan keyed on VALUE would peel a title plate to nothing,
        which is why the rule is spread along the line instead."""
        # Carved ends on a near-black plate read by catching the light, not by going
        # darker still — which is also the scan's known ceiling: ornament with no
        # contrast against its own plate is ornament the spread cannot see.
        dark = self.surface(pale=34, ink=(205, 195, 175))
        face = compositor.printable_face(dark, (0, 0, 800, 300))
        self.assertGreaterEqual(face[0], 80, f"the rod was not peeled on a dark plate: {face}")
        self.assertLessEqual(face[2], 720)

    def test_the_peel_is_capped_so_a_misread_cannot_eat_the_surface(self):
        """A box wrong enough to look like ornament all the way across is better printed on and
        reported by `check` than silently shrunk to nothing."""
        noise = Image.effect_noise((800, 300), 90).convert("RGBA")
        face = compositor.printable_face(noise, (0, 0, 800, 300))
        self.assertGreaterEqual(face[2] - face[0], 800 * (1 - 2 * compositor.FACE_MAX_PEEL) - 1)
        self.assertGreaterEqual(face[3] - face[1], 300 * (1 - 2 * compositor.FACE_MAX_PEEL) - 1)


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


class FlavourTextTests(SimpleTestCase):
    """`include_flavor_text` is named for the reference site's own generate payload, so a frontend
    passes its toggle straight through. Off by default: flavour competes with the rules for the
    one panel we get, and rules text losing size to prose is the worse trade."""

    FLAVOURED = {**FACE, "flavor_text": "The peaks remember every name they have burned."}
    PANEL = {"rules": [(0.06, 0.60, 0.94, 0.94)]}
    # The same panel with a P/T shield hanging off its bottom-right, which is what the borderless
    # brief actually produces (bd mtg-wfp measured that geometry from the other side). This is the
    # layout that makes `_rules` take its exclusion re-fit branch.
    OVERLAPPED = {"rules": [(0.06, 0.60, 0.94, 0.94)], "pt": (0.78, 0.86, 0.94, 0.97)}

    @staticmethod
    def _printed_lines(image, panel):
        """How many lines of text were actually printed into the panel.

        Counted by row projection rather than by total ink, because ink is CONFOUNDED here: the
        first fit's line height is what shifts the P/T exclusion for the second, so asking for
        flavour changes the layout even in the broken case where the flavour is never drawn. The
        number of lines on the card is not confounded — either the prose was set or it was not.
        """
        x0, y0, x1, y1 = compositor._box(panel, image.size)
        grey = image.crop((x0, y0, x1, y1)).convert("L")
        pixels = grey.load()
        rows = [
            sum(1 for x in range(grey.width) if pixels[x, y] < 120) for y in range(grey.height)
        ]
        return sum(1 for y, count in enumerate(rows) if count > 2 and rows[y - 1] <= 2)

    def test_flavour_survives_a_pt_shield_overlapping_the_rules_panel(self):
        """bd mtg-4qa — `_rules` fits the text twice and only the SECOND fit is drawn.

        That re-fit was called without `flavours`, so every creature whose P/T shield overlaps its
        rules panel printed NO flavour text and nothing reported it: the card still looked
        finished, which is the failure class CLAUDE.md forbids. The tests above missed it because
        their panel set has no `pt`, so the exclusion re-fit never ran at all.
        """
        long_flavour = {
            **FACE,
            "flavor_text": "The peaks remember every name they have burned, and the wind carries "
            "each one down to the villages below, where the old keep a list and the young keep a "
            "watch, and neither has ever once been enough to matter.",
        }
        without = compositor.compose(card((228, 208, 172)), long_flavour, self.OVERLAPPED)[0]
        with_it = compositor.compose(
            card((228, 208, 172)), long_flavour, self.OVERLAPPED, include_flavor_text=True
        )[0]
        panel = self.OVERLAPPED["rules"][0]
        self.assertGreater(
            self._printed_lines(with_it, panel),
            self._printed_lines(without, panel) + 1,
            "flavour text was asked for and the card came back with no more lines than without "
            "it, so the prose was silently dropped",
        )

    def test_flavour_is_absent_unless_it_is_asked_for(self):
        off, _ = compositor.compose(card((228, 208, 172)), self.FLAVOURED, self.PANEL)
        on, _ = compositor.compose(
            card((228, 208, 172)), self.FLAVOURED, self.PANEL, include_flavor_text=True
        )
        x0, y0, x1, y1 = compositor._box(self.PANEL["rules"][0], on.size)
        self.assertNotEqual(
            off.crop((x0, y0, x1, y1)).tobytes(), on.crop((x0, y0, x1, y1)).tobytes()
        )

    def test_a_card_with_no_flavour_text_is_unchanged_by_the_flag(self):
        """Most cards have none, and the flag must not cost them a divider or a reflow."""
        plain, _ = compositor.compose(card((228, 208, 172)), FACE, self.PANEL)
        asked, _ = compositor.compose(
            card((228, 208, 172)), FACE, self.PANEL, include_flavor_text=True
        )
        self.assertEqual(plain.tobytes(), asked.tobytes())

    def test_flavour_is_italic_and_never_set_as_a_keyword_line(self):
        """"Hulk smash!" matches the bare-keyword shape and would otherwise be set large and
        heavy in the display face, which is how a real card sets Flying — not flavour."""
        lines = textlayout.atoms("Flying", '"Hulk smash!"')
        self.assertTrue(all(a.italic for a in lines[1]))
        self.assertFalse(any(a.keyword for a in lines[1]))
        self.assertTrue(textlayout.starts_flavour(lines[1]))
        self.assertFalse(textlayout.starts_flavour(lines[0]))

    def test_flavour_lands_in_the_last_panel_only(self):
        """Splitting it across panels would put uncoloured prose above game text, and a player has
        to be able to tell at a glance which words are rules."""
        import inspect

        source = inspect.getsource(compositor._rules)
        self.assertIn("flavours[-1] = flavour", source)

    def test_flavour_takes_room_from_the_rules_text(self):
        """It shares the panel, so asking for it can only shrink the type. That is the trade the
        flag exists to make explicit rather than silent."""
        box = [(900, 300)]
        without, _ = textlayout.fit_across(["Flying"], box, 2400 * compositor.RULES_SIZE)
        with_flavour, _ = textlayout.fit_across(
            ["Flying"], box, 2400 * compositor.RULES_SIZE,
            flavours=["The peaks remember every name they have burned, and they are patient."],
        )
        self.assertLessEqual(with_flavour, without)


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


class PlateExtentTests(SimpleTestCase):
    """A display plate is measured, not taken on trust.

    MEASURED 2026-08-16, four `detect` runs over ONE stored blank: title box heights 132, 125, 120
    and 214px, so the printed name swung 82-146. Same disease as bd mtg-1uv on a second surface,
    and the same answer — measure the painted plate instead of trusting the reported box.
    """

    @staticmethod
    def plate(width=900, height=400, top=100, bottom=300, shade=40):
        """A flat plate band across the middle, hatched art above and below it.

        The art is hatched VERTICALLY, which is what makes this fixture test anything: growth
        walks outward row by row, so art drawn in horizontal bands leaves every row uniform and
        the scan sails straight through it. Real art varies both ways; a first version of this
        fixture did not, and passed against a function that never grew at all.
        """
        image = Image.new("RGBA", (width, height), (shade, shade + 4, shade + 8, 255))
        draw = ImageDraw.Draw(image)
        for x in range(0, width, 5):
            draw.line([(x, 0), (x, top)], fill=(210, 200, 180, 255), width=2)
            draw.line([(x, bottom), (x, height)], fill=(210, 200, 180, 255), width=2)
        return image

    def test_a_box_reported_short_is_grown_back_to_the_plate(self):
        image = self.plate()
        tight = compositor.plate_extent(image, (0, 160, 900, 240))  # half the real plate
        self.assertLessEqual(tight[1], 115, f"top was not grown: {tight}")
        self.assertGreaterEqual(tight[3], 285, f"bottom was not grown: {tight}")

    def test_two_different_reported_boxes_land_on_the_same_plate(self):
        """The point is not a bigger box, it is the SAME box whichever detection arrived.

        Both inputs are within PLATE_MAX_GROWTH of the real plate, which is the range this repairs:
        the four real detections spanned 120-214px on a 240px plate, a spread of 1.8x. A box far
        smaller than that is out of reach by design and is left alone rather than stretched — see
        `test_a_plate_that_grows_to_the_cap_is_left_alone`.
        """
        image = self.plate()
        a = compositor.plate_extent(image, (0, 150, 900, 250))
        b = compositor.plate_extent(image, (0, 140, 900, 265))
        self.assertLess(abs((a[3] - a[1]) - (b[3] - b[1])), 20, f"{a} vs {b}")

    def test_growth_stops_at_the_art_and_never_runs_off_the_card(self):
        image = self.plate()
        grown = compositor.plate_extent(image, (0, 150, 900, 250))
        self.assertGreaterEqual(grown[1], 90, "grew up into the hatched art")
        self.assertLessEqual(grown[3], 310, "grew down into the hatched art")

    def test_a_plate_that_grows_to_the_cap_is_left_alone(self):
        """Running to the limit means the scan never found the plate's edge — same reasoning as
        the peel, where capping out and trusting the result put text on a scroll rod."""
        flat = Image.new("RGBA", (900, 400), (40, 44, 48, 255))
        self.assertEqual(compositor.plate_extent(flat, (0, 150, 900, 250)), (0, 150, 900, 250))
