"""The structural verify step, and the retry it drives.

Every case here fired on a real card during the 2026-08-10/11 batches. The point of the module is
that each was caught only because a human happened to be looking at the output.
"""

from django.test import SimpleTestCase
from PIL import Image, ImageDraw

from generation import bleed, check, panels as panels_module

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


class PanelContrastTests(SimpleTestCase):
    """A panel too dark for the text printed on it (bd mtg-cjx).

    MEASURED on the eight-card Ice batch, job 10746c0b — the first run of the acceptance test the
    bead asks for, which is to look at the finished card at arm's length and read it. All eight
    graded sound; three were not readable. Terror of the Peaks measured 3.6:1, Lightning Bolt
    4.5:1, Giant Growth 5.0:1, against 9.4-12.3:1 for the five that read cleanly.
    """

    def _card(self, panel_value, size=(179, 240)):
        """A dark card with one strip of `panel_value` where SOUND puts the rules panel."""
        card = Image.new("RGB", size, (20, 20, 20))
        box = SOUND["rules"][0]
        card.paste(
            (panel_value, panel_value, panel_value),
            (
                int(box[0] * size[0]), int(box[1] * size[1]),
                int(box[2] * size[0]), int(box[3] * size[1]),
            ),
        )
        return card

    def test_a_pale_parchment_panel_passes(self):
        """L=200 is where the five readable cards landed."""
        self.assertIsNone(check.contrast(self._card(200), SOUND))

    def test_a_lava_coloured_panel_is_reported(self):
        """L=110 is Terror of the Peaks, which graded sound and could not be read."""
        problem = check.contrast(self._card(110), SOUND)
        self.assertIsNotNone(problem)
        self.assertEqual(problem.code, "panel_too_dark")

    def test_a_card_with_no_rules_panel_reports_only_the_missing_panel(self):
        """`missing_rules` already says this; two codes for one fault helps nobody."""
        self.assertIsNone(check.contrast(self._card(200), {k: v for k, v in SOUND.items()
                                                          if k != "rules"}))

    def test_the_darkest_strip_decides_a_multi_strip_card(self):
        """A card is only as readable as its worst paragraph."""
        card = self._card(200)
        card.paste((90, 90, 90), (20, 200, 160, 220))
        panels = {**SOUND, "rules": [SOUND["rules"][0], (0.11, 0.83, 0.89, 0.92)]}
        self.assertEqual(check.contrast(card, panels).code, "panel_too_dark")


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


class TypePlateWidthTests(SimpleTestCase):
    """bd mtg-atl. Phyrexian Obliterator, job 60265c75 and card 05 of the 2026-08-16 sign-off pack,
    came back with the narrow strip painted as three riveted segments in a row. `detect` reported
    the leftmost one, so the type line was set at roughly a third of its size in the left third of
    the card with two empty segments beside it — and it graded SOUND, because `TYPE_SIZE` is a
    fraction of the box HEIGHT and the segment is the right height. Only the width is wrong.

    Every width below is measured off a stored detection, not invented.
    """

    def _at(self, width):
        return {**SOUND, "type": (0.10, 0.60, 0.10 + width, 0.66)}

    def test_the_segmented_bar_is_caught(self):
        self.assertIn("type_too_narrow", codes(CREATURE, self._at(0.253)))

    def test_every_other_stored_face_still_passes(self):
        """0.562 is the next narrowest of the 45 (Elesh Norn, job 82157ad6); 0.804 is the median
        and 0.911 the widest. The floor has to sit in the 2.2x gap above the one failure without
        clipping the bottom of the healthy population."""
        for width in (0.562, 0.716, 0.804, 0.911):
            with self.subTest(width=width):
                self.assertNotIn("type_too_narrow", codes(CREATURE, self._at(width)))

    def test_a_card_with_no_type_plate_reports_only_the_missing_plate(self):
        """`missing_type` already says this. A zero-width absence is not a narrow bar."""
        panels = {k: v for k, v in SOUND.items() if k != "type"}
        self.assertNotIn("type_too_narrow", codes(CREATURE, panels))


