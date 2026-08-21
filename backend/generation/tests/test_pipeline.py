"""The two behaviours that used to be asserted by grepping the management command's source.

They moved into `generation.pipeline` when the HTTP API needed the same flow, and grepping a
second file would have been the wrong fix: the point was never where the code lives, it was that
a faulty card is repainted exactly once and that a licensed card is tried under its own name
first. Both are now driven with fakes instead, so they hold wherever the code sits.
"""

import io
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


def _jpeg(shade=(40, 90, 40)):
    """What Gemini actually returns — JPEG, not PNG (bd mtg-ctu)."""
    buffer = io.BytesIO()
    Image.new("RGB", (179, 240), shade).save(buffer, format="JPEG")
    return buffer.getvalue()


class ArtOnlyTests(SimpleTestCase):
    """bd mtg-l4x. Art Only was `return gemini.generate(brief, reference)` and nothing else.

    No trim, no grade, no repaint: whatever the model returned was the deliverable. MEASURED on
    the sign-off pack, 7 Art Only faces beside 7 Creative Full faces of the same cards in the same
    batch — 2 of the 7 were above the MATTED gate and one was a fully bordered card with rounded
    corners, the defect the client circled on 2026-08-13. All 7 shipped marked `ok`, because
    nothing looked.
    """

    MAT = check.Problem("matted", "a printed white margin runs around the art")

    def _run(self, matted=None, colour=None, **kwargs):
        with mock.patch.object(pipeline, "prepare", return_value=(FACE, None, False)), \
                mock.patch.object(pipeline.prompts, "art_only", return_value="brief") as brief, \
                mock.patch.object(pipeline.bleed, "trim", side_effect=lambda png: (png, 0.0)) as trim, \
                mock.patch.object(pipeline.check, "matted", return_value=matted), \
                mock.patch.object(pipeline.check, "colour_identity", return_value=colour), \
                mock.patch.object(pipeline.gemini, "generate", return_value=_jpeg()) as generate:
            result = pipeline.art(FACE, **kwargs)
        return generate, trim, brief, result

    def test_the_painted_margin_is_cut_off_art_only_too(self):
        """The half of the fix that needed one line: `trim` is pure image-in image-out and needs
        no furniture, so there was never a reason it only ran on the other mode."""
        _, trim, _, _ = self._run()
        self.assertEqual(trim.call_count, 1)

    def test_a_matted_face_is_repainted_and_then_reported_rather_than_shipped_as_ok(self):
        generate, _, _, result = self._run(matted=self.MAT)
        self.assertEqual(generate.call_count, 2)
        self.assertEqual(result.problems, [self.MAT])

    def test_a_clean_face_is_painted_once_and_carries_no_problems(self):
        generate, _, _, result = self._run()
        self.assertEqual(generate.call_count, 1)
        self.assertEqual(result.problems, [])

    def test_the_repaint_is_told_what_was_wrong_with_the_first_one(self):
        """bd mtg-x6v, on the other mode: re-sending the identical brief and hoping the dice fall
        differently measurably does not work. Art Only shares the sentence, not a copy of it."""
        _, _, brief, _ = self._run(matted=self.MAT)
        self.assertEqual(brief.call_args_list[0].kwargs["corrections"], [])
        self.assertEqual(brief.call_args_list[1].kwargs["corrections"], [self.MAT.detail])

    def test_the_colour_identity_gate_runs_on_standalone_art(self):
        """A mono-green card painted purple misstates its colour whether or not a frame is drawn
        around it. CLAUDE.md: colour identity comes from Scryfall, never from the art style."""
        wrong = check.Problem("colour_identity", "62% of this card's colour is purple")
        generate, _, _, result = self._run(colour=wrong)
        self.assertEqual(generate.call_count, 2)
        self.assertEqual(result.problems, [wrong])

    def test_a_bordered_face_is_not_graded_when_the_user_asked_for_a_border(self):
        """`borderless=False` builds the card's edge out of the scene on purpose, so a margin is
        the deliverable rather than the defect — the same condition `creative_full` uses."""
        generate, trim, _, result = self._run(
            matted=self.MAT, options=pipeline.Options(borderless=False)
        )
        self.assertEqual(trim.call_count, 0)
        self.assertEqual(generate.call_count, 1)
        self.assertEqual(result.problems, [])

    def test_the_models_jpeg_comes_back_decoded_so_a_png_name_is_a_png_file(self):
        """bd mtg-ctu, held at the level it now lives. Gemini returns JPEG; `jobs` saves
        `result.card` through PIL, which writes the format the extension names. Before this the
        bytes went to disk untouched and `file` called the `.png` a JPEG."""
        _, _, _, result = self._run()
        self.assertIsInstance(result.card, Image.Image)
        self.assertEqual(result.card.mode, "RGB")

    def test_art_only_reports_no_panels_because_it_paints_none(self):
        _, _, _, result = self._run()
        self.assertEqual(result.detected, {})
        self.assertIsNone(result.blank)


