"""Downscale the client's reference cards into `assets/exemplars/<archetype>/`.

    uv run python manage.py prepare_exemplars \\
        '../../Project Material/CLIENT-FAVORITES-2026-08-19' --archetype tangle

The output is NOT committed (see `generation/exemplars.py`), so this command is what makes it
reproducible: the assets are absent from a clean clone but the recipe for them is not.

Held out on purpose. `exemplars.SOURCES` names cards from `CLIENT-FAVORITES-2026-08-19/`, which
shares no card with the client's seven-card target sheet — the evaluation set. Using a card as
both exemplar and test subject would make the Phase 1 go/no-go meaningless.
"""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from PIL import Image

from generation import exemplars


class Command(BaseCommand):
    help = "Downscale the client's reference cards into assets/exemplars/<archetype>/."

    def add_arguments(self, parser):
        parser.add_argument("source", type=Path, help="a folder of full-size reference cards")
        parser.add_argument(
            "--archetype", action="append", dest="archetypes", default=None,
            help="which archetype to build; repeatable, default all of them",
        )
        parser.add_argument(
            "--long-edge", type=int, default=exemplars.LONG_EDGE,
            help=f"stored long edge in pixels (default {exemplars.LONG_EDGE})",
        )

    def handle(self, source, archetypes, long_edge, **_options):
        if not source.is_dir():
            raise CommandError(f"{source} is not a directory")
        # Recursive: his favorites arrive filed in subfolders by deck.
        found = {path.stem: path for path in source.rglob("*.png")}
        if not found:
            raise CommandError(f"no PNGs under {source}")

        written = 0
        for archetype in archetypes or sorted(exemplars.SOURCES):
            if archetype not in exemplars.SOURCES:
                raise CommandError(
                    f"{archetype!r} is not a frame archetype. "
                    f"Known: {', '.join(sorted(exemplars.ARCHETYPES))}"
                )
            target = exemplars.ROOT / archetype
            target.mkdir(parents=True, exist_ok=True)
            for stem in exemplars.SOURCES[archetype]:
                path = found.get(stem)
                if path is None:
                    self.stdout.write(self.style.WARNING(f"  {archetype}/{stem}: not in {source}"))
                    continue
                image = Image.open(path).convert("RGB")
                image.thumbnail((long_edge, long_edge), Image.LANCZOS)
                out = target / f"{stem}.png"
                image.save(out, optimize=True)
                written += 1
                self.stdout.write(f"  {archetype}/{out.name}  {image.size[0]}x{image.size[1]}")

        if not written:
            raise CommandError("nothing written — check the source folder's filenames")
        self.stdout.write(self.style.SUCCESS(f"\n{written} exemplars under {exemplars.ROOT}"))
        self.stdout.write("Not committed. See generation/exemplars.py for why.")
