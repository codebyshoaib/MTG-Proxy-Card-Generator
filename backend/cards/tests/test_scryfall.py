"""Resolving a decklist must produce the right faces, or fail loudly — never quietly.

Three ways this layer can be wrong, all of them expensive and none of them visible in the
finished image, so they are asserted here:

- **Over-counting faces.** A `card_faces[]` array is not a second side. Treating an
  adventure or a split card as two-sided doubles its credit cost for every user who plays
  one, and produces a stray second image.
- **Colour identity taken from the face.** The back of a modal DFC can be a colourless
  Land on a green card, which renders the pair wrong — the client's already-reported bug
  class.
- **A name that silently vanishes.** A decklist that resolves 99 of 100 cards and says
  nothing has shrunk someone's deck.

`fixtures/collection.json` is a real, unedited `POST /cards/collection` response, fetched
2026-08-07 for: Craterhoof Behemoth, Turntimber Symbiosis, Huntmaster of the Fells, Fire,
Bonecrusher Giant, Teferi Hero of Dominaria, History of Benalia, Academy at Tolaria West.
Regenerate it by POSTing those names with the User-Agent from `cards.scryfall.HEADERS`.
The suite is offline: every card here is loaded from that file, never fetched.
"""

import json
import uuid
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase

from cards import scryfall
from cards.models import Card

FIXTURE = json.loads(
    (Path(__file__).resolve().parent / "fixtures" / "collection.json").read_text()
)


def load_fixture():
    for data in FIXTURE["data"]:
        scryfall._store(data)


def card(name):
    return Card.objects.get(name__startswith=name)


class ParseDecklistTest(SimpleTestCase):
    def test_reads_the_shapes_real_exporters_write(self):
        text = """\
Deck
4 Lightning Bolt
4x Brainstorm
1 Craterhoof Behemoth (MH1) 149
2 Bonecrusher Giant (ELD) 115 *F*
Sol Ring

// exported from somewhere
# a comment
Sideboard:
1 Fire // Ice
"""
        self.assertEqual(
            scryfall.parse_decklist(text),
            [
                (4, "Lightning Bolt"),
                (4, "Brainstorm"),
                (1, "Craterhoof Behemoth"),
                (2, "Bonecrusher Giant"),
                (1, "Sol Ring"),
                (1, "Fire // Ice"),
            ],
        )

    def test_a_double_slash_inside_a_name_is_not_a_comment(self):
        """'//' opens a comment only at the start of a line — it also separates faces."""
        self.assertEqual(
            scryfall.parse_decklist("2 Bonecrusher Giant // Stomp"),
            [(2, "Bonecrusher Giant // Stomp")],
        )

    def test_quantity_defaults_to_one(self):
        self.assertEqual(scryfall.parse_decklist("Black Lotus"), [(1, "Black Lotus")])


class FrontNameTest(SimpleTestCase):
    def test_strips_the_back_face_from_an_exported_name(self):
        """/cards/collection matches ONLY the front name — measured, not documented."""
        self.assertEqual(scryfall._front("Fire // Ice"), "Fire")
        self.assertEqual(
            scryfall._front("Turntimber Symbiosis // Turntimber, Serpentine Wood"),
            "Turntimber Symbiosis",
        )
        self.assertEqual(scryfall._front("Craterhoof Behemoth"), "Craterhoof Behemoth")


class FacesTest(TestCase):
    def setUp(self):
        load_fixture()

    def test_modal_dfc_is_two_faces(self):
        got = scryfall.faces(card("Turntimber Symbiosis"))
        self.assertEqual([f["face_position"] for f in got], ["FRONT", "BACK"])
        self.assertEqual(got[0]["name"], "Turntimber Symbiosis")
        self.assertEqual(got[1]["name"], "Turntimber, Serpentine Wood")
        self.assertTrue(all(f["is_dfc"] for f in got))

    def test_transform_is_two_faces(self):
        got = scryfall.faces(card("Huntmaster of the Fells"))
        self.assertEqual(len(got), 2)
        self.assertEqual(got[1]["name"], "Ravager of the Fells")

    def test_adventure_is_ONE_face_despite_having_card_faces(self):
        """Bonecrusher Giant is one physical card: one image, one generation, 1 credit."""
        got = scryfall.faces(card("Bonecrusher Giant"))
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["face_position"], "SINGLE")
        self.assertFalse(got[0]["is_dfc"])

    def test_split_is_ONE_face_and_keeps_both_halves(self):
        got = scryfall.faces(card("Fire"))
        self.assertEqual(len(got), 1)
        self.assertEqual([p["name"] for p in got[0]["parts"]], ["Fire", "Ice"])

    def test_ordinary_card_is_one_single_face_with_no_parts(self):
        got = scryfall.faces(card("Craterhoof Behemoth"))
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["face_position"], "SINGLE")
        self.assertIsNone(got[0]["parts"])


