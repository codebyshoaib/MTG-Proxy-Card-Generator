"""The worker, run inline. `start()`'s thread is not under test; what it runs is."""

import io
import json
import tempfile
import threading
import time
from pathlib import Path
from unittest import mock

from django.test import TestCase, TransactionTestCase, override_settings
from PIL import Image

from generation import jobs
from generation.models import Job

FACES = [
    {"name": "Lightning Bolt", "face_position": "SINGLE"},
    {"name": "Delver of Secrets", "face_position": "FRONT"},
]


def _job(mode="CREATIVE_FULL"):
    return Job.objects.create(
        mode=mode,
        options={},
        cards=[{"quantity": 4, "name": face["name"], "faces": [face]} for face in FACES],
    )


class RunTests(TestCase):
    def setUp(self):
        # One worker, so the work happens in this thread and therefore in the test database.
        # The pool itself is exercised by ConcurrencyTests below.
        workers = mock.patch.object(jobs, "WORKERS", 1)
        workers.start()
        self.addCleanup(workers.stop)
        self.media = tempfile.TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        self.settings_ = override_settings(MEDIA_ROOT=Path(self.media.name))
        self.settings_.enable()
        self.addCleanup(self.settings_.disable)

    def test_every_face_lands_as_a_file_and_a_result(self):
        card = mock.Mock()
        with mock.patch.object(
            jobs.pipeline, "creative_full",
            return_value=jobs.pipeline.Result(card, [], {}, b"blank"),
        ):
            jobs.run(_job().pk)

        job = Job.objects.get()
        self.assertEqual(job.status, Job.DONE)
        self.assertEqual([r["status"] for r in job.results], ["ok", "ok"])
        self.assertEqual(job.results[0]["quantity"], 4)
        self.assertEqual(
            job.results[1]["image"], f"/media/generated/{job.pk}/delver-of-secrets-front.png"
        )

    def test_one_card_failing_does_not_sink_the_rest_of_the_deck(self):
        """A deck is dozens of paid generations. Losing the finished ones to the last card's
        exception is the expensive kind of failure."""
        with mock.patch.object(
            jobs.pipeline, "creative_full",
            side_effect=[RuntimeError("model said no"),
                         jobs.pipeline.Result(mock.Mock(), [], {}, None)],
        ):
            jobs.run(_job().pk)

        job = Job.objects.get()
        self.assertEqual(job.status, Job.DONE)
        self.assertEqual([r["status"] for r in job.results], ["failed", "ok"])
        self.assertEqual(job.results[0]["problems"][0]["detail"], "model said no")

    def test_an_unsound_card_is_reported_as_unsound_rather_than_as_a_success(self):
        """The rule underneath the whole check step: a card whose text differs from Scryfall
        must never ship silently."""
        from generation.check import Problem

        with mock.patch.object(
            jobs.pipeline, "creative_full",
            return_value=jobs.pipeline.Result(
                mock.Mock(), [Problem("PLATE_ORDER", "plates out of order")], {}, None
            ),
        ):
            jobs.run(_job().pk)

        job = Job.objects.get()
        self.assertEqual(job.results[0]["status"], "unsound")
        self.assertEqual(job.results[0]["problems"][0]["code"], "PLATE_ORDER")

    def test_art_only_writes_a_real_png_from_the_models_jpeg(self):
        """The model returns JPEG. A file called `.png` has to BE a PNG.

        MEASURED on job ac1c537c, the first Art Only run through the UI: `file` reported the
        written `lightning-bolt.png` as JPEG, and it was served as `image/png`. Browsers sniff
        past it, which is why this survived — the download is the deliverable, so the format has
        to match the name.

        `pipeline.art` now hands back the decoded image rather than the model's bytes (bd
        mtg-l4x), so the save below is what makes the format match — the same line Creative Full
        has always used.
        """
        with mock.patch.object(
            jobs.pipeline, "art",
            return_value=jobs.pipeline.Result(Image.new("RGB", (8, 11), "red"), [], {}, None),
        ) as art:
            jobs.run(_job("ART_ONLY").pk)

        job = Job.objects.get()
        self.assertEqual(art.call_count, 2)
        written = Path(self.media.name) / "generated" / str(job.pk) / "lightning-bolt.png"
        self.assertEqual(Image.open(written).format, "PNG")

    def test_creative_full_is_lettered_when_the_job_did_not_record_it(self):
        """The worker does not force a mode. A row created by hand with options={} is the
        product path: Gemini letters the card, we stamp the mana cost."""
        with mock.patch.object(
            jobs.pipeline, "creative_full",
            return_value=jobs.pipeline.Result(mock.Mock(), [], {}, None),
        ) as paint:
            jobs.run(_job().pk)
        options = paint.call_args.args[1]
        self.assertTrue(options.lettered)
        self.assertFalse(options.name_lettered)

    def test_an_unsound_art_only_face_is_reported_unsound_and_not_ok(self):
        """bd mtg-l4x. `_face` used to hard-code `problems = []` on this branch — not "no faults
        found" but "never looked", which is how a fully bordered card shipped marked ok."""
        from generation.check import Problem

        with mock.patch.object(
            jobs.pipeline, "art",
            return_value=jobs.pipeline.Result(
                Image.new("RGB", (8, 11), "red"),
                [Problem("matted", "a printed white margin runs around the art")], {}, None,
            ),
        ):
            jobs.run(_job("ART_ONLY").pk)

        job = Job.objects.get()
        self.assertEqual([r["status"] for r in job.results], ["unsound", "unsound"])
        self.assertEqual(job.results[0]["problems"][0]["code"], "matted")
        self.assertIsNone(job.results[0]["panels"], "Art Only paints no furniture to detect")
        self.assertIsNone(job.results[0]["blank"], "and there is no blank behind it either")


