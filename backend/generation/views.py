"""The three endpoints the prototype UI needs.

    GET  /api/options/          the 48/21/20 catalogue, so the frontend holds no copy of it
    POST /api/generate/         pre-flight, then a job id
    GET  /api/jobs/<id>/        status and every face finished so far

The POST body is the reference site's own payload (HOW-THEY-DO §3), so their field names survive
the whole way from the select element to `prompts.creative_full`.
"""

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from cards import scryfall
from generation import jobs, prompts
from generation.models import Job
from generation.pipeline import Options

MODES = {"ART_ONLY", "CREATIVE_FULL"}

FREE_TEXT_MAX = 500
"""`custom_style` and `custom_art_notes`, matching their two free-text fields (BUILD-SPEC §10)."""

DECKLIST_MAX = 20_000
"""Characters. A 100-card list is well under 4k; this only stops a paste that is not a decklist."""


def _catalogue(table):
    return [
        {"value": key, "label": label, "group": group}
        for key, (label, _text, group) in table.items()
    ]


@api_view(["GET"])
def options(_request):
    return Response({
        "modes": sorted(MODES),
        # The group is what lets the frontend render `<optgroup>`s instead of 48 flat rows.
        "art_styles": [
            {"value": key, "label": label, "group": prompts.STYLE_GROUP_OF.get(key, "Other")}
            for key, label in prompts.STYLE_LABELS.items()
        ],
        "art_directions": _catalogue(prompts.DIRECTIONS),
        "color_palettes": _catalogue(prompts.PALETTES),
    })


@api_view(["POST"])
def generate(request):
    body = request.data if isinstance(request.data, dict) else {}
    mode = body.get("frame_version") or "CREATIVE_FULL"
    if mode not in MODES:
        return _bad(f"frame_version must be one of {sorted(MODES)}")

    decklist = body.get("decklist") or ""
    if not isinstance(decklist, str) or not decklist.strip():
        return _bad("decklist is required")
    if len(decklist) > DECKLIST_MAX:
        return _bad(f"decklist is longer than {DECKLIST_MAX} characters")

    try:
        # Creative Full is fully lettered (CLIENT 2026-08-19 favorites: names in objects,
        # furniture in the scene). The body cannot turn that off — their API has no such switch.
        options_ = _options(body, lettered=True, name_lettered=False)
    except ValueError as invalid:
        return _bad(str(invalid))

    # Everything Scryfall can settle is settled here, before the job exists: the unknown names
    # and the unsupported layouts cost nothing and are the confirm screen's whole job.
    plan = scryfall.resolve_decklist(decklist)
    if not plan["entries"]:
        return Response(
            {
                "detail": "nothing generatable in that decklist",
                "unresolved": plan["unresolved"],
                "unsupported": plan["unsupported"],
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    if len(plan["entries"]) > jobs.MAX_CARDS:
        return _bad(
            f"{len(plan['entries'])} distinct cards is over the {jobs.MAX_CARDS}-card limit"
        )

    job = Job.objects.create(
        mode=mode,
        options=options_._asdict(),
        # One generation per DISTINCT card, with its quantity carried through for the print
        # sheet. Four copies of one card are four identical proxies, not four paid generations.
        cards=[
            {"quantity": entry["quantity"], "name": entry["card"].name, "faces": entry["faces"]}
            for entry in plan["entries"]
        ],
        unresolved=plan["unresolved"],
        unsupported=plan["unsupported"],
    )
    jobs.start(job)
    return Response(_job(job), status=status.HTTP_202_ACCEPTED)


@api_view(["GET"])
def job_status(_request, job_id):
    # A restart leaves the row saying `running` with no worker behind it, and the frontend polls a
    # dead job forever. This is the moment the answer matters, so it is the moment to check.
    jobs.reap()
    return Response(_job(get_object_or_404(Job, pk=job_id)))


def _options(body, lettered=True, name_lettered=False):
    """The seven inputs out of an untrusted body, or `ValueError`.

    `lettered` and `name_lettered` are ours, set from the mode, never from the body.
    """
    text = {}
    for field in ("art_style", "art_direction", "color_palette", "custom_art_notes"):
        value = body.get(field)
        if value in (None, ""):
            continue
        if not isinstance(value, str):
            raise ValueError(f"{field} must be a string")
        if len(value) > FREE_TEXT_MAX:
            raise ValueError(f"{field} is longer than {FREE_TEXT_MAX} characters")
        text[field] = value.strip()
    # `custom_style` is their name for free text in the style field; ours is one field that
    # takes either, so it folds in here rather than adding an eighth input.
    if body.get("custom_style"):
        text["art_style"] = str(body["custom_style"])[:FREE_TEXT_MAX].strip()

    return Options(
        **text,
        include_flavor_text=bool(body.get("include_flavor_text", False)),
        use_original_art_reference=bool(body.get("use_original_art_reference", True)),
        borderless=bool(body.get("borderless", True)),
        lettered=lettered,
        name_lettered=name_lettered,
    )


def _job(job):
    faces = sum(len(card["faces"]) for card in job.cards)
    return {
        "id": str(job.pk),
        "mode": job.mode,
        "status": job.status,
        "error": job.error,
        "options": job.options,
        "cards": [{"name": card["name"], "quantity": card["quantity"]} for card in job.cards],
        "faces": faces,
        "workers": jobs.WORKERS,
        "eta_seconds": _eta(job, faces),
        "unresolved": job.unresolved,
        "unsupported": job.unsupported,
        "results": job.results,
    }


# Until a face has finished there is nothing to extrapolate from, so the first estimate uses the
# measured average instead of a guess of zero (job 9f16e827: 45 s clean, 88 s with a repaint).
FIRST_GUESS_SECONDS = 60


def _eta(job, faces):
    """Seconds left, or None once there is nothing left to wait for.

    Deliberately crude: mean time per finished face, times the batches still to run. It is honest
    about the two things that actually move it — how many faces are left and how many run at
    once — and it stops pretending to know more than that.
    """
    if job.status in (Job.DONE, Job.FAILED):
        return None
    done = [result.get("seconds") for result in job.results if result.get("seconds")]
    remaining = max(0, faces - len(job.results))
    if not remaining:
        return 0
    each = sum(done) / len(done) if done else FIRST_GUESS_SECONDS
    batches = -(-remaining // max(1, jobs.WORKERS))  # ceiling division
    return int(each * batches)


def _bad(detail):
    return Response({"detail": detail}, status=status.HTTP_400_BAD_REQUEST)
