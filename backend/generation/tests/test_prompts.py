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
        for surface in ("horizontal ledge", "NARROW horizontal strip", "rectangular slab"):
            self.assertIn(surface, brief)
        self.assertIn("NO WRITING ANYWHERE", brief)
        self.assertIn("no fake writing", brief)

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
        """Stated mid-brief it lost to the furniture description on 2 of 3 cards."""
        self.assertTrue(prompts.creative_full(GREEN).rstrip().endswith("collide with it."))

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