class TitlePlateWidthTests(SimpleTestCase):
    """bd mtg-6bb, the half of it a gate has to carry.

    Sizing the name off the card (2026-08-17) fixed every plate that was the wrong HEIGHT. It
    cannot fix a plate that is the wrong WIDTH, because the fit-to-width loop in `_title` then
    steps the size back down and the loop is driven by how long the name is. Craterhoof Behemoth,
    job bf4f16ac, came back on a title plate spanning 0.517 of the card and its name was cut by a
    third — the only face in 58 the loop had to touch that hard.

    Every width below is measured off a stored detection, not invented.
    """

    def _at(self, width):
        return {**SOUND, "title": (0.05, 0.03, 0.05 + width, 0.11)}

    def test_the_stunted_plate_is_caught(self):
        self.assertIn("title_too_narrow", codes(CREATURE, self._at(0.517)))

    def test_every_plate_that_printed_at_full_size_still_passes(self):
        """0.681 is the narrowest plate in the archive that set its name at full size (Tree of
        Tales, job 7a7b2dc0); 0.804 is the median and 0.880 the widest."""
        for width in (0.681, 0.729, 0.804, 0.880):
            with self.subTest(width=width):
                self.assertNotIn("title_too_narrow", codes(CREATURE, self._at(width)))

    def test_a_card_with_no_title_plate_reports_only_the_missing_plate(self):
        """`missing_title` already says this. A zero-width absence is not a narrow plate."""
        panels = {k: v for k, v in SOUND.items() if k != "title"}
        self.assertNotIn("title_too_narrow", codes(CREATURE, panels))


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

    def test_a_shield_on_a_card_with_no_pt_is_a_blank_surface(self):
        """bd mtg-m8q. The `pt` box is Sol Ring's own, from job 40c627d1 — card 03 of the
        2026-08-16 sign-off pack, which shipped with an empty metal shield at bottom-right and
        graded clean on every gate. The detector found the shield; nothing asked whether an
        artifact is entitled to one."""
        panels = {**SOUND, "pt": (0.89044, 0.9186, 0.96216, 0.978)}
        self.assertIn("blank_surface", codes(SPELL, panels))

    def test_a_creature_keeps_its_shield(self):
        """The mirror of `missing_pt`: the same box on a face that HAS power is the surface the
        compositor is about to print into, and failing it would repaint 29 of the 45 stored
        faces."""
        self.assertNotIn("blank_surface", codes(CREATURE, SOUND))


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


class PtTabMarkTests(SimpleTestCase):
    """A blank tab is not a mark; a symbol carved into one is.

    CLIENT 2026-08-16, on a staged Craterhoof: "that too blank without any symbol in it, craterhoof
    has spiral in it." The model carved a spiral into the P/T tab and we printed 5/5 over it. The
    brief bans it by name, the detector's `marks` list is the mechanism for catching it, and
    `_in_pt_corner` threw it away — that filter exists to drop the BLANK tab, which the detector
    reported as a mark on 4 of 4 runs in 2026-08-13.
    """

    TAB = (0.80, 0.86, 0.94, 0.96)

    def test_the_blank_tab_reported_as_a_mark_is_still_dropped(self):
        """The false positive this filter was built for: same object, same box."""
        self.assertTrue(panels_module._is_the_pt_tab((0.80, 0.86, 0.94, 0.96), self.TAB))
        # And a slightly loose box around the same tab is still the tab.
        self.assertTrue(panels_module._is_the_pt_tab((0.805, 0.865, 0.935, 0.955), self.TAB))

    def test_a_symbol_carved_into_the_tab_is_kept(self):
        """The client's spiral: a small thing well inside the tab, not the tab."""
        spiral = (0.855, 0.895, 0.905, 0.935)
        self.assertTrue(panels_module._in_pt_corner(spiral))
        self.assertFalse(panels_module._is_the_pt_tab(spiral, self.TAB))

    def test_with_no_tab_detected_the_old_region_behaviour_stands(self):
        """Nothing to compare against, so keep the behaviour this filter has had since
        2026-08-13: a false repaint costs a credit, a missed spiral costs one card."""
        self.assertTrue(panels_module._is_the_pt_tab((0.855, 0.895, 0.905, 0.935), None))
        self.assertFalse(panels_module._is_the_pt_tab((0.10, 0.10, 0.20, 0.20), None))


