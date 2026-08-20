"""Run a batch of cards from a spec file, and record what produced it.

    uv run python manage.py pack packs/exemplar-tangle.json

Every measurement this project leans on is a comparison between two batches, and until now each
batch was driven by a hand-written shell loop and described by a `_pack.json` written by hand
afterwards. Twenty-odd folders under `Project Material/` were produced that way. The failure mode
is not that the loop is tedious — it is that the record of what produced a batch is written
separately from the run, so the two can disagree, and a stored card whose settings are wrong is
worse than no stored card at all.

So the spec is the input and the record is a copy of it. `_pack.json` is the spec as run, with the
resolved option set appended; `_job.json` is one entry per face. Both land beside the images.

The spec is JSON so a batch can be committed, diffed and re-run:

    {
      "why": "one sentence on what this batch is the evidence for",
      "bead": "mtg-jbk.2",
      "art_style": "comic_book", "art_direction": "dynamic", "color_palette": "vibrant",
      "lettered": true, "archetype": "tangle", "exemplar_count": 3,
      "cards": ["Toski, Bearer of Secrets", "Tower Winder"]
    }

`why` is required and unenforceable in spirit only: a batch nobody can say the purpose of is a
batch nobody will be able to read six weeks later. `bead` is optional.
"""

import json
import time
import traceback
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from generation import pipeline

OPTIONS = (
    "art_style", "art_direction", "color_palette", "custom_art_notes", "include_flavor_text",
    "use_original_art_reference", "borderless", "lettered", "name_lettered", "archetype",
    "exemplar_count", "cost_lettered",
)
"""Which spec keys are `pipeline.Options` fields. Anything else in the spec is documentation."""


def _slug(name):
    return "".join(c if c.isalnum() else "-" for c in name.lower()).strip("-").replace("--", "-")


class Command(BaseCommand):
    help = "Run a batch of cards from a JSON spec, writing _pack.json and _job.json beside them."

    def add_arguments(self, parser):
        parser.add_argument("spec", type=Path, help="the batch spec — see this module's docstring")
        parser.add_argument(
            "--out", type=Path, default=None,
            help="where to write (default: a folder named after the spec, beside it)",
        )
        parser.add_argument(
            "--attempts", type=int, default=2,
            help="repaints per face before a card is stored unsound (default 2)",
        )

    def handle(self, spec, out, attempts, **_options):
        if not spec.is_file():
            raise CommandError(f"{spec} is not a file")
        loaded = json.loads(spec.read_text())
        cards = loaded.get("cards")
        if not cards:
            raise CommandError(f"{spec} lists no cards")
        if not loaded.get("why"):
            raise CommandError(
                f"{spec} has no 'why'. A batch whose purpose is not written down is a batch "
                "nobody can read later — one sentence is enough."
            )
        unknown = set(loaded) - set(OPTIONS) - {"why", "bead", "cards"}
        if unknown:
            # Silently ignoring a misspelt key would run the batch on defaults and record the
            # spec as if it had been honoured, which is the one thing this command exists to stop.
            raise CommandError(f"{spec}: unknown key(s) {', '.join(sorted(unknown))}")

        options = pipeline.Options(**{k: loaded[k] for k in OPTIONS if k in loaded})
        out = out or spec.parent / spec.stem
        out.mkdir(parents=True, exist_ok=True)

        results = []
        for name in cards:
            self.stdout.write(self.style.MIGRATE_HEADING(f"\n{name}"))
            started = time.monotonic()
            try:
                faces = pipeline.faces_of(name)
            except pipeline.Rejected as rejected:
                results.append({"name": name, "status": "rejected", "error": rejected.detail})
                self.stdout.write(self.style.ERROR(f"  rejected: {rejected.detail}"))
                continue
            for face in faces:
                results.append(self._face(face, options, attempts, out, started))

        # WRITTEN LAST, and written even when a card failed: a batch that died halfway is exactly
        # the batch somebody needs the record of.
        (out / "_pack.json").write_text(
            json.dumps({**loaded, "options": options._asdict()}, indent=2), encoding="utf-8"
        )
        (out / "_job.json").write_text(json.dumps({"results": results}, indent=2), encoding="utf-8")

        ok = sum(1 for r in results if r.get("status") == "ok")
        unsound = sum(1 for r in results if r.get("status") == "unsound")
        broken = len(results) - ok - unsound
        report = self.style.SUCCESS if ok == len(results) else self.style.WARNING
        self.stdout.write(report(
            f"\n{ok} ok, {unsound} unsound, {broken} failed -> {out}\n"
            f"Score it:  manage.py score '{out}' --baseline <another batch>"
        ))

    def _face(self, face, options, attempts, out, started):
        suffix = "" if face["face_position"] == "SINGLE" else f"-{face['face_position'].lower()}"
        stem = f"{_slug(face['name'])}{suffix}"
        log = []
        try:
            result = pipeline.creative_full(
                face, options, attempts=attempts,
                note=lambda message: (log.append(message), self.stdout.write(f"  {message}")),
            )
        except Exception as failure:
            self.stdout.write(self.style.ERROR(f"  failed: {failure}"))
            return {
                "name": face["name"], "stem": stem, "status": "failed",
                "seconds": round(time.monotonic() - started, 1),
                "error": str(failure), "traceback": traceback.format_exc(), "log": log,
            }

        # THE ART AND THE BOXES, ALWAYS — same reasoning as `compose_card`: together they are
        # everything the compositor was given, so a later compositor change re-runs offline for
        # nothing instead of costing the batch again.
        if result.blank:
            (out / f"{stem}-blank.png").write_bytes(result.blank)
        if result.detected:
            (out / f"{stem}-panels.json").write_text(
                json.dumps(result.detected, indent=2, sort_keys=True)
            )
        result.card.convert("RGB").save(out / f"{stem}.png")

        for problem in result.problems:
            self.stdout.write(self.style.ERROR(f"  UNSOUND [{problem.code}] {problem.detail}"))
        return {
            "name": face["name"], "stem": stem,
            "status": "unsound" if result.problems else "ok",
            "seconds": round(time.monotonic() - started, 1),
            "problems": [{"code": p.code, "detail": p.detail} for p in result.problems],
            "log": log,
        }
