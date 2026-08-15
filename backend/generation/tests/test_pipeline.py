"""The two behaviours that used to be asserted by grepping the management command's source.

They moved into `generation.pipeline` when the HTTP API needed the same flow, and grepping a
second file would have been the wrong fix: the point was never where the code lives, it was that
a faulty card is repainted exactly once and that a licensed card is tried under its own name
first. Both are now driven with fakes instead, so they hold wherever the code sits.
"""

from unittest import mock

from django.test import SimpleTestCase
from PIL import Image

from generation import check, gemini, pipeline

FACE = {
    "name": "Terror of the Peaks",
    "face_position": "SINGLE",
    "oracle_text": "Flying",
    "color_identity": ["R"],
    "is_crossover": False,
}

FAULT = [check.Problem("PLATE_ORDER", "the type plate is above the title plate")]


class RepaintTests(SimpleTestCase):
    """One retry, not more: measured across the batches, about one card in five needs a second
    attempt and a card that fails twice usually keeps failing."""

    def _run(self, problems, **kwargs):
        with mock.patch.object(pipeline, "prepare", return_value=(FACE, None, False)), \
                mock.patch.object(pipeline.prompts, "creative_full", return_value="brief"), \
                mock.patch.object(pipeline.bleed, "trim", side_effect=lambda png: (png, 0.0)), \
                mock.patch.object(pipeline.check, "matted", return_value=None), \
                mock.patch.object(pipeline.gemini, "generate", return_value=b"png") as generate, \
                mock.patch.object(pipeline.panels, "detect", return_value={}), \
                mock.patch.object(
                    pipeline.compositor, "compose",
                    # A real image, not a Mock: `check.contrast` reads the composited card, and a
                    # pale one keeps these tests about their own subject rather than the panel.
                    return_value=(Image.new("RGB", (179, 240), (205, 200, 190)), False)), \
                mock.patch.object(pipeline.check, "inspect", return_value=problems):
            result = pipeline.creative_full(FACE, **kwargs)
        return generate, result

    def test_a_faulty_card_is_repainted_once_and_then_accepted(self):
        generate, result = self._run(FAULT, attempts=2)
        self.assertEqual(generate.call_count, 2)
        self.assertEqual(result.problems, FAULT)

    def test_a_sound_card_is_painted_once(self):
        generate, result = self._run([], attempts=2)
        self.assertEqual(generate.call_count, 1)
        self.assertEqual(result.problems, [])

    def test_from_disk_never_repaints_because_there_is_nothing_to_repaint(self):
        """`--from` composites art that already exists; a retry would be the same pixels."""
        generate, result = self._run(FAULT, attempts=2, source=b"already painted")
        self.assertEqual(generate.call_count, 0)
        self.assertIsNone(result.blank)


class NamedFirstTests(SimpleTestCase):
    """bd mtg-kx4: the licensed fallback is correct for Marvel and wrong for the other eight, so
    it may only run after the model has actually refused — never before."""

    def _paint(self, effects, refused_already=False):
        with mock.patch.object(pipeline.prompts, "creative_full") as brief, \
                mock.patch.object(pipeline.gemini, "generate", side_effect=effects), \
                mock.patch.object(
                    pipeline.refusals, "is_refused", return_value=refused_already), \
                mock.patch.object(pipeline.refusals, "remember") as remember:
            painted = pipeline._paint(FACE, True, None, pipeline.Options(), lambda _: None)
        return brief, remember, painted

    def test_the_name_is_tried_first_and_the_identity_only_after_a_refusal(self):
        refusal = gemini.NoImage("blocked", finish_reason="PROHIBITED_CONTENT")
        brief, remember, painted = self._paint([refusal, b"png"])

        self.assertEqual(painted, b"png")
        self.assertEqual(
            [call.kwargs["licensed"] for call in brief.call_args_list], [False, True]
        )
        remember.assert_called_once_with(FACE["name"])

    def test_a_remembered_refusal_skips_straight_to_the_identity_brief(self):
        """The whole value of remembering: a blocked card is paid for once, not once a run."""
        brief, remember, _ = self._paint([b"png"], refused_already=True)
        self.assertEqual([call.kwargs["licensed"] for call in brief.call_args_list], [True])
        remember.assert_not_called()

    def test_a_transient_miss_is_not_treated_as_a_refusal(self):
        """An empty part list is worth a retry, not a rewritten brief — rewriting it would throw
        away the card's name for no reason."""
        miss = gemini.NoImage("no image", finish_reason="STOP")
        with self.assertRaises(gemini.NoImage):
            self._paint([miss, b"png"])