class MattedThresholdTests(SimpleTestCase):
    """The mat threshold has to sit BETWEEN the two populations, not on top of one.

    MEASURED 2026-08-16 on a six-card batch. A Comic Book Raphael came back with a white mat on
    all four sides, graded SOUND and shipped — it scored 0.8828 against a threshold of 0.9000, so
    a defect the client would have circled was lost by 0.017.

        clean    Craterhoof 0.000    Sol Ring 0.107
        matted   Raphael    0.883
    """

    @staticmethod
    def ring(matted_share, size=400):
        """A card whose outer ring is `matted_share` flat cream and the rest dark scene."""
        image = Image.new("RGB", (size, size), (30, 34, 40))
        draw = ImageDraw.Draw(image)
        draw.rectangle([0, 0, size - 1, int(size * matted_share) - 1], fill=(242, 238, 226))
        return image

    def test_the_threshold_sits_between_the_measured_populations(self):
        self.assertGreater(bleed.MATTED, 0.107, "would fail Sol Ring, a clean card")
        self.assertLess(bleed.MATTED, 0.883, "would pass Raphael, which is matted")

    def test_a_card_matted_on_every_side_is_caught(self):
        image = Image.new("RGB", (400, 400), (242, 238, 226))
        ImageDraw.Draw(image).rectangle([60, 60, 339, 339], fill=(30, 34, 40))
        self.assertGreaterEqual(bleed.matted_share(image), bleed.MATTED)

    def test_a_full_bleed_scene_is_not_called_a_mat(self):
        """A painted scene is never one flat colour the whole way round, which is the property
        this measures — not whether the edge happens to be light."""
        image = Image.new("RGB", (400, 400))
        pixels = image.load()
        for x in range(400):
            for y in range(400):
                pixels[x, y] = ((x * 7) % 256, (y * 5) % 256, ((x + y) * 3) % 256)
        self.assertLess(bleed.matted_share(image), bleed.MATTED)


