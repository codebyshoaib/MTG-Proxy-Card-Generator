"""The batch runner, with the generation mocked out — no AI spend in the test suite.

What is worth testing here is not that Gemini works; it is that the RECORD of a batch cannot
disagree with the batch. Every one of these asserts one way that could happen.
"""

import json
import tempfile
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase
from PIL import Image

from generation import pipeline

PACKS = Path(__file__).resolve().parents[2] / "packs"

FACE = {"name": "Toski, Bearer of Secrets", "face_position": "SINGLE"}


class Spec(SimpleTestCase):
    def _run(self, spec, **kwargs):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "spec.json"
            path.write_text(json.dumps(spec))
            out = Path(directory) / "out"
            call_command("pack", path, out=out, stdout=mock.Mock(), **kwargs)
            return out

    def test_a_misspelt_key_stops_the_batch(self):
        """The failure this command exists to prevent: a typo runs on defaults and the recorded
        spec claims otherwise, so the stored cards are evidence for something that never ran."""
        with self.assertRaises(CommandError) as raised:
            self._run({"why": "x", "cards": ["Sol Ring"], "archtype": "tangle"})
        self.assertIn("archtype", str(raised.exception))

    def test_a_batch_with_no_stated_purpose_is_refused(self):
        with self.assertRaises(CommandError):
            self._run({"cards": ["Sol Ring"]})

    def test_no_cards_is_refused(self):
        with self.assertRaises(CommandError):
            self._run({"why": "x", "cards": []})


class Recording(SimpleTestCase):
    """The spec goes in, and a copy of it plus the resolved options comes out beside the images."""

    def _run(self, spec, result=None, faces=(FACE,)):
        painted = result or mock.Mock(
            card=Image.new("RGB", (8, 8)), blank=None, detected={}, problems=[],
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "spec.json"
            path.write_text(json.dumps(spec))
            out = Path(directory) / "out"
            with mock.patch.object(pipeline, "faces_of", return_value=list(faces)), \
                 mock.patch.object(pipeline, "creative_full", return_value=painted) as painter:
                call_command("pack", path, out=out, stdout=mock.Mock())
            return (
                json.loads((out / "_pack.json").read_text()),
                json.loads((out / "_job.json").read_text()),
                painter,
                sorted(p.name for p in out.iterdir()),
            )

    SPEC = {
        "why": "the record must match the run",
        "bead": "mtg-jbk.2",
        "art_style": "comic_book",
        "lettered": True,
        "archetype": "tangle",
        "exemplar_count": 3,
        "cards": ["Toski, Bearer of Secrets"],
    }

    def test_the_options_actually_passed_are_the_options_recorded(self):
        """Asserted against the Options object the pipeline was CALLED with, not against the spec.
        Comparing the record to the spec it was copied from would pass no matter what ran."""
        pack, _job, painter, _files = self._run(self.SPEC)
        options = painter.call_args[0][1]
        self.assertEqual("tangle", options.archetype)
        self.assertEqual(3, options.exemplar_count)
        self.assertEqual("comic_book", options.art_style)
        self.assertEqual(options._asdict(), pack["options"])

    def test_the_stated_purpose_survives_into_the_record(self):
        pack, _job, _painter, _files = self._run(self.SPEC)
        self.assertEqual(self.SPEC["why"], pack["why"])
        self.assertEqual("mtg-jbk.2", pack["bead"])

    def test_a_clean_card_is_recorded_ok_with_its_stem(self):
        _pack, job, _painter, files = self._run(self.SPEC)
        self.assertEqual("ok", job["results"][0]["status"])
        self.assertEqual("toski-bearer-of-secrets", job["results"][0]["stem"])
        self.assertIn("toski-bearer-of-secrets.png", files)

    def test_an_unsound_card_is_stored_with_its_problems(self):
        """Stored, not dropped: an unsound card is the one somebody needs to look at."""
        problem = mock.Mock(code="cost_no_room", detail="no room for the cost")
        painted = mock.Mock(
            card=Image.new("RGB", (8, 8)), blank=None, detected={}, problems=[problem],
        )
        _pack, job, _painter, files = self._run(self.SPEC, result=painted)
        self.assertEqual("unsound", job["results"][0]["status"])
        self.assertEqual("cost_no_room", job["results"][0]["problems"][0]["code"])
        self.assertIn("toski-bearer-of-secrets.png", files)

    def test_a_batch_that_dies_halfway_still_writes_its_record(self):
        """The batch somebody most needs the record of is the one that failed."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "spec.json"
            path.write_text(json.dumps(self.SPEC))
            out = Path(directory) / "out"
            with mock.patch.object(pipeline, "faces_of", return_value=[FACE]), \
                 mock.patch.object(pipeline, "creative_full", side_effect=RuntimeError("503")):
                call_command("pack", path, out=out, stdout=mock.Mock())
            job = json.loads((out / "_job.json").read_text())
        self.assertEqual("failed", job["results"][0]["status"])
        self.assertIn("503", job["results"][0]["error"])
        self.assertIn("traceback", job["results"][0])

    def test_a_two_faced_card_writes_one_entry_per_face(self):
        faces = [
            {"name": "Delver of Secrets", "face_position": "FRONT"},
            {"name": "Insectile Aberration", "face_position": "BACK"},
        ]
        _pack, job, _painter, files = self._run(self.SPEC, faces=faces)
        self.assertEqual(2, len(job["results"]))
        self.assertIn("delver-of-secrets-front.png", files)
        self.assertIn("insectile-aberration-back.png", files)


class CommittedPacks(SimpleTestCase):
    """The specs in `backend/packs/` are run by hand and must not rot silently."""

    def test_every_committed_pack_is_loadable_and_says_why_it_exists(self):
        specs = sorted(PACKS.glob("*.json"))
        self.assertTrue(specs, f"no packs in {PACKS}")
        for spec in specs:
            with self.subTest(spec=spec.name):
                loaded = json.loads(spec.read_text())
                self.assertTrue(loaded.get("why"))
                self.assertTrue(loaded.get("cards"))
                # Would the runner accept it? Cheaper to fail here than after seven generations.
                from generation.management.commands.pack import OPTIONS
                self.assertEqual(
                    set(), set(loaded) - set(OPTIONS) - {"why", "bead", "cards"}
                )
                pipeline.Options(**{k: loaded[k] for k in OPTIONS if k in loaded})