class ConcurrencyTests(TransactionTestCase):
    """Faces are painted at the same time, not one after another.

    MEASURED on job 9f16e827 before this existed: five faces, one at a time, 5m14s — while a
    single clean face takes ~45s and is almost entirely waiting on Gemini. The wall clock has to
    be the slowest face, not the sum of them.
    """

    def test_four_faces_overlap_instead_of_queueing(self):
        peak, running = [], []
        lock = threading.Lock()

        def slow(face, options, note=None):
            with lock:
                running.append(1)
                peak.append(len(running))
            time.sleep(0.15)
            with lock:
                running.pop()
            return jobs.pipeline.Result(mock.Mock(), [], {}, None)

        with tempfile.TemporaryDirectory() as media, override_settings(MEDIA_ROOT=Path(media)):
            with mock.patch.object(jobs, "WORKERS", 4), \
                    mock.patch.object(jobs.pipeline, "creative_full", side_effect=slow):
                job = Job.objects.create(
                    mode="CREATIVE_FULL",
                    options={},
                    cards=[
                        {"quantity": 1, "name": f"Card {n}", "faces": [
                            {"name": f"Card {n}", "face_position": "SINGLE"}]}
                        for n in range(4)
                    ],
                )
                started = time.monotonic()
                jobs.run(job.pk)
                elapsed = time.monotonic() - started

        self.assertGreater(max(peak), 1, "faces were painted one at a time")
        self.assertLess(elapsed, 0.15 * 4, "the wall clock is still the sum of the faces")
        self.assertEqual(Job.objects.get(pk=job.pk).status, Job.DONE)