class ColourIdentityTests(SimpleTestCase):
    """Graded against Scryfall, never against what the user picked on the UI.

    CLAUDE.md treats this as correctness: the client reported purple leaking into a mono-green
    card. Until 2026-08-16 the rule lived only in the brief — `prompts._palette` argued for it and
    nothing measured the result, which is why bd mtg-5pb is intermittent: `ice` on a mono-red
    Lightning Bolt came back blue-white on one run and red on a rerun with identical inputs.

    MEASURED over the six-card VERIFY2 batch: coloured cards run 23-51% saturated with their own
    hue at 72-95% of that, while white and colourless run 1% and 7% with no hue at all. Two
    populations, two rules.
    """

    @staticmethod
    def flat(rgb, size=200):
        return Image.new("RGB", (size, size), rgb)

    def test_a_green_card_that_reads_green_passes(self):
        self.assertIsNone(check.colour_identity(self.flat((40, 190, 70)), {"color_identity": ["G"]}))

    def test_a_red_card_that_reads_blue_is_caught(self):
        problem = check.colour_identity(self.flat((40, 90, 210)), {"color_identity": ["R"]})
        self.assertIsNotNone(problem)
        self.assertEqual(problem.code, "colour_identity")

    def test_purple_on_a_non_black_card_is_caught(self):
        """The client's own reported bug, and the one the brief calls absolute."""
        problem = check.colour_identity(self.flat((150, 60, 200)), {"color_identity": ["G"]})
        self.assertIsNotNone(problem)
        self.assertIn("purple", problem.detail)

    def test_purple_on_a_black_card_is_fine(self):
        self.assertIsNone(check.colour_identity(self.flat((150, 60, 200)), {"color_identity": ["B"]}))

    def test_a_neutral_card_makes_no_claim_and_is_not_failed(self):
        """White and colourless have NO hue — Elesh Norn measured 7% saturated and Sol Ring 1%.
        Asking "is the dominant hue correct" of a card with no hue fails every one of them on
        whatever scrap of colour it happens to carry."""
        for identity in ([], ["W"]):
            self.assertIsNone(
                check.colour_identity(self.flat((190, 188, 182)), {"color_identity": identity})
            )

    def test_a_card_that_only_leans_wrong_is_left_alone(self):
        """DOMINANT_SHARE has room under every correct card in the batch (72-95%), so a mixed
        scene is not a repaint — only a card that actually reads as the wrong colour is."""
        image = Image.new("RGB", (200, 200), (40, 190, 70))
        ImageDraw.Draw(image).rectangle([0, 0, 199, 99], fill=(40, 90, 210))  # half blue
        self.assertIsNone(check.colour_identity(image, {"color_identity": ["G"]}))

    def test_a_card_showing_almost_none_of_its_own_colour_fails(self):
        """MEASURED 2026-08-16: mono-black Vampiric Tutor under `rick_and_morty` came back a
        plainly GREEN card — acid portals, green slime, green monitors — and passed. By mana it
        was G 43%, U 38%, B 16%, R 3% at 0.463 saturation: its own colour was THIRD, and it
        escaped because no single wrong colour cleared DOMINANT_SHARE.

        Summing per mana colour fixed the case where ONE colour was split across two hue buckets.
        It cannot help when TWO wrong colours share the frame, which is what a busy style row
        produces. The gate asked "is the leader a colour this card lacks" and never "does this
        card show any of its own colour at all".

        OWN_SHARE_MIN is fitted between the two measured populations: correct cards above
        NEUTRAL_SHARE ran 73-100% own colour (n=8, R/G/U across four batches), the failure sat at
        16%."""
        # The Tutor's own proportions: no wrong colour clears DOMINANT_SHARE, so dominance cannot
        # fire and only the own-share test can.
        image = Image.new("RGB", (200, 200), (40, 190, 70))                     # green 44%
        ImageDraw.Draw(image).rectangle([0, 0, 199, 111], fill=(40, 90, 210))   # blue 40%
        ImageDraw.Draw(image).rectangle([0, 0, 199, 31], fill=(150, 60, 200))   # its own 16%
        problem = check.colour_identity(image, {"color_identity": ["B"]})
        self.assertIsNotNone(problem, "a card showing almost none of its own colour escaped")
        self.assertIn("its own", problem.detail)

    def test_white_and_colourless_are_exempt_because_they_have_no_hue_to_show(self):
        """`_HUE_BUCKETS` maps hues to R, G, U and B only — there is deliberately no white bucket,
        because white is signalled by the ABSENCE of hue and colourless has no colour to claim.
        Their own-share is therefore 0 by construction, and applying the own-colour test to them
        would fail every saturated white card including correct ones. They are judged by
        NEUTRAL_SHARE and by dominance, exactly as before."""
        # Neither colour clears DOMINANT_SHARE, so dominance cannot fire and the own-share test is
        # the only thing that could — which is the point of the fixture.
        image = Image.new("RGB", (200, 200), (40, 190, 70))                    # green 55%
        ImageDraw.Draw(image).rectangle([0, 0, 199, 89], fill=(40, 90, 210))   # blue 45%
        for identity in (["W"], []):
            with self.subTest(identity=identity):
                problem = check.colour_identity(image, {"color_identity": identity})
                self.assertIsNone(problem, "own-share must not judge a colour with no hue")

    def test_a_dominant_colour_of_its_own_is_still_a_pass_at_a_low_share(self):
        """The own-share test must not fire when the leader IS the card's colour. A green card
        leading on green at 35%, under OWN_SHARE_MIN, is a mixed scene rather than a wrong one —
        the same tolerance `test_a_mixed_scene_is_not_a_failure` protects."""
        image = Image.new("RGB", (200, 200), (40, 190, 70))                    # green leads
        ImageDraw.Draw(image).rectangle([0, 0, 199, 63], fill=(40, 90, 210))   # blue
        ImageDraw.Draw(image).rectangle([0, 0, 199, 31], fill=(230, 130, 40))  # orange
        self.assertIsNone(check.colour_identity(image, {"color_identity": ["G"]}))

    def test_the_gate_takes_no_user_selection(self):
        """The style, direction and palette are what it guards against, so it must not be able to
        see them — a gate that took the selection could be talked out of firing by it."""
        import inspect as _inspect

        args = _inspect.signature(check.colour_identity).parameters
        self.assertEqual(list(args), ["card", "face"])

    def test_hue_buckets_are_summed_per_mana_colour_not_judged_separately(self):
        """MEASURED 2026-08-16: Counterspell under `fire` came back blue 53% + cyan 38% and passed
        only because neither bucket alone cleared DOMINANT_SHARE — a RED card at 53% would have
        passed identically. Blue and cyan are one mana colour to a player, and so are red and
        orange, so the dominance test is run on the sum."""
        image = Image.new("RGB", (200, 200), (200, 60, 40))       # red
        ImageDraw.Draw(image).rectangle([0, 0, 199, 89], fill=(230, 130, 40))  # orange
        problem = check.colour_identity(image, {"color_identity": ["U"]})
        self.assertIsNotNone(problem, "red+orange split below the bar and escaped the gate")
        self.assertIn("red", problem.detail)


