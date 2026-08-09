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

    def test_style_is_passed_through_verbatim(self):
        self.assertIn("Art style: dark fantasy oil", prompts.art_only(GREEN, "dark fantasy oil"))

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
