"""The model draws the mana cost, and every symbol is graded against Scryfall — Phase 3.

The four failures on record are the whole reason this needs a gate rather than a hope. Measured
over 25 generations (`prompts._lettering_block`), the model took 18 of 22 costs and missed in one
pattern: `Progenitus` painted 9 pips of a ten-pip cost, `Niv-Mizzet, Parun` 5 of 6, `Kitchen Finks`
drew hybrid `{G/W}` as two separate pips, and `Birthing Pod` drew Phyrexian `{G/P}` as plain green.

Each of those four is a test below. A gate that does not catch the failures already on record is
not a gate.

AND THE FIRST BUILD OF THAT GATE DID NOT CATCH THEM, which is what `Blind` below exists to stop
coming back. `packs/cost-hard.json`, 2026-08-20, passed Kitchen Finks and Niv-Mizzet — the second
stored `status: "ok"` — because it graded the cost from `read_back`, and `read_back` sees the card's
NAME. It recognised both cards and reported the costs it remembered. Every test in `Grading` would
have passed throughout: the comparison was never the broken part, the evidence handed to it was.
"""

import io
import json
from unittest import mock

from django.test import SimpleTestCase
from PIL import Image

from generation import check, panels, pipeline, prompts

TOSKI = {
    "name": "Toski, Bearer of Secrets",
    "type_line": "Legendary Creature — Squirrel",
    "oracle_text": "Indestructible",
    "mana_cost": "{3}{G}",
    "color_identity": ["G"],
    "power": "1",
    "toughness": "1",
    "face_position": "SINGLE",
    "is_crossover": False,
}
TREE = {**TOSKI, "name": "Tree of Tales", "type_line": "Artifact Land", "mana_cost": "",
        "oracle_text": "", "power": None, "toughness": None}


def _read(cost=None, **surfaces):
    """A `panels.read_back` answer, whose cost patch is the SIGHTED one — see `Blind`."""
    patches = [
        {"where": "title_plate", "text": surfaces.get("title", TOSKI["name"])},
        {"where": "type_strip", "text": surfaces.get("type", TOSKI["type_line"])},
        {"where": "rules_panel", "text": surfaces.get("rules", TOSKI["oracle_text"])},
        {"where": "tab", "text": surfaces.get("tab", "1/1")},
    ]
    if cost is not None:
        patches.insert(1, {"where": "cost", "text": cost})
    return {"title": [10, 50, 120, 950], "name": [20, 60, 110, 500],
            "type": [300, 50, 360, 950], "rules": [[500, 50, 900, 950]], "text": patches}


def _drawn(face, cost, sighted=None, **surfaces):
    """Grade a lettered card whose pips came back as `cost`, read both ways.

    BOTH READERS SAY THE SAME THING unless `sighted` says otherwise, because a disagreement is a
    fault in its own right (`check._cost_disagreement`) and would otherwise be the only thing every
    test here reported. `sighted` is for the tests that are about the disagreement.
    """
    read = _read(cost if sighted is None else sighted, **surfaces)
    return check.proofread(face, read, cost_lettered=True, cost_printed=cost)


def _codes(problems):
    return [problem.code for problem in problems]


class Symbols(SimpleTestCase):
    """`check._symbols`, which is NOT `_normalised` — see its docstring for why that matters."""

    def test_order_is_meaning(self):
        self.assertNotEqual(check._symbols("{2}{G}"), check._symbols("{G}{2}"))

    def test_a_generic_number_is_one_symbol_and_not_that_many(self):
        """`Progenitus` is the card this exists for: ten pips painted as nine."""
        self.assertEqual(1, len(check._symbols("{11}")))
        self.assertNotEqual(check._symbols("{11}"), check._symbols("{1}{1}"))

    def test_hybrid_halves_compare_as_a_set(self):
        """Which half of a split circle a reader names first is not a property of the card."""
        self.assertEqual(check._symbols("{G/W}"), check._symbols("{W/G}"))

    def test_case_does_not_matter_but_count_does(self):
        self.assertEqual(check._symbols("{g}"), check._symbols("{G}"))
        self.assertNotEqual(check._symbols("{G}{G}"), check._symbols("{G}"))

    def test_normalised_would_get_this_wrong(self):
        """The trap this function exists to avoid, asserted so nobody merges the two by accident:
        `_normalised` strips braces, so it cannot tell one eleven from two ones."""
        self.assertEqual(check._normalised("{11}"), check._normalised("{1}{1}"))
        self.assertNotEqual(check._symbols("{11}"), check._symbols("{1}{1}"))