class ProofreadTests(SimpleTestCase):
    """The text gate, back for the lettered mode (`CLAUDE.md`'s one surviving rule).

    Every case here is a defect from the 25-card lettered batch, where the existing structural
    gates passed 23 of 25 and were blind to all of them.
    """

    FACE = {
        "name": "Thirsting Roots",
        "type_line": "Sorcery",
        "oracle_text": "Choose one —\n• Search your library for a basic land card, reveal it, put "
        "it into your hand, then shuffle.\n• Proliferate.",
        "power": None,
        "loyalty": None,
    }

    def read(self, *patches, title=(0.1, 0.03, 0.9, 0.11)):
        read = {"text": [{"where": where, "text": text} for where, text in patches]}
        if title:
            read["title"] = title
        return read

    def correct(self, **overrides):
        return self.read(
            ("title_plate", self.FACE["name"]),
            ("type_strip", self.FACE["type_line"]),
            ("rules_panel", self.FACE["oracle_text"].replace("\n", " ")),
            **overrides,
        )

    def codes(self, face, read):
        return [problem.code for problem in check.proofread(face, read)]

    def test_a_card_that_says_what_scryfall_says_reports_nothing(self):
        self.assertEqual(check.proofread(self.FACE, self.correct()), [])

    def test_a_panel_transcribed_as_several_patches_still_matches(self):
        """The model returns one entry per patch and a three-paragraph panel may come back as one
        or as three. Grading on which would be grading the transcription, not the card."""
        read = self.read(
            ("title_plate", "Thirsting Roots"),
            ("type_strip", "Sorcery"),
            ("rules_panel", "Choose one —"),
            ("rules_panel", "• Search your library for a basic land card, reveal it, put it into "
             "your hand, then shuffle."),
            ("rules_panel", "• Proliferate."),
        )
        self.assertEqual(check.proofread(self.FACE, read), [])

    def test_punctuation_the_transcription_cannot_resolve_is_not_graded(self):
        """An em dash and a hyphen are two strokes of ink at body size. Grading the distinction
        buys false repaints and no correctness."""
        read = self.correct()
        read["text"][2]["text"] = read["text"][2]["text"].replace("—", "-").replace("•", "-")
        self.assertEqual(check.proofread(self.FACE, read), [])

    def test_a_symbol_is_graded_the_same_with_or_without_braces(self):
        """`{T}: Add {C}{C}` is drawn as a tap symbol and two diamonds, and a transcription may or
        may not put the braces back."""
        sol = {**self.FACE, "name": "Sol Ring", "type_line": "Artifact",
               "oracle_text": "{T}: Add {C}{C}."}
        read = self.read(("title_plate", "Sol Ring"), ("type_strip", "Artifact"),
                         ("rules_panel", "T: Add CC."))
        self.assertEqual(check.proofread(sol, read), [])

    def test_a_word_the_model_invented_is_caught(self):
        read = self.correct()
        read["text"][1]["text"] = "Instant"
        self.assertIn("text_wrong", self.codes(self.FACE, read))

    def test_rules_text_obscured_by_the_artwork_is_caught(self):
        """Palantír of Orthanc, card 20: a chain crossed the MIDDLE of the rules panel and hid
        four words. Every structural gate passed it."""
        read = self.correct()
        read["text"][2]["text"] = "Choose one — • Search your [?] for a [?] land card, reveal it."
        self.assertIn("text_wrong", self.codes(self.FACE, read))

    def test_a_field_left_unprinted_is_caught(self):
        read = self.read(("title_plate", "Thirsting Roots"), ("type_strip", "Sorcery"))
        self.assertIn("text_missing", self.codes(self.FACE, read))

    def test_runes_flanking_a_real_line_are_caught(self):
        """Lim-Dûl's Vault, card 21: runes either side of `Instant` on the type strip. The brief
        has banned them since the first Creative Full card and they still arrive."""
        read = self.correct()
        read["text"][1]["text"] = "ᛗᚫᛉ Sorcery ᚠᚱᚦ"
        self.assertIn("text_wrong", self.codes(self.FACE, read))

    def test_a_set_symbol_or_artist_credit_anywhere_else_is_caught(self):
        read = self.correct()
        read["text"].append({"where": "other", "text": "Illus. A. Painter 042/280"})
        self.assertIn("text_extra", self.codes(self.FACE, read))

    def test_script_in_the_artwork_is_not_graded(self):
        """Delver of Secrets came back twice with arcane script in its scene. That is
        illustration, and failing it bought a repaint that changed nothing — the same evidence
        that narrowed `_offending_marks`."""
        read = self.correct()
        read["text"].append({"where": "artwork", "text": "ᚦᚱ ᛉᚫ"})
        self.assertEqual(check.proofread(self.FACE, read), [])

    def test_a_field_the_card_does_not_have_but_the_model_lettered_is_caught(self):
        """A sorcery with a power/toughness written into a tab. bd mtg-m8q's defect, one layer
        further on: the surface got painted AND filled in."""
        read = self.correct()
        read["text"].append({"where": "tab", "text": "2/2"})
        self.assertIn("text_extra", self.codes(self.FACE, read))

    def test_a_creature_is_graded_on_its_power_and_toughness(self):
        goyf = {**self.FACE, "name": "Tarmogoyf", "type_line": "Creature — Lhurgoyf",
                "oracle_text": "Tarmogoyf's power is equal to the number of card types among "
                "cards in all graveyards and its toughness is equal to that number plus 1.",
                "power": "*", "toughness": "1+*"}
        read = self.read(("title_plate", goyf["name"]), ("type_strip", goyf["type_line"]),
                         ("rules_panel", goyf["oracle_text"]), ("tab", "*/1+*"))
        self.assertEqual(check.proofread(goyf, read), [])
        read["text"][3]["text"] = "2/3"
        self.assertIn("text_wrong", self.codes(goyf, read))

    def test_a_planeswalker_is_graded_on_its_starting_loyalty(self):
        jace = {**self.FACE, "name": "Jace, the Mind Sculptor",
                "type_line": "Legendary Planeswalker — Jace", "oracle_text": "+2: Look.",
                "loyalty": 3}
        read = self.read(("title_plate", jace["name"]), ("type_strip", jace["type_line"]),
                         ("rules_panel", "+2: Look."), ("tab", "3"))
        self.assertEqual(check.proofread(jace, read), [])

    def test_no_title_plate_means_the_cost_has_nowhere_to_go(self):
        """The one field we still composite. Without the plate the card ships with no cost at
        all, which is a structural fault before it is a text one."""
        self.assertIn("missing_title", self.codes(self.FACE, self.correct(title=None)))


