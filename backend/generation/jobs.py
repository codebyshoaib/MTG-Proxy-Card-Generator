"""Running a job off the request.

# ponytail: an in-process thread pool, not a queue. It dies with the server and does not survive
# a restart, which is the right trade for a prototype UI and the wrong one the moment a paying
# user's deck is in flight — swap in Celery/RQ behind `start()` when that day comes.
"""

import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from django.conf import settings
from django.db import connection

from generation import pipeline
from generation.models import Job

MAX_CARDS = 60
"""Distinct cards one job may generate.

A guard on spend, not on taste: every card is two paid AI calls, and a pasted 400-line decklist
with no cap is a bill nobody authorised.
"""

WORKERS = int(os.environ.get("GENERATION_WORKERS", "4"))
"""Faces painted at once.

MEASURED on the first frontend run (job 9f16e827): a clean face takes ~45 s and a repainted one
~88 s, of which almost all is waiting on Gemini. Run one at a time, five faces took 5m14s; the
work is I/O and independent per face, so the wall clock should be the slowest face and not the
sum. Four is a guess at what one API key tolerates, not a measurement — raise it with
GENERATION_WORKERS once someone has watched the rate limits.
"""

_results = threading.Lock()
"""Serialises the read-modify-write on `Job.results`, which every worker appends to."""


def _slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def start(job):
    threading.Thread(target=run, args=(job.pk,), daemon=True).start()


def run(job_id):
    job = Job.objects.get(pk=job_id)
    job.status = Job.RUNNING
    job.save(update_fields=["status"])
    options = pipeline.Options(**job.options)
    directory = settings.MEDIA_ROOT / "generated" / str(job.pk)
    directory.mkdir(parents=True, exist_ok=True)

    work = [(entry, face) for entry in job.cards for face in entry["faces"]]
    paint = lambda item: _face(job_id, job.mode, options, directory, *item)  # noqa: E731
    try:
        # Results are appended as each face lands, so the order is completion order rather than
        # decklist order — which is what the user watching the grid actually sees.
        if WORKERS <= 1:
            # No pool at all on one worker: it keeps a traceback in the caller's thread, and it
            # is what the tests run, where a worker thread would not see the test database.
            for item in work:
                paint(item)
        else:
            with ThreadPoolExecutor(max_workers=WORKERS) as pool:
                list(pool.map(paint, work))
        _finish(job_id, Job.DONE)
    except Exception as failure:  # noqa: BLE001 — the job itself, not one card
        _finish(job_id, Job.FAILED, str(failure))
    finally:
        connection.close()


def _face(job_id, mode, options, directory, entry, face):
    """One face, in its own thread. Never raises: a bad card must not sink the rest of the deck."""
    log, started = [], time.monotonic()
    try:
        name = _file_stem(face)
        if mode == "ART_ONLY":
            (directory / f"{name}.png").write_bytes(pipeline.art(face, options, note=log.append))
            problems = []
        else:
            result = pipeline.creative_full(face, options, note=log.append)
            result.card.convert("RGB").save(directory / f"{name}.png")
            problems = [{"code": p.code, "detail": p.detail} for p in result.problems]
        _append(job_id, {
            "name": face["name"],
            "quantity": entry["quantity"],
            "status": "unsound" if problems else "ok",
            "image": f"{settings.MEDIA_URL}generated/{job_id}/{name}.png",
            "problems": problems,
            "log": log,
            "seconds": round(time.monotonic() - started, 1),
        })
    except Exception as failure:  # noqa: BLE001 — one bad card must not sink the deck
        _append(job_id, {
            "name": face["name"],
            "quantity": entry["quantity"],
            "status": "failed",
            "image": None,
            "problems": [{"code": "ERROR", "detail": str(failure)}],
            "log": log,
            "seconds": round(time.monotonic() - started, 1),
        })
    finally:
        # Each worker thread gets its own database connection and nothing else closes it.
        connection.close()


def _file_stem(face):
    """The file name for one face — the card, plus which face when there are two."""
    suffix = "" if face["face_position"] == "SINGLE" else f"-{face['face_position'].lower()}"
    return f"{_slug(face['name'])}{suffix}"


def _append(job_id, result):
    """One finished face, straight to the row, so the poller sees cards arrive one at a time."""
    with _results:
        job = Job.objects.get(pk=job_id)
        job.results = job.results + [result]
        job.save(update_fields=["results"])


def _finish(job_id, status, error=""):
    with _results:
        Job.objects.filter(pk=job_id).update(status=status, error=error)