class Grading(SimpleTestCase):
    def test_a_correct_cost_passes(self):
        self.assertEqual([], _codes(_drawn(TOSKI, "{3}{G}")))

    def test_a_cost_short_by_one_pip_fails(self):
        """`Progenitus`, 9 of 10, and `Niv-Mizzet, Parun`, 5 of 6 — the two counting failures."""
        problems = _drawn(TOSKI, "{2}{G}")
        self.assertEqual(["cost_wrong"], _codes(problems))
        self.assertIn("2 symbol(s) in that exact order", problems[0].detail)

    def test_a_hybrid_drawn_as_two_pips_fails(self):
        """`Kitchen Finks`: `{G/W}` came back as a green pip beside a white one."""
        finks = {**TOSKI, "mana_cost": "{1}{G/W}{G/W}"}
        problems = _drawn(finks, "{1}{G}{W}{G}{W}")
        self.assertEqual(["cost_wrong"], _codes(problems))
        self.assertIn("ONE split circle, not two", problems[0].detail)

    def test_the_hybrid_failure_exactly_as_it_came_back(self):
        """Kitchen Finks on 2026-08-20 did not draw four pips for its two hybrids — it drew ONE
        of each half. So the count matches nothing and neither does the shape."""
        finks = {**TOSKI, "mana_cost": "{1}{G/W}{G/W}"}
        self.assertEqual(["cost_wrong"], _codes(_drawn(finks, "{1}{G}{W}")))

    def test_a_phyrexian_pip_drawn_as_plain_mana_fails(self):
        """`Birthing Pod`: `{G/P}` came back as an ordinary green pip."""
        pod = {**TOSKI, "mana_cost": "{3}{G/P}"}
        self.assertEqual(["cost_wrong"], _codes(_drawn(pod, "{3}{G}")))

    def test_an_unnameable_symbol_fails_rather_than_being_skipped(self):
        """`{?}` is the read saying a drawn pip is not a Magic symbol, which is the defect
        the vendored SVGs make impossible on the stamped path."""
        problems = _drawn(TOSKI, "{3}{?}")
        self.assertEqual(["cost_wrong"], _codes(problems))
        self.assertIn("not a Magic symbol", problems[0].detail)

    def test_a_missing_cost_is_reported(self):
        self.assertEqual(["text_missing"], _codes(_drawn(TOSKI, "")))

    def test_a_land_has_no_cost_and_a_drawn_one_is_invented(self):
        """bd mtg-m8q's lesson on the grading side: a field the card does not have, carrying
        marks, was invented."""
        problems = _drawn(TREE, "{G}", title=TREE["name"], type=TREE["type_line"],
                          rules="", tab="")
        self.assertIn("text_extra", _codes(problems))

    def test_no_cost_is_graded_for_correctness_when_we_stamp_it(self):
        """Grading a field we drew ourselves, against a transcription of our own drawing, tests
        the read-back and not the card. A wrong cost there would be OUR bug, and repainting the
        card cannot fix our compositor.

        A drawn cost on this path is still not ignored — it is `text_extra`, because the model has
        painted a cost nobody asked for and ours is about to land on top of it.
        """
        for drawn in ("{3}{G}", "{9}{9}{9}"):
            with self.subTest(drawn=drawn):
                self.assertEqual(["text_extra"], _codes(check.proofread(TOSKI, _read(drawn))))

    def test_nothing_at_all_is_reported_when_no_cost_was_drawn(self):
        self.assertEqual([], _codes(check.proofread(TOSKI, _read())))

    def test_the_read_back_can_report_the_cost_at_all(self):
        """The enum is the contract between the vision prompt and the grader."""
        self.assertIn("cost", panels.SURFACES)
        self.assertIn("cost", panels.READ_SCHEMA["properties"]["text"]["items"]
                      ["properties"]["where"]["enum"])
        self.assertIn("MANA COST", panels.READ_PROMPT)