class CostCollisionTests(SimpleTestCase):
    """The cost stamped over the card's own name.

    MEASURED on the first live lettered run, 2026-08-17: Progenitus had a dragon crossing the right
    half of its title plate, `read_back` reported the plate as the clear left half only (x 0.09 to
    0.56), and ten pips right-aligned to 0.56 landed on the word "Progenitus". No text gate can see
    it — the read-back transcribes the card before the cost exists.
    """

    PROGENITUS = {"name": "Progenitus", "mana_cost": "{W}{W}{U}{U}{B}{B}{R}{R}{G}{G}"}
    PLATE = (0.06, 0.05, 0.94, 0.15)

    def test_a_plate_with_room_for_both_reports_nothing(self):
        read = {"title": self.PLATE, "name": (0.10, 0.07, 0.35, 0.13)}
        self.assertIsNone(check.cost_collides(self.PROGENITUS, read))

    def test_the_measured_failure_is_caught(self):
        read = {"title": (0.09, 0.06, 0.56, 0.13), "name": (0.10, 0.07, 0.42, 0.13)}
        self.assertEqual(check.cost_collides(self.PROGENITUS, read).code, "cost_no_room")

    def test_a_long_name_on_a_full_plate_is_caught_too(self):
        """The other direction: the plate is right, the model just lettered too far across."""
        read = {"title": self.PLATE, "name": (0.10, 0.07, 0.90, 0.13)}
        self.assertEqual(check.cost_collides(self.PROGENITUS, read).code, "cost_no_room")

    def test_a_one_pip_cost_needs_far_less_room_than_a_ten_pip_one(self):
        read = {"title": self.PLATE, "name": (0.10, 0.07, 0.70, 0.13)}
        self.assertIsNone(check.cost_collides({"name": "Forest", "mana_cost": "{G}"}, read))
        self.assertEqual(check.cost_collides(self.PROGENITUS, read).code, "cost_no_room")

    def test_a_card_with_no_cost_cannot_collide(self):
        read = {"title": self.PLATE, "name": (0.10, 0.07, 0.93, 0.13)}
        self.assertIsNone(check.cost_collides({"name": "Forest", "mana_cost": ""}, read))

    def test_a_name_box_the_read_back_did_not_return_is_not_guessed_at(self):
        """Same rule as `panels._usable`: an absent box means the reader was unsure, and inventing
        one here would fail good cards on arithmetic nobody measured."""
        self.assertIsNone(check.cost_collides(self.PROGENITUS, {"title": self.PLATE}))


