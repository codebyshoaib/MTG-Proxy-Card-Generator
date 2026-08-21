"""Showing the model the look instead of describing it — Phase 1.

The asset files are not committed (see `generation/exemplars.py`), so the tests that need real
images skip when they are absent. Everything about the CONTRACT — the attachment order, what the
brief says about which image is which, and failing loudly rather than silently unconditioned —
is tested with fakes and runs on a clean clone.
"""

import io
import unittest
from unittest import mock

from django.test import SimpleTestCase
from PIL import Image

from generation import exemplars, gemini, prompts

FACE = {
    "name": "Toski, Bearer of Secrets",
    "type_line": "Legendary Creature — Squirrel",
    "oracle_text": "This spell can't be countered.\nIndestructible\nToski attacks each combat if able.",
    "mana_cost": "{3}{G}",
    "color_identity": ["G"],
    "power": "1",
    "toughness": "1",
    "face_position": "SINGLE",
    "is_crossover": False,
}


class Loading(SimpleTestCase):
    def test_an_unknown_archetype_is_refused_by_name(self):
        with self.assertRaises(exemplars.Missing) as raised:
            exemplars.paths("sparkly")
        # The message has to name the real ones: this is the error a typo on the CLI produces.
        self.assertIn("tangle", str(raised.exception))

    def test_a_missing_directory_raises_rather_than_returning_nothing(self):
        """The failure mode this guards is invisible in the output, which is why it is loud.

        An empty list would generate a perfectly valid card with no conditioning at all. It would
        score badly, and nothing in the image would say why — the assets are absent on a clean
        clone by design, so this is the normal way to hit it, not an exotic one.
        """
        with mock.patch.object(exemplars, "ROOT", exemplars.ROOT / "does-not-exist"):
            with self.assertRaises(exemplars.Missing) as raised:
                exemplars.load("tangle")
        self.assertIn("prepare_exemplars", str(raised.exception))

    def test_every_archetype_has_a_frame_note_for_the_brief(self):
        """`ARCHETYPE_NOTES` is indexed by archetype, so a new archetype without one is a KeyError
        at generation time — after the user has paid for nothing."""
        self.assertEqual(set(exemplars.ARCHETYPES), set(prompts.ARCHETYPE_NOTES))
        self.assertEqual(set(exemplars.ARCHETYPES), set(exemplars.SOURCES))


class Attachment(SimpleTestCase):
    """The order in `gemini.generate` is a contract the brief depends on — see its docstring."""

    def _parts(self, **kwargs):
        with mock.patch.object(gemini, "_call") as call:
            call.return_value = mock.Mock(
                candidates=[mock.Mock(content=mock.Mock(parts=[
                    mock.Mock(inline_data=mock.Mock(data=b"png")),
                ]))]
            )
            gemini.generate("BRIEF", **kwargs)
        return call.call_args[0][0]

    def test_exemplars_come_first_then_the_reference_then_the_prompt(self):
        parts = self._parts(reference=b"art", exemplars=[b"one", b"two"])
        self.assertEqual(4, len(parts))
        self.assertEqual([b"one", b"two", b"art"], [part.inline_data.data for part in parts[:3]])
        self.assertEqual("BRIEF", parts[-1])

    def test_exemplars_are_labelled_png_and_the_reference_jpeg(self):
        """Mislabelling an attached image's mime type works until the day it does not."""
        parts = self._parts(reference=b"art", exemplars=[b"one"])
        self.assertEqual("image/png", parts[0].inline_data.mime_type)
        self.assertEqual("image/jpeg", parts[1].inline_data.mime_type)

    def test_the_old_two_argument_call_is_unchanged(self):
        """Every measurement on record came through this path; it must not have moved."""
        parts = self._parts(reference=b"art")
        self.assertEqual(2, len(parts))
        self.assertEqual(b"art", parts[0].inline_data.data)