class Blind(SimpleTestCase):
    """THE COST IS GRADED FROM A CROP WITH NO NAME IN IT, and this class is why.

    `packs/cost-hard.json`, 2026-08-20. Every one of `Grading`'s tests passed, and the gate still
    shipped two wrong costs, because it was fed `read_back`'s transcription — and `read_back` is
    looking at an image with the card's name printed across the top of it. Same pixels, both ways:

        Kitchen Finks       whole card {1}{G/W}{G/W}       crop {1}{G}{W}
        Niv-Mizzet, Parun   whole card {U}{U}{U}{R}{R}{R}  crop {U}{U}{U}{R}{R}

    The model READS WORDS and RECALLS SYMBOLS. So the transcription stays authoritative for name,
    type, rules and P/T, and is inadmissible for the pips.
    """

    def test_grading_a_cost_without_the_blind_read_is_refused_outright(self):
        """The quiet version of this mistake restores the false pass and still looks like a gate,
        so it is not allowed to be quiet."""
        with self.assertRaises(ValueError) as raised:
            check.proofread(TOSKI, _read("{3}{G}"), cost_lettered=True)
        self.assertIn("panels.cost_read", str(raised.exception))

    def test_the_two_readings_must_agree_or_the_card_is_repainted(self):
        """KITCHEN FINKS, BOTH WAYS. Batch 1: the whole-card reader recognised the card and said
        `{1}{G/W}{G/W}` over two plain pips. Batch 3: the cropped reader, handed a definition of a
        hybrid and a pip with a pale ring, said `{1}{G/W}{G/W}` over the same two plain pips while
        the whole-card reader got it right. Neither reader is trustworthy alone.
        """
        finks = {**TOSKI, "mana_cost": "{1}{G/W}{G/W}"}
        for blind, sighted in (("{1}{G}{W}", "{1}{G/W}{G/W}"), ("{1}{G/W}{G/W}", "{1}{G}{W}")):
            with self.subTest(blind=blind, sighted=sighted):
                problems = check.proofread(
                    finks, _read(sighted), cost_lettered=True, cost_printed=blind,
                )
                self.assertEqual(["cost_wrong"], _codes(problems))
                self.assertIn("cannot be read reliably", problems[0].detail)

    def test_a_disagreement_is_reported_even_when_one_reading_matches_scryfall(self):
        """The point of the rule. Whichever reader happens to agree with Scryfall, agreeing with
        Scryfall is not evidence about the pixels — it is what recall looks like."""
        problems = check.proofread(
            TOSKI, _read("{3}{G}"), cost_lettered=True, cost_printed="{2}{G}",
        )
        self.assertEqual(["cost_wrong"], _codes(problems))
        self.assertIn("cannot be read reliably", problems[0].detail)

    def test_the_repaint_is_told_what_makes_a_pip_unambiguous(self):
        """A disagreement does not say WHICH reader is wrong, so the instruction cannot claim to.
        It asks for pips that cannot be read two ways, which is the actual defect."""
        problems = check.proofread(
            TOSKI, _read("{3}{G}"), cost_lettered=True, cost_printed="{2}{G}",
        )
        self.assertIn("cut by a straight line", problems[0].detail)
        self.assertIn("no contrasting ring", problems[0].detail)

    def test_agreement_on_a_wrong_cost_is_still_a_wrong_cost(self):
        """Agreement is necessary, not sufficient — the agreed reading is then graded."""
        self.assertEqual(["cost_wrong"], _codes(_drawn(TOSKI, "{2}{G}")))

    def test_agreement_on_the_right_cost_passes_and_is_not_stray_writing(self):
        """It is one drawing read twice, not a second cost on the card."""
        self.assertEqual([], _codes(_drawn(TOSKI, "{3}{G}")))

    def test_a_missing_cost_is_reported_as_missing_and_not_as_a_disagreement(self):
        """Nothing painted is `text_missing`, which tells the model to draw one. Calling it a
        disagreement would tell it to draw the one it did not draw more clearly."""
        problems = check.proofread(
            TOSKI, _read(""), cost_lettered=True, cost_printed="",
        )
        self.assertEqual(["text_missing"], _codes(problems))

    def test_an_unreadable_pip_keeps_its_own_message(self):
        """`{?}` has a better instruction than "the readers disagree" — draw a real symbol."""
        problems = check.proofread(
            TOSKI, _read("{3}{G}"), cost_lettered=True, cost_printed="{3}{?}",
        )
        self.assertEqual(["cost_wrong"], _codes(problems))
        self.assertIn("not a Magic symbol", problems[0].detail)

    def test_the_schema_asks_for_the_box_the_crop_needs(self):
        self.assertIn("cost", panels.READ_SCHEMA["properties"])
        self.assertIn("mana symbols", panels.READ_SCHEMA["properties"]["cost"]["description"])
        self.assertIn('- "cost": the box of the MANA COST', panels.READ_PROMPT)

    def test_the_crop_prompt_tells_the_model_its_memory_is_a_wrong_answer(self):
        """The one instruction the whole fix rests on. It is asked to count circles."""
        self.assertIn("a remembered cost is a wrong answer here", panels.COST_PROMPT)
        self.assertIn("COUNT THE CIRCLES", panels.COST_PROMPT)
        self.assertIn("it is NOT {G/W}", panels.COST_PROMPT)

    def test_the_crop_prompt_defines_a_split_by_its_dividing_line(self):
        """KITCHEN FINKS, batch 3. Told only that a hybrid has "two halves, each a different
        colour", the reader called a green disc inside a pale ring a hybrid. Two colours is not the
        test; a dividing line with a pictogram either side of it is."""
        for wording in ("STRAIGHT LINE", "RING", "one plain pip"):
            self.assertIn(wording, panels.COST_PROMPT)

    def test_the_crop_prompt_never_names_the_card_or_its_cost(self):
        """A crop prompt that mentioned either would reintroduce the leak it exists to remove."""
        for leak in ("Kitchen Finks", "Scryfall", "expected", "should read"):
            self.assertNotIn(leak, panels.COST_PROMPT)