class TypeEndMarkTests(SimpleTestCase):
    """A painted badge in the type line's set-symbol slot.

    SIGNOFF 2026-08-19, Elesh Norn: the type line was lettered correctly and the card still grew a
    red Phyrexian phi at the right-hand end of the strip. `proofread` compares transcribed words
    to Scryfall, so a graphic that is not words is invisible to it. Asking the vision model
    'is there a set symbol' would grade the hint. This grades the pixels.
    """

    SIZE = (896, 1200)
    STRIP = (0.10, 0.60, 0.90, 0.66)
    READ = {"type": STRIP}

    def card(self, badge=False, vine=False, pale=False):
        """A dark (or pale) type strip with left-aligned lettering, optionally a right-end mark."""
        plate = (228, 214, 190) if pale else (36, 32, 28)
        ink = (40, 32, 24) if pale else (210, 186, 96)
        image = Image.new("RGB", self.SIZE, (18, 20, 24))
        draw = ImageDraw.Draw(image)
        box = (
            int(self.STRIP[0] * self.SIZE[0]), int(self.STRIP[1] * self.SIZE[1]),
            int(self.STRIP[2] * self.SIZE[0]), int(self.STRIP[3] * self.SIZE[1]),
        )
        draw.rectangle(box, fill=plate)
        # Left-aligned type line, as the brief asks. Rectangles, not a font — this grades the
        # SLOT, and a real glyph's outline is one more variable than the test is about.
        top, bottom = box[1] + 14, box[3] - 14
        x = box[0] + 16
        for width in (38, 22, 30, 18, 26, 20):
            draw.rectangle((x, top, x + width, bottom), fill=ink)
            x += width + 8
        if badge:
            # Compact filled body at the far right — Elesh's phi, a rarity diamond, a gem.
            cy = (box[1] + box[3]) / 2
            r = (box[3] - box[1]) * 0.38
            cx = box[2] - (box[3] - box[1]) * 0.70
            draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(196, 28, 28))
        if vine:
            # Sparse crossing entering from above, the Craterhoof / Sol Ring wrapping case.
            draw.line(
                (box[2] - 40, box[1] - 30, box[2] - 10, box[3] + 30),
                fill=(48, 90, 36), width=4,
            )
        return image

    def test_a_bare_right_end_passes(self):
        self.assertIsNone(check.type_end_mark(self.card(), self.READ))

    def test_the_measured_phi_is_caught(self):
        problem = check.type_end_mark(self.card(badge=True), self.READ)
        self.assertIsNotNone(problem)
        self.assertEqual(problem.code, "painted_marks")
        self.assertIn("right-hand end", problem.detail)
        self.assertIn("bare", problem.detail)

    def test_a_wrapping_vine_is_not_a_set_symbol(self):
        """Craterhoof's vine fills the same slot by position and not by body. Failing it would
        repaint cards the brief asked to wrap the furniture with the scene."""
        self.assertIsNone(check.type_end_mark(self.card(vine=True), self.READ))

    def test_a_pale_strip_is_graded_too(self):
        """The mask is deviation from the plate, not 'brighter than dark'."""
        self.assertIsNone(check.type_end_mark(self.card(pale=True), self.READ))
        self.assertEqual(
            check.type_end_mark(self.card(badge=True, pale=True), self.READ).code,
            "painted_marks",
        )

    def test_a_strip_the_read_back_did_not_return_is_not_guessed_at(self):
        self.assertIsNone(check.type_end_mark(self.card(badge=True), {}))

    def test_the_type_strip_is_asked_for_so_the_slot_can_be_graded(self):
        """Without this box the gate has nothing to crop, and a yes/no in the prompt would grade
        the hint rather than the card."""
        self.assertIn("type", panels_module.READ_SCHEMA["properties"])
        self.assertIn('"type"', panels_module.READ_PROMPT)
        self.assertIn("narrow strip the type line sits on", panels_module.READ_PROMPT)


