"""The Art Only brief must always carry the two things that make it Art Only.

Both are correctness rules, not wording preferences: the colour identity comes from
Scryfall (BUILD-SPEC §7) and the ban on furniture is the whole difference between this mode
and Creative Full (BUILD-SPEC §2).
"""

from django.test import SimpleTestCase

from generation import prompts

GREEN = {
    "name": "Craterhoof Behemoth",
    "type_line": "Creature — Beast",
    "oracle_text": "Trample, haste",
    "flavor_text": "",
    "color_identity": ["G"],
    "art_crop": "https://cards.scryfall.io/art_crop/x.jpg",
    "face_position": "SINGLE",
}


class ArtOnlyBriefTests(SimpleTestCase):
    def test_colour_identity_is_named_and_purple_is_forbidden(self):
        brief = prompts.art_only(GREEN)
        self.assertIn("green", brief)
        self.assertIn("purple", brief)  # the named ban, not a colour we asked for

    def test_colourless_card_does_not_claim_a_colour(self):
        brief = prompts.art_only({**GREEN, "name": "Sol Ring", "color_identity": []})
        self.assertIn("colourless", brief)
        for colour in ("green", "white", "blue", "black", "red"):
            self.assertNotIn(colour, brief)

    def test_furniture_is_forbidden_by_name(self):
        brief = prompts.art_only(GREEN)
        for banned in ("no text", "no mana symbols", "no border", "no frame", "no banner"):
            self.assertIn(banned, brief)

    def test_reference_is_only_described_when_one_is_attached(self):
        self.assertIn("attached image", prompts.art_only(GREEN))
        self.assertNotIn("attached image", prompts.art_only(GREEN, reference=False))

    def test_an_unknown_style_is_passed_through_verbatim(self):
        """The fallback is what the "Custom Art Style" free-text field rides on."""
        self.assertIn("Art style: dark fantasy oil", prompts.art_only(GREEN, "dark fantasy oil"))

    def test_the_catalogue_matches_the_reference_site_key_for_key(self):
        """48 styles, keyed by the exact value their API sends as `art_style`, so a frontend can
        pass the selection straight through with no mapping table in between."""
        self.assertEqual(len(prompts.STYLES), 48)
        self.assertEqual(set(prompts.STYLES), set(prompts.STYLE_LABELS))
        for key in prompts.STYLES:
            self.assertEqual(key, key.lower().replace(" ", "_").replace(".", ""))

    def test_a_style_resolves_from_its_key_or_its_label(self):
        """Their API sends snake_case values; their UI shows Title Case labels. Both arrive."""
        self.assertEqual(prompts._style_text("hr_giger"), prompts._style_text("H.R. Giger"))
        self.assertEqual(prompts._style_text("neon_noir"), prompts._style_text("Neon Noir"))
        self.assertIsNone(prompts._style_text(None))

    def test_a_known_style_expands_into_its_attributes(self):
        """A bare label gives a generic treatment; the attributes are the look (bd mtg-8x6)."""
        brief = prompts.art_only(GREEN, "Comic Book")
        self.assertIn("cross-hatching", brief)
        self.assertIn("halftone", brief)

    def test_the_quality_bar_is_in_every_brief_even_with_no_style(self):
        """The reference site's art beats ours on composition and light, not on model or
        resolution — its cards are the same 1792x2400. Naming only a style produced flat art:
        Lightning Bolt under "Graffiti" came back a wall with no subject on it."""
        for brief in (prompts.art_only(GREEN), prompts.art_only(GREEN, "Comic Book")):
            self.assertIn("ONE dominant subject", brief)
            self.assertIn("haze", brief)

    def test_direction_and_palette_reach_the_brief(self):
        """BUILD-SPEC §10 ships three option groups; we had only wired up the first."""
        brief = prompts.art_only(GREEN, "Anime", direction="dynamic", palette="vibrant")
        self.assertIn("Composition: caught mid-action", brief)
        self.assertIn("Colour treatment: saturated and high-key", brief)

    def test_the_catalogue_keys_are_the_reference_site_s_own(self):
        """Extracted verbatim from their bundle on 2026-08-15, so a value from their API — or
        from a user who read their docs — resolves here instead of passing through as prose."""
        for key in ("worms_eye", "rule_of_thirds", "intimate", "menacing"):
            self.assertIn(key, prompts.DIRECTIONS)
        for key in ("earth_tones", "jewel_tones", "toxic", "cosmic"):
            self.assertIn(key, prompts.PALETTES)

    def test_an_unknown_direction_or_palette_passes_through_verbatim(self):
        """Same rule as `_style_text`: the select and the free-text field are one field, so an
        unrecognised value is a feature rather than a gap."""
        brief = prompts.art_only(GREEN, direction="shot from a well", palette="lit by one candle")
        self.assertIn("Composition: shot from a well", brief)
        self.assertIn("Colour treatment: lit by one candle", brief)

    def test_the_catalogue_is_the_reference_site_s_counts(self):
        """48/21/20, read off their bundle (HOW-THEY-DO §3). The frontend renders these lists,
        so a row lost here is a dropdown that silently shrinks."""
        self.assertEqual(len(prompts.STYLE_LABELS), 48)
        self.assertEqual(len(prompts.DIRECTIONS), 21)
        self.assertEqual(len(prompts.PALETTES), 20)

    def test_no_palette_names_a_hue_that_could_restate_the_colour_identity(self):
        """Colour identity comes from Scryfall, never from the palette (CLAUDE.md) — the client
        reported purple leaking into a mono-green card. Palettes describe LIGHT, not paint."""
        for key, (label, text, group) in prompts.PALETTES.items():
            with self.subTest(palette=key):
                self.assertNotIn("purple", text.lower())
                self.assertNotIn("violet", text.lower())

    def test_every_style_names_a_medium(self):
        """A row listing only light and mood renders photoreal: 'Neon Noir' described neon rim
        light and wet surfaces, and Counterspell came back a cinematic photograph — the client's
        original complaint, reintroduced by us. A medium is what keeps a style illustrative."""
        # Grown with the catalogue when it went from 8 rows to the reference site's full 48. Each
        # word here is a MEDIUM someone works in, never a mood or a subject — that distinction is
        # the whole point of the test, so adding "epic" or "gothic" to make a row pass would
        # quietly disable it.
        media = (
            "illustration",
            "cartoon",
            "inked",
            "ink ",
            "painted",
            "painting",
            "graffiti",
            "anime",
            "manga",
            "render",
            "sketch",
            "drawing",
            "sprite",
            "poster",
            "lithograph",
            "collage",
            "diorama",
            "window",
            "cel",
            "panel",
        )
        for key, attributes in prompts.STYLES.items():
            with self.subTest(style=key):
                self.assertTrue(
                    any(m in attributes for m in media),
                    f"{key} names no medium, so it will render photoreal",
                )

    def test_the_palette_lights_the_scene_and_does_not_repaint_the_subject(self):
        """Mono-red Raphael came back a red turtle and mono-white Frodo came back greyscale,
        both because "and nothing else" outranked the subject's own colour (bd mtg-roq)."""
        brief = prompts.art_only({**GREEN, "color_identity": ["W"]})
        self.assertNotIn("must read as white and nothing else", brief)
        self.assertIn("do not drain it to monochrome", brief)

    def test_the_colour_is_assigned_to_the_light_not_to_every_surface(self):
        """MEASURED: 'a luminous red palette in the light, the atmosphere, the ground and the
        accents' floods the frame — mean saturation 195-199 for ours against 91-133 for the
        reference site's own version of the same four cards. A red dragon on red rock in red haze
        has no silhouette. The mana colour is emissive; surfaces stay neutral."""
        brief = prompts.art_only({**GREEN, "color_identity": ["R"]})
        self.assertIn("belongs to the LIGHT", brief)
        self.assertIn("stone stays grey", brief)
        self.assertNotIn("the ground and the accents", brief)

    def test_the_subject_may_keep_a_colour_the_card_does_not_have(self):
        """MEASURED 2026-08-11: the paragraph named only NEUTRAL things that keep their colour —
        stone, steel, bone, smoke — so nothing told the model a subject with a colour of its own
        may keep it. Mono-red Raphael came back a red turtle again, shell and all, on a card
        whose whole point is that he is green. The reference site's Raphael is green on the same
        red card, so their brief permits it and ours did not."""
        brief = prompts.art_only({**GREEN, "color_identity": ["R"]})
        self.assertIn("THE SUBJECT KEEPS ITS OWN COLOUR", brief)
        self.assertIn("a green turtle on a red card stays green", brief)
        self.assertIn("never paint applied to the subject itself", brief)

    def test_black_is_carried_by_darkness_because_it_has_no_light_of_its_own(self):
        """MEASURED 2026-08-16: mono-black is the only identity that has never passed
        `check.colour_identity`. Phyrexian Obliterator came back red 79% under the `pastel` palette
        and red 100% under `oil_painting` — a plain style with nothing fighting it. Four failures,
        two styles, no passes.

        The cause is structural rather than a wording miss. The paragraph above assigns the
        identity to emissive light, and black has no emissive colour: there is no black glow, so
        there is nothing to assign and whatever warmth the style carries wins by default.

        `check.colour_identity` passes a card by exactly two routes — it makes no colour claim
        (saturated share below NEUTRAL_SHARE, which is how white and colourless pass), or the
        dominant hue is one of its own, and the hue `check` reads back as black is purple. Black
        is given both, and warm light is banned by name because warm light is the measured
        failure."""
        black = prompts.art_only({**GREEN, "color_identity": ["B"]})
        self.assertIn("no light of its own", black)
        self.assertIn("NO WARM LIGHT", black)
        self.assertNotIn("belongs to the LIGHT", black)

    def test_white_is_the_absence_of_hue_and_is_never_lit_warm(self):
        """MEASURED 2026-08-16: two of three mono-white cards under `watercolor` misstated their
        colour. Serra Angel came back red 98%, was repainted, and came back red 98% again —
        UNSOUND. Swords to Plowshares came back red 99% on attempt 1 and only a repaint saved it.

        Structural, like black, and for the mirror-image reason. `check._HUE_BUCKETS` maps hues to
        R, G, U and B only: white has no hue of its own, so it can pass by exactly ONE route —
        staying under NEUTRAL_SHARE, i.e. genuinely desaturated. Any warm cast at all puts it over.

        And the generic clause was pushing it there. Read back to a white card it said the white
        "belongs to the LIGHT — glows, FLAMES, energy, rim light, the HOT SPOTS" and "must read as
        the brightest thing ... which is what makes it READ HOT". Watercolour's warm paper needed
        no encouragement.

        White's brightness stays; its warmth goes. Gold armour and brass are still allowed as
        MATERIAL — the distinction the rest of this clause already draws — but never as the light
        over the scene."""
        white = prompts.art_only({**GREEN, "color_identity": ["W"]})
        self.assertIn("NO WARM CAST", white)
        self.assertNotIn("read hot", white)
        self.assertNotIn("flames", white)

    def test_the_other_colours_keep_the_emissive_clause_they_were_measured_on(self):
        """Only white and mono-black are carved out. Red, green and blue all have a hue `check`
        can read back, and the emissive wording is verified on them under a hostile palette
        (COLOUR-2026-08-16: red 74%, green 83%, blue 91%, all PASS)."""
        for identity in (["R"], ["G"], ["U"], ["W", "U"]):
            with self.subTest(identity=identity):
                brief = prompts.art_only({**GREEN, "color_identity": identity})
                self.assertIn("belongs to the LIGHT", brief)
                self.assertNotIn("NO WARM CAST", brief)

    def test_a_black_card_with_a_partner_colour_keeps_the_emissive_clause(self):
        """B/R and B/G have a partner colour that does own an emissive, so the generic clause has
        something to assign and has not been measured failing. Widening the black branch to cover
        them would be a guess."""
        both = prompts.art_only({**GREEN, "color_identity": ["B", "R"]})
        self.assertIn("belongs to the LIGHT", both)
        self.assertNotIn("NO WARM LIGHT", both)

    def test_the_palette_restates_the_identity_instead_of_pointing_back_at_it(self):
        """A back-reference lost to the palette on a real card (bd mtg-5pb).

        Job 9f16e827: `ice` on mono-red Lightning Bolt came back blue-white — frost, icicles,
        cold glare — with red left as an ember. The clause said "within the colour identity
        above"; pointing at a rule is weaker than restating it, and the rerun with identical
        inputs read red, so it is intermittent rather than absent.
        """
        for brief in (
            prompts.art_only({**GREEN, "color_identity": ["R"]}, palette="ice"),
            prompts.creative_full({**GREEN, "color_identity": ["R"]}, palette="ice"),
        ):
            self.assertIn("lit through ice, frost and pale glare", brief)
            self.assertIn("the red of this card's colour identity stays the brightest", brief)
            self.assertIn("Where the two disagree, the red wins", brief)
            self.assertNotIn("within the colour identity above", brief)

    def test_a_colourless_card_gets_no_second_weaker_restatement(self):
        """Colourless already forbids all five hues by name. Restating it here would hand the
        model two rules to reconcile where it had one to follow."""
        brief = prompts.art_only({**GREEN, "color_identity": []}, palette="ice")
        self.assertIn("Colour treatment: lit through ice", brief)
        self.assertNotIn("stays the brightest", brief)

    def test_a_style_that_names_colours_still_loses_to_the_card(self):
        """The other door the same bug walks through (bd mtg-v2n): the Rick and Morty row
        hard-codes 'acid-bright greens and cyans' and turned mono-black Vampiric Tutor green."""
        for brief in (
            prompts.art_only(GREEN, "rick_and_morty"),
            prompts.creative_full(GREEN, "rick_and_morty"),
        ):
            self.assertIn("still decides which colour reads hottest", brief)

    def test_a_licensed_card_is_briefed_from_its_type_line_not_its_name(self):
        """Hulk is refused with the art attached AND without it; the same card's type line
        generates first try. The card keeps its mechanics and loses only the proper noun."""
        hulk = {
            "name": "Hulk, Bruce Banner",
            "type_line": "Legendary Creature — Gamma Berserker Hero",
            "oracle_text": "Whenever Hulk attacks, it gets +2/+2.",
            "flavor_text": '"Hulk smash!"',
            "color_identity": ["R"],
            "art_crop": None,
            "face_position": "SINGLE",
        }
        brief = prompts.art_only(hulk, "Baroque", reference=False, licensed=True)
        self.assertNotIn("Hulk", brief)
        self.assertNotIn("Bruce Banner", brief)
        self.assertIn("a legendary gamma berserker hero", brief)
        self.assertIn("Whenever this creature attacks", brief)  # rules text survives
        self.assertIn("Legendary Creature", brief)  # so does the type line

    def test_a_typeless_licensed_card_still_gets_a_subject(self):
        brief = prompts.art_only(
            {**GREEN, "name": "Someone, A Person", "type_line": "Legendary Enchantment"},
            reference=False,
            licensed=True,
        )
        self.assertIn("Subject: a legendary enchantment", brief)

    def test_the_style_is_told_it_outranks_the_reference(self):
        """Swords to Plowshares came back a sunlit farm under a dark-fantasy brief because
        the brief asked to preserve the setting and never said which side wins."""
        brief = prompts.art_only(GREEN, "dark fantasy oil")
        self.assertIn("the art style wins", brief)
        self.assertIn("not its setting", brief)

    def test_the_card_is_handed_a_staging_instead_of_being_told_not_to_copy_one(self):
        """CLIENT 2026-08-16: Craterhoof came back "the same animal in the same pose as the
        original". REFERENCE already says "invent a NEW moment for them, with a different pose, a
        different action, a different angle" and it lost — the fourth correctly-worded clause on
        this project to be ignored.

        The other three were only fixed by changing the KIND of instruction, never by rewording:
        the P/T shield by looking closer, the title order by a late positive restatement, the
        overlap by being made compulsory with a count. So the model is given a camera and a moment
        to paint rather than a staging to avoid."""
        brief = prompts.art_only(GREEN)
        self.assertIn("STAGE IT THIS WAY", brief)
        self.assertIn("NOT the staging of the attached reference", brief)
        # It has to arrive after the reference it overrides, or it is arguing with something the
        # model has not read yet.
        self.assertLess(brief.index("official artwork"), brief.index("STAGE IT THIS WAY"))

    def test_the_staging_is_fixed_by_the_card_so_a_rerun_is_comparable(self):
        """A random staging would make the same card differ on every run, which breaks the one
        method this project uses to tell a fix from noise: rerun the same card over the same
        settings and compare. `hash()` is salted per process, so the name's own bytes are used."""
        self.assertEqual(prompts._staging(GREEN), prompts._staging(GREEN))
        self.assertEqual(prompts._staging({**GREEN}), prompts._staging(GREEN))

    def test_different_cards_get_different_stagings(self):
        """One staging for every card would be a house style, not a fix — it would put the whole
        set in the same pose instead of the reference's."""
        names = ("Craterhoof Behemoth", "Raphael, Tough Turtle", "Tower Winder", "Sol Ring",
                 "Lightning Bolt", "Counterspell", "Elesh Norn", "Swords to Plowshares")
        stagings = {prompts._staging({**GREEN, "name": n}) for n in names}
        self.assertGreater(len(stagings), len(names) // 2, f"stagings collapse: {stagings}")

    def test_no_staging_names_an_action_only_a_creature_could_do(self):
        """Creative Full briefs artifacts and instants through this same path. "Charging at the
        viewer" is a direction to a beast and nonsense to Sol Ring, so the vocabulary is angles and
        beats, which apply to anything that can be drawn."""
        for phrase in prompts.STAGING_CAMERA + prompts.STAGING_MOMENT:
            for creature_only in ("charg", "roar", "attack", "leap", "claw", "wing", "snarl"):
                self.assertNotIn(creature_only, phrase.lower(), f"{phrase!r} assumes a creature")

    def test_the_reference_gives_the_character_and_not_the_composition(self):
        """CLIENT 2026-08-13: "it is a little too similar to the original art on one of them, we
        usually dont want them to come out looking like the original card, just elements to be
        there." Our Raphael restaged the official card exactly — same turtle, same bowling-ball
        dumbbells, same gym — because the brief asked for "what is in it, and what they are doing".

        Both halves are load-bearing. Dropping the identity is the opposite failure and it was the
        client's FIRST complaint about the batch, so the brief has to take the character and refuse
        the staging, in that order."""
        brief = prompts.art_only(GREEN)
        self.assertIn("ONLY WHO OR WHAT the subject is", brief)
        self.assertIn("Do not restage the picture", brief)
        self.assertIn("the same character and not the same picture", brief)
        # And the same paragraph in both modes: one answer to the question, not two that drift.
        self.assertIn(prompts.REFERENCE, prompts.creative_full(GREEN))


class CreativeFullBriefTests(SimpleTestCase):
    """Creative Full inverts Art Only: furniture is the deliverable, lettering is the defect."""

    def test_borderless_is_the_default_and_framed_is_still_reachable(self):
        """CLIENT 2026-08-13: "the white borders on the first card are not ideal ... id be okay
        with black borders or black going around, (what we use to do is type into the custom art
        notes 'borderless' and try to get no black or white borders, if you can do that it would
        be by far the best!)" — so borderless is the default, and the framed edge stays because
        ~20 of the reference site's own 24 gallery cards do it and the client accepted it too."""
        self.assertIn("THE CARD IS FULL BLEED", prompts.creative_full(GREEN))
        self.assertIn("THE CARD'S EDGE", prompts.creative_full(GREEN, borderless=False))

    def test_the_overlap_is_compulsory_and_is_the_last_thing_the_brief_says(self):
        """CLIENT 2026-08-15, sending a card whose vines cross its own title arch: "you see how
        this card feels like 1 piece of art ... the examples you showed me ... dont have an
        abstract text box design."

        The brief already asked for this — "at one or two points something from the scene ...
        crosses in FRONT of one" — and MEASURED 2026-08-16 it produced zero overlaps on our
        Craterhoof and Raphael, against vines over the title plate and roots over the rules panel
        on the reference site's own Craterhoof. Soft wording placed ABOVE the surface list did not
        survive, so this asserts the three things that changed: it is required, it names a count,
        and it is last (bd mtg-39a — a restatement at the end is what fixed title order)."""
        brief = prompts.creative_full(GREEN)
        self.assertIn("AND: THE OVERLAP", brief)
        self.assertIn("At least TWO of the raised surfaces", brief)
        # The soft version must be gone, not merely outvoted by the new one.
        self.assertNotIn("at one or two points", brief)
        # Late and alone, like the top-plate clause: after the surfaces paragraph it lost inside,
        # and before the lettering ban, whose last place is measured.
        lines = brief.split("\n")
        overlap = next(i for i, l in enumerate(lines) if l.startswith("AND: THE OVERLAP"))
        surfaces = next(i for i, l in enumerate(lines) if l.startswith("Paint exactly these"))
        ban = next(i for i, l in enumerate(lines) if l.startswith("ABSOLUTE REQUIREMENT"))
        self.assertLess(surfaces, overlap)
        self.assertLess(overlap, ban)
        # Framed cards have the edge material doing this job and have not drawn the complaint.
        self.assertNotIn("AND: THE OVERLAP", prompts.creative_full(GREEN, borderless=False))

    def test_the_overlap_is_kept_off_the_face_the_compositor_prints_into(self):
        """The overlap is free at a surface's rim and expensive across its middle: `compositor`
        prints the rules text into the interior, so an element painted over it lands under our own
        lettering and `check.contrast` fails the card into a repaint. Asking for the overlap
        without bounding it trades the client's complaint for a legibility one."""
        brief = prompts.creative_full(GREEN)
        self.assertIn("OUTER EDGE or over one of its corners", brief)
        self.assertIn("broad flat middle of every surface stays completely clear", brief)

    def test_surfaces_do_not_end_in_a_square_cut(self):
        """Every surface on the reference site's Craterhoof ends in a carved boss; ours end square,
        which is most of what "laid on" looks like at a glance. Cheap, and unlike the overlap it
        risks nothing near the printable face."""
        self.assertIn("No surface ends in a square cut", prompts.creative_full(GREEN))

    def test_full_bleed_is_asked_for_positively_before_it_is_banned(self):
        """bd mtg-z12's finding cuts both ways: naming an object summons it, and "no border" is a
        sentence with a border in it. So the ask is what to paint — scene to the trim on all four
        sides — and the ban follows it rather than standing alone."""
        brief = prompts.creative_full(GREEN)
        self.assertIn("The picture runs off all four edges of the image", brief)
        self.assertIn("All four corners are painted scene", brief)
        self.assertLess(
            brief.index("The picture runs off all four edges"),
            brief.index("Nothing surrounds the picture"),
        )
        self.assertIn("no white or black edge anywhere", brief)
        # MEASURED 2026-08-13, first generation under this brief: it obeyed the full bleed and
        # still built a card, with a riveted steel band across the top tenth and the picture inset
        # in a rectangle below it. No border was drawn — the band and the strips MADE one.
        self.assertIn("There is NO ART WINDOW", brief)
        self.assertIn("no surface reaches the left or right edge", brief)
        self.assertIn("NARROWER than the card", brief)
        # The noun itself stays out of the brief in BOTH modes, which is what mtg-z12 measured.
        for noun in ("border", "frame around", "mount", "inset inside", "matted"):
            self.assertNotIn(noun, brief)

    def test_borderless_plates_are_objects_in_the_scene_so_they_are_still_anchored(self):
        """The edge material was what stopped the plates reading as pasted on: asked for with
        nothing anchoring them they came back as three cream rectangles on every card in the batch.
        Take the edge away and the anchor has to become the plate itself being a THING — which is
        how the ink-sketch cards the client sent do it, every text surface a painted ribbon in the
        same ink as the art with the art running behind it."""
        brief = prompts.creative_full(GREEN)
        self.assertIn("OBJECT IN THE SCENE", brief)
        self.assertIn("casts its own shadow", brief)
        self.assertIn("crossing in FRONT of them", brief)
        self.assertIn("ONE piece of art", brief)

    def test_borderless_frees_placement_but_not_the_order_or_the_baseline(self):
        """The client's fourth ask is "creative as to where to place the text ... make the card
        feel like 1 piece of art". It is granted as width and position, not as rotation: the
        compositor lays out axis-aligned lines and `check` asserts the vertical order, and their own
        Wheel of Fortune with rules text on a painted diagonal is the least readable card in the
        reference gallery."""
        brief = prompts.creative_full(GREEN)
        self.assertIn("need not span the card's full width", brief)
        self.assertIn("as long as the ORDER down the card is kept", brief)
        self.assertIn("stay straight and level", brief)

    def test_the_pt_tab_is_dark_like_the_other_two_display_surfaces(self):
        """CLIENT 2026-08-16: "some P/T are large some small and small pure black dull ugly".

        The VALUE paragraph governed the top plate, the narrow strip and the broad strip, and said
        nothing about the tab — the only display surface left free. So its value came out of the
        art, and `compositor.panel_palette` branched on it: below luminance 128 the numerals are
        GOLD with a stroke and a saturated shadow, above it they are unstroked near-black. Measured
        over nine cards, six landed dark (71-126) and three landed pale (151-162), so the same
        field alternated between the handsome treatment and flat black on grey stone.

        The tab is a display surface and Magic's convention for it is fixed — dark plate, light
        numerals, on every card ever printed. Pinning its value is the same fix the other two
        display surfaces already have, and it costs the compositor nothing: panel_palette then
        picks gold on its own."""
        brief = prompts.creative_full({**GREEN, "power": "5", "toughness": "5"})
        value = brief[brief.index("VALUE, and getting this wrong"):]
        self.assertIn("The tab at the bottom right is DARK", value)

    def test_a_flat_face_is_square_to_the_viewer_and_ends_at_a_definite_edge(self):
        """Both measured on one card, 2026-08-16, the first batch after "straight-sided" went in
        (bd mtg-cig). Straight-sided constrains the OUTLINE and neither of these is an outline.

        PLANE: Elesh Norn's P/T came back a broken stone slab lying flat on the ground and receding
        away from the camera. "4/7" is composited square onto it, so the number sits on a plane the
        art says is horizontal and reads as pasted on. It satisfied straight-sided — the slab IS a
        rectangle — and `panels.detect` and `check` both passed it.

        EDGE: the pastel Obliterator's rules slab fades into dark mud rather than ending. Row-mean
        lightness down its detected box runs 111-171 to y0.877 and then 82, 54, 39, 34 — the
        painted face stops near y0.885 and the box runs to y0.940, so the last line is set in dark
        ink on the artwork. `printable_face` returns that box unchanged because it peels width
        only, `plate_extent` grows the bottom further, and the card's UNSOUND [panel_too_dark] at
        4.53:1 is this defect being sampled rather than a panel that is genuinely too dark.
        """
        brief = prompts.creative_full(GREEN)
        self.assertIn("square to the viewer", brief)
        self.assertIn("ENDS at a definite edge", brief)

    def test_the_word_borderless_in_the_notes_turns_the_mode_on(self):
        """The client's own workflow on the reference site is typing "borderless" into Custom Art
        Notes, so the word arriving in `notes` has to do what the argument does — and the note is
        still passed through verbatim as well."""
        brief = prompts.creative_full(GREEN, notes="borderless", borderless=False)
        self.assertIn("THE CARD IS FULL BLEED", brief)
        self.assertNotIn("THE CARD'S EDGE", brief)
        self.assertIn("Also: borderless.", brief)

    def test_borderless_never_mentions_edge_material_it_does_not_have(self):
        """Four sentences elsewhere in the brief hang off the edge existing — the 1/12th margin,
        what may cover the subject, where writing is banned, where purple is banned. A brief that
        forbids writing "on the edge material" of a card with no edge material is telling the model
        the edge is there."""
        brief = prompts.creative_full(GREEN)
        self.assertNotIn("edge material", brief)
        self.assertIn("not anywhere in the artwork", brief)  # what replaces it in the writing ban
        self.assertIn("edge material", prompts.creative_full(GREEN, borderless=False))

    def test_no_surface_above_the_top_plate_but_the_scene_may_run_above_it(self):
        """"Nothing may be painted above the top plate" is right on a framed card and wrong on a
        full-bleed one, where the scene has to reach the top edge — the two instructions would
        cancel and one of them would lose."""
        for borderless in (True, False):
            with self.subTest(borderless=borderless):
                brief = prompts.creative_full(GREEN, borderless=borderless)
                self.assertIn("No surface may be painted above the top plate", brief)

    def test_the_surfaces_are_demanded_and_lettering_is_forbidden(self):
        brief = prompts.creative_full(GREEN, "Comic Book")
        for surface in ("plate across the very top", "NARROW horizontal strip", "broad pale strip"):
            self.assertIn(surface, brief)
        self.assertIn("NO WRITING ANYWHERE", brief)
        self.assertIn("no fake writing", brief)

    def test_the_edge_is_asked_for_as_material_and_never_as_a_border(self):
        """~20 of 24 reference-site cards build the card's edge out of the scene's material and
        hang the plates off it; ours were three rectangles floating on a painting with nothing
        anchoring them. bd mtg-z12 got a gallery mount from the word "border" and concluded the
        framed look was the failure — it was the noun. Naming the object brings the object, so
        the shape is asked for and the noun stays out."""
        brief = prompts.creative_full(GREEN, borderless=False)
        self.assertIn("closes in around the scene at the card's edge", brief)
        self.assertIn("crosses in FRONT of it", brief)
        for noun in ("border", "frame around", "mount", "inset inside", "matted"):
            self.assertNotIn(noun, brief)

    def test_the_edge_material_carries_the_colour_as_light(self):
        """Theirs is a hot orange ribbon of lava; ours came back near-black rock, which is what
        made the whole card read dark and muddy beside it. The emissive convention _palette
        enforces for the scene (bd mtg-roq) had never been stated for the edge, and the material
        list led with "cracked obsidian", so the model painted a dark rim."""
        brief = prompts.creative_full(GREEN, borderless=False)
        self.assertIn("Run the card's colour through it as LIGHT", brief)
        self.assertIn("not a dark rim around a bright picture", brief)
        self.assertNotIn("cracked obsidian", brief)

    def test_the_edge_encloses_the_card_and_not_only_the_picture(self):
        """First generation under the framed brief enclosed the ARTWORK and stopped: both side
        members died where the lower surfaces began, the bottom never closed, and the two bottom
        corners came back as dead black wedges. To a model painting a picture, "the card's edge"
        and "around the scene" are the same sentence."""
        brief = prompts.creative_full(GREEN, borderless=False)
        self.assertIn("encloses the whole CARD", brief)
        self.assertIn("closes across the bottom", brief)
        self.assertIn("No corner and no edge of this card is left as empty dark space", brief)

    def test_the_surface_count_is_restated_after_the_surfaces_are_described(self):
        """"and no others" sat in the same sentence as the descriptions and lost to them: the
        generation after the enclosing-edge line was added came back with a row of THREE extra
        glowing slabs between the picture and the type strip, which also stole the rules slab's
        height and made the overflow warning fire for real."""
        brief = prompts.creative_full({**GREEN, "power": "5"})
        self.assertIn("That is 4 and only 4", brief)  # 3 surfaces + the P/T boss
        self.assertIn("do not split a surface into a row of smaller ones", brief)
        self.assertIn("never another plate, tablet, ingot", brief)

    def test_exactly_one_pale_strip_is_asked_for_however_many_abilities(self):
        """REVERSED 2026-08-10 after a four-card batch, and this test is the record of it. The
        reference site sets one pale strip per ability; asked of our model it does not work.
        One-ability cards (Vampiric Tutor, Sol Ring) came back with large readable text filling
        the panel; three- and two-ability cards (Terror, Craterhoof) came back with tiny text in
        half-empty strips, and Craterhoof inverted the requested height ratio outright.

        The mechanism was measured in test_compositor before the first strip was ever painted:
        every strip shares one type size, so the size is capped by the WORST-fitting strip, while
        one slab lends spare height between paragraphs — 115px against 97px at equal area."""
        for oracle in ("Trample", "Flying\nTrample", "Flying\nTrample\nHaste\nVigilance"):
            with self.subTest(oracle=oracle):
                brief = prompts.creative_full({**GREEN, "oracle_text": oracle})
                self.assertIn("ONE broad pale strip across the lower third", brief)
                self.assertNotIn("SEPARATE pale strips", brief)
                self.assertIn("Paint exactly these 3 raised surfaces", brief)

    def test_the_vertical_order_of_the_surfaces_is_stated_as_a_requirement(self):
        """MEASURED across ten generations of one card at identical settings: their surfaces move
        a great deal — the type plate sits under the title on some and halfway down on others,
        the rules panel is a full-width band on some and a narrow right-hand float on others —
        but the vertical ORDER is the same on all ten. Ours listed the surfaces and never said
        the order mattered, and two consecutive generations put the name plate in the lower
        third."""
        brief = prompts.creative_full({**GREEN, "power": "5"})
        self.assertIn("Their order down the card is fixed", brief)
        self.assertIn("TOPMOST thing on the card", brief)
        self.assertIn("No surface may be painted above the top plate", brief)

    def test_custom_art_notes_reach_the_brief_verbatim(self):
        """`custom_art_notes` in their generate payload. Placed after the style so it refines
        rather than replaces it, and before the furniture so it cannot argue with the surfaces.
        Verbatim, because it is the one field where second-guessing the user is wrong."""
        brief = prompts.creative_full(GREEN, "Anime", notes="give it six eyes and no mouth")
        self.assertIn("Also: give it six eyes and no mouth.", brief)
        self.assertLess(brief.index("Also: give it"), brief.index("THE RAISED SURFACES"))
        self.assertGreater(brief.index("Also: give it"), brief.index("Art style:"))
        self.assertNotIn("Also:", prompts.creative_full(GREEN, "Anime"))

    def test_the_narrow_side_panel_is_offered_only_to_short_cards(self):
        """The reference site produces a narrow right-hand rules panel on about 2 of every 10
        cards. It is the best-looking layout they have and the most expensive: half the measure
        is roughly twice the lines, and text that will not fit at a readable size costs a
        regeneration. Their brief evidently just permits it; ours permits it only where the
        arithmetic survives — the long cards are exactly the ones that came back unreadable."""
        short = prompts.creative_full({**GREEN, "oracle_text": "Counter target spell."})
        self.assertIn("TALL NARROW", short)
        long = prompts.creative_full(
            {**GREEN, "oracle_text": "Flying\n" + "Whenever this creature attacks it gets bigger. " * 5}
        )
        self.assertNotIn("TALL NARROW", long)

    def test_the_float_is_still_one_panel_with_level_text_edges(self):
        """The compositor lays out axis-aligned lines, and their own Wheel of Fortune — rules set
        on a painted diagonal — is the one card in their gallery that is barely readable."""
        short = prompts.creative_full({**GREEN, "oracle_text": "Counter target spell."})
        self.assertIn("Either way it is one panel", short)
        self.assertIn("straight level top and bottom edges", short)

    def test_the_length_hint_is_a_total_and_a_paragraph_count_never_the_text(self):
        """You cannot paint text you were never given — Atraxa came back fully lettered from this
        line's predecessor. The paragraph count tells the model the strip needs room for the gaps
        between abilities without showing it a single word."""
        brief = prompts.creative_full({**GREEN, "oracle_text": "Flying\nTrample and haste"})
        self.assertIn("characters of text, in 2 separate paragraphs", brief)
        self.assertNotIn("Trample and haste", brief)

    def test_no_surface_may_be_a_plain_rectangle_but_its_text_edges_stay_level(self):
        """Both halves are load-bearing. Even bevelled rectangles are what made every card in a
        batch look like the same sticker set; but the compositor lays out axis-aligned lines, and
        their own Wheel of Fortune — rules text set on a painted diagonal — is the one card in
        the gallery that is barely readable."""
        brief = prompts.creative_full(GREEN)
        self.assertIn("No surface is a plain rectangle", brief)
        self.assertIn("stay roughly straight and level", brief)

    def test_surfaces_are_described_as_shapes_not_as_fields(self):
        """Naming a field invites filling it: "title banner" got a painted title and "plaque for
        power/toughness" got a literal "P/T" (Atraxa and Terror, 2026-08-10)."""
        brief = prompts.creative_full({**GREEN, "power": "5"})
        for invitation in ("title banner", "type bar", "power/toughness", "rules panel"):
            self.assertNotIn(invitation, brief)

    def test_the_name_and_the_rules_text_are_never_shown(self):
        """You cannot paint text you were never given. Atraxa painted its own name and type line
        straight from the brief, so Creative Full withholds both and passes only the length."""
        brief = prompts.creative_full(GREEN)
        self.assertNotIn(GREEN["name"], brief)
        self.assertNotIn(GREEN["oracle_text"], brief)
        self.assertIn(f"about {len(GREEN['oracle_text'])} characters", brief)

    def test_runes_get_their_own_sentence_after_the_list(self):
        """MEASURED 2026-08-11 on Raphael: a band of carved rune-like marks came back in the gap
        BETWEEN the type plate and the rules panel — a region the ban named as "surfaces" and
        "edge material" and therefore did not cover. Runes are the recurring form of this failure
        rather than one item in a list of twelve, and the reference site has it too: their
        Twinflame Tyrant carries painted fake runes beside its real composited text."""
        brief = prompts.creative_full(GREEN)
        self.assertIn("not in the gaps between them", brief)
        self.assertIn("RUNES ESPECIALLY", brief)
        self.assertIn("failed even when the marks are meant as ornament", brief)
        self.assertGreater(brief.index("RUNES ESPECIALLY"), brief.index("ABSOLUTE REQUIREMENT"))

    def test_the_ban_on_writing_is_the_last_thing_in_the_brief(self):
        """Stated mid-brief it lost to the furniture description on 2 of 3 cards. It keeps the
        last position even against the purple ban added after it: painted lettering collides with
        the text we composite and makes the card unusable, where a purple tint misstates the
        colour identity of a card that still works."""
        for identity in ([], ["G"], ["B"], ["W", "U"]):
            with self.subTest(colour=identity):
                brief = prompts.creative_full({**GREEN, "color_identity": identity})
                # The rune sentence is part of the same ban and is allowed to follow it; nothing
                # about the FURNITURE may.
                tail = brief.rstrip()
                self.assertTrue(
                    tail.endswith("collide with it.") or tail.endswith("a crack, a leaf."),
                    tail[-60:],
                )

    def test_a_non_black_card_repeats_the_purple_ban_late(self):
        """MEASURED 2026-08-10, eight-card batch: mono-green Craterhoof came back with magenta
        crystal growths. The ban was already in _palette near the top, and this file has learned
        twice that a ban stated early loses to the description that follows it. Purple reading as
        black mana is the client's reported bug and a BUILD-SPEC §7 failure, not a preference."""
        green = prompts.creative_full(GREEN)
        self.assertIn("no purple, violet, magenta or lilac", green)
        self.assertLess(green.index("no purple, violet"), green.index("ABSOLUTE REQUIREMENT"))
        # And it stays there when anything new is appended to the ban. It was inserted by
        # counting back from the end and silently jumped the writing ban the day a rune sentence
        # was added, which is why it is now located by searching for the ban itself.
        self.assertLess(green.index("no purple, violet"), green.index("RUNES ESPECIALLY"))

    def test_a_black_card_is_not_told_to_avoid_purple(self):
        """Purple reads as black mana, so on a black card it is correct rather than a defect."""
        black = prompts.creative_full({**GREEN, "color_identity": ["B"]})
        self.assertNotIn("no purple, violet, magenta or lilac", black)

    def test_the_top_plate_may_not_be_omitted(self):
        """Sol Ring came back with no name plate at all in the eight-card batch, so its name went
        unprinted — the narrow strip already carried this instruction and the top plate did not."""
        self.assertIn("Do not omit this piece — every card has one", prompts.creative_full(GREEN))

    def test_furniture_is_made_of_the_art_not_laid_over_it(self):
        """A frame overlay on an art window scored 0/3 and read as art in a box (bd mtg-9pi)."""
        self.assertIn("SAME MATERIAL as the art", prompts.creative_full(GREEN))

    def test_the_text_zone_is_kept_clear_of_the_subject(self):
        brief = prompts.creative_full(GREEN)
        self.assertIn("UPPER-MIDDLE", brief)
        self.assertIn("middle 92%", brief)

    def test_the_rules_slab_may_not_be_made_of_the_scene_it_sits_in(self):
        """"Glowing amber stone" was the only mid-value material in a list of pale ones, and it
        is what red and green cards reached for (job 10746c0b). Those slabs measured 3.6:1 and
        4.5:1 against the printed text — sound by every structural check, unreadable in the hand.
        """
        brief = prompts.creative_full(GREEN)
        self.assertIn("LIGHT AND PALE", brief)
        self.assertIn("NOT a slab made of lava", brief)
        self.assertNotIn("glowing amber stone", brief)

    def test_the_quiet_lower_third_is_a_continuation_and_not_a_blank(self):
        """Calm is not empty (bd mtg-cjx, bd mtg-9ww).

        "Keep the lower half calm" made the model stop painting and leave dead space. What
        legibility needs is the scene continuing at low contrast — the same distinction the
        raised surfaces already carry, one layer further out. The brief has to ask for the
        continuation and forbid the blank, or it gets one of them at random.
        """
        brief = prompts.creative_full(GREEN)
        self.assertIn("CONTINUES through the lower third", brief)
        self.assertIn("never stops into a blank panel", brief)
        # The wording that produced the dead space must not come back.
        self.assertNotIn("Nothing that matters may sit in the lower third", brief)

    def test_art_only_is_not_given_a_calm_zone_it_has_no_text_to_protect(self):
        """The calm-zone clause is CONDITIONAL ON MODE, which bd mtg-cjx left undecided.

        Settled by running Art Only end to end on 2026-08-15 (jobs ac1c537c, ec31fe09): with no
        text box and no trim, full-bleed centred art is correct there. Reserving a quiet lower
        third for text that never arrives would throw away a third of the picture.
        """
        brief = prompts.art_only(GREEN)
        self.assertNotIn("lower third", brief)
        self.assertIn("fills the entire frame, edge to edge", brief)

    def test_a_pt_tab_is_only_asked_for_when_the_card_has_one(self):
        self.assertNotIn("a small raised tab", prompts.creative_full(GREEN))
        self.assertIn("a small raised tab", prompts.creative_full({**GREEN, "power": "5"}))

    def test_the_pt_tab_shape_is_left_open_because_naming_one_pinned_it(self):
        """MEASURED 2026-08-16 across 18 full-res CREATURE cards from their gallery: rounded
        rectangle or tab 11, disc 2, bare-on-the-art or irregular 3, SHIELD 2. Shield is 11% of the
        reference and was 100% of ours, because the brief said "shield-shaped boss" and naming a
        shape pins it — the same mechanism `test_surfaces_are_described_as_shapes_not_as_fields`
        guards for "banner" and "plaque".

        It is a correctness fix and not a taste one. The shield is a pointed rim around a small
        recessed face — bd mtg-1uv, "a fixed box cannot track a painted one" — and the smallest
        surface on the card at 0.067 of the width, which is what held detection at 35%. So what
        gets pinned now is the FACE, which is what we print on, not the outline."""
        brief = prompts.creative_full({**GREEN, "power": "5"})
        self.assertNotIn("shield-shaped", brief)
        # CLIENT 2026-08-16: "it shall come as per the art, not always shield." Leaving the choice
        # open was not enough — 1 of 3 staged Craterhoofs still came back a shield — so the shape
        # is led by the scene's material with concrete alternatives to paint.
        self.assertIn("Its shape comes from what this scene is made of", brief)
        for shape in ("a broken slab", "a river pebble", "a torn tag", "a beaten plate"):
            self.assertIn(shape, brief)

    def test_the_pt_tab_face_is_asked_for_as_bare_material(self):
        """CLIENT 2026-08-16: "and that too blank without any symbol in it, craterhoof has spiral
        in it" — the model carved a spiral into the tab and the 5/5 printed over it. Stated as what
        the face IS, not as a fourth ban: bd mtg-z12's finding is that naming a thing summons it,
        and "spiral" is already named once in the set-symbol clause."""
        brief = prompts.creative_full({**GREEN, "power": "5"})
        self.assertIn("BARE MATERIAL", brief)
        self.assertIn("nothing cut or carved into it", brief)


    def test_the_art_is_told_it_outranks_the_furniture(self):
        """MEASURED on the first three Creative Full generations: the rules panel came back
        eating ~40% of the card and the type bar was omitted, on all three."""
        brief = prompts.creative_full(GREEN)
        self.assertIn("THE ARTWORK DOMINATES", brief)
        self.assertIn("no more than a third of the card's height", brief)
        self.assertIn("Do not omit this piece", brief)

    def test_the_display_plates_are_dark_and_only_the_rules_slab_is_light(self):
        """The earlier reading — "their panels are cream parchment" — was taken from the rules
        slab alone and applied to all three, giving cream-on-cream-on-cream with black text
        everywhere and no hierarchy. Across their gallery the two display surfaces are dark with
        warm gold lettering. compositor.panel_palette already picks gold-on-dark or ink-on-light
        from the pixels, so this is a brief change with no code behind it."""
        brief = prompts.creative_full(GREEN)
        self.assertIn("narrow strip are DARK", brief)
        self.assertIn("broad strip is LIGHT", brief)
        self.assertIn("Do not paint all three the same value", brief)
        self.assertNotIn("Each surface must be PALE", brief)

    def test_legibility_is_asked_for_as_an_even_middle_not_as_an_empty_surface(self):
        """"quiet: low contrast, low detail, no busy texture and no bright hotspot" produced dead
        flat beige. Their slab on Terror of the Peaks is glowing lava with cracks running through
        it and the black text still reads, because what legibility needs is an even middle."""
        brief = prompts.creative_full(GREEN)
        self.assertIn("keep that band even in value", brief)
        self.assertIn("veins of glow", brief)
        self.assertNotIn("low contrast, low detail", brief)

    def test_a_colourless_card_forbids_each_mana_colour_by_name(self):
        """"No one mana colour may dominate" is too abstract: Sol Ring under Comic Book came back
        a fire-red card with an orange ring, and colourless reading as red is a §7 failure."""
        brief = prompts.creative_full({**GREEN, "color_identity": []})
        self.assertIn("COLOURLESS", brief)
        for banned in ("No red fire", "no green growth", "no blue water", "no black rot"):
            self.assertIn(banned, brief)


class StripHeightTests(SimpleTestCase):
    """The brief states how tall THIS card's rules strip has to be, instead of wishing for it.

    MEASURED 2026-08-15 over n=40 real printed 2015-frame cards (bd mtg-8h9,
    bd mtg-8h9): `compositor.RULES_MIN` is right to within 6% of the tightest
    real printing, so a card that trips it is genuinely unreadable and the floor must not be moved
    to make cards pass. The defect is upstream — the painted surface is too short — and the model
    could never have known, because we deliberately never show it the text.
    """

    TERSE = {**GREEN, "oracle_text": "Trample, haste"}
    WORDY = {
        **GREEN,
        "oracle_text": "Indestructible\nWhen this permanent enters, if you cast it, you gain "
        "protection from everything until your next turn.\nAt the beginning of your upkeep, you "
        "lose 1 life for each burden counter on it.\n{T}: Put a burden counter on it, then draw a "
        "card for each burden counter on it.",
    }

    def test_a_wordier_card_asks_for_a_taller_strip(self):
        self.assertGreater(
            prompts._strip_height(self.WORDY)[0], prompts._strip_height(self.TERSE)[0]
        )

    def test_the_requirement_reaches_the_brief_with_a_number_in_it(self):
        brief = prompts.creative_full(self.WORDY)
        self.assertIn("AT LEAST", brief)
        self.assertIn(prompts._strip_height(self.WORDY)[1], brief)
        # And it must not license several strips: the brief already says "do not split a
        # surface into a row of smaller ones — the one broad pale strip is the only place the
        # rules text goes". A height clause that says "or their combined height" contradicts it,
        # and a brief that asks for two incompatible things gets one of them at random.
        self.assertNotIn("COMBINED", brief)

    def test_a_card_with_no_rules_text_is_not_told_to_paint_a_strip_of_none(self):
        """Vanilla creatures exist, and an f-string with a None in it is a brief that reads as
        broken to the model."""
        vanilla = {**GREEN, "oracle_text": ""}
        self.assertIsNone(prompts._strip_height(vanilla))
        brief = prompts.creative_full(vanilla)
        self.assertNotIn("None", brief)
        self.assertIn("tall enough to hold every line of text", brief)

    def test_the_surface_budget_never_contradicts_the_strip_it_asks_for(self):
        """A brief that asks for two incompatible things gets one of them at random — the same
        class of bug as bd mtg-cjx. The band alone can be a quarter of the card, and a quarter
        plus the top plate plus the narrow strip is already over the old fixed 'a third'."""
        allowed = dict((phrase, fraction) for fraction, phrase in prompts.TOTAL_LADDER)
        for face in (self.TERSE, self.WORDY, {**GREEN, "oracle_text": "Flying"}):
            room = prompts._strip_height(face)
            budget = allowed[prompts._surface_budget(face)]
            self.assertGreaterEqual(
                budget,
                room[0] + prompts.OTHER_SURFACES - 0.02,
                f"the budget leaves no room for the strip the same brief demands: {face}",
            )

    def test_the_demand_never_inflates_past_what_the_text_actually_needs(self):
        """The bug this replaced. A ladder of 1/8, 1/6, 1/5, 1/4, 1/3 had no rung between a
        quarter and a third, so a card needing 26.6% was told to paint 33.3% — a quarter more
        room than it needs. MEASURED over 8 live faces: the strip came back at or above the asked
        height 1 time in 8, and across six runs of that card it never passed 27.6%. An unreachable
        number is an ignored one, so the demand must track the need to within one rounding step.
        """
        for face in (self.TERSE, self.WORDY, {**GREEN, "oracle_text": "Flying"}):
            asked, _ = prompts._strip_height(face)
            if asked in (prompts.STRIP_MIN, prompts.STRIP_MAX):
                continue  # clamped by the floor or the cap, which are deliberate
            need = prompts._needed(face)
            self.assertGreaterEqual(asked, need, "it must still be enough to hold the text")
            self.assertLess(asked - need, prompts.STRIP_STEP, "rounded up by more than one step")

    def test_a_short_card_is_not_told_to_paint_a_sliver(self):
        """"As tall as this card's text needs" stops being sensible at the short end: a 44
        character card needs one line, which is 3% of the card. Asking for that would demand a
        nameplate rather than a text box, and LESS than the model paints unprompted — Lightning
        Bolt came back at 14.0% on 2026-08-15."""
        bolt = {**GREEN, "oracle_text": "Lightning Bolt deals 3 damage to any target."}
        asked, phrase = prompts._strip_height(bolt)
        self.assertEqual(asked, prompts.STRIP_MIN)
        self.assertIn(phrase, prompts.creative_full(bolt))

    def test_the_artwork_still_dominates_however_wordy_the_card(self):
        """Measured 2026-08-10, the slab came back eating ~40% of three cards in a row and the art
        had to be told it outranks the furniture. Sizing the strip to the text must not undo that."""
        for face in (self.TERSE, self.WORDY):
            self.assertLessEqual(prompts._strip_height(face)[0], 1 / 3)

    def test_a_strip_of_the_size_the_brief_asks_for_really_does_clear_the_floor(self):
        """The round trip, and the only test here with real teeth.

        `_strip_height` computes a number and the brief states it; this checks that a strip of
        exactly that size, handed to the compositor, produces text above `compositor.RULES_MIN`.
        Without this the brief and the renderer can agree on a wrong number forever.
        """
        from PIL import Image

        from cards import compositor

        for face in (self.TERSE, self.WORDY, {**GREEN, "oracle_text": "Flying"}):
            fraction, phrase = prompts._strip_height(face)
            card = Image.new("RGBA", prompts.CANVAS, (228, 208, 172, 255))
            printable = {
                "name": "Craterhoof Behemoth",
                "mana_cost": "{5}{G}{G}{G}",
                "type_line": "Creature — Beast",
                "oracle_text": face["oracle_text"],
                "power": "5",
                "toughness": "5",
            }
            panel = (0.06, 0.94 - fraction, 0.94, 0.94)
            _, overflowed = compositor.compose(card, printable, {"rules": [panel]})
            self.assertFalse(
                overflowed,
                f"the brief asks for {phrase} and that is still too small for "
                f"{len(face['oracle_text'])} characters",
            )


class TopPlatePlacementTests(SimpleTestCase):
    """The top plate has to be asked for LATE, not only in the list of surfaces.

    MEASURED 2026-08-15 (bd mtg-8h9), the first diagnosis the kept blank made possible: Elesh Norn
    came back with all four surfaces painted in the right ORDER and all four crammed into the
    bottom 45% of the card. The name landed at y=0.556 and check.title_out_of_order failed it. Job
    c66d6b93 did the same on the same card earlier. The placement was already stated once, in the
    middle of the ~100-word sentence listing the surfaces, and it lost there — the same way the
    lettering ban lost until it was moved to the end.
    """

    def _lines(self, **kwargs):
        return prompts.creative_full(GREEN, **kwargs).split("\n")

    def test_the_top_plate_is_asked_for_again_near_the_end(self):
        lines = self._lines()
        clause = next(i for i, l in enumerate(lines) if "THE TOP PLATE SITS AT THE TOP" in l)
        surfaces = next(i for i, l in enumerate(lines) if "Paint exactly these" in l)
        ban = next(i for i, l in enumerate(lines) if l.startswith("ABSOLUTE REQUIREMENT"))
        self.assertGreater(clause, surfaces, "restating it before the list is not restating it")
        self.assertLess(clause, ban, "nothing may push the lettering ban off the end")

    def test_it_names_shapes_and_not_the_fields_they_will_carry(self):
        """The first draft of this clause said "the name plate... the type strip... the rules
        panel" and broke test_surfaces_are_described_as_shapes_not_as_fields. Naming a field
        invites filling it, and a painted title collides with the one we composite."""
        brief = prompts.creative_full({**GREEN, "power": "5"})
        for invitation in ("title banner", "type bar", "power/toughness", "rules panel"):
            self.assertNotIn(invitation, brief)

    def test_the_framed_layout_asks_for_the_edge_instead_of_the_top_tenth(self):
        """Borderless floats the plate just inside the top because the scene runs behind it;
        framed has an actual edge for it to touch."""
        self.assertIn("inside the top tenth", "\n".join(self._lines()))
        self.assertIn("touches the upper edge", "\n".join(self._lines(borderless=False)))

    def test_the_purple_ban_keeps_its_place_immediately_before_the_lettering_ban(self):
        """Both are inserted at the same anchor, so adding one must not demote the other — the
        purple ban's late position is itself measured (BUILD-SPEC 7, a client-reported bug)."""
        lines = prompts.creative_full({**GREEN, "color_identity": ["G"]}).split("\n")
        purple = next(i for i, l in enumerate(lines) if l.startswith("AND: no purple"))
        ban = next(i for i, l in enumerate(lines) if l.startswith("ABSOLUTE REQUIREMENT"))
        self.assertEqual(ban - purple, 1, "something was inserted between purple and the ban")


class LateClauseOrderTests(SimpleTestCase):
    """The clauses restated at the end are ordered, and the order is measured, not stylistic.

    `before_the_writing_ban` inserts in call order, so whatever is added last sits closest to the
    lettering ban that ends the brief. MEASURED 2026-08-16: with the overlap clause added AFTER the
    top plate's, 3 of 6 cards in one batch failed on the top plate — twice with no title surface
    painted at all, once with the plate at y=0.58 — against 0 of 3 before it. One clause of extra
    distance from the end was enough to break it.
    """

    CREATURE = {**GREEN, "power": "5", "toughness": "5"}

    def test_the_top_plate_restatement_stays_nearer_the_end_than_the_overlap(self):
        brief = prompts.creative_full(self.CREATURE)
        self.assertLess(brief.index("AND: THE OVERLAP"), brief.index("AND: THE TOP PLATE"))

    def test_every_late_clause_still_lands_before_the_lettering_ban(self):
        """That ban's last place is itself measured — it had to move to the very end before it
        held on 3 of 3 — so nothing may be appended after it."""
        brief = prompts.creative_full(self.CREATURE)
        ban = brief.index("ABSOLUTE REQUIREMENT")
        for clause in ("AND: THE OVERLAP", "AND: THE TOP PLATE", "AND: no purple"):
            self.assertLess(brief.index(clause), ban, f"{clause} sits after the lettering ban")