class Cropping(SimpleTestCase):
    """`panels.cost_read` — that it crops to the pips, and that nothing else reaches the model."""

    def _call(self, box, answer="{3}{G}", size=(1000, 1400)):
        image = Image.new("RGB", size, "white")
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")

        models = mock.Mock()
        models.generate_content.return_value = mock.Mock(
            text=json.dumps({"symbols": answer})
        )
        with mock.patch.object(panels.gemini, "client", return_value=mock.Mock(models=models)):
            read = panels.cost_read(buffer.getvalue(), box)
        sent = models.generate_content.call_args.kwargs["contents"]
        return read, Image.open(io.BytesIO(sent[0].inline_data.data)), sent[1]

    def test_it_returns_what_the_model_read(self):
        read, _crop, _prompt = self._call((0.70, 0.03, 0.94, 0.09))
        self.assertEqual("{3}{G}", read)

    def test_the_crop_is_the_cost_box_and_a_hair_more(self):
        """`COST_MARGIN` of slack: a pip's outer ring sliced off invents a defect, and too much
        slack lets the name back into frame."""
        _read, crop, _prompt = self._call((0.70, 0.03, 0.94, 0.09), size=(1000, 1000))
        self.assertEqual((0.94 - 0.70 + 2 * panels.COST_MARGIN) * 1000, crop.width)
        self.assertEqual((0.09 - 0.03 + 2 * panels.COST_MARGIN) * 1000, crop.height)

    def test_the_crop_is_a_small_fraction_of_the_card(self):
        """The point of this call is what it EXCLUDES. If the crop were most of the card the name
        would be in it and the gate would be back where it started."""
        _read, crop, _prompt = self._call((0.70, 0.03, 0.94, 0.09))
        self.assertLess((crop.width * crop.height) / (1000 * 1400), 0.05)

    def test_a_box_at_the_very_edge_is_not_asked_for_pixels_that_do_not_exist(self):
        """The margin would run off the top-right corner of a cost drawn into it."""
        _read, crop, _prompt = self._call((0.90, 0.0, 1.0, 0.05))
        self.assertGreater(crop.width, 0)
        self.assertGreater(crop.height, 0)

    def test_it_asks_the_crop_question_and_not_the_whole_card_question(self):
        _read, _crop, prompt = self._call((0.70, 0.03, 0.94, 0.09))
        self.assertEqual(panels.COST_PROMPT, prompt)

    def test_an_empty_answer_survives_as_an_empty_string(self):
        """A crop with no pips in it must read as "no cost drawn", which `proofread` turns into
        `text_missing` — never as a pass."""
        read, _crop, _prompt = self._call((0.70, 0.03, 0.94, 0.09), answer="")
        self.assertEqual("", read)
        self.assertEqual(["text_missing"], _codes(_drawn(TOSKI, read)))