class ObstructionTests(SimpleTestCase):
    """Something painted across the panel the text has to go on.

    `contrast` cannot see this: it takes the panel's MEAN, and the vines that put "you control." on
    top of a vine on Craterhoof moved its mean by 5%. Obstruction is local.
    """

    PANEL = {"rules": [(0.10, 0.65, 0.90, 0.90)]}

    def blank(self, bars=0, thickness=0.01):
        """A pale panel on a dark card, with `bars` painted across it."""
        image = Image.new("RGBA", (896, 1200), (24, 26, 30, 255))
        draw = ImageDraw.Draw(image)
        draw.rectangle((0.10 * 896, 0.65 * 1200, 0.90 * 896, 0.90 * 1200), fill=(238, 222, 188, 255))
        for index in range(bars):
            top = (0.68 + index * 0.05) * 1200
            draw.rectangle((0.10 * 896, top, 0.90 * 896, top + thickness * 1200), fill=(48, 62, 34, 255))
        return image

    def test_a_bare_panel_passes(self):
        self.assertIsNone(check.obstructed(self.blank(), self.PANEL))

    def test_a_panel_painted_across_is_refused(self):
        problem = check.obstructed(self.blank(bars=4), self.PANEL)
        self.assertIsNotNone(problem)
        self.assertEqual(problem.code, "panel_obstructed")

    def test_the_detail_tells_the_repaint_what_to_do(self):
        """The retry hands the grader's own wording back to the model, so it has to name the fix and
        not just the fault (bd mtg-x6v)."""
        problem = check.obstructed(self.blank(bars=4), self.PANEL)
        self.assertIn("OUTSIDE", problem.detail)

    def test_a_dark_slab_is_not_graded(self):
        """`compositor.foreground_mask` is for light surfaces only — on a dark slab it returns the
        slab itself, which would fail every card that has one."""
        image = Image.new("RGBA", (896, 1200), (24, 26, 30, 255))
        ImageDraw.Draw(image).rectangle(
            (0.10 * 896, 0.65 * 1200, 0.90 * 896, 0.90 * 1200), fill=(38, 42, 58, 255)
        )
        self.assertIsNone(check.obstructed(image, self.PANEL))

    def test_the_panel_rim_is_not_obstruction(self):
        """Every panel has a raised border, and it is inside the box the detector reports. Counting
        it would fail every card ever painted."""
        image = Image.new("RGBA", (896, 1200), (24, 26, 30, 255))
        draw = ImageDraw.Draw(image)
        draw.rectangle((0.10 * 896, 0.65 * 1200, 0.90 * 896, 0.90 * 1200), fill=(238, 222, 188, 255))
        draw.rectangle(
            (0.10 * 896, 0.65 * 1200, 0.90 * 896, 0.90 * 1200), outline=(52, 40, 26, 255), width=6
        )
        self.assertIsNone(check.obstructed(image, self.PANEL))

    def test_a_missing_panel_is_left_to_its_own_code(self):
        self.assertIsNone(check.obstructed(self.blank(), {}))


class HonestBoxTests(SimpleTestCase):
    """`panels.detect` must report the whole flat face, even where something crosses it.

    MEASURED 2026-08-17 on a live Craterhoof. The prompt used to say "where something from the
    artwork crosses in FRONT of a surface, keep that out of the box", and the detector obeyed:
    it reported the rules panel as x0.103-0.570 where the painted pale face runs 0.106-0.896, so
    the text was set into the left 47% of a panel that is clean out to 0.68 on every row.

    Worse, it made `obstructed` blind by construction — the gate only measures inside the reported
    box, so a detector that clips the box to dodge a branch hides the exact fault the gate exists
    to find. On that card the gate read "passed" at the clipped box and 13.0% at the honest one.
    """

    def test_the_gate_only_sees_what_the_box_includes(self):
        """The reason the detector prompt had to change, held as a test so it cannot drift back."""
        image = Image.new("RGBA", (896, 1200), (24, 26, 30, 255))
        draw = ImageDraw.Draw(image)
        draw.rectangle((0.10 * 896, 0.65 * 1200, 0.90 * 896, 0.90 * 1200), fill=(238, 222, 188, 255))
        # A branch across the panel's right third, exactly the Craterhoof case.
        draw.rectangle((0.60 * 896, 0.65 * 1200, 0.72 * 896, 0.90 * 1200), fill=(48, 40, 30, 255))
        clipped = {"rules": [(0.10, 0.65, 0.57, 0.90)]}
        honest = {"rules": [(0.10, 0.65, 0.90, 0.90)]}
        self.assertIsNone(check.obstructed(image, clipped), "a clipped box hides the branch")
        self.assertIsNotNone(check.obstructed(image, honest), "an honest box has to see it")