class FaceDataTest(TestCase):
    def setUp(self):
        load_fixture()

    def test_colour_identity_comes_from_the_card_not_the_face(self):
        """The Land back face carries colors:[] on a green card. Taking it renders the
        pair colourless — BUILD-SPEC §9.2, and the bug class the client reported."""
        back = scryfall.faces(card("Turntimber Symbiosis"))[1]
        self.assertEqual(back["colors"], [])
        self.assertEqual(back["color_identity"], ["G"])

    def test_each_face_gets_its_own_type_line_and_rules_text(self):
        """On a DFC the top level has no oracle_text and type_line is the two joined."""
        front, back = scryfall.faces(card("Turntimber Symbiosis"))
        self.assertTrue(front["type_line"].startswith("Sorcery"))
        self.assertTrue(back["type_line"].startswith("Land"))
        self.assertNotIn("//", front["type_line"])
        self.assertNotEqual(front["oracle_text"], back["oracle_text"])
        self.assertTrue(front["oracle_text"])
        self.assertTrue(back["oracle_text"])

    def test_both_faces_share_the_pairing_key_and_the_display_name(self):
        front, back = scryfall.faces(card("Huntmaster of the Fells"))
        self.assertEqual(front["scryfall_id"], back["scryfall_id"])
        self.assertEqual(front["display_name"], "Huntmaster of the Fells // Ravager of the Fells")

    def test_creature_carries_power_and_toughness(self):
        face = scryfall.faces(card("Craterhoof Behemoth"))[0]
        self.assertEqual((face["power"], face["toughness"]), ("5", "5"))
        self.assertEqual(face["mana_cost"], "{5}{G}{G}{G}")

    def test_planeswalker_loyalty_survives(self):
        """Scryfall has no 'planeswalker' LAYOUT — Teferi is layout 'normal'. The renderer
        must select on type_line, not layout. BUILD-SPEC §9's table says otherwise."""
        teferi = card("Teferi, Hero of Dominaria")
        self.assertEqual(teferi.layout, "normal")
        face = scryfall.faces(teferi)[0]
        self.assertIn("Planeswalker", face["type_line"])
        self.assertEqual(face["loyalty"], "4")


class ResolveTest(TestCase):
    def test_a_cached_card_costs_no_request(self):
        load_fixture()
        with patch("cards.scryfall.requests.post") as post:
            found, missing = scryfall.resolve(["Craterhoof Behemoth"])
        post.assert_not_called()
        self.assertEqual(missing, [])
        self.assertEqual(found["Craterhoof Behemoth"].layout, "normal")

    def test_a_full_two_faced_name_hits_the_cache_and_so_does_the_front_alone(self):
        load_fixture()
        with patch("cards.scryfall.requests.post") as post:
            found, missing = scryfall.resolve(
                ["Fire // Ice", "Fire", "Turntimber Symbiosis"]
            )
        post.assert_not_called()
        self.assertEqual(missing, [])
        self.assertEqual(found["Fire // Ice"].name, "Fire // Ice")
        self.assertEqual(found["Fire"].name, "Fire // Ice")

    def test_a_miss_is_fetched_and_asked_for_by_its_FRONT_name(self):
        with patch("cards.scryfall.requests.post") as post:
            post.return_value.json.return_value = FIXTURE
            found, missing = scryfall.resolve(["Fire // Ice"])
        sent = post.call_args.kwargs["json"]["identifiers"]
        self.assertEqual(sent, [{"name": "Fire"}], "the full name lands in not_found")
        self.assertEqual(missing, [])
        self.assertEqual(found["Fire // Ice"].name, "Fire // Ice")

    def test_an_unknown_name_is_reported_not_dropped(self):
        with patch("cards.scryfall.requests.post") as post:
            post.return_value.json.return_value = {"data": FIXTURE["data"]}
            found, missing = scryfall.resolve(["Craterhoof Behemoth", "Nonesuch Card"])
        self.assertEqual(missing, ["Nonesuch Card"])
        self.assertIn("Craterhoof Behemoth", found)

    def test_a_hundred_card_deck_is_two_requests_not_a_hundred(self):
        names = [f"Card {n}" for n in range(100)]
        with patch("cards.scryfall.requests.post") as post, patch("cards.scryfall.time.sleep"):
            post.return_value.json.return_value = {"data": []}
            scryfall.resolve(names)
        self.assertEqual(post.call_count, 2)
        self.assertEqual(len(post.call_args_list[0].kwargs["json"]["identifiers"]), 75)

    def test_duplicate_names_are_asked_for_once(self):
        with patch("cards.scryfall.requests.post") as post:
            post.return_value.json.return_value = {"data": []}
            scryfall.resolve(["Sol Ring", "Sol Ring", "Sol Ring"])
        self.assertEqual(len(post.call_args.kwargs["json"]["identifiers"]), 1)

    def test_the_identifying_user_agent_is_sent(self):
        """Without one, /symbology returned a body with no 'data' key rather than a 4xx."""
        with patch("cards.scryfall.requests.post") as post:
            post.return_value.json.return_value = {"data": []}
            scryfall.resolve(["Sol Ring"])
        self.assertIn("mtg-proxy-generator", post.call_args.kwargs["headers"]["User-Agent"])


