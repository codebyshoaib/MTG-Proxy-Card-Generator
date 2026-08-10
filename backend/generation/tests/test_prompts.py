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
        brief = prompts.art_only(GREEN, "Anime", direction="Dynamic", palette="Vibrant")
        self.assertIn("Composition: Dynamic", brief)
        self.assertIn("Colour treatment: Vibrant", brief)

    def test_every_style_names_a_medium(self):
        """A row listing only light and mood renders photoreal: 'Neon Noir' described neon rim
        light and wet surfaces, and Counterspell came back a cinematic photograph — the client's
        original complaint, reintroduced by us. A medium is what keeps a style illustrative."""
        media = (
            "illustration",
            "cartoon",
            "inked",
            "ink ",
            "painted",
            "painting",
            "graffiti",
            "anime",
        )
        for label, attributes in prompts.STYLES.items():
            with self.subTest(style=label):
                self.assertTrue(
                    any(m in attributes for m in media),
                    f"{label} names no medium, so it will render photoreal",
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


class CreativeFullBriefTests(SimpleTestCase):
    """Creative Full inverts Art Only: furniture is the deliverable, lettering is the defect."""

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
        brief = prompts.creative_full(GREEN)
        self.assertIn("closes in around the scene at the card's edge", brief)
        self.assertIn("crosses in FRONT of it", brief)
        for noun in ("border", "frame around", "mount", "inset inside", "matted"):
            self.assertNotIn(noun, brief)

    def test_the_edge_material_carries_the_colour_as_light(self):
        """Theirs is a hot orange ribbon of lava; ours came back near-black rock, which is what
        made the whole card read dark and muddy beside it. The emissive convention _palette
        enforces for the scene (bd mtg-roq) had never been stated for the edge, and the material
        list led with "cracked obsidian", so the model painted a dark rim."""
        brief = prompts.creative_full(GREEN)
        self.assertIn("Run the card's colour through it as LIGHT", brief)
        self.assertIn("not a dark rim around a bright picture", brief)
        self.assertNotIn("cracked obsidian", brief)

    def test_the_edge_encloses_the_card_and_not_only_the_picture(self):
        """First generation under the framed brief enclosed the ARTWORK and stopped: both side
        members died where the lower surfaces began, the bottom never closed, and the two bottom
        corners came back as dead black wedges. To a model painting a picture, "the card's edge"
        and "around the scene" are the same sentence."""
        brief = prompts.creative_full(GREEN)
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
        self.assertIn("Nothing may be painted above the top plate", brief)

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

    def test_the_ban_on_writing_is_the_last_thing_in_the_brief(self):
        """Stated mid-brief it lost to the furniture description on 2 of 3 cards. It keeps the
        last position even against the purple ban added after it: painted lettering collides with
        the text we composite and makes the card unusable, where a purple tint misstates the
        colour identity of a card that still works."""
        for identity in ([], ["G"], ["B"], ["W", "U"]):
            with self.subTest(colour=identity):
                brief = prompts.creative_full({**GREEN, "color_identity": identity})
                self.assertTrue(brief.rstrip().endswith("collide with it."))

    def test_a_non_black_card_repeats_the_purple_ban_late(self):
        """MEASURED 2026-08-10, eight-card batch: mono-green Craterhoof came back with magenta
        crystal growths. The ban was already in _palette near the top, and this file has learned
        twice that a ban stated early loses to the description that follows it. Purple reading as
        black mana is the client's reported bug and a BUILD-SPEC §7 failure, not a preference."""
        green = prompts.creative_full(GREEN)
        self.assertIn("no purple, violet, magenta or lilac", green)
        self.assertLess(green.index("no purple, violet"), green.index("ABSOLUTE REQUIREMENT"))

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

    def test_a_pt_plaque_is_only_asked_for_when_the_card_has_one(self):
        self.assertNotIn("shield-shaped boss", prompts.creative_full(GREEN))
        self.assertIn("shield-shaped boss", prompts.creative_full({**GREEN, "power": "5"}))


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