class KeepTheEvidenceTests(TestCase):
    """A card that came back wrong keeps what is needed to work out why (bd mtg-57t).

    On 2026-08-15 two cards tripped `text_too_small` through the UI and the post-mortem stopped
    dead: there was no way to tell whether the model under-painted the strip or `panels.detect`
    under-reported it, which need opposite fixes. `pipeline` already hands both back — the blank
    and the detected boxes — and the worker was throwing them away, so every diagnosis cost a
    fresh paid generation and still ended in a guess.
    """

    def setUp(self):
        workers = mock.patch.object(jobs, "WORKERS", 1)
        workers.start()
        self.addCleanup(workers.stop)
        self.media = tempfile.TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        self.settings_ = override_settings(MEDIA_ROOT=Path(self.media.name))
        self.settings_.enable()
        self.addCleanup(self.settings_.disable)

    BOXES = {"title": (0.05, 0.03, 0.95, 0.11), "rules": [(0.06, 0.65, 0.94, 0.90)]}
    # The row is JSON, so tuples come back as lists. Compare against what a round trip gives.
    STORED = json.loads(json.dumps(BOXES))

    def _run(self, problems):
        from generation import check

        result = jobs.pipeline.Result(mock.Mock(), problems, self.BOXES, b"the-blank-png")
        with mock.patch.object(jobs.pipeline, "creative_full", return_value=result):
            jobs.run(_job().pk)
        return Job.objects.get()

    def test_an_unsound_card_keeps_its_blank_and_its_boxes(self):
        from generation.check import Problem

        job = self._run([Problem("text_too_small", "too small")])
        blank = Path(self.media.name) / "generated" / str(job.pk) / "lightning-bolt-blank.png"
        self.assertTrue(blank.exists(), "the blank is the only record of what was painted")
        self.assertEqual(blank.read_bytes(), b"the-blank-png")
        self.assertEqual(job.results[0]["panels"], self.STORED)
        self.assertEqual(job.results[0]["blank"], f"/media/generated/{job.pk}/lightning-bolt-blank.png")

    def test_a_sound_card_keeps_its_boxes_but_not_9mb_of_blank(self):
        """The boxes answer the question and cost nothing; the blank is ~9MB a face and a card
        that graded clean has nothing to investigate."""
        job = self._run([])
        blank = Path(self.media.name) / "generated" / str(job.pk) / "lightning-bolt-blank.png"
        self.assertFalse(blank.exists())
        self.assertIsNone(job.results[0]["blank"])
        self.assertEqual(job.results[0]["panels"], self.STORED, "the boxes are kept either way")

    def test_keep_blanks_keeps_it_on_a_sound_card_too(self):
        """For an evidence batch the point is to localise a fault BEFORE knowing there is one:
        with the blank and the composited card side by side, "the model under-painted it" and
        "the detector under-reported it" are told apart by looking. Off by default — the disk
        trade above still holds for ordinary runs."""
        with self.settings(KEEP_BLANKS=True):
            job = self._run([])
        blank = Path(self.media.name) / "generated" / str(job.pk) / "lightning-bolt-blank.png"
        self.assertTrue(blank.exists())
        self.assertEqual(blank.read_bytes(), b"the-blank-png")
        self.assertEqual(job.results[0]["blank"], f"/media/generated/{job.pk}/lightning-bolt-blank.png")
        self.assertEqual(job.results[0]["status"], "ok", "keeping evidence does not fail the card")


class ReapTests(TestCase):
    """A restart leaves a row saying `running` with nothing behind it, and the frontend polls it
    forever. The pool is in-process, so 'is anyone working on this' is exactly 'is it this
    process' (bd mtg-57t)."""

    def test_a_job_left_running_by_another_process_is_failed(self):
        job = _job()
        Job.objects.filter(pk=job.pk).update(status=Job.RUNNING, worker_pid=999_999)
        self.assertEqual(jobs.reap(), 1)
        job.refresh_from_db()
        self.assertEqual(job.status, Job.FAILED)
        self.assertIn("restarted", job.error)

    def test_this_process_s_own_running_job_is_left_alone(self):
        import os

        job = _job()
        Job.objects.filter(pk=job.pk).update(status=Job.RUNNING, worker_pid=os.getpid())
        self.assertEqual(jobs.reap(), 0)
        job.refresh_from_db()
        self.assertEqual(job.status, Job.RUNNING)

    def test_a_job_nobody_has_claimed_is_not_reaped(self):
        """A NULL pid means never claimed, not abandoned. Reaping those would fail any row made by
        hand — which is what every fixture is, and what broke the polling test first time."""
        job = _job()
        Job.objects.filter(pk=job.pk).update(status=Job.RUNNING, worker_pid=None)
        self.assertEqual(jobs.reap(), 0)
        job.refresh_from_db()
        self.assertEqual(job.status, Job.RUNNING)

    def test_start_stamps_the_pid_before_the_worker_exists(self):
        """Stamped on the request thread, not inside `run`. Otherwise a poll landing between
        `start()` returning and the worker being scheduled reaps a job just accepted."""
        import os

        job = _job()
        with mock.patch.object(jobs.threading, "Thread"):  # never actually run the work
            jobs.start(job)
        job.refresh_from_db()
        self.assertEqual(job.worker_pid, os.getpid())
