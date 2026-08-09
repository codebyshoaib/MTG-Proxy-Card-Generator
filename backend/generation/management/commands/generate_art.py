"""Art Only, end to end, from the command line.

    uv run python manage.py generate_art "Craterhoof Behemoth" --style "dark fantasy oil"

Scryfall resolve -> brief -> one image call -> PNG on disk. This is the whole Art Only mode
(BUILD-SPEC §3: "Art Only stops after step 3"); the HTTP view is a later wrapper around the
same three calls.
"""

import re
from pathlib import Path

import requests
from django.core.management.base import BaseCommand, CommandError

from cards import scryfall
from generation import gemini, prompts


def _slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


class Command(BaseCommand):
    help = "Generate Art Only artwork for one card."

    def add_arguments(self, parser):
        parser.add_argument("card")
        parser.add_argument("--style", default=None)
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

    def handle(self, card, style, out, no_reference, dry_run, **_):
        found, missing = scryfall.resolve([card])
        if missing:
            raise CommandError(f"Scryfall does not know {missing[0]!r}")
        resolved = found[card]
        if resolved.layout in scryfall.UNSUPPORTED:
            raise CommandError(f"{resolved.name}: layout {resolved.layout} is not supported")

        for face in scryfall.faces(resolved):
            prompt = prompts.art_only(face, style)
            self.stdout.write(f"--- {face['name']} ({face['face_position']})\n{prompt}\n")
            if dry_run:
                continue

            reference = None
            if not no_reference and face["art_crop"]:
                response = requests.get(
                    face["art_crop"], headers=scryfall.HEADERS, timeout=30
                )
                response.raise_for_status()
                reference = response.content

            png = gemini.generate(prompt, reference)
            out.mkdir(parents=True, exist_ok=True)
            suffix = "" if face["face_position"] == "SINGLE" else f"-{face['face_position'].lower()}"
            path = out / f"{_slug(face['name'])}{suffix}.png"
            path.write_bytes(png)
            self.stdout.write(self.style.SUCCESS(f"{path} ({len(png):,} B)"))
