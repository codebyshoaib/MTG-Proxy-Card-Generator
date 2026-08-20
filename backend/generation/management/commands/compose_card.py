"""Creative Full, end to end, from the command line.

    uv run python manage.py compose_card "Terror of the Peaks" --style dark_fantasy

The flow itself lives in `generation.pipeline`, which the HTTP API calls too — this command is
the same three calls with somewhere to print to and two debug switches the API has no use for.

`--from` skips the image call and composites onto a card already on disk, which is what to use
while tuning the compositor: it costs nothing and keeps the layout the same between runs.

Every option is named for the reference site's own POST /api/ai-proxies/generate/ payload, so a
frontend or an API layer maps one-to-one with no translation table in between.
"""

import json
import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from PIL import ImageDraw

from cards import compositor
from generation import panels, pipeline


def _slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


class Command(BaseCommand):
    help = "Generate one Creative Full card (Gemini letters the card; we stamp the mana cost). --composited stamps every field; --name-lettered letters only the name."

    def add_arguments(self, parser):
        parser.add_argument("card")
        parser.add_argument("--style", default=None, help="art_style: key, label or free text")
        parser.add_argument("--direction", default=None, help="art_direction")
        parser.add_argument("--palette", default=None, help="color_palette")
        parser.add_argument("--notes", default=None, help="custom_art_notes, free text")
        parser.add_argument(
            "--flavor", action="store_true",
            help="include_flavor_text: print the card's flavour text under its rules",
        )
        parser.add_argument(
            "--no-reference", dest="use_reference", action="store_false",
            help="use_original_art_reference=false: do not attach Scryfall's own art",
        )
        parser.add_argument(
            "--framed", dest="borderless", action="store_false",
            help="build the card's edge out of the scene instead of running the art full bleed "
                 "(borderless is the default — client, 2026-08-13)",
        )
        parser.add_argument(
            "--attempts", type=int, default=2,
            help="how many times to paint before accepting a structurally faulty card "
                 "(default 2: measured, about one card in five needs a second)",
        )
        parser.add_argument("--out", default=Path("card-out"), type=Path)
        parser.add_argument(
            "--from", dest="source", default=None, type=Path,
            help="Replay onto this existing PNG instead of generating one. Default treats the "
                 "source as already lettered (stamp cost only). Pass --composited for blank furniture.",
        )
        parser.add_argument(
            "--panels", dest="panel_boxes", default=None, type=Path,
            help="Reuse the boxes in this <stem>-panels.json instead of asking for them again. "
                 "With --from this costs NOTHING and is fully deterministic, so a compositor "
                 "change can be measured on stored art without a detection change confounding it.",
        )
        parser.add_argument(
            "--boxes", action="store_true",
            help="Also write a copy with the detected boxes outlined, to check the detector.",
        )
        parser.add_argument(
            "--lettered", dest="lettered", action="store_true",
            help="Let the model paint every field except the mana cost (the default).",
        )
        parser.add_argument(
            "--name-lettered", dest="name_lettered", action="store_true",
            help="Letter only the name; stamp type, rules, P/T and mana. The hybrid that failed "
                 "his seven on 2026-08-20 — kept so a replay can still use it.",
        )
        parser.add_argument(
            "--composited", dest="composited", action="store_true",
            help="Paint blank furniture and stamp Scryfall's text including the name.",
        )
        parser.set_defaults(lettered=False, name_lettered=False, composited=False)

    def handle(
        self, card, style, out, source, boxes, direction, palette, notes, flavor,
        use_reference, attempts, borderless, lettered, composited, name_lettered, panel_boxes, **_,
    ):
        try:
            faces = pipeline.faces_of(card)
        except pipeline.Rejected as rejected:
            raise CommandError(rejected.detail) from rejected

        if composited:
            lettered, name_lettered = False, False
        elif name_lettered:
            lettered, name_lettered = False, True
        else:
            lettered, name_lettered = True, False
        options = pipeline.Options(
            art_style=style, art_direction=direction, color_palette=palette, custom_art_notes=notes,
            include_flavor_text=flavor, use_original_art_reference=use_reference,
            borderless=borderless, lettered=lettered, name_lettered=name_lettered,
        )
        out.mkdir(parents=True, exist_ok=True)
        for face in faces:
            suffix = "" if face["face_position"] == "SINGLE" else f"-{face['face_position'].lower()}"
            stem = f"{_slug(face['name'])}{suffix}"

            result = pipeline.creative_full(
                face, options,
                attempts=attempts,
                source=source.read_bytes() if source else None,
                panel_boxes=json.loads(panel_boxes.read_text()) if panel_boxes else None,
                note=lambda message: self.stdout.write(self.style.WARNING(f"  {message}")),
            )
            # THE ART AND THE BOXES, ALWAYS, not only when the card came back faulty. Together they
            # are everything the compositor was given, so a later compositor change re-runs on them
            # offline for nothing: `--from <stem>-blank.png --panels <stem>-panels.json`. Kept
            # unconditionally here and not in `jobs`, where a 9MB blank per face is a real cost and
            # a clean card has nothing to investigate — a CLI run is somebody deliberately looking.
            if result.blank:
                (out / f"{stem}-blank.png").write_bytes(result.blank)
            if result.detected:
                (out / f"{stem}-panels.json").write_text(
                    json.dumps(result.detected, indent=2, sort_keys=True)
                )

            # Where, not just whether. Across a batch the failure that matters is a surface
            # landing in the wrong place, and that is invisible in a list of keys.
            self.stdout.write(f"{face['name']}: " + self._where(result.detected))
            for problem in result.problems:
                self.stdout.write(self.style.ERROR(f"  UNSOUND [{problem.code}] {problem.detail}"))

            path = out / f"{stem}.png"
            result.card.convert("RGB").save(path)
            report = self.style.WARNING if result.problems else self.style.SUCCESS
            self.stdout.write(report(f"{path}"))

            if boxes:
                self._boxes(result, out / f"{stem}-boxes.png")

    def _boxes(self, result, path):
        debug = result.card.copy()
        drawer = ImageDraw.Draw(debug)
        for key, panel in result.detected.items():
            strips = compositor._rules_panels(panel) if key in panels.LISTS else [panel]
            # The two fault keys are drawn too, and in red: when a card is repainted for a spare
            # surface or a painted set symbol, the first thing to check is whether the detector
            # was right about it.
            colour = (255, 40, 40) if key in panels.FAULTS else (255, 0, 255)
            for index, one in enumerate(strips):
                x0, y0, x1, y1 = compositor._box(one, debug.size)
                drawer.rectangle((x0, y0, x1, y1), outline=colour, width=6)
                label = f"{key}{index + 1}" if len(strips) > 1 else key
                drawer.text((x0 + 10, y0 + 10), label, fill=colour)
        debug.convert("RGB").save(path)

    def _where(self, detected):
        """Every detected surface and where it landed, for reading a batch at a glance."""
        where = []
        for key in panels.KEYS + panels.FAULTS:
            panel = detected.get(key)
            if not panel:
                continue
            for one in compositor._rules_panels(panel) if key in panels.LISTS else [panel]:
                where.append(f"{key} y{one[1]:.2f}-{one[3]:.2f} x{one[0]:.2f}-{one[2]:.2f}")
        return "; ".join(where) or "nothing detected"