class ResolveDecklistTest(TestCase):
    def setUp(self):
        load_fixture()

    def _resolve(self, text):
        with patch("cards.scryfall.requests.post") as post:
            post.return_value.json.return_value = {"data": []}
            return scryfall.resolve_decklist(text)

    def test_produces_the_generation_plan_for_a_mixed_decklist(self):
        plan = self._resolve(
            "1 Craterhoof Behemoth\n"
            "1 Turntimber Symbiosis // Turntimber, Serpentine Wood\n"
            "2 Bonecrusher Giant\n"
        )
        self.assertEqual(plan["unresolved"], [])
        self.assertEqual([len(e["faces"]) for e in plan["entries"]], [1, 2, 1])
        # One credit per face: the DFC is 2, the adventure is 1 despite its 2 halves.
        self.assertEqual(sum(len(e["faces"]) for e in plan["entries"]), 4)

    def test_an_unsupported_layout_is_rejected_before_anything_is_charged(self):
        plan = self._resolve("1 Craterhoof Behemoth\n1 Academy at Tolaria West\n")
        self.assertEqual(plan["unsupported"], [{"name": "Academy at Tolaria West", "layout": "planar"}])
        self.assertEqual(len(plan["entries"]), 1)

    def test_a_battle_is_rejected_rather_than_composited_without_its_defense(self):
        """bd mtg-l8j. Scryfall gives a Battle layout `transform`, so the two-sided machinery
        takes it and it composites looking finished with no defense number on it — AFTER the paid
        call. CLAUDE.md: an unresolvable layout must fail loudly, never render a dropped value.
        Rejected on the type line because the layout does not distinguish it from a werewolf.
        """
        plan = self._resolve("1 Huntmaster of the Fells\n1 Invasion of Alara\n")
        self.assertEqual(
            plan["unsupported"],
            [{"name": "Invasion of Alara", "layout": "battle"}],
            "reported as 'battle', not 'transform' — the layout is not why it was rejected",
        )
        self.assertEqual([e["card"].layout for e in plan["entries"]], ["transform"])

    def test_saga_is_supported(self):
        plan = self._resolve("1 History of Benalia")
        self.assertEqual(len(plan["entries"]), 1)
        self.assertEqual(plan["entries"][0]["card"].layout, "saga")

    def test_quantity_is_carried_through(self):
        plan = self._resolve("4 Craterhoof Behemoth")
        self.assertEqual(plan["entries"][0]["quantity"], 4)


class CrossoverArtTests(TestCase):
    """`promo_types` marks a licensed crossover, and only those pay for a second lookup.

    The substitution itself is one live Scryfall request and is not exercised here; what is
    covered is the flag that decides whether it happens at all, because a false positive
    costs a request on every card in every deck.
    """

    def test_a_crossover_printing_is_flagged(self):
        card = Card(
            scryfall_id=uuid.uuid4(),
            name="Lightning Bolt",
            layout="normal",
            data={
                "id": str(uuid.uuid4()),
                "name": "Lightning Bolt",
                "layout": "normal",
                "promo_types": ["universesbeyond"],
            },
        )
        self.assertTrue(scryfall.faces(card)[0]["is_crossover"])

    def test_an_ordinary_printing_is_not_flagged_and_keeps_its_own_art(self):
        card = Card(
            scryfall_id=uuid.uuid4(),
            name="Counterspell",
            layout="normal",
            data={
                "id": str(uuid.uuid4()),
                "name": "Counterspell",
                "layout": "normal",
                "promo_types": ["surgefoil"],
                "image_uris": {"art_crop": "https://example.test/counterspell.jpg"},
            },
        )
        face = scryfall.faces(card)[0]
        self.assertFalse(face["is_crossover"])
        # No network: a non-crossover resolves to its own art and is not licensed-only.
        original = scryfall.art_reference(face)
        self.assertEqual(original.art_crop, "https://example.test/counterspell.jpg")
        self.assertFalse(original.licensed)
        # Its own flavour too. The field exists so that a CROSSOVER's flavour comes from the same
        # printing its art does — with it taken from resolve() instead, Lightning Bolt printed
        # Christopher Rush's Alpha art under Marvel flavour text, one card wearing two printings.
        self.assertEqual(original.flavor_text, "")