class Brief(SimpleTestCase):
    def test_the_cost_is_handed_over_as_data_with_its_count(self):
        brief = prompts.creative_full(TOSKI, lettered=True, cost_lettered=True)
        self.assertIn('"mana_cost": "{3}{G}"', brief)
        self.assertIn("DRAW EXACTLY 2 SYMBOL(S)", brief)

    def test_the_reserved_well_is_gone_when_the_model_draws_the_cost(self):
        """The two instructions are contradictory, and the reservation is what `cost_no_room` fired
        on for 3 of the client's 7 on 2026-08-20."""
        brief = prompts.creative_full(TOSKI, lettered=True, cost_lettered=True)
        self.assertNotIn("IS RESERVED for", brief)
        self.assertIn("IS RESERVED for", prompts.creative_full(TOSKI, lettered=True))

    def test_the_final_ban_stops_forbidding_the_cost(self):
        """It is the sentence that overrides everything above it, so leaving it in place would
        beat the instruction to draw the cost."""
        brief = prompts.creative_full(TOSKI, lettered=True, cost_lettered=True)
        self.assertNotIn("is not yours to paint", brief)
        self.assertIn("No mana symbol appears anywhere else", brief)
        self.assertIn("is not yours to paint", prompts.creative_full(TOSKI, lettered=True))

    def test_the_counting_rules_name_both_measured_failure_shapes(self):
        brief = prompts.creative_full(TOSKI, lettered=True, cost_lettered=True)
        self.assertIn("never that many circles", brief)       # {11} as eleven pips
        self.assertIn("never two circles side by side", brief)  # {G/W} as two pips

    def test_the_medallion_placement_is_offered_not_required(self):
        """12 of his 19 put the cost on medallions under the name. `check` grades which symbols
        were drawn and never where they sit, so this is an offer."""
        brief = prompts.creative_full(TOSKI, lettered=True, cost_lettered=True)
        self.assertIn("medallions on a second row", brief)
        self.assertIn("whichever the composition wants", brief)

    def test_a_land_is_told_nothing_about_a_cost_it_does_not_have(self):
        """bd mtg-m8q: a card told about a field it does not have has been told to paint it."""
        brief = prompts.creative_full(TREE, lettered=True, cost_lettered=True)
        self.assertNotIn("mana_cost", brief)
        self.assertNotIn("DRAW EXACTLY", brief)

    def test_it_works_through_the_exemplar_brief_too(self):
        brief = prompts.creative_full(
            TOSKI, lettered=True, cost_lettered=True, archetype="tangle", exemplars=3
        )
        self.assertIn("DRAW EXACTLY 2 SYMBOL(S)", brief)
        self.assertNotIn("IS RESERVED for", brief)