class Brief(SimpleTestCase):
    def test_an_archetype_dispatches_away_from_the_prose_brief(self):
        """The two briefs are an A/B, so the control must stay reachable and unchanged."""
        control = prompts.creative_full(FACE, lettered=True)
        exemplar = prompts.creative_full(FACE, lettered=True, archetype="tangle", exemplars=3)
        self.assertNotEqual(control, exemplar)
        # Prose borderless forbids the frame; exemplar path makes the frame compulsory.
        self.assertIn("THE CARD IS FULL BLEED", control)
        self.assertIn("THE CARD'S FRAME", exemplar)
        self.assertNotIn("THE CARD'S FRAME", control)
        self.assertLess(len(exemplar), len(control))

    def test_the_frame_is_compulsory_and_the_canvas_is_full_bleed(self):
        """Spell the edge in pixels — "FULL BLEED" jargon alone did not stop Tower Winder insets.
        """
        brief = prompts.creative_full(FACE, lettered=True, archetype="portal", exemplars=2)
        self.assertIn("ALL FOUR SIDES", brief)
        self.assertIn("WHERE THE IMAGE ENDS", brief)
        self.assertIn("pixel by pixel", brief)
        self.assertIn("NOT a photograph of a card", brief)
        self.assertIn("PALE margin", brief)
        self.assertNotIn("Either is right", brief)
        self.assertNotIn("dark rim that IS the edge is fine", brief)
        self.assertIn("arch, gate or window", brief)

    def test_mural_asks_for_continuous_scene_not_an_art_window(self):
        brief = prompts.creative_full(FACE, lettered=True, archetype="mural", exemplars=3)
        self.assertIn("ONE CONTINUOUS SCENE", brief)
        self.assertIn("NO rectangular art panel", brief)
        self.assertIn("art window", brief.lower())
        self.assertNotIn("decorated border closes the card on ALL FOUR SIDES", brief)
        self.assertIn("HOW THE SCENE FILLS THE WHOLE CARD", brief)

    def test_the_brief_counts_the_images_it_was_actually_given(self):
        """The brief points at images BY POSITION. A miscount misdescribes them, and no gate
        downstream can see it — the card just comes back worse."""
        self.assertIn("FIRST 2 ATTACHED IMAGES ARE", prompts.creative_full(
            FACE, lettered=True, archetype="tangle", exemplars=2))
        self.assertIn("FIRST 1 ATTACHED IMAGE IS", prompts.creative_full(
            FACE, lettered=True, archetype="tangle", exemplars=1))

    def test_the_reference_art_is_the_last_image_only_when_something_precedes_it(self):
        with_exemplars = prompts.creative_full(FACE, lettered=True, archetype="tangle", exemplars=2)
        alone = prompts.creative_full(FACE, lettered=True, archetype="tangle", exemplars=0)
        self.assertIn("THE LAST ATTACHED IMAGE", with_exemplars)
        self.assertNotIn("THE LAST ATTACHED IMAGE", alone)
        self.assertIn(prompts.REFERENCE_OPENING, alone)

    def test_the_artwork_is_labelled_once_and_not_twice(self):
        """`REFERENCE` names the attachment in its own first sentence, so a brief that prepends a
        position label instead of replacing it tells the model two different things about the same
        image. The first draft of this did exactly that."""
        brief = prompts.creative_full(FACE, lettered=True, archetype="tangle", exemplars=3)
        self.assertNotIn(prompts.REFERENCE_OPENING, brief)
        self.assertEqual(1, brief.count("is the card's official artwork."))

    def test_colour_is_taken_from_the_card_and_never_from_the_exemplars(self):
        """The `tangle` set is three blue-black cards and Toski is mono-green.

        `check.colour_identity` fires on this and CLAUDE.md calls it a bug the client reported, so
        the brief has to redirect rather than only forbid — a bare ban has lost four times on this
        project (see `prompts.REFERENCE`).
        """
        brief = prompts.creative_full(FACE, lettered=True, archetype="tangle", exemplars=3)
        self.assertIn("not their colour", brief)
        self.assertIn("THIS card's colours", brief)

    def test_the_name_is_asked_for_in_a_display_face(self):
        """"One clean serif throughout" is why every card we ship reads as typeset."""
        brief = prompts.creative_full(FACE, lettered=True, archetype="tangle", exemplars=3)
        self.assertIn("display face", brief)
        self.assertNotIn("one clean serif throughout", brief)
        self.assertIn("one clean serif throughout", prompts.creative_full(FACE, lettered=True))

    def test_the_writing_ban_is_still_last(self):
        """Its position is measured — see `prompts._writing_ban`."""
        brief = prompts.creative_full(FACE, lettered=True, archetype="tangle", exemplars=3)
        self.assertIn("ABSOLUTE REQUIREMENT", brief.rsplit("\n\n", 1)[-1])

    def test_the_exact_strings_are_still_handed_over(self):
        """Whatever else changed, the model still letters Scryfall's text and not its own."""
        brief = prompts.creative_full(FACE, lettered=True, archetype="tangle", exemplars=3)
        self.assertIn("Toski attacks each combat if able.", brief)
        self.assertIn("Legendary Creature — Squirrel", brief)


class Assets(SimpleTestCase):
    """The real files, when this machine has them."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if not exemplars.available():
            raise unittest.SkipTest("no exemplars built — run manage.py prepare_exemplars")

    def test_every_built_archetype_has_at_least_two_readable_cards(self):
        """Two, because one exemplar reads as a card to copy and several read as a style.

        `mural` is the exception and is allowed one: the client's corpus only has Kaalia and
        Tower Winder in that archetype, and Tower Winder is in the held-out evaluation set.
        """
        for archetype in sorted(exemplars.available()):
            with self.subTest(archetype=archetype):
                images = exemplars.load(archetype)
                self.assertGreaterEqual(len(images), 1 if archetype == "mural" else 2)
                for blob in images:
                    with Image.open(io.BytesIO(blob)) as image:
                        self.assertLessEqual(max(image.size), exemplars.LONG_EDGE)

    def test_count_limits_what_is_loaded_for_the_ab(self):
        archetype = sorted(exemplars.available())[0]
        self.assertEqual(1, len(exemplars.load(archetype, 1)))

    def test_no_exemplar_is_a_card_in_the_evaluation_set(self):
        """Teaching to the test would make the Phase 1 go/no-go meaningless.

        The evaluation set is the client's own seven-card sheet. None of those cards may appear in
        `SOURCES`, and this asserts it by name rather than by trusting the folder layout.
        """
        def identity(stem):
            # Whole card, not a substring: Command Tower is an exemplar and Tower Winder is in
            # the evaluation set, and a substring test calls those the same card.
            return "".join(character for character in stem.lower() if character.isalnum())

        evaluation = {
            identity(card) for card in (
                "Tromell", "Tree_of_Tales", "Triumph_of_the_Hordes", "Thirsting_Roots",
                "Three_Visits", "Toski", "Tower_Winder",
            )
        }
        named = {identity(stem) for stems in exemplars.SOURCES.values() for stem in stems}
        self.assertEqual(set(), named & evaluation)
