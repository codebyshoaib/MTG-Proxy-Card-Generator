"""The worker, run inline. `start()`'s thread is not under test; what it runs is."""

import tempfile
import threading
import time
from pathlib import Path
from unittest import mock

from django.test import TestCase, TransactionTestCase, override_settings

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

    def test_art_only_writes_the_png_the_model_returned(self):
        with mock.patch.object(jobs.pipeline, "art", return_value=b"PNG BYTES") as art:
            jobs.run(_job("ART_ONLY").pk)

        job = Job.objects.get()
        self.assertEqual(art.call_count, 2)
        written = Path(self.media.name) / "generated" / str(job.pk) / "lightning-bolt.png"
        self.assertEqual(written.read_bytes(), b"PNG BYTES")


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