class MissingShieldTests(SimpleTestCase):
    """A creature whose shield went undetected gets it placed instead of costing a repaint.

    bd mtg-wfp. The shield IS painted — confirmed by eye on the stored blanks — and `detect` finds
    it on 7 of 20 runs over the same fixed images. Every miss used to fire `missing_pt`, burn a
    full extra image call on art that was already correct, and if the repaint missed too, ship a
    creature with no power or toughness on it.
    """

    CREATURE = {**FACE, "power": "4", "toughness": "7"}
    STRIP = {"rules": [(0.10, 0.68, 0.89, 0.90)]}

    def _run(self, face, detected):
        seen = {}

        def inspect(_face, panels, _overflowed):
            seen["panels"] = panels
            return []

        with mock.patch.object(pipeline, "prepare", return_value=(face, None, False)), \
                mock.patch.object(pipeline.prompts, "creative_full", return_value="brief"), \
                mock.patch.object(pipeline.bleed, "trim", side_effect=lambda png: (png, 0.0)), \
                mock.patch.object(pipeline.check, "matted", return_value=None), \
                mock.patch.object(pipeline.gemini, "generate", return_value=b"png") as generate, \
                mock.patch.object(pipeline.panels, "detect", return_value=dict(detected)), \
                mock.patch.object(
                    pipeline.compositor, "compose",
                    # A real image, not a Mock: `check.contrast` reads the composited card, and a
                    # pale one keeps these tests about their own subject rather than the panel.
                    return_value=(Image.new("RGB", (179, 240), (205, 200, 190)), False)), \
                mock.patch.object(pipeline.check, "inspect", side_effect=inspect):
            pipeline.creative_full(face, attempts=2)
        return generate, seen["panels"]

    def test_the_grader_sees_the_placed_shield_so_no_repaint_is_burnt(self):
        """Placed BEFORE `check` runs, deliberately: place it after and the card is still graded
        `missing_pt` and repainted, which is the entire cost of this bug."""
        generate, panels_seen = self._run(self.CREATURE, self.STRIP)
        self.assertIn("pt", panels_seen)
        self.assertEqual(generate.call_count, 1, "a correct card was repainted anyway")

    def test_a_card_with_no_power_is_left_alone(self):
        """An instant has no P/T to print, so inventing a shield for it would be a surface with
        nothing on it — the defect `check.spare` exists to catch."""
        _, panels_seen = self._run(FACE, self.STRIP)
        self.assertNotIn("pt", panels_seen)

    def test_a_detected_shield_is_never_overwritten_by_the_guess(self):
        real = (0.79, 0.83, 0.94, 0.96)
        _, panels_seen = self._run(self.CREATURE, {**self.STRIP, "pt": real})
        self.assertEqual(panels_seen["pt"], real)

    def test_with_no_strip_to_anchor_to_the_card_still_fails_honestly(self):
        """No guess is better than a guess with nothing behind it: P/T stays unprinted, which is
        visible, rather than being stamped somewhere invented."""
        _, panels_seen = self._run(self.CREATURE, {"title": (0.05, 0.03, 0.95, 0.11)})
        self.assertNotIn("pt", panels_seen)