class RepaintTests(SimpleTestCase):
    """One retry, not more: measured across the batches, about one card in five needs a second
    attempt and a card that fails twice usually keeps failing."""

    # Real bytes and not `b"png"`: the pipeline decodes the blank now, because `check.obstructed`
    # grades what the model painted rather than the finished card. Same reason the composed return
    # below is a real image.
    def _run(self, problems, **kwargs):
        with mock.patch.object(pipeline, "prepare", return_value=(FACE, None, False)), \
                mock.patch.object(pipeline.prompts, "creative_full", return_value="brief"), \
                mock.patch.object(pipeline.bleed, "trim", side_effect=lambda png: (png, 0.0)), \
                mock.patch.object(pipeline.check, "matted", return_value=None), \
                mock.patch.object(pipeline.gemini, "generate", return_value=_jpeg()) as generate, \
                mock.patch.object(pipeline.panels, "detect", return_value={}), \
                mock.patch.object(
                    pipeline.compositor, "compose",
                    # A real image, not a Mock: `check.contrast` reads the composited card, and a
                    # pale one keeps these tests about their own subject rather than the panel.
                    return_value=(Image.new("RGB", (179, 240), (205, 200, 190)), False)), \
                mock.patch.object(pipeline.check, "inspect", return_value=problems):
            result = pipeline.creative_full(FACE, pipeline.Options(lettered=False, name_lettered=False), **kwargs)
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
        generate, result = self._run(FAULT, attempts=2, source=_jpeg((90, 40, 40)))
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
            painted = pipeline._paint(
                FACE, True, None,
                pipeline.Options(archetype=None, exemplar_count=None, cost_lettered=False),
                lambda _: None,
            )
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
    """A creature whose tab went undetected is REPORTED, never given a guessed box.

    bd mtg-1uv, resolved 2026-08-16 by deleting `panels.infer_pt` rather than tuning it. The guess
    existed because detection of this one surface was unreliable — 7 of 20 runs over the same
    stored blanks on 2026-08-15. Re-running that identical experiment after the enlarged corner was
    paired into the call and the tab shape was opened away from the shield gives 24 of 24, plus
    15 of 15 across a day of live runs.

    With its premise gone, what remained was a box that is wrong whenever it fires: it overhung the
    painted surface on 5 of 5 undetected cards, and outside its fitted domain the error flips sign.
    So a miss now reaches `check`, fires `missing_pt` and is repainted; a card that still has no tab
    is reported UNSOUND rather than shipped with a number hanging off a rim.
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
                mock.patch.object(pipeline.gemini, "generate", return_value=_jpeg()) as generate, \
                mock.patch.object(pipeline.panels, "detect", return_value=dict(detected)), \
                mock.patch.object(
                    pipeline.compositor, "compose",
                    # A real image, not a Mock: `check.contrast` reads the composited card, and a
                    # pale one keeps these tests about their own subject rather than the panel.
                    return_value=(Image.new("RGB", (179, 240), (205, 200, 190)), False)), \
                mock.patch.object(pipeline.check, "inspect", side_effect=inspect):
            pipeline.creative_full(face, pipeline.Options(lettered=False, name_lettered=False), attempts=2)
        return generate, seen["panels"]

    def test_an_undetected_tab_reaches_the_grader_unfilled(self):
        """The whole point of the deletion. `check` must see the card the customer would get, and
        a card whose tab was not found has no P/T surface — so `missing_pt` fires and the pipeline
        repaints, instead of the grader being handed a box nobody painted."""
        _, panels_seen = self._run(self.CREATURE, self.STRIP)
        self.assertNotIn("pt", panels_seen)

    def test_a_detected_tab_is_passed_through_untouched(self):
        real = (0.79, 0.83, 0.94, 0.96)
        _, panels_seen = self._run(self.CREATURE, {**self.STRIP, "pt": real})
        self.assertEqual(panels_seen["pt"], real)

    def test_a_card_with_no_power_is_left_alone(self):
        """An instant has no P/T to print, so a surface for it would be one with nothing on it —
        the defect `check.spare` exists to catch."""
        _, panels_seen = self._run(FACE, self.STRIP)
        self.assertNotIn("pt", panels_seen)


class LetteredTests(SimpleTestCase):
    """The product path: the model sets every field but the cost, and the cost is graded.

    Two things have to hold or the mode must not ship. It costs the SAME two calls a composited
    card does — `read_back` replaces `detect`, it does not join it — and `proofread` runs, because
    `CLAUDE.md`'s surviving rule is that a card whose printed text differs from Scryfall must never
    ship silently. Explicit `archetype=None` here — the default mural path needs exemplar files
    on disk; these unit tests are the prose/lettered control without them.
    """

    # Prose control path: no exemplars, stamped cost. Product defaults are mural+cost_lettered.
    OPTIONS = pipeline.Options(archetype=None, exemplar_count=None, cost_lettered=False)

    READ = {
        "title": (0.05, 0.03, 0.95, 0.11),
        "rules": [(0.06, 0.65, 0.94, 0.90)],
        "text": [{"where": "title_plate", "text": "Terror of the Peaks"}],
    }

    def _run(self, problems=(), mark=None, **kwargs):
        with mock.patch.object(pipeline, "prepare", return_value=(FACE, None, False)), \
                mock.patch.object(pipeline.prompts, "creative_full", return_value="brief") as brief, \
                mock.patch.object(pipeline.bleed, "trim", side_effect=lambda png: (png, 0.0)), \
                mock.patch.object(pipeline.panels, "read_back", return_value=self.READ) as read, \
                mock.patch.object(pipeline.panels, "detect") as detect, \
                mock.patch.object(pipeline.check, "proofread", side_effect=lambda *a, **k: list(problems)) as grade, \
                mock.patch.object(pipeline.check, "type_end_mark", return_value=mark), \
                mock.patch.object(pipeline.check, "contrast", return_value=None), \
                mock.patch.object(pipeline.check, "colour_identity", return_value=None), \
                mock.patch.object(pipeline.check, "matted", return_value=None), \
                mock.patch.object(pipeline.gemini, "generate", return_value=_jpeg()) as generate:
            result = pipeline.creative_full(FACE, self.OPTIONS, **kwargs)
        return generate, read, detect, grade, brief, result

    def test_it_reads_the_card_back_instead_of_detecting_blanks(self):
        """`detect`'s prompt opens "BLANK raised surfaces and no writing on it" and its `marks`
        list means any painted lettering, which on a lettered card is every surface."""
        _, read, detect, _, _, _ = self._run()
        self.assertEqual(read.call_count, 1)
        detect.assert_not_called()

    def test_a_clean_card_costs_one_image_call_and_one_vision_call(self):
        generate, read, _, _, _, result = self._run()
        self.assertEqual((generate.call_count, read.call_count), (1, 1))
        self.assertEqual(result.problems, [])

    def test_the_text_gate_runs_and_its_wording_drives_the_repaint(self):
        wrong = check.Problem("text_wrong", "the type line reads 'Instant' and must read 'Sorcery'")
        generate, _, _, grade, brief, result = self._run(problems=[wrong])
        self.assertEqual(grade.call_count, 2, "the gate did not run on both attempts")
        self.assertEqual(generate.call_count, 2, "a card with wrong text was not repainted")
        self.assertEqual(brief.call_args.kwargs["corrections"], [wrong.detail])
        self.assertEqual([p.code for p in result.problems], ["text_wrong"])

    def test_the_product_default_is_lettered(self):
        _, _, detect, _, brief, _ = self._run()
        self.assertTrue(brief.call_args.kwargs["lettered"])
        self.assertFalse(brief.call_args.kwargs["name_lettered"])
        detect.assert_not_called()

    def test_a_badge_on_the_type_line_repaints(self):
        """SIGNOFF 2026-08-19, Elesh Norn. The text gate passed; the slot still had a set mark.
        The retry is what makes that defect not ship."""
        badge = check.Problem(
            "painted_marks",
            "the right-hand end of the type line carries a painted badge or set mark",
        )
        generate, _, _, _, brief, result = self._run(mark=badge)
        self.assertEqual(generate.call_count, 2)
        self.assertEqual(brief.call_args.kwargs["corrections"], [badge.detail])
        self.assertEqual([p.code for p in result.problems], ["painted_marks"])

    def test_a_cost_that_would_sit_on_the_rim_repaints(self):
        """CLIENT-PACK 2026-08-19. `cost_collides` compares boxes; this grades the inner
        face. Without the retry the last pip ships on the gold."""
        rim = check.Problem(
            "cost_no_room",
            "the inner face of the title plate is too short for this mana cost",
        )
        with mock.patch.object(pipeline.check, "cost_off_rim", return_value=rim):
            generate, _, _, _, brief, result = self._run()
        self.assertEqual(generate.call_count, 2)
        self.assertEqual(brief.call_args.kwargs["corrections"], [rim.detail])
        self.assertEqual([p.code for p in result.problems], ["cost_no_room"])


class NameLetteredTests(SimpleTestCase):
    """Opt-in hybrid: the model letters the name; we stamp type, rules, P/T, mana.

    Failed as the daily path on his seven (2026-08-20): named-detect dropped blank
    type/rules/P/T, names still sat on bars. Kept as `--name-lettered`. Same two calls —
    `detect(..., named=True)` replaces a blank detect, it does not join `read_back`.
    """

    LOCATED = {
        "title": (0.05, 0.03, 0.95, 0.11),
        "name": (0.08, 0.04, 0.55, 0.10),
        "type": (0.05, 0.58, 0.95, 0.64),
        "rules": [(0.06, 0.65, 0.94, 0.90)],
        "text": [{"where": "title_plate", "text": "Terror of the Peaks"}],
    }

    def _run(self, problems=(), **kwargs):
        with mock.patch.object(pipeline, "prepare", return_value=(FACE, None, False)), \
                mock.patch.object(pipeline.prompts, "creative_full", return_value="brief") as brief, \
                mock.patch.object(pipeline.bleed, "trim", side_effect=lambda png: (png, 0.0)), \
                mock.patch.object(pipeline.panels, "detect", return_value=self.LOCATED) as detect, \
                mock.patch.object(pipeline.panels, "read_back") as read, \
                mock.patch.object(
                    pipeline.compositor, "compose",
                    return_value=(Image.new("RGB", (179, 240), (205, 200, 190)), False),
                ) as compose, \
                mock.patch.object(
                    pipeline.check, "proofread",
                    side_effect=lambda *a, **k: list(problems),
                ) as grade, \
                mock.patch.object(pipeline.check, "inspect", return_value=[]), \
                mock.patch.object(pipeline.check, "cost_collides", return_value=None), \
                mock.patch.object(pipeline.check, "cost_off_rim", return_value=None), \
                mock.patch.object(pipeline.check, "obstructed", return_value=None), \
                mock.patch.object(pipeline.check, "contrast", return_value=None), \
                mock.patch.object(pipeline.check, "colour_identity", return_value=None), \
                mock.patch.object(pipeline.check, "matted", return_value=None), \
                mock.patch.object(pipeline.gemini, "generate", return_value=_jpeg()) as generate:
            result = pipeline.creative_full(
                FACE, pipeline.Options(lettered=False, name_lettered=True), **kwargs
            )
        return generate, detect, read, grade, brief, compose, result

    def test_it_detects_named_surfaces_instead_of_reading_the_body_back(self):
        _, detect, read, _, brief, compose, _ = self._run()
        self.assertTrue(brief.call_args.kwargs["name_lettered"])
        self.assertFalse(brief.call_args.kwargs["lettered"])
        detect.assert_called_once()
        self.assertTrue(detect.call_args.kwargs["named"])
        read.assert_not_called()
        self.assertTrue(compose.call_args.kwargs["name_lettered"])

    def test_a_wrong_name_repaints(self):
        wrong = check.Problem(
            "text_wrong",
            "the card's name reads 'Terror' and must read 'Terror of the Peaks'",
        )
        generate, _, _, grade, brief, _, result = self._run(problems=[wrong])
        self.assertEqual(grade.call_count, 2)
        self.assertEqual(generate.call_count, 2)
        self.assertEqual(brief.call_args.kwargs["corrections"], [wrong.detail])
        self.assertEqual([p.code for p in result.problems], ["text_wrong"])

    def test_proofread_is_asked_for_the_name_only(self):
        _, _, _, grade, _, _, _ = self._run()
        self.assertEqual(grade.call_args.kwargs["only"], ("title_plate",))


class StoredBoxesTests(SimpleTestCase):
    """Re-compositing stored art must cost nothing and move nothing but the code.

    `source` alone was half the story: it skips the image call but still pays for a vision call and
    still lets the boxes move, so a compositor change measured that way is confounded with a
    detection change. Those need opposite fixes — the ambiguity that stopped a diagnosis dead on
    2026-08-15, when two cards tripped `text_too_small` and nothing could say which had happened.
    """

    # The module FACE is minimal because every other test has `detect` return {} and composites
    # nothing. These boxes make the compositor actually run, so it needs the fields it prints.
    FACE = {**FACE, "type_line": "Creature — Dragon", "mana_cost": "{3}{R}{R}",
            "power": "5", "toughness": "4"}
    BOXES = {
        "title": [0.05, 0.03, 0.95, 0.11],
        "type": [0.05, 0.58, 0.95, 0.64],
        "rules": [[0.06, 0.65, 0.94, 0.90]],
    }

    def _run(self, **kwargs):
        with mock.patch.object(pipeline, "prepare", return_value=(self.FACE, None, False)), \
                mock.patch.object(pipeline.prompts, "creative_full", return_value="brief"), \
                mock.patch.object(pipeline.bleed, "trim", side_effect=lambda png: (png, 0.0)), \
                mock.patch.object(pipeline.panels, "detect", return_value={}) as detect, \
                mock.patch.object(pipeline.check, "inspect", return_value=[]), \
                mock.patch.object(pipeline.check, "contrast", return_value=None), \
                mock.patch.object(pipeline.check, "colour_identity", return_value=None), \
                mock.patch.object(pipeline.check, "matted", return_value=None), \
                mock.patch.object(pipeline.gemini, "generate", return_value=_jpeg()) as generate:
            result = pipeline.creative_full(self.FACE, pipeline.Options(lettered=False, name_lettered=False), **kwargs)
        return generate, detect, result

    def test_stored_boxes_skip_the_vision_call_entirely(self):
        generate, detect, result = self._run(source=_jpeg(), panel_boxes=self.BOXES)
        detect.assert_not_called()
        generate.assert_not_called()
        self.assertEqual(result.detected, self.BOXES)

    def test_boxes_survive_a_json_round_trip(self):
        """They are written as JSON, so they come back as lists of lists, not tuples of tuples."""
        import json
        _, _, result = self._run(source=_jpeg(), panel_boxes=json.loads(json.dumps(self.BOXES)))
        self.assertEqual(result.detected["rules"], [[0.06, 0.65, 0.94, 0.90]])

    def test_a_repaint_re_detects_and_does_not_reuse_the_dead_card_s_boxes(self):
        """The override sits INSIDE the retry loop. Reassigning it would hand attempt 1's boxes to
        attempt 2's repainted image — measured on a card that no longer exists."""
        with mock.patch.object(pipeline, "prepare", return_value=(FACE, None, False)), \
                mock.patch.object(pipeline.prompts, "creative_full", return_value="brief"), \
                mock.patch.object(pipeline.bleed, "trim", side_effect=lambda png: (png, 0.0)), \
                mock.patch.object(pipeline.panels, "detect", return_value={}) as detect, \
                mock.patch.object(pipeline.check, "inspect", return_value=list(FAULT)), \
                mock.patch.object(pipeline.check, "contrast", return_value=None), \
                mock.patch.object(pipeline.check, "colour_identity", return_value=None), \
                mock.patch.object(pipeline.check, "matted", return_value=None), \
                mock.patch.object(pipeline.gemini, "generate", return_value=_jpeg()):
            pipeline.creative_full(FACE, pipeline.Options(lettered=False, name_lettered=False), attempts=2)
        self.assertEqual(detect.call_count, 2, "the repaint reused the first attempt's boxes")