class Escalation(SimpleTestCase):
    """A cost still wrong after every attempt is repainted with the well reserved, never stamped
    over. Stamping onto a card that already has a drawn cost leaves the card with two."""

    def _run(self, sequence, attempts=2, options=None):
        """`sequence` is the problems each `_letter` call returns, in order."""
        calls = []
        blank = Image.new("RGB", (8, 8))

        def letter(png, face, options):
            calls.append(options)
            problems = sequence[min(len(calls) - 1, len(sequence) - 1)]
            return blank, {}, list(problems)

        notes = []
        with mock.patch.object(pipeline, "_paint", return_value=b"png"), \
             mock.patch.object(pipeline, "prepare", return_value=(TOSKI, None, False)), \
             mock.patch.object(pipeline.bleed, "trim", side_effect=lambda png: (png, 0.0)), \
             mock.patch.object(pipeline, "_letter", side_effect=letter):
            result = pipeline.creative_full(
                TOSKI, options or pipeline.Options(lettered=True, cost_lettered=True),
                attempts=attempts, note=notes.append,
            )
        return result, [call.cost_lettered for call in calls], notes, calls

    WRONG = [check.Problem("cost_wrong", "the mana cost reads x")]
    OTHER = [check.Problem("text_wrong", "the type line reads y")]

    def test_a_wrong_cost_is_repainted_with_the_well_reserved(self):
        result, calls, notes, _all = self._run([self.WRONG, self.WRONG, []])
        # Two attempts asking the model for the cost, then one with it reserved.
        self.assertEqual([True, True, False], calls)
        self.assertEqual([], result.problems)
        self.assertTrue(any("reserved for our own symbol artwork" in note for note in notes))

    def test_the_fallback_drops_the_exemplars_along_with_the_cost(self):
        """THE PROGENITUS BUG, 2026-08-20. The fallback asks for a reserved well; every exemplar
        draws its cost into a full-width plate. Kept together, `cost_no_room` fired twice and the
        stored card had no mana cost on it at all.
        """
        options = pipeline.Options(
            lettered=True, cost_lettered=True, archetype="tangle", exemplar_count=3,
        )
        _result, _flags, notes, calls = self._run(
            [self.WRONG, self.WRONG, []], options=options,
        )
        self.assertEqual(["tangle", "tangle", None], [call.archetype for call in calls])
        self.assertEqual([3, 3, None], [call.exemplar_count for call in calls])
        self.assertTrue(any("without the exemplars" in note for note in notes))

    def test_the_exemplars_survive_an_ordinary_repaint(self):
        """Only the cost escalation drops them. A repaint for any other fault is still an
        exemplar-conditioned card, which is the whole of Phase 1."""
        options = pipeline.Options(
            lettered=True, cost_lettered=True, archetype="tangle", exemplar_count=3,
        )
        _result, _flags, _notes, calls = self._run([self.OTHER, []], options=options)
        self.assertEqual(["tangle", "tangle"], [call.archetype for call in calls])

    def test_the_caller_s_options_are_not_mutated_by_the_escalation(self):
        """The job record has to say what was ASKED for, not what the last attempt settled on."""
        options = pipeline.Options(
            lettered=True, cost_lettered=True, archetype="tangle", exemplar_count=3,
        )
        self._run([self.WRONG, self.WRONG, []], options=options)
        self.assertEqual((True, "tangle", 3),
                         (options.cost_lettered, options.archetype, options.exemplar_count))

    def test_the_fallback_gets_exactly_one_attempt_and_the_card_still_ships(self):
        """Even if the reserved repaint also fails, the card is returned unsound rather than
        looped on — the budget is a budget."""
        result, calls, _notes, _all = self._run([self.WRONG, self.WRONG, self.OTHER])
        self.assertEqual([True, True, False], calls)
        self.assertEqual(["text_wrong"], _codes(result.problems))

    def test_a_correct_cost_never_escalates(self):
        result, calls, notes, _all = self._run([[]])
        self.assertEqual([True], calls)
        self.assertEqual([], result.problems)
        self.assertEqual([], notes)

    def test_a_fault_that_is_not_the_cost_is_an_ordinary_repaint(self):
        """Escalation is for the failure the model cannot fix by trying again. Everything else
        keeps the retry it always had, and never stops asking for the drawn cost."""
        _result, calls, _notes, _all = self._run([self.OTHER, []])
        self.assertEqual([True, True], calls)

    def test_a_stamped_run_never_escalates_because_there_is_nothing_to_escalate_to(self):
        calls = []
        blank = Image.new("RGB", (8, 8))

        def letter(png, face, letter_options):
            calls.append(letter_options.cost_lettered)
            return blank, {}, list(self.WRONG)

        with mock.patch.object(pipeline, "_paint", return_value=b"png"), \
             mock.patch.object(pipeline, "prepare", return_value=(TOSKI, None, False)), \
             mock.patch.object(pipeline.bleed, "trim", side_effect=lambda png: (png, 0.0)), \
             mock.patch.object(pipeline, "_letter", side_effect=letter):
            pipeline.creative_full(
                TOSKI, pipeline.Options(lettered=True), attempts=2, note=lambda _m: None,
            )
        self.assertEqual([False, False], calls)
