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
    # Stamped HERE, on the request thread, and not inside `run` — `run` is on a worker thread, so
    # between `start()` returning and it getting scheduled the row would sit QUEUED with no pid,
    # and a poll landing in that window would `reap` a job that had just been accepted.
    Job.objects.filter(pk=job.pk).update(worker_pid=os.getpid())
    threading.Thread(target=run, args=(job.pk,), daemon=True).start()


def reap():
    """Fail any job a restart orphaned. Returns how many.

    The pool is in-process, so a job can only be running inside the process that claimed it. A row
    that says `running` and names a different pid has no worker behind it and never will — before
    this it stayed `running` forever and the frontend polled it forever (bd mtg-57t).

    Called when someone asks about a job rather than at startup: it needs no app-loading hook, it
    cannot run during migrations, and the only moment the answer matters is when it is being read.
    Assumes one server process, which is what the in-process pool already assumes.
    """
    # A NULL pid means never claimed, not abandoned — every job `start()` accepts is stamped on
    # the request thread before the worker exists, so a real orphan always carries one. Reaping
    # NULLs instead would fail any row created by hand, which is what a fixture is.
    orphans = (
        Job.objects.filter(status__in=[Job.QUEUED, Job.RUNNING])
        .exclude(worker_pid__isnull=True)
        .exclude(worker_pid=os.getpid())
    )
    return orphans.update(
        status=Job.FAILED,
        error="the server restarted while this job was running, so it was abandoned. "
        "Nothing is left of it but the cards that had already finished — generate again.",
    )


def run(job_id):
    job = Job.objects.get(pk=job_id)
    job.status = Job.RUNNING
    job.worker_pid = os.getpid()
    job.save(update_fields=["status", "worker_pid"])
    options = pipeline.Options(**job.options)
    # Worker invariant, not a stored preference. Creative Full is the lettered path: a row
    # created before that default, or by hand with options={}, still has to letter.
    if job.mode != "ART_ONLY" and not options.lettered:
        options = options._replace(lettered=True)
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
        # Both modes return a `pipeline.Result` and both are graded (bd mtg-l4x). Art Only used to
        # branch away here into `_write_png(pipeline.art(...))` with `problems = []` hard-coded —
        # not "no faults found" but "never looked", which is how a fully bordered card shipped
        # marked ok. `Result.detected` is empty for Art Only because it paints no furniture; that
        # is the only difference left.
        result = (pipeline.art if mode == "ART_ONLY" else pipeline.creative_full)(
            face, options, note=log.append
        )
        result.card.convert("RGB").save(directory / f"{name}.png")
        problems = [{"code": p.code, "detail": p.detail} for p in result.problems]
        panels = result.detected or None
        if mode != "ART_ONLY":
            # KEEP THE EVIDENCE ON A CARD THAT CAME BACK WRONG (bd mtg-57t). The blank and the
            # boxes are already in hand — `pipeline` returns both — and throwing them away is what
            # made every post-mortem cost a fresh paid generation. On 2026-08-15 that stopped a
            # diagnosis dead: two cards tripped `text_too_small` and there was no way to tell
            # whether the model under-painted the strip or `panels.detect` under-reported it, which
            # need opposite fixes.
            #
            # Only when it is unsound, because the blank is ~9MB a face and a card that graded
            # clean has nothing to investigate. `panels` is small enough to keep either way, and
            # it is the half that actually answers the question.
            if (problems or settings.KEEP_BLANKS) and result.blank:
                # Raw, unlike the Art Only deliverable: the blank is evidence we read with PIL,
                # which sniffs the content and ignores the extension. Re-encoding it would put a
                # decode between a faulty card and its own post-mortem — the one moment the bytes
                # may be malformed is exactly when this file matters.
                (directory / f"{name}-blank.png").write_bytes(result.blank)
        _append(job_id, {
            "name": face["name"],
            "quantity": entry["quantity"],
            "status": "unsound" if problems else "ok",
            "image": f"{settings.MEDIA_URL}generated/{job_id}/{name}.png",
            "problems": problems,
            "log": log,
            "seconds": round(time.monotonic() - started, 1),
            # What the vision pass reported, normalised 0-1: the only record of what the model
            # actually painted, and what every panel-geometry bug is argued from.
            "panels": panels,
            "blank": (
                f"{settings.MEDIA_URL}generated/{job_id}/{name}-blank.png"
                if (problems or settings.KEEP_BLANKS) and mode != "ART_ONLY"
                else None
            ),
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
