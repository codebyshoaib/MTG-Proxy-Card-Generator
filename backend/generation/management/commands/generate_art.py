"""Art Only, end to end, from the command line.

    uv run python manage.py generate_art "Craterhoof Behemoth" --style "dark fantasy oil"

Scryfall resolve -> brief -> one image call -> PNG on disk. This is the whole Art Only mode
(BUILD-SPEC §3: "Art Only stops after step 3"), and `generation.pipeline` holds the flow itself,
so the HTTP view and this command send the same brief.
"""

import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from generation import gemini, pipeline


def _slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


class Command(BaseCommand):
    help = "Generate Art Only artwork for one card."

    def add_arguments(self, parser):
        parser.add_argument("card")
        parser.add_argument("--style", default=None)
        parser.add_argument("--direction", default=None, help="Art Direction, BUILD-SPEC §10")
        parser.add_argument("--palette", default=None, help="Colour Palette, BUILD-SPEC §10")
        parser.add_argument("--out", default="art-out", type=Path)
        parser.add_argument(
            "--no-reference",
            action="store_true",
            help=(
                "Skip the Scryfall art_crop attachment. Worth trying on famous art: the "
                "reference can beat the style brief (handover §7)."
            ),
        )
        parser.add_argument(
            "--dry-run", action="store_true", help="Print the prompt, spend nothing."
        )

    def handle(self, card, style, out, no_reference, dry_run, direction, palette, **_):
        try:
            faces = pipeline.faces_of(card)
        except pipeline.Rejected as rejected:
            raise CommandError(rejected.detail) from rejected

        options = pipeline.Options(
            art_style=style, art_direction=direction, color_palette=palette,
            use_original_art_reference=not no_reference,
        )
        for face in faces:
            note = lambda message: self.stdout.write(self.style.WARNING(message))  # noqa: E731
            prompt, reference = pipeline.art_brief(face, options, note)
            self.stdout.write(f"--- {face['name']} ({face['face_position']})\n{prompt}\n")
            if dry_run:
                continue

            png = gemini.generate(prompt, reference)
            out.mkdir(parents=True, exist_ok=True)
            suffix = "" if face["face_position"] == "SINGLE" else f"-{face['face_position'].lower()}"
            path = out / f"{_slug(face['name'])}{suffix}.png"
            path.write_bytes(png)
            self.stdout.write(self.style.SUCCESS(f"{path} ({len(png):,} B)"))
